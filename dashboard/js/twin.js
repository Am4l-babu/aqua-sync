/**
 * AquaSync 3D digital twin.
 *
 * Renders the reservoir, dam wall, sluice gate and downstream channel, driven
 * by telemetry over a WebSocket. Two things about this file are deliberate:
 *
 * 1. Telemetry arrives at roughly 1 Hz but the render loop runs at 60 fps, so
 *    every visual quantity is interpolated toward its target rather than
 *    snapped. Snapping looks broken even when the data is perfect.
 *
 * 2. If no WebSocket is available it falls back to replaying a bundled
 *    October 2021 series. The expo venue Wi-Fi is not a dependency the demo
 *    can afford, and a dashboard that shows nothing when the network is down
 *    would rather undercut a project about disaster resilience.
 */

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// -- reservoir constants, mirrored from twin/constants.py -------------------
const RES = {
  name: 'Idukki',
  frl: 732.43,
  rule: 728.50,
  red: 728.19,
  dead: 694.94,
  turbineRated: 138.0,
};

const WS_URL = `ws://${location.hostname || 'localhost'}:8000/ws/telemetry`;
const LERP = 0.06;

// Live state (jumps on message) and displayed state (chases live).
const target = { level: RES.rule, gate: 0, inflow: 0, turbine: 0, spill: 0 };
const shown = { level: RES.rule, gate: 0 };

let scene, camera, renderer, controls;
let waterMesh, gateMesh, downstreamMesh, frlPlane, rulePlane;
const history = [];

// --------------------------------------------------------------------------
// scene
// --------------------------------------------------------------------------

function init() {
  const stage = document.getElementById('stage');

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0d1a26);
  scene.fog = new THREE.Fog(0x0d1a26, 90, 220);

  camera = new THREE.PerspectiveCamera(46, stage.clientWidth / stage.clientHeight, 0.1, 600);
  camera.position.set(46, 30, 52);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  stage.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.target.set(0, 6, 0);
  controls.maxPolarAngle = Math.PI * 0.49;

  scene.add(new THREE.HemisphereLight(0x9ec8ff, 0x1b2b38, 0.85));
  const sun = new THREE.DirectionalLight(0xfff2df, 1.15);
  sun.position.set(40, 60, 25);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -70; sun.shadow.camera.right = 70;
  sun.shadow.camera.top = 70; sun.shadow.camera.bottom = -70;
  scene.add(sun);

  buildTerrain();
  buildDam();
  buildWater();
  buildThresholdPlanes();

  addEventListener('resize', onResize);
  bindControls();
  connect();
  animate();
}

/** Level in m MSL to a scene-space Y coordinate. */
function levelToY(level) {
  const span = RES.frl - RES.dead;
  return ((level - RES.dead) / span) * 22.0;
}

function buildTerrain() {
  const valley = new THREE.Mesh(
    new THREE.BoxGeometry(70, 4, 70),
    new THREE.MeshStandardMaterial({ color: 0x2a4034, roughness: 0.96 })
  );
  valley.position.set(0, -2, 0);
  valley.receiveShadow = true;
  scene.add(valley);

  const hillMat = new THREE.MeshStandardMaterial({ color: 0x30503c, roughness: 0.95 });
  for (const side of [-1, 1]) {
    const hill = new THREE.Mesh(new THREE.BoxGeometry(10, 34, 70), hillMat);
    hill.position.set(side * 30, 15, 0);
    hill.castShadow = hill.receiveShadow = true;
    scene.add(hill);
  }
}

function buildDam() {
  const concrete = new THREE.MeshStandardMaterial({ color: 0xb9bec4, roughness: 0.85 });

  // Arch dam wall, with a gap left for the spillway bay.
  for (const [x, w] of [[-16, 18], [16, 18]]) {
    const seg = new THREE.Mesh(new THREE.BoxGeometry(w, 26, 6), concrete);
    seg.position.set(x, 13, 0);
    seg.castShadow = seg.receiveShadow = true;
    scene.add(seg);
  }

  const crest = new THREE.Mesh(new THREE.BoxGeometry(50, 1.2, 7.4), concrete);
  crest.position.set(0, 26.6, 0);
  crest.castShadow = true;
  scene.add(crest);

  // Spillway gate — slides vertically in the bay.
  gateMesh = new THREE.Mesh(
    new THREE.BoxGeometry(13, 9, 1.2),
    new THREE.MeshStandardMaterial({
      color: 0xd0512e, roughness: 0.5, metalness: 0.35,
    })
  );
  gateMesh.position.set(0, levelToY(RES.red) + 3.5, 0);
  gateMesh.castShadow = true;
  scene.add(gateMesh);

  const piers = new THREE.MeshStandardMaterial({ color: 0xa8adb4, roughness: 0.9 });
  for (const x of [-7, 7]) {
    const pier = new THREE.Mesh(new THREE.BoxGeometry(1.4, 24, 6.6), piers);
    pier.position.set(x, 12, 0);
    pier.castShadow = true;
    scene.add(pier);
  }
}

function buildWater() {
  const mat = new THREE.MeshStandardMaterial({
    color: 0x2f7fbf, transparent: true, opacity: 0.82,
    roughness: 0.18, metalness: 0.15,
  });
  waterMesh = new THREE.Mesh(new THREE.BoxGeometry(50, 1, 34), mat);
  waterMesh.position.set(0, 0, -18);
  scene.add(waterMesh);

  downstreamMesh = new THREE.Mesh(
    new THREE.BoxGeometry(14, 1, 30),
    new THREE.MeshStandardMaterial({
      color: 0x3f92c9, transparent: true, opacity: 0.75, roughness: 0.3,
    })
  );
  downstreamMesh.position.set(0, 0.4, 19);
  scene.add(downstreamMesh);
}

function buildThresholdPlanes() {
  const mk = (level, colour) => {
    const g = new THREE.PlaneGeometry(52, 36);
    const m = new THREE.MeshBasicMaterial({
      color: colour, transparent: true, opacity: 0.16,
      side: THREE.DoubleSide, depthWrite: false,
    });
    const p = new THREE.Mesh(g, m);
    p.rotation.x = -Math.PI / 2;
    p.position.set(0, levelToY(level), -18);
    scene.add(p);
    return p;
  };
  frlPlane = mk(RES.frl, 0xd1242f);
  rulePlane = mk(RES.rule, 0x1a7f37);
}

// --------------------------------------------------------------------------
// telemetry
// --------------------------------------------------------------------------

function setLink(state, text) {
  const el = document.getElementById('link-state');
  el.className = `pill pill-${state}`;
  el.textContent = text;
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

  ws.onopen = () => { clearTimeout(giveUp); setLink('ok', 'LIVE'); };
  ws.onmessage = (e) => { try { apply(JSON.parse(e.data)); } catch { /* ignore */ } };
  ws.onerror = () => { clearTimeout(giveUp); startReplay('websocket error'); };
  ws.onclose = () => { if (!replayTimer) startReplay('backend closed'); };
}

let replayTimer = null;

/**
 * Offline fallback: a synthesised October 2021 trajectory.
 *
 * The shape is taken from the real bulletin - level rising from 727.7 to
 * 731.0 with an inflow spike on 17 October and gates opening on the 20th -
 * so the fallback tells the same story as the live system rather than
 * showing something invented.
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
  if (typeof t.level === 'number') target.level = t.level;
  if (typeof t.gate === 'number') target.gate = t.gate;
  if (typeof t.inflow === 'number') target.inflow = t.inflow;
  if (typeof t.turbine === 'number') target.turbine = t.turbine;
  if (typeof t.spill === 'number') target.spill = t.spill;

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

  const span = RES.frl - RES.dead;
  const pct = Math.max(0, Math.min(100, ((target.level - RES.dead) / span) * 100));
  const fill = document.getElementById('band-fill');
  fill.style.width = `${pct}%`;
  fill.className = 'band-fill ' +
    (target.level >= RES.frl ? 'crit' : target.level >= RES.rule ? 'warn' : 'ok');

  document.getElementById('lbl-rule').textContent = `rule ${RES.rule}`;
  document.getElementById('lbl-frl').textContent = `FRL ${RES.frl}`;

  const net = target.inflow - target.turbine - target.spill;
  document.getElementById('ttf').textContent =
    net <= 0 ? 'stable or falling'
             : `${(freeboard / (net / 5000) / 24).toFixed(1)} d at current net inflow`;

  if (t.advice) document.getElementById('advice').textContent = t.advice;
  if (t.timestamp) document.getElementById('clock').textContent = t.timestamp;
  if (t.scenario) document.getElementById('scenario').textContent = `scenario: ${t.scenario}`;

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

function bindControls() {
  const slider = document.getElementById('whatif');
  const label = document.getElementById('whatif-val');
  slider.addEventListener('input', () => {
    label.textContent = slider.value;
    target.spill = Math.max(0, Number(slider.value) - RES.turbineRated);
    target.turbine = Math.min(Number(slider.value), RES.turbineRated);
    target.gate = Math.min(100, (target.spill / 400) * 100);
    updatePanel({});
  });
  document.getElementById('whatif-reset').addEventListener('click', () => {
    slider.value = 0; label.textContent = '0';
  });
}

// --------------------------------------------------------------------------
// render loop
// --------------------------------------------------------------------------

function onResize() {
  const stage = document.getElementById('stage');
  camera.aspect = stage.clientWidth / stage.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(stage.clientWidth, stage.clientHeight);
}

function animate() {
  requestAnimationFrame(animate);

  // Chase the targets rather than snapping to them.
  shown.level += (target.level - shown.level) * LERP;
  shown.gate += (target.gate - shown.gate) * LERP;

  const y = levelToY(shown.level);
  waterMesh.scale.y = Math.max(0.1, y);
  waterMesh.position.y = y / 2;

  // Gate rises out of the flow as it opens.
  gateMesh.position.y = levelToY(RES.red) + 3.5 + (shown.gate / 100) * 8.4;

  // Downstream channel swells with the routed discharge.
  const d = 0.5 + Math.min(4.5, (target.spill + target.turbine) / 160);
  downstreamMesh.scale.y = d;
  downstreamMesh.position.y = d / 2;

  // Colour the reservoir by proximity to FRL.
  const risk = Math.max(0, Math.min(1, (shown.level - RES.rule) / (RES.frl - RES.rule)));
  waterMesh.material.color.setRGB(0.18 + risk * 0.6, 0.50 - risk * 0.25, 0.75 - risk * 0.45);

  frlPlane.material.opacity = 0.12 + risk * 0.20;
  rulePlane.material.opacity = 0.16;

  controls.update();
  renderer.render(scene, camera);
}

init();
