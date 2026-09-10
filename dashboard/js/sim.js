/**
 * The simulation view: the counterfactual, scrubbable, driving the twin.
 *
 * The side-panel card shows the answer. This drawer shows the *episode*: the
 * recorded bulletin level, the twin's replay of the same releases, and the
 * optimiser's schedule, hour by hour on a real axis, with a scrubber that
 * moves the 3D water and the readouts to any hour of the storm. It exists so
 * a visitor - or a tester - can look at the result rather than be told it.
 *
 * Three disciplines carry over from the card and are load-bearing here too:
 *
 *   1. Everything drawn comes from `/api/scenarios/{key}/counterfactual`.
 *      Nothing is simulated in the browser.
 *   2. The headline is cushion, in whole metres, never peak reduction.
 *      The API's own `headline_note` is shown verbatim.
 *   3. While the scrubber drives the twin, the source badge says SIMULATED
 *      and the status bar says which schedule and which hour. A replayed
 *      hour of 2021 must never look like a measurement.
 *
 * The recorded line is deliberately on the chart. It is what makes the
 * 0.30 m replay error something a viewer can see for themselves.
 */

const AMBER = '#e0a53a', GREEN = '#35c07a', BLUE = '#4aa3df';
const RED = 'rgba(226,86,79,.75)', GREY = 'rgba(200,214,226,.7)';
const RULE = 'rgba(224,165,58,.45)';

/**
 * @param {object} deps
 * @param {(key:string)=>Promise<object>} deps.fetchCounterfactual
 * @param {()=>Promise<object[]>} deps.fetchScenarios
 * @param {(s:object)=>void} deps.onDrive   called with the hour's state
 * @param {()=>void} deps.onRelease         called when the twin is handed back
 * @param {()=>void} deps.onLayout          called after the drawer opens/closes
 * @param {()=>{frl:number, rule:number}} deps.res
 */
export function createSimView(deps) {
  const $ = (id) => document.getElementById(id);
  const drawer = $('sim-drawer');
  const el = {
    state: $('simv-state'), scenario: $('simv-scenario'), run: $('simv-run'),
    storm: $('simv-storm'),
    play: $('simv-play'), speed: $('simv-speed'), trace: $('simv-trace'),
    close: $('simv-close'), headline: $('simv-headline'), chart: $('simv-chart'),
    scrub: $('simv-scrub'), cursor: $('simv-cursor'), out: $('simv-out'),
    policy: $('simv-policy'), note: $('simv-note'), toggle: $('sim-toggle'),
  };

  const st = {
    open: false, data: null, key: null, idx: 0, playing: false,
    trace: 'day', driving: false, raf: 0, last: 0, cursorNodes: null,
  };

  // ----------------------------------------------------------- scenarios
  async function populateScenarios() {
    try {
      const list = await deps.fetchScenarios();
      el.scenario.innerHTML = list.map((s) =>
        `<option value="${s.key}">${s.title} (${s.start} to ${s.end})</option>`).join('');
      return list;
    } catch {
      el.scenario.innerHTML = '<option value="">API not reachable</option>';
      return [];
    }
  }

  // ------------------------------------------------------------- loading
  async function run(key = el.scenario.value) {
    if (!key) {
      // No scenario list means no API. Say so in the chip too, not just in
      // the disabled select.
      setState('OFFLINE', 'chip-off');
      el.headline.textContent = 'Needs the API. Serve this page from uvicorn to run the optimiser.';
      return;
    }
    const scale = Number(el.storm.value) || 1;
    st.key = key;
    st.scale = scale;
    stop();
    setState('RUNNING', 'chip-stale');
    el.headline.textContent =
      'Running the optimiser: an exhaustive policy search, about 15 s the first time, instant after.';
    el.chart.innerHTML = '';
    el.out.hidden = true;
    el.policy.textContent = '';
    el.note.textContent = '';
    try {
      st.data = await deps.fetchCounterfactual(key, scale);
    } catch (err) {
      st.data = null;
      setState('OFFLINE', 'chip-off');
      el.headline.textContent = 'Needs the API. Serve this page from uvicorn to run the optimiser.';
      el.chart.innerHTML = '<p class="chart-empty">The optimiser runs on the backend and is not available offline.</p>';
      return;
    }
    renderResults();
    drawChart();
    loadSweep(key);
    // A scaled storm is a stress test, and the chip must not call it
    // hindsight: hindsight is of something that happened.
    if (st.data.summary.stress_note) setState('STRESS TEST', 'chip-stale');
    else setState('HINDSIGHT', 'chip-model');
    const n = st.data.series.observed_level.length;
    el.scrub.max = String(n - 1);
    setIndex(Math.min(st.idx, n - 1), true);
  }

  function setState(text, cls) {
    el.state.textContent = text;
    el.state.className = `chip ${cls}`;
  }

  function fmtM(v) { return Number.isFinite(v) ? `${v.toFixed(2)} m` : '—'; }
  function crore(inr) {
    return `${inr >= 0 ? '+' : '−'}₹${Math.abs(inr / 1e7).toFixed(1)} cr`;
  }

  function renderResults() {
    const s = st.data.summary;
    const gain = s.freeboard_gained_m;
    // "About -3 m more cushion" is a sentence nobody should read. Say the
    // direction in words and keep the magnitude in whole metres.
    const mag = Math.round(Math.abs(gain));
    el.headline.textContent =
      (gain >= 0.5 ? `About ${mag} m more cushion than the day`
        : gain <= -0.5 ? `About ${mag} m less cushion than the day`
          : 'About the same cushion as the day') +
      (s.revenue_delta_inr >= 0 ? ', with more revenue, not less.' : ', at a cost in revenue.');
    el.headline.className = `headline ${gain >= 0.5 ? 'good' : ''}`;

    $('simv-peak-obs').textContent = fmtM(s.peak_level_baseline);
    $('simv-peak-opt').textContent = fmtM(s.peak_level_optimised);
    $('simv-fb-obs').textContent = fmtM(s.min_freeboard_baseline_m);
    $('simv-fb-opt').textContent = fmtM(s.min_freeboard_optimised_m);
    $('simv-rev').textContent = crore(s.revenue_delta_inr);

    // Routed river discharge below the dam: 1D Muskingum on CWC's published
    // 8 h travel time, not gauge-calibrated (r² 0.005 on daily data). One
    // dam's contribution only - never read against bankfull, which needs the
    // cascade. The rows are here because the API already computes them and
    // the page never showed them.
    const q = (v) => (Number.isFinite(v) ? `${v.toFixed(0)} cumecs` : '—');
    $('simv-ds-obs').textContent = q(s.peak_downstream_baseline);
    $('simv-ds-opt').textContent = q(s.peak_downstream_optimised);

    // Replay error exists only for the recorded storm. For a scaled one the
    // API drops it, and the row says so rather than showing a stale 0.30 m.
    const stressed = !!s.stress_note;
    $('simv-mae').textContent = stressed ? 'n/a, scaled storm' : fmtM(s.replay_level_mae_m);
    $('simv-maxerr').textContent = stressed ? 'n/a, scaled storm' : fmtM(s.replay_level_max_err_m);
    $('simv-hours').textContent = `${s.hours_simulated} h`;
    el.out.hidden = false;

    if (s.baseline_breached_frl || s.optimised_breached_frl) {
      const who = s.baseline_breached_frl && s.optimised_breached_frl ? 'Both schedules reach'
        : s.baseline_breached_frl ? "The day's schedule reaches" : 'The AquaSync schedule reaches';
      el.headline.textContent += ` ${who} FRL in this run.`;
    }

    const p = st.data.policy;
    el.policy.textContent = p
      ? `Policy found: draw down to ${p.target_level_m.toFixed(2)} m from h+${p.start_hour}, ` +
        `at up to ${p.max_rate_cumecs.toFixed(0)} cumecs.`
      : '';
    el.note.textContent = stressed
      ? `${s.stress_note} ${s.headline_note} Downstream peaks are one dam's routed ` +
        `contribution on an uncalibrated reach; read them against each other, not against bankfull.`
      : `Hindsight, not forecast: the optimiser sees the inflow that actually arrived. ` +
        `${s.headline_note} Cushion is stated in whole metres because the replay error is ` +
        `${s.replay_level_mae_m.toFixed(2)} m MAE. Downstream peaks are one dam's routed ` +
        `contribution on an uncalibrated reach; read them against each other, not against bankfull.`;
  }

  /**
   * The storm-multiple sweep, if `scripts/stress_sweep.py` has been run for
   * this scenario. Answers one question: at what size of this storm does
   * each schedule reach FRL? An upper bound on a coarse ladder, and a
   * sensitivity rather than a return period - the API's caveat says so.
   */
  async function loadSweep(key) {
    const day = $('simv-sw-day'), opt = $('simv-sw-opt'), note = $('simv-sw-note');
    if (!day || !opt) return;
    day.textContent = opt.textContent = '…';
    try {
      const d = await deps.fetchSweep(key);
      if (st.key !== key) return;
      const f = d.first_multiple_reaching_frl;
      const top = d.ladder[d.ladder.length - 1];
      const say = (v) => (v == null ? `not by ×${top}` : `×${v}`);
      day.textContent = say(f.baseline);
      opt.textContent = say(f.optimised);
      if (note) note.textContent =
        `Storm multiple at which FRL is first reached, on a ladder of ×${d.ladder.join(', ×')}: ` +
        `an upper bound, not a threshold, and not a return period.`;
      drawSweep(d);
    } catch {
      day.textContent = opt.textContent = 'no sweep on disk';
      if (note) note.textContent = 'Run scripts/stress_sweep.py to fill these rows.';
      const c = $('simv-sw-chart');
      if (c) c.innerHTML = '';
    }
  }

  /** Peak level against storm multiple, both schedules, FRL ruled. */
  function drawSweep(d) {
    const box = $('simv-sw-chart');
    if (!box) return;
    const W = box.clientWidth || 300, H = box.clientHeight || 70;
    const ml = 34, mr = 8, mt = 6, mb = 16;
    const rows = d.rows;
    const xs = rows.map((r) => r.inflow_scale);
    const ys = rows.flatMap((r) => [r.peak_level_baseline_m, r.peak_level_optimised_m]).concat(d.frl_m);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const lo = Math.min(...ys) - 0.5, hi = Math.max(...ys) + 0.5;
    const x = (v) => ml + ((v - x0) / (x1 - x0)) * (W - ml - mr);
    const y = (v) => mt + (1 - (v - lo) / (hi - lo)) * (H - mt - mb);
    const line = (k, colour) =>
      `<polyline fill="none" stroke="${colour}" stroke-width="1.6" points="` +
      rows.map((r) => `${x(r.inflow_scale).toFixed(1)},${y(r[k]).toFixed(1)}`).join(' ') + '"/>';
    const dots = (k, colour) => rows.map((r) =>
      `<circle cx="${x(r.inflow_scale).toFixed(1)}" cy="${y(r[k]).toFixed(1)}" r="2.2" fill="${colour}"/>`).join('');
    const ticks = xs.map((v) =>
      `<text x="${x(v).toFixed(1)}" y="${H - 4}" class="tick" text-anchor="middle">×${v}</text>`).join('');
    box.innerHTML =
      `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">` +
      `<line x1="${ml}" x2="${W - mr}" y1="${y(d.frl_m).toFixed(1)}" y2="${y(d.frl_m).toFixed(1)}" stroke="${RED}" stroke-width="1" stroke-dasharray="4 3"/>` +
      `<text x="${ml - 4}" y="${(y(d.frl_m) + 3.5).toFixed(1)}" class="tick" text-anchor="end">FRL</text>` +
      line('peak_level_baseline_m', AMBER) + line('peak_level_optimised_m', GREEN) +
      dots('peak_level_baseline_m', AMBER) + dots('peak_level_optimised_m', GREEN) +
      ticks + '</svg>';
  }

  // --------------------------------------------------------------- chart
  /** Nice tick step for a span, from a 1-2-5 ladder. */
  function tickStep(span, target) {
    const raw = span / target;
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 5, 10]) if (m * pow >= raw) return m * pow;
    return 10 * pow;
  }

  function drawChart() {
    if (!st.data) return;
    const W = el.chart.clientWidth, H = el.chart.clientHeight;
    if (W < 40 || H < 40) return;
    const S = st.data.series;
    const { frl, rule } = deps.res();
    const n = S.observed_level.length;

    const ml = 48, mr = 14, mt = 16, mb = 20, gap = 14;
    const plotW = W - ml - mr;
    const levH = Math.round((H - mt - mb - gap) * 0.62);
    const relTop = mt + levH + gap;
    const relH = H - mb - relTop;
    const x = (i) => ml + (i / (n - 1)) * plotW;

    const finite = (a) => a.filter((v) => Number.isFinite(v));
    const lv = [...finite(S.observed_level), ...finite(S.optimised_level),
      ...finite(S.bulletin_level ?? []), frl, rule];
    let lo = Math.min(...lv), hi = Math.max(...lv);
    const padL = (hi - lo) * 0.06 || 0.5;
    lo -= padL; hi += padL;
    const yL = (v) => mt + (1 - (v - lo) / (hi - lo)) * levH;

    const rv = [...S.observed_release, ...S.optimised_release, ...(S.inflow ?? [])];
    const rhi = Math.max(1, ...finite(rv)) * 1.05;
    const yR = (v) => relTop + (1 - v / rhi) * relH;

    const path = (arr, y) => {
      let d = '', pen = false;
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i];
        if (!Number.isFinite(v)) { pen = false; continue; }
        d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        pen = true;
      }
      return d;
    };
    const line = (arr, y, colour, w = 1.6, dash = '') =>
      `<path d="${path(arr, y)}" fill="none" stroke="${colour}" stroke-width="${w}"` +
      `${dash ? ` stroke-dasharray="${dash}"` : ''} stroke-linejoin="round"/>`;

    // Axes and ticks.
    let g = '';
    const stepL = tickStep(hi - lo, 5);
    for (let v = Math.ceil(lo / stepL) * stepL; v <= hi; v += stepL) {
      g += `<line x1="${ml}" x2="${W - mr}" y1="${yL(v).toFixed(1)}" y2="${yL(v).toFixed(1)}" class="grid"/>` +
        `<text x="${ml - 6}" y="${(yL(v) + 3.5).toFixed(1)}" class="tick" text-anchor="end">${v.toFixed(0)}</text>`;
    }
    const stepR = tickStep(rhi, 3);
    for (let v = 0; v <= rhi; v += stepR) {
      g += `<line x1="${ml}" x2="${W - mr}" y1="${yR(v).toFixed(1)}" y2="${yR(v).toFixed(1)}" class="grid"/>` +
        `<text x="${ml - 6}" y="${(yR(v) + 3.5).toFixed(1)}" class="tick" text-anchor="end">${v.toFixed(0)}</text>`;
    }
    g += `<text x="${ml - 6}" y="${mt + 10}" class="axis" text-anchor="end">m</text>`;
    g += `<text x="${ml - 6}" y="${relTop + 10}" class="axis" text-anchor="end">m³/s</text>`;

    // Days along the bottom, labelled from the API's own timestamps.
    const stamps = S.timestamps ?? [];
    const every = n > 240 ? 48 : 24;
    for (let i = 0; i < n; i += every) {
      const label = stamps[i] ? stamps[i].slice(5, 10).replace('-', '/') : `h+${i}`;
      g += `<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${mt}" y2="${H - mb}" class="grid"/>` +
        `<text x="${x(i).toFixed(1)}" y="${H - 6}" class="tick" text-anchor="middle">${label}</text>`;
    }

    // Reference levels, then the traces. Recorded first so the twin's lines
    // sit on top of it and the gap between them reads as the replay error.
    g += `<line x1="${ml}" x2="${W - mr}" y1="${yL(frl).toFixed(1)}" y2="${yL(frl).toFixed(1)}" stroke="${RED}" stroke-width="1" stroke-dasharray="4 3"/>`;
    g += `<line x1="${ml}" x2="${W - mr}" y1="${yL(rule).toFixed(1)}" y2="${yL(rule).toFixed(1)}" stroke="${RULE}" stroke-width="1" stroke-dasharray="4 3"/>`;
    if (S.bulletin_level) g += line(S.bulletin_level, yL, GREY, 1.2, '2 3');
    g += line(S.observed_level, yL, AMBER);
    g += line(S.optimised_level, yL, GREEN);
    if (S.inflow) g += line(S.inflow, yR, BLUE, 1.1);
    g += line(S.observed_release, yR, AMBER, 1.3);
    g += line(S.optimised_release, yR, GREEN, 1.3);

    // The cursor: one line and a dot per trace, moved by attribute so a
    // scrub does not redraw 480 points of six series.
    g += `<g id="simv-cur">` +
      `<line x1="0" x2="0" y1="${mt}" y2="${H - mb}" stroke="rgba(232,240,247,.55)" stroke-width="1"/>` +
      `<circle r="3.2" fill="${AMBER}" data-s="observed_level"/>` +
      `<circle r="3.2" fill="${GREEN}" data-s="optimised_level"/>` +
      `<circle r="2.6" fill="${GREY}" data-s="bulletin_level"/>` +
      `</g>`;

    el.chart.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${g}</svg>`;
    st.cursorNodes = { x, yL, group: el.chart.querySelector('#simv-cur') };
    placeCursor();
  }

  function placeCursor() {
    const c = st.cursorNodes;
    if (!c || !st.data) return;
    const S = st.data.series;
    const px = c.x(st.idx).toFixed(1);
    const ln = c.group.querySelector('line');
    ln.setAttribute('x1', px); ln.setAttribute('x2', px);
    for (const dot of c.group.querySelectorAll('circle')) {
      const v = (S[dot.dataset.s] ?? [])[st.idx];
      if (!Number.isFinite(v)) { dot.setAttribute('visibility', 'hidden'); continue; }
      dot.removeAttribute('visibility');
      dot.setAttribute('cx', px);
      dot.setAttribute('cy', c.yL(v).toFixed(1));
    }
  }

  // ----------------------------------------------------------- scrubbing
  function stateAt(i) {
    const S = st.data.series;
    const opt = st.trace === 'opt';
    const level = opt ? S.optimised_level[i] : S.observed_level[i];
    const release = opt ? S.optimised_release[i] : S.observed_release[i];
    const p = st.data.policy;
    return {
      hour: i,
      timestamp: (S.timestamps ?? [])[i] ?? `h+${i}`,
      scenario: st.key,
      trace: st.trace,
      traceLabel: opt ? 'AquaSync schedule' : 'the day, twin replay',
      level, release,
      inflow: (S.inflow ?? [])[i] ?? 0,
      recorded: (S.bulletin_level ?? [])[i],
      advice: opt && p
        ? `AquaSync policy, in hindsight: draw down to ${p.target_level_m.toFixed(2)} m ` +
          `from h+${p.start_hour} at up to ${p.max_rate_cumecs.toFixed(0)} cumecs. ` +
          `Sees the inflow that actually arrived.`
        : `Replaying what the operators released on the day, from the KSEB bulletin, ` +
          `through the twin.`,
    };
  }

  function setIndex(i, force = false) {
    if (!st.data) return;
    const n = st.data.series.observed_level.length;
    i = Math.max(0, Math.min(n - 1, Math.round(i)));
    if (i === st.idx && !force) return;
    st.idx = i;
    el.scrub.value = String(i);
    placeCursor();

    const S = st.data.series;
    const f = (v, dp = 2) => (Number.isFinite(v) ? v.toFixed(dp) : '—');
    el.cursor.textContent =
      `h+${i} · ${(S.timestamps ?? [])[i] ?? ''} · recorded ${f(S.bulletin_level?.[i])} m · ` +
      `the day ${f(S.observed_level[i])} m · AquaSync ${f(S.optimised_level[i])} m · ` +
      `inflow ${f(S.inflow?.[i], 0)} · release the day ${f(S.observed_release[i], 0)} / ` +
      `AquaSync ${f(S.optimised_release[i], 0)} cumecs`;

    if (st.open) {
      st.driving = true;
      deps.onDrive(stateAt(i));
    }
  }

  function tick(now) {
    if (!st.playing) return;
    const dt = Math.min(0.25, (now - st.last) / 1000);
    st.last = now;
    const n = st.data.series.observed_level.length;
    // Advance a fractional position, so a slow speed on a fast display still
    // moves rather than rounding back to the same hour every frame.
    st.frac += Number(el.speed.value) * dt;
    if (st.frac >= n - 1) { setIndex(n - 1); stop(); return; }
    setIndex(st.frac);
    st.raf = requestAnimationFrame(tick);
  }

  function play() {
    if (!st.data || st.playing) return;
    const n = st.data.series.observed_level.length;
    if (st.idx >= n - 1) setIndex(0, true);
    st.playing = true;
    st.frac = st.idx;
    st.last = performance.now();
    el.play.textContent = 'Pause';
    st.raf = requestAnimationFrame(tick);
  }

  function stop() {
    st.playing = false;
    cancelAnimationFrame(st.raf);
    el.play.textContent = 'Play';
  }

  // ------------------------------------------------------------- opening
  function open(opts = {}) {
    if (opts.scenario) el.scenario.value = opts.scenario;
    if (opts.trace) setTrace(opts.trace);
    if (Number.isFinite(opts.hour)) st.idx = opts.hour;
    st.open = true;
    drawer.hidden = false;
    el.toggle.classList.add('on');
    drawer.parentElement.classList.add('sim-open');
    deps.onLayout();
    const wanted = Number(el.storm.value) || 1;
    if (!st.data || st.key !== el.scenario.value || st.scale !== wanted) run();
    else { drawChart(); setIndex(st.idx, true); }
  }

  function close() {
    stop();
    st.open = false;
    drawer.hidden = true;
    el.toggle.classList.remove('on');
    drawer.parentElement.classList.remove('sim-open');
    if (st.driving) { st.driving = false; deps.onRelease(); }
    deps.onLayout();
  }

  function setTrace(t) {
    st.trace = t === 'opt' ? 'opt' : 'day';
    for (const b of el.trace.querySelectorAll('button')) {
      b.classList.toggle('on', b.dataset.trace === st.trace);
    }
    if (st.data) setIndex(st.idx, true);
  }

  // ------------------------------------------------------------- binding
  el.toggle.addEventListener('click', () => (st.open ? close() : open()));
  el.close.addEventListener('click', close);
  el.run.addEventListener('click', () => run());
  el.scenario.addEventListener('change', () => run());
  el.storm.addEventListener('change', () => run());
  el.play.addEventListener('click', () => (st.playing ? stop() : play()));
  el.scrub.addEventListener('input', () => { stop(); setIndex(Number(el.scrub.value)); });
  el.trace.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-trace]');
    if (b) setTrace(b.dataset.trace);
  });
  addEventListener('resize', () => { if (st.open) drawChart(); });
  addEventListener('keydown', (e) => {
    // A focused button fires its own click on Space, so handling Space
    // here as well toggled play twice - once by us, once by the button.
    if (!st.open || e.target.matches('input, select, textarea, button')) return;
    if (e.code === 'Space') { e.preventDefault(); st.playing ? stop() : play(); }
    else if (e.code === 'ArrowRight') { stop(); setIndex(st.idx + (e.shiftKey ? 24 : 1)); }
    else if (e.code === 'ArrowLeft') { stop(); setIndex(st.idx - (e.shiftKey ? 24 : 1)); }
    else if (e.code === 'Home') { stop(); setIndex(0); }
    else if (e.code === 'End') { stop(); setIndex(Infinity); }
    else if (e.code === 'Escape') close();
  });

  return { open, close, run, populateScenarios, isDriving: () => st.driving };
}
