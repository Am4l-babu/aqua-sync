/* Crisis Commander — hand the visitor the decision, then score it.
 *
 * Talks to /api/crisis/{key}: GET for the briefing, POST for the outcome.
 * If the API is not running the page says so plainly rather than inventing
 * numbers — a demo that fabricates results is worse than one that admits the
 * backend is down, and the expo venue's network is not a dependency worth
 * trusting.
 */

const SCENARIO = new URLSearchParams(location.search).get('scenario') || 'periyar_oct_2021';
const API = location.origin.startsWith('http') ? '' : 'http://localhost:8000';

const $ = (id) => document.getElementById(id);
const CONTROLS = ['target_level', 'start_hour', 'max_rate'];

const fmt = {
  target_level: (v) => `${(+v).toFixed(2)} m`,
  start_hour: (v) => (+v === 0 ? 'immediately' : `${v} h`),
  max_rate: (v) => `${Math.round(v)} cumecs`,
};

let brief = null;

function setStatus(msg, kind = '') {
  const el = $('status');
  el.textContent = msg;
  el.className = `fineprint ${kind}`;
}

function stat(label, value, note) {
  return `<div class="stat"><span class="stat-v">${value}</span>
          <span class="stat-l">${label}</span>
          ${note ? `<span class="stat-n">${note}</span>` : ''}</div>`;
}

async function loadBriefing() {
  const res = await fetch(`${API}/api/crisis/${SCENARIO}`);
  if (!res.ok) throw new Error(`briefing failed: ${res.status}`);
  brief = await res.json();

  $('subtitle').textContent = `${brief.reservoir} · ${brief.title}`;
  $('narrative').textContent = brief.narrative;

  $('stats').innerHTML = [
    stat('level now', `${brief.level_now_m.toFixed(2)} m`,
         `${brief.freeboard_now_m.toFixed(2)} m below FRL`),
    stat('rule level', `${brief.rule_level_m.toFixed(2)} m`, 'where it should sit'),
    stat('inflow now', `${Math.round(brief.inflow_now_cumecs)}`, 'cumecs'),
    stat('rain, last 24 h', `${brief.rain_last_24h_mm.toFixed(0)} mm`, 'and more forecast'),
    stat('turbines take', `${Math.round(brief.turbine_capacity_cumecs)}`,
         'cumecs — above this, water is wasted'),
  ].join('');

  for (const key of CONTROLS) {
    const c = brief.controls[key];
    const el = $(key);
    Object.assign(el, { min: c.min, max: c.max, step: c.step, value: c.default, disabled: false });
    el.addEventListener('input', () => { $(`v-${key.split('_')[0]}`).textContent = fmt[key](el.value); });
    $(`v-${key.split('_')[0]}`).textContent = fmt[key](c.default);
  }
  $('commit').disabled = false;
  setStatus('The first order takes a few seconds while the hindsight-optimal policy is searched.');
}

function row(label, key, unit, better) {
  const pick = (side) => {
    const v = window.__last[side][key];
    if (v === null || v === undefined) return '—';
    return typeof v === 'boolean' ? (v ? 'yes' : 'no') : `${(+v).toFixed(2)}${unit}`;
  };
  const you = window.__last.you[key];
  const ref = window.__last.aquasync[key];
  let cls = '';
  if (typeof you === 'number' && typeof ref === 'number' && better) {
    cls = better(you, ref) ? 'good' : 'bad';
  }
  return `<tr><th>${label}</th><td class="${cls}">${pick('you')}</td>
          <td>${pick('what_happened')}</td><td>${pick('aquasync')}</td></tr>`;
}

async function commit() {
  $('commit').disabled = true;
  setStatus('Playing your order forward against the inflow that actually arrived…');

  const body = {};
  for (const key of CONTROLS) body[key] = +$(key).value;
  body.start_hour = Math.round(body.start_hour);

  let out;
  try {
    const res = await fetch(`${API}/api/crisis/${SCENARIO}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    out = await res.json();
  } catch (err) {
    setStatus(`Could not reach the twin: ${err.message}. Start it with `
              + `"uvicorn aquasync.api.main:app --port 8000" from backend/.`, 'bad');
    $('commit').disabled = false;
    return;
  }

  window.__last = out;
  $('verdict').textContent = out.verdict;
  $('cmp-body').innerHTML = [
    row('Peak level', 'peak_level_m', ' m', (a, b) => a <= b + 0.01),
    row('Flood cushion left', 'min_freeboard_m', ' m', (a, b) => a >= b - 0.01),
    row('Went over FRL', 'breaches_frl', '', null),
    row('Peak downstream', 'peak_downstream_cumecs', ' cumecs', (a, b) => a <= b + 1),
    row('Revenue vs the day', 'revenue_delta_cr', ' cr', (a, b) => a >= b - 0.01),
  ].join('');

  const p = out.aquasync_policy;
  $('policy-note').textContent =
    `AquaSync would have drawn down towards ${p.target_level.toFixed(2)} m, `
    + `starting at hour ${p.start_hour}, at up to ${Math.round(p.max_rate)} cumecs. `
    + `Green means you matched or beat it.`;

  $('result').hidden = false;
  $('commit').disabled = false;
  setStatus('Change the order and commit again — the references stay fixed.');
}

$('commit').addEventListener('click', commit);
loadBriefing().catch((err) => {
  setStatus(`Could not load the briefing: ${err.message}. Start the API with `
            + `"uvicorn aquasync.api.main:app --port 8000" from backend/.`, 'bad');
});
