/* =========================================================
   MYRA — System Core UI (Stage 1, v5)
   Three particle characters (CORE / MALE / FEMALE) formed
   by ~34,000 fine dots flowing in waves. Smooth futuristic
   silhouettes — identity comes from body shape & hair, not
   carved facial details. A scan-light sweeps through the
   dots bottom-to-top. Themes tint the whole system.
   Real AI chat arrives in Stage 3; replies here are demo.
   ========================================================= */
'use strict';

/* ---------- Helpers ---------- */
const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rand = (a, b) => a + Math.random() * (b - a);
const lerp = (a, b, t) => a + (b - a) * t;
const g2 = (x, y, cx, cy, sx, sy, amp) => {
  const dx = (x - cx) / sx, dy = (y - cy) / sy;
  return amp * Math.exp(-(dx * dx + dy * dy));
};
let toastTimer = null;
function toast(msg, ms = 3600) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms);
}
function setHoloStatus(txt) { const el = $('holoStatus'); if (el) el.textContent = txt; }
let _stateChip = '';
function setHoloState(txt) {
  if (txt === _stateChip) return;
  _stateChip = txt;
  const el = $('holoState'); if (el) el.textContent = txt;
}

/* ---------- Session console + history ---------- */
const EVENTS = [];
function logEvent(msg) {
  EVENTS.push([new Date(), msg]);
  const el = $('consoleLog');
  if (el) el.textContent = EVENTS.map(([d, m]) => `[${d.toLocaleTimeString('en-GB')}] ${m}`).join('\n');
}
const HISTORY = [];
function pushHistory(who, text) { HISTORY.push({ who, text, at: new Date() }); }

/* =========================================================
   Themes
   ========================================================= */
const THEME_HEX = { normal: 0x22d3ee, friendly: 0x4ade80, hacker: 0xf87171 };
const THEME_MAP_RGB = { normal: '94,234,212', friendly: '134,239,172', hacker: '252,165,165' };
let themeName = localStorage.getItem('myra_theme') || 'normal';
if (!THEME_HEX[themeName]) themeName = 'normal';

/* =========================================================
   Particle figures — smooth silhouettes, grayscale light
   (the theme color tints everything via material color)
   ========================================================= */
const N = 34000;
function savedChar() {
  const c = localStorage.getItem('myra_char');
  if (c === 'core' || c === 'male' || c === 'female') return c;
  const old = localStorage.getItem('stonic_gender');
  return old === 'male' ? 'male' : 'female';
}
const HOLO = {
  char: savedChar(),
  formedChar: null,
  power: true,
  speaking: false,
  speakBlend: 0,
  formT: 0,
  mode: 'in',
  pendingChar: null,
  targetRotY: 0,
  autoRot: 0,
  dragging: false,
  accentMats: [],
  pMat: null,
};

const LGT = (() => {
  const nrm = (x, y, z) => { const l = Math.hypot(x, y, z); return [x / l, y / l, z / l]; };
  return { key: nrm(-0.45, 0.78, 0.88), rim: nrm(0.85, 0.3, -0.72) };
})();
function shade(nx, ny, nz) {
  const l = Math.hypot(nx, ny, nz) || 1;
  nx /= l; ny /= l; nz /= l;
  const dKey = Math.max(0, nx * LGT.key[0] + ny * LGT.key[1] + nz * LGT.key[2]);
  const dRim = Math.max(0, nx * LGT.rim[0] + ny * LGT.rim[1] + nz * LGT.rim[2]);
  return clamp(0.58 + 0.52 * dKey + 0.32 * Math.pow(dRim, 3), 0.32, 1.3);
}

const HEAD_ROWS = {
  female: [
    [1.52, .15, .13, .10], [1.60, .245, .205, .055], [1.70, .315, .26, .03],
    [1.80, .365, .30, .012], [1.92, .405, .33, 0], [2.03, .41, .335, 0],
    [2.13, .415, .345, .005], [2.26, .435, .355, -.008], [2.40, .43, .365, -.03],
    [2.52, .35, .30, -.05], [2.62, .17, .15, -.06],
  ],
  male: [
    [1.52, .185, .155, .10], [1.60, .285, .235, .055], [1.70, .345, .28, .03],
    [1.80, .39, .32, .012], [1.92, .425, .35, 0], [2.03, .435, .355, 0],
    [2.13, .445, .365, .008], [2.26, .45, .37, -.012], [2.40, .445, .38, -.035],
    [2.52, .365, .315, -.05], [2.62, .185, .165, -.06],
  ],
};
function rowAt(rows, y) {
  if (y <= rows[0][0]) return rows[0].slice(1);
  for (let i = 0; i < rows.length - 1; i++) {
    const a = rows[i], b = rows[i + 1];
    if (y >= a[0] && y <= b[0]) {
      const t = (y - a[0]) / (b[0] - a[0]);
      return [lerp(a[1], b[1], t), lerp(a[2], b[2], t), lerp(a[3], b[3], t)];
    }
  }
  return rows[rows.length - 1].slice(1);
}
function profileAt(prof, y) {
  for (let i = 0; i < prof.length - 1; i++) {
    const a = prof[i], b = prof[i + 1];
    if (y <= a[0] && y >= b[0]) return lerp(a[1], b[1], (a[0] - y) / (a[0] - b[0]));
  }
  return prof[prof.length - 1][1];
}
function pushPt(arr, x, y, z, gray, headW) {
  arr.push({ x, y, z, gray: clamp(gray, 0.05, 1.6), headW });
}

/* Smooth head — silhouette does the talking */
function sampleSmoothHead(out, female) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  for (let i = 0; i < 11500; i++) {
    const y = rand(1.52, 2.62);
    const [rx, rz, cz] = rowAt(rows, y);
    let th;
    if (Math.random() < 0.5) th = Math.PI / 2 + rand(-0.9, 0.9);
    else th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x = rx * Math.cos(th);
    let z = cz + rz * fr;
    if (fr > 0.3) { // only a whisper of a nose so the profile isn't an egg
      z += g2(x, y, 0, 1.9, 0.05, 0.17, 0.04) * clamp((fr - 0.3) / 0.5, 0, 1);
    }
    const b = shade(x / (rx * rx), (y - 2.05) * 1.4, (z - cz) / (rz * rz));
    pushPt(out, x + rand(-.002, .002), y + rand(-.002, .002), z + rand(-.002, .002), b * 1.02, 1);
  }
  // ears (smooth, small)
  const [rxEar] = rowAt(rows, 1.95);
  for (const s of [1, -1]) {
    for (let i = 0; i < 160; i++) {
      const a = Math.random() * Math.PI * 2, rr = Math.sqrt(Math.random());
      pushPt(out, s * (rxEar + 0.002 + rr * 0.018), 1.95 + Math.sin(a) * rr * 0.08, -0.01 + Math.cos(a) * rr * 0.05, 0.68, 1);
    }
  }
}

function hairlineOK(x0, y, female) {
  if (female) return y >= 2.34 - 0.42 * Math.pow(clamp(Math.abs(x0) / 0.46, 0, 1), 1.6);
  return y >= 2.285 + 0.085 * Math.exp(-Math.pow((Math.abs(x0) - 0.27) / 0.09, 2));
}
function sampleHairCap(out, n, female) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  let placed = 0, guard = 0;
  while (placed < n && guard++ < n * 60) {
    const y = rand(1.98, 2.66);
    const [rx, rz, cz] = rowAt(rows, Math.min(y, 2.62));
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x0 = rx * Math.cos(th);
    if (fr > 0.22 && !hairlineOK(x0, y, female) && guard < n * 45) continue;
    const taper = y < 2.12 ? 1.05 : (female ? 1.11 : 1.09);
    const hx = x0 * taper + rand(-.007, .007);
    let hy = y + 0.032 + rand(-.007, .007);
    const hz = cz + rz * fr * taper - 0.012 + rand(-.007, .007);
    if (!female && fr > 0.3 && Math.abs(hx) < 0.3 && hy > 2.3) hy += 0.04 * (1 - Math.abs(hx) / 0.3);
    pushPt(out, hx, hy, hz, shade(hx * 1.6, hy - 2.0, hz * 1.4) * 0.66, 1);
    placed++;
  }
}

/* Female long hair as smooth sheets: back curtain + two front falls */
function sampleHairFemaleLong(out) {
  const prof = [[2.45, .47], [2.1, .55], [1.7, .585], [1.35, .555], [1.05, .48]];
  let placed = 0, guard = 0;
  while (placed < 6200 && guard++ < 6200 * 30) {
    const y = rand(1.05, 2.45);
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    if (fr > 0.38) continue;                    // keep the face window open
    const r = profileAt(prof, y) * rand(0.985, 1.02);
    const x = r * Math.cos(th), z = r * 0.92 * fr - 0.045;
    pushPt(out, x + rand(-.006, .006), y, z + rand(-.006, .006),
      shade(Math.cos(th), (y - 1.9) * 0.7, fr) * 0.62, clamp((y - 0.95) / 1.35, 0.18, 1));
    placed++;
  }
  // front falls over the chest (smooth ribbons)
  for (const s of [1, -1]) {
    for (let i = 0; i < 1300; i++) {
      const t = Math.random();
      const w = rand(-1, 1);
      const y = 2.18 - t * 1.33;
      const cx = s * (0.4 - 0.02 * t + 0.045 * Math.sin(t * 2.3 + (s > 0 ? 0 : 2)));
      const cz = 0.2 + 0.16 * Math.sin(t * Math.PI * 0.78);
      const x = cx + w * 0.085 * (1 - 0.3 * t) + Math.sin(t * 7 + w * 2) * 0.011;
      const z = cz + (1 - Math.abs(w)) * 0.035 + rand(-.008, .008);
      pushPt(out, x, y + rand(-.01, .01), z, shade(x * 1.4, (y - 1.9) * 0.7, z * 1.3) * 0.7, clamp(1.05 - t * 0.88, 0.18, 1));
    }
  }
}

function sampleLoft(out, n, rows, zScale, brightMul, headWFn, frontBumpFn) {
  const yMin = rows[rows.length - 1][0], yMax = rows[0][0];
  for (let i = 0; i < n; i++) {
    const y = rand(yMin, yMax);
    const r = profileAt(rows, y) * rand(0.985, 1.015);
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x = r * Math.cos(th);
    let z = r * zScale * fr;
    if (frontBumpFn && fr > 0.25) z += frontBumpFn(x, y) * clamp((fr - 0.25) / 0.5, 0, 1);
    const b = shade(Math.cos(th), 0.14, fr) * brightMul;
    const dim = y < 0.48 ? 0.55 + (y - 0.3) * 2.0 : 1;
    pushPt(out, x + rand(-.004, .004), y, z + rand(-.004, .004), b * clamp(dim, 0.5, 1), headWFn ? headWFn(y) : 0);
  }
}

function buildBustPoints(female) {
  const pts = [];
  sampleSmoothHead(pts, female);
  if (female) {
    sampleHairCap(pts, 5200, true);
    sampleHairFemaleLong(pts);
  } else {
    sampleHairCap(pts, 5400, false);
  }
  const neckRows = female
    ? [[1.50, .135], [1.38, .14], [1.26, .165], [1.16, .26], [1.10, .34]]
    : [[1.50, .16], [1.38, .17], [1.26, .195], [1.16, .305], [1.10, .385]];
  sampleLoft(pts, 1500, neckRows, 0.88, 0.92, (y) => 0.55 * clamp((y - 1.12) / 0.38, 0, 1), null);
  const chestRows = female
    ? [[1.12, .52], [1.06, .78], [1.00, .88], [0.88, .90], [0.72, .84], [0.55, .76], [0.40, .66], [0.30, .58]]
    : [[1.12, .62], [1.06, .92], [1.00, 1.04], [0.88, 1.07], [0.72, .99], [0.55, .89], [0.40, .78], [0.30, .70]];
  const bustBump = female
    ? (x, y) => g2(x, y, .23, .72, .15, .13, .045) + g2(x, y, -.23, .72, .15, .13, .045)
    : null;
  sampleLoft(pts, Math.max(N - pts.length, 200), chestRows, 0.55, 0.85, null, bustBump);
  return pts;
}

function buildCorePoints() {
  const pts = [];
  const CY = 1.55, R = 0.95;
  for (let i = 0; i < 15000; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = R * rand(0.96, 1.03);
    const x = r * s * Math.cos(th), y = CY + r * u, z = r * s * Math.sin(th);
    pushPt(pts, x, y, z, shade(x, u, z), 0);
  }
  for (let i = 0; i < 7000; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = R * 0.55 * Math.pow(Math.random(), 0.6);
    pushPt(pts, r * s * Math.cos(th), CY + r * u, r * s * Math.sin(th), lerp(1.55, 0.7, r / (R * 0.55)), 0);
  }
  [[1.25, 0.3, 1.28], [0.5, -0.7, 1.38], [1.8, 1.1, 1.22]].forEach(([tiltX, tiltZ, rad]) => {
    for (let i = 0; i < 3000; i++) {
      const a = Math.random() * Math.PI * 2;
      const x = Math.cos(a) * rad, z = Math.sin(a) * rad;
      const y1 = -z * Math.sin(tiltX), z1 = z * Math.cos(tiltX);
      const x2 = x * Math.cos(tiltZ) - y1 * Math.sin(tiltZ);
      const y2 = x * Math.sin(tiltZ) + y1 * Math.cos(tiltZ);
      pushPt(pts, x2 + rand(-.015, .015), CY + y2 + rand(-.015, .015), z1 + rand(-.015, .015), 1.1, 0);
    }
  });
  for (let i = 0; i < 3000; i++) {
    const a = Math.random() * Math.PI * 2, r = rand(1.0, 1.55);
    pushPt(pts, Math.cos(a) * r, CY + rand(-.05, .05), Math.sin(a) * r, rand(0.35, 0.75), 0);
  }
  return pts;
}

function buildFigure(charType) {
  let pts;
  if (charType === 'core') pts = buildCorePoints();
  else pts = buildBustPoints(charType === 'female');
  while (pts.length > N) pts.pop();
  while (pts.length < N) {
    const a = Math.random() * Math.PI * 2, r = rand(1.3, 1.9);
    pushPt(pts, Math.cos(a) * r, rand(0.4, 2.6), Math.sin(a) * r, 0.28, 0);
  }
  const targets = new Float32Array(N * 3);
  const gray = new Float32Array(N);
  const headW = new Float32Array(N);
  const delay = new Float32Array(N);
  pts.forEach((p, i) => {
    targets[i * 3] = p.x; targets[i * 3 + 1] = p.y; targets[i * 3 + 2] = p.z;
    gray[i] = p.gray;
    headW[i] = p.headW;
    const normY = clamp((p.y - 0.3) / 2.35, 0, 1);
    const rr = Math.hypot(p.x, p.z);
    delay[i] = clamp(normY * 0.5 + (Math.sin(p.y * 3.2 + rr * 2.5) * 0.5 + 0.5) * 0.26 + Math.random() * 0.24, 0, 1);
  });
  return { targets, gray, headW, delay };
}

/* ----- Theme tint (material color over grayscale dots) ----- */
const GLOBE_MATS = [];
function applyTint() {
  const hex = THEME_HEX[themeName];
  if (HOLO.pMat) {
    const c = new THREE.Color(hex);
    if (HOLO.char === 'female') c.offsetHSL(-0.02, 0.04, 0.03);
    HOLO.pMat.color.copy(c);
  }
  HOLO.accentMats.forEach((m) => { if (m.color && !m.userData.lockColor) m.color.setHex(hex); });
  GLOBE_MATS.forEach((m) => { if (m.color) m.color.setHex(hex); });
  if (window._redrawMap) window._redrawMap();
}

/* ----- Three.js scene ----- */
function initHologram() {
  if (typeof THREE === 'undefined') {
    setHoloStatus('⚠️ Three.js failed to load — check ui/vendor/three.min.js');
    return;
  }
  const canvas = $('holoCanvas');
  const wrap = canvas.parentElement;
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(0, 1.74, 4.05);
  camera.lookAt(0, 1.42, 0);

  const world = new THREE.Group();
  scene.add(world);

  { // stars
    const sp = [];
    for (let i = 0; i < 420; i++) sp.push(rand(-8, 8), rand(-0.4, 6.4), rand(-6, 2.5));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
    const m = new THREE.PointsMaterial({ color: 0x9fd8e8, size: 0.02, transparent: true, opacity: 0.45, depthWrite: false });
    m.userData.baseOp = 0.45; m.userData.lockColor = true;
    HOLO.accentMats.push(m);
    scene.add(new THREE.Points(g, m));
  }

  /* Soft glow floor (no rings) + projector beam */
  const accentMat = (op) => {
    const m = new THREE.MeshBasicMaterial({ color: THEME_HEX[themeName], transparent: true, opacity: op, side: THREE.DoubleSide, depthWrite: false });
    m.userData.baseOp = op;
    HOLO.accentMats.push(m);
    return m;
  };
  const disc = new THREE.Group();
  const glowOuter = new THREE.Mesh(new THREE.CircleGeometry(1.2, 56), accentMat(0.07));
  glowOuter.rotation.x = -Math.PI / 2; glowOuter.position.y = 0.004;
  const glowInner = new THREE.Mesh(new THREE.CircleGeometry(0.6, 48), accentMat(0.14));
  glowInner.rotation.x = -Math.PI / 2; glowInner.position.y = 0.008;
  disc.add(glowOuter, glowInner);
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.95, 0.3, 0.34, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: THEME_HEX[themeName], transparent: true, opacity: 0.045, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
  beam.material.userData.baseOp = 0.045;
  HOLO.accentMats.push(beam.material);
  beam.position.y = 0.17;
  disc.add(beam);
  world.add(disc);

  /* Particle figure */
  const built = buildFigure(HOLO.char);
  HOLO.formedChar = HOLO.char;
  let targets = built.targets, gray = built.gray, headW = built.headW, delay = built.delay;

  const scatter = new Float32Array(N * 3);
  const orbit = new Float32Array(N);
  const phase = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = rand(1.7, 3.3);
    scatter[i * 3] = r * s * Math.cos(th);
    scatter[i * 3 + 1] = 1.5 + r * u * 0.78;
    scatter[i * 3 + 2] = r * s * Math.sin(th);
    orbit[i] = rand(2.2, 4.6);
    phase[i] = Math.random() * Math.PI * 2;
  }

  const positions = new Float32Array(scatter);
  const colArr = new Float32Array(N * 3);
  for (let i = 0; i < N; i++) { colArr[i * 3] = colArr[i * 3 + 1] = colArr[i * 3 + 2] = gray[i]; }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colArr, 3));
  const pMat = new THREE.PointsMaterial({
    size: 0.0155, vertexColors: true, transparent: true, opacity: 0.88,
    blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
  });
  HOLO.pMat = pMat;
  const figure = new THREE.Points(geo, pMat);
  world.add(figure);
  applyTint();

  HOLO.applyFigure = (charType) => {
    const b = buildFigure(charType);
    targets = b.targets; gray = b.gray; headW = b.headW; delay = b.delay;
    HOLO.formedChar = charType;
    applyTint();
  };

  let lastX = 0;
  canvas.addEventListener('pointerdown', (e) => { HOLO.dragging = true; lastX = e.clientX; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', (e) => {
    if (!HOLO.dragging) return;
    HOLO.targetRotY += (e.clientX - lastX) * 0.008;
    lastX = e.clientX;
  });
  const stopDrag = () => { HOLO.dragging = false; };
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);

  const resize = () => {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(wrap);
  resize();

  let visible = true;
  document.addEventListener('visibilitychange', () => { visible = !document.hidden; });

  const clock = new THREE.Clock();
  (function animate() {
    requestAnimationFrame(animate);
    if (!visible) return;
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;

    if (!HOLO.power) {
      HOLO.formT = Math.max(0, HOLO.formT - dt * 1.4);
    } else if (HOLO.mode === 'out') {
      HOLO.formT = Math.max(0, HOLO.formT - dt * 1.6);
      if (HOLO.formT <= 0 && HOLO.pendingChar) {
        HOLO.applyFigure(HOLO.pendingChar);
        HOLO.pendingChar = null;
        HOLO.mode = 'in';
      }
    } else {
      HOLO.formT = Math.min(1, HOLO.formT + dt * 0.34);
    }
    const formT = HOLO.formT;
    const formed = clamp((formT - 0.72) / 0.28, 0, 1);

    const sTarget = (HOLO.speaking && HOLO.power) ? 1 : 0;
    HOLO.speakBlend += (sTarget - HOLO.speakBlend) * 0.07;
    const sb = HOLO.speakBlend;

    const nodA = (0.018 * Math.sin(t * 1.15) + sb * 0.08 * Math.sin(t * 7.3)) * formed;
    const tiltA = (0.014 * Math.sin(t * 0.85 + 1) + sb * 0.045 * Math.sin(t * 3.0)) * formed;
    const cosN = Math.cos(nodA), sinN = Math.sin(nodA);
    const cosT2 = Math.cos(tiltA), sinT2 = Math.sin(tiltA);
    const PIVOT_Y = 1.42;

    /* Scan-light: a bright band traveling through the dots, bottom → top */
    const scanCycle = t % 5.6;
    const scanY = scanCycle < 4.4 ? 0.05 + (scanCycle / 4.4) * 2.85 : -10;
    const scanOn = HOLO.power && formT > 0.25;

    const pos = geo.attributes.position.array;
    const col = geo.attributes.color.array;
    for (let i = 0; i < N; i++) {
      const i3 = i * 3;
      const p = clamp((formT - delay[i] * 0.45) / 0.55, 0, 1);
      const e = 1 - Math.pow(1 - p, 3);
      let x = scatter[i3] + (targets[i3] - scatter[i3]) * e;
      let y = scatter[i3 + 1] + (targets[i3 + 1] - scatter[i3 + 1]) * e;
      let z = scatter[i3 + 2] + (targets[i3 + 2] - scatter[i3 + 2]) * e;

      const sw = (1 - e) * (1 - e) * orbit[i];
      if (sw > 0.001) {
        const c = Math.cos(sw), s2 = Math.sin(sw);
        const nx = x * c - z * s2, nz = x * s2 + z * c;
        x = nx; z = nz;
      }
      y += Math.sin(p * Math.PI) * (1 - p) * 0.12 * Math.sin(phase[i] * 3 + t * 2);

      const ph = phase[i];
      const shim = Math.sin(t * 2.3 + ph) * (0.0036 + sb * 0.009 * headW[i]) * e;
      const rl = Math.sqrt(x * x + z * z) || 1e-4;
      x += (x / rl) * shim; z += (z / rl) * shim;
      y += Math.sin(t * 1.7 + ph * 1.3) * 0.0026 * e;

      const w = headW[i];
      if (w > 0.01 && formed > 0) {
        const cN = 1 + (cosN - 1) * w, sN = sinN * w;
        const dy = y - PIVOT_Y;
        y = PIVOT_Y + dy * cN - z * sN;
        z = dy * sN + z * cN;
        const cT = 1 + (cosT2 - 1) * w, sT = sinT2 * w;
        const dy2 = y - PIVOT_Y;
        const nx = x * cT - dy2 * sT;
        y = PIVOT_Y + x * sT + dy2 * cT;
        x = nx;
      }
      pos[i3] = x; pos[i3 + 1] = y; pos[i3 + 2] = z;

      /* brightness incl. scan band */
      let v = gray[i] * (0.35 + 0.65 * e);
      if (scanOn) {
        const dyS = targets[i3 + 1] - scanY;
        v *= 1 + 0.95 * Math.exp(-(dyS * dyS) / 0.09) * e;
      }
      col[i3] = v; col[i3 + 1] = v; col[i3 + 2] = v;
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;

    figure.position.y = Math.sin(t * 1.12) * 0.028;
    const pulse = HOLO.formedChar === 'core' ? 1 + sb * 0.045 * Math.sin(t * 9) + 0.012 * Math.sin(t * 2.2) : 1;
    figure.scale.setScalar(pulse);

    if (!HOLO.dragging && HOLO.power) HOLO.autoRot += dt * 0.09;
    world.rotation.y += ((HOLO.targetRotY + HOLO.autoRot) - world.rotation.y) * 0.08;

    pMat.opacity += ((HOLO.power ? 0.88 : 0.04) - pMat.opacity) * 0.08;
    HOLO.accentMats.forEach((m) => {
      const bse = m.userData.baseOp !== undefined ? m.userData.baseOp : 0.9;
      m.opacity += ((HOLO.power ? bse : bse * 0.06) - m.opacity) * 0.08;
    });

    setHoloState(!HOLO.power ? 'OFFLINE' : (formT < 0.985 ? 'FORMING…' : (sb > 0.35 ? 'SPEAKING' : 'IDLE // LISTENING')));
    renderer.render(scene, camera);
  })();
}

/* ----- Character switching ----- */
const IDLE_STATUS = {
  core: '⬢ Core online — listening',
  male: '🎩 At your service. Listening…',
  female: "💗 I'm right here with you… listening",
};
function idleStatus() { return IDLE_STATUS[HOLO.char] || IDLE_STATUS.core; }

function syncCharUI() {
  document.querySelectorAll('[data-char]').forEach((el) => {
    el.classList.toggle('active', el.dataset.char === HOLO.char);
  });
  ['core', 'male', 'female'].forEach((c) => {
    const card = $('card-' + c);
    if (card) {
      card.classList.toggle('is-active', c === HOLO.char);
      const badge = card.querySelector('.cc-badge');
      if (badge) badge.classList.toggle('hidden', c !== HOLO.char);
    }
  });
  applyTint();
}
function setChar(charType) {
  if (charType === HOLO.char && HOLO.mode === 'in' && HOLO.formT > 0.9) return;
  HOLO.char = charType;
  localStorage.setItem('myra_char', charType);
  HOLO.pendingChar = charType;
  HOLO.mode = 'out';
  syncCharUI();
  setHoloStatus('✨ Re-forming into ' + charType.toUpperCase() + '…');
  logEvent('character → ' + charType.toUpperCase());
}
function reform() {
  if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
  HOLO.pendingChar = HOLO.char;
  HOLO.mode = 'out';
  setHoloStatus('✨ Forming again — watch the waves of dots!');
  logEvent('formation replay');
}

/* =========================================================
   SAT-LINK dotted world map (own coarse continent outlines)
   ========================================================= */
const CONTINENTS = [
  [[6,30],[14,20],[28,12],[44,8],[60,10],[74,6],[88,10],[96,18],[92,26],[84,30],[90,38],[84,46],[74,48],[66,55],[58,62],[52,58],[50,50],[42,47],[34,50],[24,47],[14,40],[8,34]],
  [[86,4],[100,6],[102,13],[92,18],[83,11]],
  [[54,64],[62,60],[72,62],[80,68],[78,80],[70,93],[63,97],[59,84],[52,74]],
  [[96,28],[100,19],[108,13],[118,12],[128,16],[127,25],[120,30],[112,29],[106,34],[99,35],[94,31]],
  [[96,20],[99,19],[99,24],[96,24]],
  [[97,42],[107,38],[120,39],[131,46],[133,58],[126,72],[118,84],[110,88],[102,78],[97,62],[93,50]],
  [[126,18],[140,9],[158,7],[176,10],[190,16],[194,26],[186,36],[174,36],[168,29],[160,36],[156,46],[150,56],[145,60],[141,49],[136,42],[130,33],[124,26]],
  [[182,32],[187,30],[188,36],[183,38]],
  [[148,63],[160,61],[168,65],[160,70],[148,69]],
  [[170,62],[180,64],[178,69],[170,68]],
  [[166,74],[180,71],[190,78],[185,89],[170,90],[163,82]],
];
function inPoly(poly, x, y) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
const isLand = (mx, my) => CONTINENTS.some((p) => inPoly(p, mx, my));

function initMap() {
  const cv = $('mapCanvas');
  if (!cv) return;
  const box = cv.parentElement;
  const draw = () => {
    const w = box.clientWidth, h = box.clientHeight;
    if (!w || !h) return;
    cv.width = w; cv.height = h;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    const rgb = THEME_MAP_RGB[themeName] || THEME_MAP_RGB.normal;
    const sx = w / 200, sy = h / 100, step = 3.4;
    for (let gy = 2; gy < h - 2; gy += step) {
      for (let gx = 2; gx < w - 2; gx += step) {
        const land = isLand(gx / sx, gy / sy);
        ctx.fillStyle = land ? `rgba(${rgb},0.55)` : `rgba(${rgb},0.05)`;
        ctx.beginPath();
        ctx.arc(gx, gy, land ? 1.05 : 0.55, 0, 6.2832);
        ctx.fill();
      }
    }
  };
  window._redrawMap = draw;
  new ResizeObserver(draw).observe(box);
  draw();
}

/* ----- 3D dotted Earth ----- */
let globeBuilt = false, globeActive = false;
function initGlobe() {
  if (globeBuilt || typeof THREE === 'undefined') return;
  globeBuilt = true;
  const cv = $('globeCanvas');
  const box = cv.parentElement;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 60);
  camera.position.set(0, 0.5, 3.4);
  camera.lookAt(0, 0, 0);
  const group = new THREE.Group();
  group.rotation.x = 0.32;
  scene.add(group);

  const landPts = [];
  const GA = Math.PI * (3 - Math.sqrt(5));
  const TOTAL = 26000;
  for (let i = 0; i < TOTAL; i++) {
    const y = 1 - (i / (TOTAL - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = GA * i;
    const x = Math.cos(th) * r, z = Math.sin(th) * r;
    const lat = Math.asin(clamp(y, -1, 1)) * 180 / Math.PI;
    const lon = Math.atan2(z, x) * 180 / Math.PI;
    const mx = (lon + 180) / 360 * 200, my = (90 - lat) / 180 * 100;
    if (isLand(mx, my)) landPts.push(x, y, z);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(landPts, 3));
  const landMat = new THREE.PointsMaterial({ color: THEME_HEX[themeName], size: 0.021, transparent: true, opacity: 0.95, depthWrite: false });
  GLOBE_MATS.push(landMat);
  group.add(new THREE.Points(g, landMat));

  const ocean = new THREE.Mesh(
    new THREE.SphereGeometry(0.985, 40, 28),
    new THREE.MeshBasicMaterial({ color: 0x0a2422, transparent: true, opacity: 0.5 }));
  group.add(ocean);
  [[1.18, Math.PI / 2.3, 0.4], [1.3, Math.PI / 1.7, -0.6]].forEach(([rad, rx, ry]) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(rad, 0.004, 8, 110),
      new THREE.MeshBasicMaterial({ color: THEME_HEX[themeName], transparent: true, opacity: 0.4 }));
    GLOBE_MATS.push(ring.material);
    ring.rotation.set(rx, ry, 0);
    group.add(ring);
  });

  const spots = [[-100, 40], [-60, -15], [12, 50], [20, 5], [47, 28], [80, 22], [105, 32], [134, -25]];
  const hotPts = [];
  spots.forEach(([lon, lat]) => {
    const phi = (90 - lat) * Math.PI / 180, lam = lon * Math.PI / 180;
    hotPts.push(Math.sin(phi) * Math.cos(lam) * 1.01, Math.cos(phi) * 1.01, Math.sin(phi) * Math.sin(lam) * 1.01);
  });
  const hg = new THREE.BufferGeometry();
  hg.setAttribute('position', new THREE.Float32BufferAttribute(hotPts, 3));
  group.add(new THREE.Points(hg, new THREE.PointsMaterial({ color: 0xfb923c, size: 0.055, transparent: true, opacity: 0.95, depthWrite: false })));

  let dragging = false, lastX = 0, userRot = 0;
  cv.addEventListener('pointerdown', (e) => { dragging = true; lastX = e.clientX; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener('pointermove', (e) => { if (dragging) { userRot += (e.clientX - lastX) * 0.01; lastX = e.clientX; } });
  const sd = () => { dragging = false; };
  cv.addEventListener('pointerup', sd);
  cv.addEventListener('pointercancel', sd);

  const resize = () => {
    const w = box.clientWidth, h = box.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(box);
  resize();

  const ck = new THREE.Clock();
  (function anim() {
    requestAnimationFrame(anim);
    if (!globeActive || document.hidden) return;
    const dt = Math.min(ck.getDelta(), 0.05);
    const spin = $('globeSpin');
    if (!dragging && (!spin || spin.checked)) userRot += dt * 0.12;
    group.rotation.y = userRot;
    renderer.render(scene, camera);
  })();
}

/* =========================================================
   Live headlines — real feeds when online, cache offline
   (the permanent backend feed lands in Stage 10)
   ========================================================= */
const FEEDS = [
  { src: 'BBC', url: 'https://feeds.bbci.co.uk/news/world/rss.xml' },
  { src: 'Al Jazeera', url: 'https://www.aljazeera.com/xml/rss/all.xml' },
];
const DEMO_NEWS = [
  { title: 'Demo headline — real world news will stream here when online', link: '#', src: 'DEMO', ts: Date.now() },
  { title: 'Demo headline — ask MYRA and she will read the top stories aloud (Stage 10)', link: '#', src: 'DEMO', ts: Date.now() },
  { title: 'Demo headline — map hotspots will flash where events happen', link: '#', src: 'DEMO', ts: Date.now() },
];
let newsItems = [], newsLive = false, newsRegion = 'all';

function timeAgo(ts) {
  const m = Math.floor((Date.now() - ts) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  return h < 24 ? h + 'h ago' : Math.floor(h / 24) + 'd ago';
}
function setLiveBadge(state) { // 'live' | 'cached' | 'off'
  [['liveBadge'], ['liveBadgeFull']].forEach(([id]) => {
    const el = $(id);
    if (!el) return;
    el.className = 'live-badge' + (state === 'live' ? ' on' : state === 'cached' ? ' cached' : '');
    el.textContent = state === 'live' ? '● LIVE' : state === 'cached' ? '○ OFFLINE · CACHED' : '○ CONNECTING';
  });
}
const REGION_KEYS = {
  asia: ['asia', 'china', 'india', 'japan', 'korea', 'pakistan', 'bangladesh', 'taiwan', 'beijing', 'delhi', 'tokyo', 'modi'],
  europe: ['europe', 'britain', ' uk ', 'france', 'german', 'ukraine', 'russia', 'london', 'paris', 'berlin', 'eu '],
  america: ['america', 'washington', 'canada', 'mexico', 'brazil', 'new york', 'trump', 'white house', 'congress'],
  'middle east': ['gaza', 'israel', 'iran', 'iraq', 'saudi', 'lebanon', 'syria', 'yemen', 'middle east'],
  tech: ['ai ', 'artificial intelligence', 'tech', 'software', 'chip', 'cyber', 'apple', 'google', 'microsoft', 'spacex', 'robot'],
};
function filterNews(items) {
  if (newsRegion === 'all') return items;
  const keys = REGION_KEYS[newsRegion] || [];
  const hit = items.filter((it) => keys.some((k) => it.title.toLowerCase().includes(k)));
  return hit.length >= 2 ? hit : items;
}
function renderNews() {
  const items = newsItems.length ? newsItems : DEMO_NEWS;
  const mini = $('miniHeadlines');
  mini.innerHTML = '';
  items.slice(0, 3).forEach((it) => {
    const li = document.createElement('li');
    const tag = document.createElement('span');
    tag.className = 'hl-src'; tag.textContent = it.src;
    li.appendChild(tag);
    if (it.link && it.link !== '#') {
      const a = document.createElement('a');
      a.href = it.link; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = it.title;
      li.appendChild(a);
    } else li.appendChild(document.createTextNode(it.title));
    const tm = document.createElement('span');
    tm.className = 'hl-time'; tm.textContent = timeAgo(it.ts);
    li.appendChild(tm);
    mini.appendChild(li);
  });
  const full = $('fullHeadlines');
  full.innerHTML = '';
  filterNews(items).slice(0, 10).forEach((it) => {
    const card = document.createElement('div');
    card.className = 'news-card';
    const tag = document.createElement('div');
    tag.className = 'news-tag'; tag.textContent = it.src;
    const title = document.createElement('div');
    title.className = 'news-title';
    if (it.link && it.link !== '#') {
      const a = document.createElement('a');
      a.href = it.link; a.target = '_blank'; a.rel = 'noopener';
      a.textContent = it.title;
      title.appendChild(a);
    } else title.textContent = it.title;
    const meta = document.createElement('div');
    meta.className = 'news-meta';
    meta.textContent = 'Source: ' + it.src + ' · ' + timeAgo(it.ts);
    card.append(tag, title, meta);
    full.appendChild(card);
  });
}
function loadNewsCache() {
  try {
    const c = JSON.parse(localStorage.getItem('myra_news_cache') || 'null');
    if (c && Array.isArray(c.items) && c.items.length) {
      newsItems = c.items;
      setLiveBadge('cached');
      $('feedUpdated').textContent = '· cached ' + new Date(c.ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      return true;
    }
  } catch (e) { /* ignore */ }
  return false;
}
async function fetchOneFeed(feed) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 9000);
  try {
    const res = await fetch('https://api.rss2json.com/v1/api.json?rss_url=' + encodeURIComponent(feed.url), { signal: ctrl.signal });
    const data = await res.json();
    if (data.status !== 'ok' || !Array.isArray(data.items)) throw new Error('bad feed');
    return data.items.map((it) => ({
      title: (it.title || '').trim(),
      link: it.link || '#',
      src: feed.src,
      ts: it.pubDate ? Date.parse(it.pubDate.replace(' ', 'T') + 'Z') || Date.now() : Date.now(),
    })).filter((x) => x.title);
  } finally { clearTimeout(to); }
}
async function fetchNews(manual) {
  if (!navigator.onLine) {
    setLiveBadge(loadNewsCache() ? 'cached' : 'off');
    renderNews();
    if (manual) toast('📡 You are offline — showing the last saved headlines.');
    logEvent('news: offline, cache shown');
    return;
  }
  try {
    const results = await Promise.allSettled(FEEDS.map(fetchOneFeed));
    let items = [];
    results.forEach((r) => { if (r.status === 'fulfilled') items = items.concat(r.value); });
    if (!items.length) throw new Error('no items');
    items.sort((a, b) => b.ts - a.ts);
    newsItems = items.slice(0, 16);
    newsLive = true;
    localStorage.setItem('myra_news_cache', JSON.stringify({ ts: Date.now(), items: newsItems }));
    setLiveBadge('live');
    $('feedUpdated').textContent = '· live ' + new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    renderNews();
    logEvent('news: live headlines updated (' + newsItems.length + ')');
    if (manual) toast('📰 Headlines refreshed — showing live news.');
  } catch (e) {
    newsLive = false;
    const had = loadNewsCache();
    setLiveBadge(had ? 'cached' : 'off');
    renderNews();
    logEvent('news: fetch failed, fallback shown');
    if (manual) toast('📡 Could not reach the news service — showing ' + (had ? 'cached' : 'demo') + ' headlines.');
  }
}

/* =========================================================
   Circuit wires — module chips to the hologram frame
   ========================================================= */
const CHIP_COLORS = { memory: '#22d3ee', skills: '#4ade80', character: '#fb7185', setting: '#e2e8f0' };
function drawWires() {
  const zone = $('stageZone'), svg = $('wires'), stage = $('stage');
  if (!zone || !svg || !stage) return;
  const zr = zone.getBoundingClientRect();
  if (zr.width < 480) { svg.innerHTML = ''; return; }
  const sr = stage.getBoundingClientRect();
  svg.setAttribute('viewBox', `0 0 ${zr.width} ${zr.height}`);
  const fracs = [0.18, 0.4, 0.62, 0.84];
  let s = '';
  document.querySelectorAll('.mod-chip').forEach((chip, i) => {
    const r = chip.getBoundingClientRect();
    const col = CHIP_COLORS[chip.dataset.view] || '#22d3ee';
    const x1 = r.right - zr.left, y1 = r.top - zr.top + r.height / 2;
    const x2 = sr.left - zr.left, y2 = sr.top - zr.top + sr.height * (fracs[i] || 0.5);
    const mx = (x1 + x2) / 2;
    s += `<path d="M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}" stroke="${col}"/>`;
    s += `<circle cx="${x1}" cy="${y1}" r="3.2" fill="${col}"/><circle cx="${x2}" cy="${y2}" r="2.8" fill="${col}"/>`;
  });
  svg.innerHTML = s;
}

/* =========================================================
   Full-screen windows navigation
   ========================================================= */
let satLoaded = false;
function setWorldTab(tab) {
  const isGlobe = tab !== 'sat';
  $('wmTabGlobe').classList.toggle('active', isGlobe);
  $('wmTabSat').classList.toggle('active', !isGlobe);
  $('globeBox').classList.toggle('hidden', !isGlobe);
  $('satBox').classList.toggle('hidden', isGlobe);
  globeActive = isGlobe && !$('view-world').classList.contains('hidden');
  if (!isGlobe && !satLoaded) {
    satLoaded = true;
    const ifr = document.createElement('iframe');
    ifr.className = 'sat-frame';
    ifr.title = 'Live satellite view';
    ifr.setAttribute('sandbox', 'allow-scripts');
    ifr.setAttribute('referrerpolicy', 'no-referrer');
    ifr.loading = 'lazy';
    ifr.src = 'https://embed.windy.com/embed.html?type=map&location=coordinates&metricRain=default&metricTemp=default&metricWind=default&zoom=3&overlay=satellite&product=satellite&level=surface&lat=22&lon=84';
    $('satBox').appendChild(ifr);
    logEvent('world: live satellite embed requested');
  }
}
function openView(name, opt) {
  document.querySelectorAll('.fullview').forEach((v) => v.classList.add('hidden'));
  const v = $('view-' + name);
  if (v) v.classList.remove('hidden');
  document.body.classList.add('view-open');
  globeActive = false;
  if (name === 'world') {
    initGlobe();
    setWorldTab(opt && opt.tab === 'sat' ? 'sat' : 'globe');
    globeActive = !(opt && opt.tab === 'sat');
  }
  if (name === 'history') renderHistory();
  if (name === 'console') logEvent('console opened');
  logEvent('window opened: ' + name);
}
function closeViews() {
  document.querySelectorAll('.fullview').forEach((v) => v.classList.add('hidden'));
  document.body.classList.remove('view-open');
  globeActive = false;
  setTimeout(drawWires, 60);
}
function renderHistory() {
  const box = $('historyList');
  box.innerHTML = '';
  if (!HISTORY.length) {
    box.innerHTML = '<div class="empty-note">No conversation yet this session.</div>';
    return;
  }
  HISTORY.forEach((h) => {
    const d = document.createElement('div');
    d.className = 'hist-item' + (h.who === 'user' ? ' user' : '');
    const who = document.createElement('span');
    who.className = 'h-who';
    who.textContent = h.who === 'user' ? 'YOU' : 'MYRA';
    const tm = document.createElement('span');
    tm.className = 'h-time';
    tm.textContent = h.at.toLocaleTimeString('en-GB');
    d.append(who, tm, document.createElement('br'), document.createTextNode(h.text));
    box.appendChild(d);
  });
}

/* =========================================================
   Speaking (demo TTS; real voice in Stage 5)
   ========================================================= */
let VOICE_MUTED = false;
function speakDemo(text) {
  if (!HOLO.power) return;
  if (VOICE_MUTED) {
    setHoloStatus('🔇 Voice muted — tap 🔊 under the hologram to unmute');
    return;
  }
  HOLO.speaking = true;
  setHoloStatus('🗣️ MYRA is speaking…');
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    HOLO.speaking = false;
    setHoloStatus(idleStatus());
  };
  setTimeout(finish, Math.min(800 + text.length * 55, 9000));
  if ('speechSynthesis' in window) {
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-US';
      u.pitch = HOLO.char === 'female' ? 1.25 : (HOLO.char === 'male' ? 0.82 : 1.0);
      u.rate = HOLO.char === 'core' ? 1.02 : 1.0;
      const voices = speechSynthesis.getVoices();
      const match = HOLO.char === 'female'
        ? voices.find((v) => /female|zira|samantha|Jenny|veena/i.test(v.name))
        : HOLO.char === 'male'
          ? voices.find((v) => /male|david|daniel|ravi/i.test(v.name))
          : null;
      if (match) u.voice = match;
      u.onend = finish;
      u.onerror = finish;
      speechSynthesis.speak(u);
    } catch (e) { /* animation still plays */ }
  }
}
function stopSpeaking() {
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  HOLO.speaking = false;
  setHoloStatus(idleStatus());
}

/* =========================================================
   Chat demo (real AI brain in Stage 3)
   ========================================================= */
const demoReplies = {
  core: [
    'Message received. My neural core is not connected yet — Gemini and Groq link up in Stage 3, then I can truly think with you.',
    'Systems nominal. Interface only, for now. In Stage 4 I will begin remembering everything you tell me.',
    'Try switching me to MALE or FEMALE above — my particles will scatter and re-form into a new shape.',
  ],
  male: [
    'Very good, sir. I have noted that. My full intelligence arrives in Stage 3 — until then, I remain at your service in demo form.',
    'As always, I shall be ready when you are. In Stage 5 you will hear my proper voice as well.',
    'Might I suggest trying the modules on the left? Memory, Skills, Character — each opens its own window now.',
  ],
  female: [
    "Got it, love! 💗 I'm still waking up — my real brain connects in Stage 3, and then we can talk about everything.",
    'See how my head moves when I speak? In Stage 5 you will hear my real voice too — I can’t wait!',
    'Psst… open the WORLD MONITOR and spin the Earth with me. It’s beautiful from up here.',
  ],
};
const GREETINGS = {
  core: '⬢ Core online. All interface systems ready. My real brain connects in Stage 3 — until then, try my modules and watch me form.',
  male: 'Good day, sir. 🎩 I am MYRA, at your service. This is only my interface for now — my full intelligence arrives in Stage 3.',
  female: "Hello, I'm MYRA — your personal desktop companion. 💗 Right now only my interface is alive (Stage 1) — my real brain arrives in Stage 3. Type something below and watch me respond!",
};
let demoIdx = 0;

function addMsg(text, who, skipHistory) {
  const log = $('chatLog');
  const div = document.createElement('div');
  div.className = 'msg ' + (who === 'user' ? 'msg-user' : 'msg-ai');
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;
  if (who === 'ai' && text) {
    const btn = document.createElement('button');
    btn.className = 'speak-btn';
    btn.textContent = '🔊';
    btn.title = 'Read aloud (demo)';
    btn.onclick = () => speakDemo(text);
    bubble.appendChild(btn);
  }
  div.appendChild(bubble);
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  if (text && !skipHistory) pushHistory(who, text);
  return bubble;
}
function sendChat() {
  const input = $('chatInput');
  const text = input.value.trim();
  if (!text || !HOLO.power) return;
  addMsg(text, 'user');
  input.value = '';
  setHoloStatus('🤔 MYRA is thinking…');
  setHoloState('THINKING…');
  const typing = addMsg('', 'ai', true);
  typing.innerHTML = '<span class="typing">•••</span>';
  setTimeout(() => {
    const pool = demoReplies[HOLO.char] || demoReplies.core;
    const reply = pool[demoIdx++ % pool.length];
    typing.textContent = reply;
    const btn = document.createElement('button');
    btn.className = 'speak-btn';
    btn.textContent = '🔊';
    btn.onclick = () => speakDemo(reply);
    typing.appendChild(btn);
    $('chatLog').scrollTop = $('chatLog').scrollHeight;
    pushHistory('ai', reply);
    speakDemo(reply);
  }, 900);
}
function newChat() {
  const log = $('chatLog');
  log.innerHTML = '';
  const ready = document.createElement('div');
  ready.className = 'sys-ready';
  ready.textContent = '✦ NEW CONVERSATION ✦';
  log.appendChild(ready);
  demoIdx = 0;
  addMsg(GREETINGS[HOLO.char] || GREETINGS.core, 'ai');
  logEvent('new conversation started');
}

/* =========================================================
   Power / TERMINATE
   ========================================================= */
function setPower(on) {
  HOLO.power = on;
  document.body.classList.toggle('power-off', !on);
  const btn = $('terminateBtn');
  if (btn) {
    btn.textContent = on ? '⏻ TERMINATE' : '▶ ACTIVATE';
    btn.classList.toggle('is-off', !on);
  }
  if (!on) {
    stopSpeaking();
    setMic(false, true);
    closeViews();
    setHoloStatus('⏻ System offline — press ACTIVATE and the dots will form again');
    toast('⏻ MYRA powered down — particles scattered. Press ACTIVATE to wake her.');
    logEvent('power OFF (terminated)');
  } else {
    setHoloStatus('✨ Waking up — particles gathering…');
    toast('🤖 MYRA online! Watch the figure form.');
    logEvent('power ON');
  }
}

/* =========================================================
   Stage controls: mic toggle + voice mute
   ========================================================= */
let MIC_ARMED = false;
function setMic(on, silent) {
  MIC_ARMED = on;
  $('stageMicBtn').classList.toggle('on', on);
  $('stageMicBtn').textContent = on ? '🔴' : '🎤';
  if (!silent) {
    toast(on
      ? '🎤 Mic ON (armed) — real listening arrives in Stage 5. When MYRA speaks, the badge above her shows SPEAKING.'
      : '🎤 Mic OFF.');
    logEvent('mic ' + (on ? 'armed' : 'off'));
  }
}
function setMute(muted) {
  VOICE_MUTED = muted;
  const b = $('muteBtn');
  b.textContent = muted ? '🔇' : '🔊';
  b.classList.toggle('on', muted);
  if (muted) stopSpeaking();
  toast(muted ? '🔇 MYRA\'s voice muted — she will reply in text only.' : '🔊 Voice unmuted.');
  logEvent('voice ' + (muted ? 'muted' : 'unmuted'));
}

/* =========================================================
   Visual Hub — the single home of camera/screen control
   ========================================================= */
const VIS = { cam: false, scr: false };
function setVisual(kind, on) {
  VIS[kind] = on;
  $('camIndicator').classList.toggle('hidden', !(VIS.cam || VIS.scr));
  $('camChip').textContent = 'CAM · ' + (VIS.cam ? 'ON' : 'OFF');
  $('camChip').classList.toggle('on', VIS.cam);
  $('scrChip').textContent = 'SCREEN · ' + (VIS.scr ? 'ON' : 'OFF');
  $('scrChip').classList.toggle('on', VIS.scr);
  $('vhCamBtn').classList.toggle('on', VIS.cam);
  $('vhScrBtn').classList.toggle('on', VIS.scr);
  logEvent('visual hub: ' + kind + ' ' + (on ? 'ON (demo)' : 'OFF'));
  toast(on
    ? '🔴 Indicator demo only — no real camera/screen access yet. Permission-based vision arrives in Stage 9, and this red warning will glow whenever it is on.'
    : '✅ Turned off — MYRA cannot see anything now.', 4600);
}

/* =========================================================
   Memory demo (plugs into SQLite in Stage 4)
   ========================================================= */
function loadMemories() {
  try { return JSON.parse(localStorage.getItem('myra_memories_demo') || '[]'); }
  catch (e) { return []; }
}
function renderMemories() {
  const list = $('memoryList');
  const mems = loadMemories();
  list.innerHTML = '';
  mems.forEach((m, idx) => {
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = '🧠 ' + m;
    const del = document.createElement('button');
    del.textContent = '🗑️';
    del.title = 'Forget this';
    del.onclick = () => {
      const arr = loadMemories();
      arr.splice(idx, 1);
      localStorage.setItem('myra_memories_demo', JSON.stringify(arr));
      renderMemories();
    };
    li.append(span, del);
    list.appendChild(li);
  });
  $('memoryEmpty').classList.toggle('hidden', mems.length > 0);
}

/* =========================================================
   Dropdowns (Feedback / Support / Profile)
   ========================================================= */
function closeDropdowns(exceptId) {
  document.querySelectorAll('.dropdown').forEach((d) => {
    if (d.id !== exceptId) d.classList.add('hidden');
  });
}
function setupDropdown(btnId, dropId) {
  const btn = $(btnId), drop = $(dropId);
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const wasHidden = drop.classList.contains('hidden');
    closeDropdowns();
    if (wasHidden) drop.classList.remove('hidden');
  });
  drop.addEventListener('click', (e) => e.stopPropagation());
}

/* =========================================================
   Event wiring
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  document.body.dataset.theme = themeName;
  logEvent('MYRA shell boot · theme=' + themeName + ' · char=' + HOLO.char);

  initHologram();
  initMap();
  syncCharUI();
  renderMemories();
  loadNewsCache();
  renderNews();
  setTimeout(() => fetchNews(false), 700);
  setInterval(() => fetchNews(false), 10 * 60 * 1000);
  window.addEventListener('online', () => { fetchNews(false); logEvent('network online'); });
  window.addEventListener('offline', () => { setLiveBadge('cached'); logEvent('network offline — cache mode'); });
  setTimeout(drawWires, 350);
  let rT = null;
  window.addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(drawWires, 160); });

  /* Assistant + owner names */
  const savedName = localStorage.getItem('myra_name');
  if (savedName) { $('npName').textContent = savedName.toUpperCase(); $('nameInput').value = savedName; }
  else $('nameInput').value = 'MYRA';
  $('nameSave').addEventListener('click', () => {
    const v = $('nameInput').value.trim() || 'MYRA';
    localStorage.setItem('myra_name', v);
    $('npName').textContent = v.toUpperCase();
    toast('✨ Name saved — say hello to ' + v + '!');
  });
  const applyOwner = (name) => {
    $('profileNameTop').textContent = (name || 'Profile').split(' ')[0];
    $('profileAvatar').textContent = (name || 'S').trim().charAt(0).toUpperCase() || 'S';
    $('ownerName').value = name || '';
  };
  applyOwner(localStorage.getItem('myra_owner') || 'Saidul');
  $('ownerSave').addEventListener('click', () => {
    const v = $('ownerName').value.trim();
    if (v) { localStorage.setItem('myra_owner', v); applyOwner(v); toast('👤 Profile saved. Welcome, ' + v.split(' ')[0] + '!'); }
  });
  $('profileCharBtn').addEventListener('click', () => { closeDropdowns(); openView('character'); });

  /* Top-bar dropdowns */
  setupDropdown('feedbackBtn', 'feedbackDrop');
  setupDropdown('supportBtn', 'supportDrop');
  setupDropdown('profileBtn', 'profileDrop');
  document.addEventListener('click', () => closeDropdowns());
  $('feedbackSend').addEventListener('click', () => {
    const v = $('feedbackText').value.trim();
    if (!v) { toast('✏️ Write something first!'); return; }
    const arr = JSON.parse(localStorage.getItem('myra_feedback') || '[]');
    arr.push({ ts: Date.now(), text: v });
    localStorage.setItem('myra_feedback', JSON.stringify(arr));
    $('feedbackText').value = '';
    closeDropdowns();
    toast('💬 Thanks! Your feedback is saved on this device.');
    logEvent('feedback saved');
  });

  /* Awareness */
  const aw = $('awarenessToggle');
  aw.checked = localStorage.getItem('myra_awareness') === '1';
  aw.addEventListener('change', () => {
    localStorage.setItem('myra_awareness', aw.checked ? '1' : '0');
    toast(aw.checked
      ? '👁️ Awareness ON — in Stages 5 & 9 MYRA will proactively notice things, always within the permissions you grant. It is just a setting for now.'
      : '👁️ Awareness OFF — MYRA will only respond when you talk to her.', 4800);
    logEvent('awareness ' + (aw.checked ? 'ON' : 'OFF'));
  });

  /* Theme */
  const themeSel = $('themeSelect');
  themeSel.value = themeName;
  themeSel.addEventListener('change', () => {
    themeName = themeSel.value;
    document.body.dataset.theme = themeName;
    localStorage.setItem('myra_theme', themeName);
    applyTint();
    drawWires();
    toast(themeName === 'normal' ? '⬛ Normal black theme.' : themeName === 'friendly' ? '💚 Friendly green theme — soft and warm.' : '🔴 Hacker red theme — alert mode vibes (looks only!).');
    logEvent('theme → ' + themeName);
  });

  /* Clocks */
  const tick = () => {
    const el = $('clock'); if (el) el.textContent = new Date().toLocaleTimeString('en-GB');
    const u = $('utcClock'); if (u) u.textContent = 'UTC ' + new Date().toUTCString().slice(17, 25);
  };
  tick(); setInterval(tick, 1000);

  /* Server health */
  const checkHealth = () => {
    if (location.protocol === 'file:') {
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = 'Preview mode (no server)';
      return;
    }
    fetch('/api/health').then((r) => r.json()).then((d) => {
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = `Server connected ✅ (Stage ${d.stage})`;
    }).catch(() => {
      $('serverDot').className = 'dot dot-off';
      $('serverText').textContent = 'Server disconnected ❌';
    });
  };
  checkHealth();
  setInterval(checkHealth, 20000);

  /* Stage controls */
  $('terminateBtn').addEventListener('click', () => setPower(!HOLO.power));
  $('reformBtn').addEventListener('click', reform);
  $('stageMicBtn').addEventListener('click', () => {
    if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
    setMic(!MIC_ARMED);
  });
  $('muteBtn').addEventListener('click', () => setMute(!VOICE_MUTED));

  /* Character switch — the ONLY place */
  document.querySelectorAll('[data-char]').forEach((el) => {
    el.addEventListener('click', () => {
      if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
      const c = el.dataset.char;
      setChar(c);
      toast(c === 'core' ? '⬢ CORE form — pure AI light.'
        : c === 'male' ? '♂ MALE form — your JARVIS-style assistant is taking shape.'
        : '♀ FEMALE form — your companion is taking shape. 💗');
    });
  });

  /* Full-screen windows */
  document.querySelectorAll('.mod-chip').forEach((chip) => {
    chip.addEventListener('click', () => openView(chip.dataset.view));
  });
  $('openWorldBtn').addEventListener('click', () => openView('world'));
  $('previewWindow').addEventListener('click', () => openView('world'));
  document.querySelectorAll('.wm-chip').forEach((b) => {
    b.addEventListener('click', (e) => { e.stopPropagation(); openView('world', { tab: b.dataset.wmtab }); });
  });
  $('wmTabGlobe').addEventListener('click', () => { setWorldTab('globe'); globeActive = true; });
  $('wmTabSat').addEventListener('click', () => setWorldTab('sat'));
  document.querySelectorAll('[data-back]').forEach((b) => b.addEventListener('click', closeViews));
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDropdowns();
      closeViews();
      $('convoPanel').classList.remove('expanded');
      $('expandConvoBtn').textContent = '⤢';
    }
  });

  /* Conversation tabs */
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.mode-panel').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      $('mode-' + tab.dataset.mode).classList.add('active');
    });
  });

  /* Right-panel toolbar */
  $('newChatBtn').addEventListener('click', newChat);
  $('historyBtn').addEventListener('click', () => openView('history'));
  $('consoleBtn').addEventListener('click', () => openView('console'));
  $('clearHistory').addEventListener('click', () => { HISTORY.length = 0; renderHistory(); toast('🕘 History cleared for this session.'); });
  $('expandConvoBtn').addEventListener('click', () => {
    const p = $('convoPanel');
    const on = p.classList.toggle('expanded');
    $('expandConvoBtn').textContent = on ? '⤡' : '⤢';
    document.body.classList.toggle('view-open', on);
    logEvent('conversation panel ' + (on ? 'expanded to full view' : 'restored'));
  });
  $('collapseRightBtn').addEventListener('click', () => {
    document.body.classList.add('right-collapsed');
    $('reopenRightBtn').classList.remove('hidden');
    setTimeout(drawWires, 80);
    logEvent('right panel hidden');
  });
  $('reopenRightBtn').addEventListener('click', () => {
    document.body.classList.remove('right-collapsed');
    $('reopenRightBtn').classList.add('hidden');
    setTimeout(drawWires, 80);
    logEvent('right panel restored');
  });

  /* Chat */
  $('sendBtn').addEventListener('click', sendChat);
  $('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

  /* Agent demo */
  const runAgentDemo = () => {
    const task = $('agentInput').value.trim() || '(empty task)';
    const log = $('agentLog');
    log.textContent = `📝 Task received: "${task}"\n`;
    logEvent('agent task (demo): ' + task.slice(0, 60));
    setTimeout(() => { log.textContent += '⏳ In Stage 8, I would now open the browser myself…\n'; }, 600);
    setTimeout(() => { log.textContent += '🔍 …search, read the results, and hand you a summary report.\n✅ For now this is a demo layout.'; }, 1400);
  };
  $('agentBtn').addEventListener('click', runAgentDemo);
  $('agentInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') runAgentDemo(); });

  /* Notes demo */
  const addNote = () => {
    const v = $('noteInput').value.trim();
    if (!v) return;
    const li = document.createElement('li');
    const span = document.createElement('span');
    span.textContent = '📌 ' + v;
    const del = document.createElement('button');
    del.textContent = '🗑️';
    del.onclick = () => li.remove();
    li.append(span, del);
    $('notesList').prepend(li);
    $('noteInput').value = '';
  };
  $('noteAdd').addEventListener('click', addNote);
  $('noteInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') addNote(); });

  /* Memory window */
  const addMemory = () => {
    const v = $('memoryInput').value.trim();
    if (!v) return;
    const arr = loadMemories();
    arr.unshift(v);
    localStorage.setItem('myra_memories_demo', JSON.stringify(arr));
    $('memoryInput').value = '';
    renderMemories();
    toast('🧠 Noted! (Demo memory — the permanent SQLite brain arrives in Stage 4.)');
    logEvent('memory added (demo)');
  };
  $('memoryAdd').addEventListener('click', addMemory);
  $('memoryInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') addMemory(); });
  $('clearMemory').addEventListener('click', () => {
    localStorage.removeItem('myra_memories_demo');
    renderMemories();
    toast('🗑️ All demo memories erased.');
  });

  /* API keys (Stage 2) */
  $('saveKeys').addEventListener('click', () => {
    $('geminiKey').value = '';
    $('groqKey').value = '';
    toast('⚠️ Keys are NOT saved in Stage 1 — the secure save system arrives in Stage 2. Fields cleared for safety. Never share real keys with anyone!', 5200);
  });

  /* Reset preferences */
  $('resetPrefs').addEventListener('click', () => {
    ['myra_char', 'myra_name', 'myra_skills', 'myra_personality', 'myra_theme', 'myra_awareness', 'myra_owner']
      .forEach((k) => localStorage.removeItem(k));
    toast('🧹 Preferences reset — reload the page to start fresh.', 4200);
    logEvent('preferences reset');
  });

  /* Visual Hub — the ONLY camera/screen controls */
  $('vhCamBtn').addEventListener('click', () => setVisual('cam', !VIS.cam));
  $('vhScrBtn').addEventListener('click', () => setVisual('scr', !VIS.scr));
  document.querySelectorAll('.vh-suggest').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelector('[data-mode="voice"]').click();
      $('chatInput').value = btn.dataset.vh;
      $('chatInput').focus();
      toast('👁️ Real vision arrives in Stage 9 — I placed your request in the chat box; send it to see the demo.');
    });
  });

  /* Skills toggles */
  const saved = JSON.parse(localStorage.getItem('myra_skills') || '{}');
  document.querySelectorAll('.skill-toggle').forEach((tg) => {
    if (tg.dataset.skill in saved) tg.checked = saved[tg.dataset.skill];
    tg.addEventListener('change', () => {
      saved[tg.dataset.skill] = tg.checked;
      localStorage.setItem('myra_skills', JSON.stringify(saved));
      toast(`🧩 Skill ${tg.checked ? 'enabled ✅' : 'disabled ⛔'} — saved in this browser (skill engine in Stage 7).`);
    });
  });

  /* Personality */
  const persSel = $('personality');
  const savedPers = localStorage.getItem('myra_personality');
  if (savedPers) persSel.value = savedPers;
  persSel.addEventListener('change', (e) => {
    localStorage.setItem('myra_personality', e.target.value);
    toast(`🎭 Personality set to "${e.target.value}" — it will shape replies from Stage 3.`);
  });

  /* News */
  $('refreshNews').addEventListener('click', () => fetchNews(true));
  document.querySelectorAll('.rg-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.rg-chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      newsRegion = chip.dataset.region;
      renderNews();
    });
  });

  pushHistory('ai', GREETINGS[HOLO.char] || GREETINGS.core);
  setHoloStatus(idleStatus());
  logEvent('shell ready · stage 1 interface');
  toast('✨ MYRA v0.5 — smoother new faces, themes up top, and a living World Monitor. Try CORE / MALE / FEMALE and spin the Earth!', 6400);
});
