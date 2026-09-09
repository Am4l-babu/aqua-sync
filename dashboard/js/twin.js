/**
 * AquaSync 3D digital twin - telemetry, panel and state.
 *
 * The scene itself lives in scene.js, built on the real DEM of the Periyar
 * valley. This file owns everything else: the socket, the fallback, the
 * readouts, the what-if sandbox, and the mapping from reported state to what
 * the scene shows.
 *
 * Two things about it are deliberate:
 *
 * 1. Telemetry arrives at roughly 1 Hz but the render loop runs at 60 fps, so
 *    every visual quantity eases toward its target rather than snapping.
 *    Snapping looks broken even when the data is perfect. The easing is
 *    time-based, not per-frame, so a 144 Hz display does not converge 2.4x
 *    faster than a 60 Hz one.
 *
 * 2. If no WebSocket is available it falls back to a bundled October 2021
 *    trajectory and says so in the status bar. The expo venue Wi-Fi is not a
 *    dependency the demo can afford, and a dashboard that shows nothing when
 *    the network is down would rather undercut a project about resilience.
 */

import { TwinScene } from './scene.js';

// -- reservoir constants ----------------------------------------------------
// Mirrored from twin/constants.py as a starting point, then replaced by
// whatever /api/reservoirs reports so the two cannot drift apart unnoticed.
const RES = {
  name: 'Idukki',
  frl: 732.43,
  rule: 728.50,
  red: 728.19,
  dead: 694.94,
  turbineRated: 138.0,
  liveStorageAtFrl: 1459.49,   // Mm3
  beta: 1.348,                 // level-storage exponent, calibrated
};

// Same origin as the page when served by the API, which is how it is meant to
// run. Falling back to :8000 only helps when the page is opened some other
// way, and using the page's own scheme keeps it working behind TLS.
const WS_URL = (() => {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = location.host || 'localhost:8000';
  return `${proto}//${host}/ws/telemetry`;
})();

// Seconds for the shown value to close ~63% of the gap to the target.
const EASE_TAU = 0.55;

const target = { level: RES.rule, gate: 0, inflow: 0, turbine: 0, spill: 0 };
const shown = { level: RES.rule, gate: 0, spill: 0, turbine: 0 };

const history = [];
let twin = null;
let replayTimer = null;
let manualOverride = false;

// --------------------------------------------------------------------------
// hypsometry
// --------------------------------------------------------------------------

/**
 * Reservoir surface area at a given level, km2.
 *
 * The twin stores S(h) = S_frl * ((h - dead)/(frl - dead))^beta, so the
 * surface area is its derivative. This used to be a bare 5000 in the
 * time-to-FRL line, which implied about 18 km2 against the calibrated
 * curve's 50 km2 and so ran the clock nearly three times too fast.
 */
function surfaceAreaKm2(level) {
  const span = RES.frl - RES.dead;
  const h = Math.max(0.01, Math.min(level, RES.frl) - RES.dead);
  return RES.liveStorageAtFrl * RES.beta * Math.pow(h, RES.beta - 1) / Math.pow(span, RES.beta);
}

/** Hours until FRL at the current net inflow, or null if it is not rising. */
function hoursToFrl(level, netCumecs) {
  if (!(netCumecs > 0)) return null;
  const freeboard = RES.frl - level;
  if (freeboard <= 0) return 0;
  const riseMs = netCumecs / (surfaceAreaKm2(level) * 1e6);   // m/s
  return freeboard / riseMs / 3600;
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------

async function init() {
  const stage = document.getElementById('stage');
  twin = new TwinScene(stage);

  try {
    const meta = await twin.load('assets');
    captionProvenance(meta);
  } catch (err) {
    // The terrain is an asset, not a hard dependency - say so rather than
    // showing an empty canvas.
    console.error('terrain failed to load', err);
    captionUnavailable();
  }

  await adoptServerConstants();
  bindControls();
  connect();
  scheduleRigPoll(0);
  animate();
}

/** Replace the mirrored constants with the API's, when it is reachable. */
async function adoptServerConstants() {
  try {
    const res = await fetch('/api/reservoirs', { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return;
    const idukki = (await res.json()).find((r) => r.key === 'idukki');
    if (!idukki) return;
    RES.frl = idukki.frl;
    RES.rule = idukki.rule_level;
    RES.red = idukki.red;
    RES.dead = idukki.dead;
    RES.liveStorageAtFrl = idukki.live_storage_at_frl_mm3;
    target.level = RES.rule;
    shown.level = RES.rule;
  } catch { /* offline: the mirrored values stand, and they are documented */ }
}

function captionProvenance(meta) {
  const el = document.getElementById('scene-note');
  if (!el) return;
  const km = (meta.span_m / 1000).toFixed(0);
  el.innerHTML =
    `<strong>Terrain: measured.</strong> ${km} km of the Periyar valley from the ` +
    `${meta.source}, ${meta.metres_per_sample.toFixed(0)} m posting. ` +
    `<strong>Structures: schematic.</strong> No bathymetry exists for the reservoir, ` +
    `so the bed is not drawn and water is shaded by distance from the bank, not depth.`;
}

function captionUnavailable() {
  const el = document.getElementById('scene-note');
  if (el) el.textContent = 'Terrain data unavailable - run scripts/build_terrain.py.';
}

// --------------------------------------------------------------------------
// telemetry
// --------------------------------------------------------------------------

function setLink(state, text) {
  const el = document.getElementById('link-state');
  el.className = `pill pill-${state}`;
  el.textContent = text;
}

/**
 * Show the provenance the server declared, never an inference from the
 * transport. Only LIVE is green: a recorded episode and a rig that has gone
 * quiet must both be visibly not-live, because the one thing this dashboard
 * must never do is present a simulated value as a measured one.
 */
const SOURCE_STYLE = {
  LIVE: ['ok', 'LIVE'],
  REPLAY: ['warn', 'REPLAY'],
  STALE: ['warn', 'STALE'],
  SIMULATED: ['warn', 'SIMULATED'],
};

function showSource(source) {
  const [state, label] = SOURCE_STYLE[source] || ['warn', String(source || 'UNKNOWN')];
  setLink(state, label);
  return label;
}

function connect() {
  let ws;
  try {
    ws = new WebSocket(WS_URL);
  } catch {
    return startReplay('no websocket');
  }

  const giveUp = setTimeout(() => {
    if (ws.readyState !== WebSocket.OPEN) { ws.close(); startReplay('backend unreachable'); }
  }, 2500);

  // Connecting proves the backend is reachable, nothing more. The badge
  // stays neutral until a frame arrives and states its own provenance -
  // this used to light up LIVE here while a 2021 replay streamed beneath it.
  ws.onopen = () => { clearTimeout(giveUp); setLink('warn', 'CONNECTED'); };
  ws.onmessage = (e) => { try { apply(JSON.parse(e.data)); } catch { /* ignore */ } };
  ws.onerror = () => { clearTimeout(giveUp); startReplay('websocket error'); };
  ws.onclose = () => { if (!replayTimer) startReplay('backend closed'); };
}

/**
 * Offline fallback: a synthesised October 2021 trajectory.
 *
 * The shape is taken from the real bulletin - level rising from 727.7 to
 * 731.0 with an inflow spike on 17 October and gates opening on the 20th -
 * so the fallback tells the same story as the live system. It is a
 * synthesis, not the record, and the status bar says "replay" throughout.
 */
function startReplay(reason) {
  if (replayTimer) return;
  setLink('warn', 'REPLAY');
  document.getElementById('source').textContent = `source: replay (${reason})`;

  const days = [
    { level: 727.66, inflow: 116, spill: 0 },
    { level: 727.71, inflow: 124, spill: 0 },
    { level: 727.76, inflow: 205, spill: 0 },
    { level: 728.13, inflow: 134, spill: 0 },
    { level: 728.34, inflow: 219, spill: 0 },
    { level: 728.47, inflow: 173, spill: 0 },
    { level: 728.58, inflow: 145, spill: 0 },
    { level: 728.73, inflow: 150, spill: 0 },
    { level: 728.81, inflow: 116, spill: 0 },
    { level: 730.11, inflow: 879, spill: 0 },     // 17 Oct - 168 mm
    { level: 730.92, inflow: 330, spill: 0 },
    { level: 730.95, inflow: 220, spill: 84 },    // 20 Oct - gates open
    { level: 730.96, inflow: 229, spill: 105 },
    { level: 730.99, inflow: 240, spill: 105 },
    { level: 730.97, inflow: 161, spill: 58 },
    { level: 730.99, inflow: 170, spill: 42 },
  ];

  let i = 0;
  replayTimer = setInterval(() => {
    const d = days[i % days.length];
    apply({
      level: d.level,
      inflow: d.inflow,
      turbine: Math.min(d.inflow, RES.turbineRated),
      spill: d.spill,
      gate: Math.min(100, (d.spill / 400) * 100),
      timestamp: `2021-10-${String(8 + (i % days.length)).padStart(2, '0')}`,
      scenario: 'periyar_oct_2021',
      advice: d.spill === 0 && d.level > RES.rule
        ? `Level ${d.level.toFixed(2)} m is above the ${RES.rule} m rule level with gates shut. Begin drawdown.`
        : `Holding. Release ${(d.spill + Math.min(d.inflow, RES.turbineRated)).toFixed(0)} cumecs.`,
    });
    i += 1;
  }, 1400);
}

function apply(t) {
  // A dragged what-if slider is the operator asking a question. Do not
  // overwrite their answer with the next frame of the stream; the status bar
  // says so until they reset it.
  if (!manualOverride) {
    if (typeof t.gate === 'number') target.gate = t.gate;
    if (typeof t.turbine === 'number') target.turbine = t.turbine;
    if (typeof t.spill === 'number') target.spill = t.spill;
  }
  if (typeof t.level === 'number') target.level = t.level;
  if (typeof t.inflow === 'number') target.inflow = t.inflow;

  history.push(target.level);
  if (history.length > 90) history.shift();

  updatePanel(t);
}

// --------------------------------------------------------------------------
// panel
// --------------------------------------------------------------------------

function fmt(v, unit, dp = 0) {
  return Number.isFinite(v) ? `${v.toFixed(dp)} ${unit}` : '—';
}

function updatePanel(t) {
  const freeboard = RES.frl - target.level;

  document.getElementById('level').textContent = target.level.toFixed(2);
  document.getElementById('freeboard').textContent = fmt(freeboard, 'm', 2);
  document.getElementById('inflow').textContent = fmt(target.inflow, 'cumecs');
  document.getElementById('turbine').textContent = fmt(target.turbine, 'cumecs');
  document.getElementById('spill').textContent = fmt(target.spill, 'cumecs');
  document.getElementById('gate').textContent = fmt(target.gate, '%');

  const storage = RES.liveStorageAtFrl
    * Math.pow(Math.max(0, target.level - RES.dead) / (RES.frl - RES.dead), RES.beta);
  const storageEl = document.getElementById('storage');
  if (storageEl) storageEl.textContent = fmt(storage, 'Mm³', 0);

  const span = RES.frl - RES.dead;
  const pct = Math.max(0, Math.min(100, ((target.level - RES.dead) / span) * 100));
  const fill = document.getElementById('band-fill');
  fill.style.width = `${pct}%`;
  fill.className = 'band-fill ' +
    (target.level >= RES.frl ? 'crit' : target.level >= RES.rule ? 'warn' : 'ok');

  document.getElementById('lbl-rule').textContent = `rule ${RES.rule}`;
  document.getElementById('lbl-frl').textContent = `FRL ${RES.frl}`;

  const net = target.inflow - target.turbine - target.spill;
  const hrs = hoursToFrl(target.level, net);
  document.getElementById('ttf').textContent =
    hrs === null ? 'stable or falling'
      : hrs < 48 ? `${hrs.toFixed(1)} h at current net inflow`
        : `${(hrs / 24).toFixed(1)} d at current net inflow`;

  if (t.advice) document.getElementById('advice').textContent = t.advice;
  if (t.timestamp) document.getElementById('clock').textContent = t.timestamp;
  if (t.scenario) document.getElementById('scenario').textContent = `scenario: ${t.scenario}`;
  if (t.source && !manualOverride) {
    const label = showSource(t.source);
    document.getElementById('source').textContent =
      t.source === 'REPLAY' ? 'source: replay (recorded episode, not live)'
        : `source: ${label.toLowerCase()}`;
  }

  const card = document.getElementById('advice-card');
  card.classList.toggle('alert', target.level >= RES.rule && target.spill === 0);

  drawSpark();
}

function drawSpark() {
  const el = document.getElementById('spark');
  if (history.length < 2) return;
  const lo = Math.min(...history), hi = Math.max(...history);
  const range = Math.max(0.05, hi - lo);
  const pts = history.map((v, i) => {
    const x = (i / (history.length - 1)) * 100;
    const y = 30 - ((v - lo) / range) * 26;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  el.innerHTML =
    `<svg viewBox="0 0 100 32" preserveAspectRatio="none">
       <polyline points="${pts}" fill="none" stroke="#4aa3df" stroke-width="1.6"/>
     </svg>`;
}

// --------------------------------------------------------------------------
// what-if sandbox
// --------------------------------------------------------------------------

/**
 * Ask the API what a constant `release` (cumecs) does to Idukki over the next
 * 72 hours, starting from whatever level and inflow the dashboard is showing.
 * Served same-origin, so the URL is relative. Throws if the API is unreachable
 * or returns a non-OK status.
 */
async function postWhatIf(release) {
  const body = {
    start_level: target.level,
    inflow_cumecs: Math.max(0, target.inflow),
    release_cumecs: release,
    hours: 72,
  };
  const res = await fetch('/api/whatif', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`whatif ${res.status}`);
  return res.json();
}

/** Write a /api/whatif result into the What-if card. */
function renderWhatIf(r) {
  const out = document.getElementById('whatif-out');
  const peak = Number(r.peak_level);
  const cushion = RES.frl - peak;
  const ttf = Number(r.hours_to_frl);

  document.getElementById('wi-peak').textContent = `${peak.toFixed(2)} m`;
  document.getElementById('wi-cushion').textContent = `${cushion.toFixed(2)} m`;

  const breach = document.getElementById('wi-breach');
  breach.textContent = r.breaches_frl ? 'yes' : 'no';
  breach.classList.toggle('crit', !!r.breaches_frl);

  document.getElementById('wi-ttf').textContent =
    Number.isFinite(ttf) && ttf > 0 ? `${ttf.toFixed(0)} h` : '—';

  document.getElementById('wi-advice').textContent = r.advice || '';
  document.getElementById('whatif-status').textContent =
    'Constant inflow and release, 72 h. Advisory — a named operator approves every release.';
  out.hidden = false;
}

/** Reset the card to its pre-interaction state. */
function clearWhatIf() {
  document.getElementById('whatif-out').hidden = true;
  document.getElementById('wi-advice').textContent = '';
  document.getElementById('whatif-status').textContent =
    'Move the slider to test a constant release.';
}

function bindControls() {
  const slider = document.getElementById('whatif');
  const label = document.getElementById('whatif-val');
  const source = document.getElementById('source');

  // Live: label and the 3D gate follow the handle continuously.
  slider.addEventListener('input', () => {
    manualOverride = true;
    label.textContent = slider.value;
    const q = Number(slider.value);
    target.turbine = Math.min(q, RES.turbineRated);
    target.spill = Math.max(0, q - RES.turbineRated);
    target.gate = Math.min(100, (target.spill / 400) * 100);
    source.textContent = 'source: what-if override (release set by hand)';
    updatePanel({});
  });

  // On release: ask the API what that constant release does over 72 h.
  // Debounced so a quick drag-and-release fires one request.
  let timer = 0;
  slider.addEventListener('change', () => {
    clearTimeout(timer);
    const release = Number(slider.value);
    document.getElementById('whatif-status').textContent = 'Simulating…';
    timer = setTimeout(async () => {
      try {
        renderWhatIf(await postWhatIf(release));
      } catch {
        document.getElementById('whatif-out').hidden = true;
        document.getElementById('wi-advice').textContent = '';
        document.getElementById('whatif-status').textContent =
          'Sandbox needs the API running — serve this page from uvicorn.';
      }
    }, 250);
  });

  document.getElementById('whatif-reset').addEventListener('click', () => {
    clearTimeout(timer);
    slider.value = 0;
    label.textContent = '0';
    slider.dispatchEvent(new Event('input'));
    // The dispatch above re-arms the override, so clear it afterwards: the
    // next telemetry frame should take the panel back.
    manualOverride = false;
    source.textContent = 'source: telemetry';
    clearWhatIf();
  });
}

// --------------------------------------------------------------------------
// scale rig
// --------------------------------------------------------------------------

/**
 * Poll the bench rig and render it in its own units.
 *
 * Deliberately a separate card from the reservoir readouts. The rig is a
 * 400 mm tank; Idukki is a 60 km² reservoir. Putting a tank depth anywhere
 * near the m MSL readout, even in the same column, invites a reader to treat
 * one as the other.
 */
/** Mirror a rig fault onto the 3D view, where it cannot be missed. */
function setStageAlert(faults) {
  const el = document.getElementById('stage-alert');
  if (!el) return;
  el.textContent = faults.length ? `RIG FAULT — ${faults[0]}` : '';
  el.hidden = faults.length === 0;
}

const RIG_POLL_MS = 1000;
const RIG_POLL_MAX_MS = 15000;
let rigBackoffMs = RIG_POLL_MS;
let rigTimer = null;

/** Poll again after `delay` ms, replacing any pending poll. */
function scheduleRigPoll(delay) {
  clearTimeout(rigTimer);
  rigTimer = setTimeout(pollRig, delay);
}

async function pollRig() {
  const state = document.getElementById('rig-state');
  const warn = document.getElementById('rig-warn');
  const set = (id, text) => { document.getElementById(id).textContent = text; };

  try {
    const r = await fetch('/api/rig', { signal: AbortSignal.timeout(2500) });
    if (!r.ok) throw new Error(String(r.status));
    const s = await r.json();
    rigBackoffMs = RIG_POLL_MS;

    const live = s.source === 'LIVE';
    state.textContent = live ? 'LIVE' : s.source === 'STALE' ? 'STALE' : 'OFFLINE';
    state.className = `chip ${live ? 'chip-live' : s.source === 'STALE' ? 'chip-stale' : 'chip-off'}`;

    const d = s.reading;
    if (!d) {
      for (const id of ['rig-level', 'rig-flow', 'rig-sensors', 'rig-gate-cmd',
        'rig-gate-ver', 'rig-chain']) set(id, '—');
      warn.hidden = true;
      document.getElementById('rig-note').textContent = s.status;
      return;
    }

    set('rig-level', d.level_m == null ? '—' : `${d.level_m.toFixed(3)} m`);
    set('rig-flow', d.flow_lpm == null ? '—' : `${d.flow_lpm.toFixed(2)} L/min`);
    set('rig-sensors', d.sensors_agree === false ? 'DISAGREE' : 'agree');
    set('rig-gate-cmd', d.gate_commanded_pct == null ? '—' : `${d.gate_commanded_pct.toFixed(0)} %`);
    set('rig-gate-ver', d.gate_verified_pct == null ? '—' : `${d.gate_verified_pct.toFixed(0)} %`);
    set('rig-chain', `${s.audit_chain.verified} verified · ${s.audit_chain.breaks} breaks`);

    const faults = [];
    if (d.actuator_disagreement) {
      faults.push(
        `ACTUATOR DISAGREEMENT — commanded ${d.gate_commanded_pct.toFixed(0)}%, ` +
        `verified ${d.gate_verified_pct.toFixed(0)}%. The gate is not where it was told to be.`);
    }
    if (d.gate_jammed) faults.push('Gate reports JAMMED.');
    if (d.sensors_agree === false) {
      faults.push('Level sensors disagree — the estimate is running on one channel.');
    }
    warn.textContent = faults.join(' ');
    warn.hidden = faults.length === 0;
    setStageAlert(faults);
  } catch {
    state.textContent = 'OFFLINE';
    state.className = 'chip chip-off';
    warn.hidden = true;
    setStageAlert([]);
    // No backend at all is a supported state - the expo demo runs with the
    // network cable pulled. Polling every second then means a 404 per second
    // for as long as the page is open, which buries anything worth seeing in
    // the console. Back off instead, and recover the moment it answers.
    rigBackoffMs = Math.min(rigBackoffMs * 2, RIG_POLL_MAX_MS);
  } finally {
    scheduleRigPoll(rigBackoffMs);
  }
}

// --------------------------------------------------------------------------
// render loop
// --------------------------------------------------------------------------

function animate() {
  requestAnimationFrame(animate);
  if (!twin) return;

  // Frame-rate independent easing: the same wall-clock settling time on any
  // display. dt comes back from the scene's own clock.
  const dt = twin.lastDt ?? 1 / 60;
  const k = 1 - Math.exp(-dt / EASE_TAU);
  shown.level += (target.level - shown.level) * k;
  shown.gate += (target.gate - shown.gate) * k;
  shown.spill += (target.spill - shown.spill) * k;
  shown.turbine += (target.turbine - shown.turbine) * k;

  twin.lastDt = twin.update(shown);
}

init();
