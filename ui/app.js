/* =========================================================
   MYRA — System Core UI (Stage 3, v0.8)
   Three particle characters (CORE / MALE / FEMALE). The
   great formation of ~34,000 dots happens ONCE when MYRA
   first opens; after that, switching character smoothly
   MORPHS the dots from one shape into the next, and power
   off simply fades her out. The figure floats (dots
   dissolve below the chest — no pedestal, no rings), lit
   by a scan-light sweeping bottom-to-top.
   Real AI chat is live: Gemini first, Groq as backup.
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
function setHoloStatus(txt) {
  const el = $('holoStatus');
  if (!el) return;
  if (!txt || /waking up|right here|online/i.test(txt)) {
    el.classList.add('hidden');
    el.textContent = '';
  } else {
    el.classList.remove('hidden');
    el.textContent = txt;
  }
}
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
const THEME_HEX = { normal: 0x22d3ee, friendly: 0x4ade80, hacker: 0xf87171, stonic: 0x3b82f6 };
const THEME_MAP_RGB = { normal: '94,234,212', friendly: '134,239,172', hacker: '252,165,165', stonic: '147,197,253' };
let themeName = localStorage.getItem('myra_theme') || 'stonic';
if (!THEME_HEX[themeName]) themeName = 'stonic';

/* =========================================================
   Particle figures — smooth silhouettes, grayscale light
   (theme color tints everything via material color)
   ========================================================= */
const N = 34000;
function savedChar() {
  const c = localStorage.getItem('myra_char');
  if (c === 'core' || c === 'male' || c === 'female' || c === 'custom') return c;
  const old = localStorage.getItem('stonic_gender');
  return old === 'male' ? 'male' : 'female';
}
const HOLO = {
  char: savedChar(),
  formedChar: null,
  power: true,
  speaking: false,
  speakBlend: 0,
  formT: 0,          // boot formation 0→1, happens once
  bootDone: false,
  morph: null,       // { fromPos, fromGray, t } while shape-shifting
  targetRotY: 0,
  autoRot: 0,
  dragging: false,
  accentMats: [],
  pMat: null,
  startMorph: null,  // set inside initHologram
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
    [1.48, .15, .13, .10], [1.56, .24, .20, .055], [1.66, .31, .26, .03],
    [1.76, .365, .30, .012], [1.88, .40, .33, 0], [2.00, .41, .335, 0],
    [2.10, .415, .345, .005], [2.22, .43, .355, -.008], [2.36, .425, .365, -.03],
    [2.48, .34, .30, -.05], [2.58, .21, .19, -.06], [2.66, .05, .04, -.065],
  ],
  male: [
    [1.48, .18, .155, .10], [1.56, .28, .235, .055], [1.66, .34, .28, .03],
    [1.76, .39, .32, .012], [1.88, .42, .35, 0], [2.00, .435, .355, 0],
    [2.10, .445, .365, .008], [2.22, .445, .37, -.012], [2.36, .44, .38, -.035],
    [2.48, .36, .315, -.05], [2.58, .22, .20, -.06], [2.66, .05, .04, -.065],
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
  arr.push({ x, y, z, gray: clamp(gray, 0.04, 1.6), headW });
}

/* Smooth sculpted face & head with nose, lips, chin and eye contours */
function sampleSmoothHead(out, female) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  for (let i = 0; i < 11500; i++) {
    const y = rand(1.48, 2.66);
    const [rx, rz, cz] = rowAt(rows, y);
    let th;
    if (Math.random() < 0.5) th = Math.PI / 2 + rand(-0.9, 0.9);
    else th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x = rx * Math.cos(th);
    let z = cz + rz * fr;
    // Enhanced facial features sculpting
    if (fr > 0.28) {
      const nose = g2(x, y, 0, 1.93, 0.045, 0.12, 0.055);
      const lips = g2(x, y, 0, 1.76, 0.07, 0.038, 0.024);
      const chin = g2(x, y, 0, 1.62, 0.075, 0.055, 0.032);
      const eyeL = g2(x, y, -0.14, 2.02, 0.065, 0.045, 0.022);
      const eyeR = g2(x, y, 0.14, 2.02, 0.065, 0.045, 0.022);
      z += (nose + lips + chin - eyeL - eyeR) * clamp((fr - 0.28) / 0.5, 0, 1);
    }
    const b = shade(x / (rx * rx), (y - 2.05) * 1.4, (z - cz) / (rz * rz));
    pushPt(out, x + rand(-.002, .002), y + rand(-.002, .002), z + rand(-.002, .002), b * 1.02, 1);
  }
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
    const y = rand(1.95, 2.67);
    const [rx, rz, cz] = rowAt(rows, Math.min(y, 2.65));
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

/* Female long hair as smooth sheets */
function sampleHairFemaleLong(out) {
  const prof = [[2.45, .47], [2.1, .55], [1.7, .585], [1.35, .555], [1.05, .48]];
  let placed = 0, guard = 0;
  while (placed < 6200 && guard++ < 6200 * 30) {
    const y = rand(1.05, 2.45);
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    if (fr > 0.38) continue;
    const r = profileAt(prof, y) * rand(0.985, 1.02);
    pushPt(out, r * Math.cos(th) + rand(-.006, .006), y, r * 0.92 * fr - 0.045 + rand(-.006, .006),
      shade(Math.cos(th), (y - 1.9) * 0.7, fr) * 0.62, clamp((y - 0.95) / 1.35, 0.18, 1));
    placed++;
  }
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

/* Sample both upper arms extending down from shoulders */
function sampleArms(out, female, n) {
  const armThick = female ? 0.13 : 0.16;
  const shoulderX = female ? 0.62 : 0.72;
  for (let i = 0; i < n; i++) {
    const s = Math.random() < 0.5 ? -1 : 1;
    const y = rand(0.40, 1.18);
    const t = clamp((1.18 - y) / 0.78, 0, 1);
    const cx = s * (shoulderX + t * 0.07);
    const cz = -0.01 + t * 0.03;
    const a = Math.random() * Math.PI * 2;
    const r = armThick * (1 - t * 0.2) * rand(0.9, 1.05);
    const x = cx + r * Math.cos(a);
    const z = cz + r * Math.sin(a);
    const b = shade(Math.cos(a), 0.1, Math.sin(a)) * (y < 0.52 ? (y - 0.35) * 4 : 0.85);
    pushPt(out, x + rand(-.004, .004), y + rand(-.004, .004), z + rand(-.004, .004), clamp(b, 0.08, 1.2), 0);
  }
}

/* Dots dissolving below the chest */
function sampleDissipation(out, n, chestRows) {
  const baseY = 0.46;
  const baseR = profileAt(chestRows, baseY);
  for (let i = 0; i < n; i++) {
    const drop = Math.pow(Math.random(), 1.7) * 0.62;
    const th = Math.random() * Math.PI * 2;
    const r = baseR * rand(0.5, 1.0) * (1 + drop * 1.1);
    const y = baseY - drop;
    const g = rand(0.05, 0.24) * (1 - drop * 1.15);
    pushPt(out, r * Math.cos(th) + rand(-.02, .02), y, r * 0.55 * Math.sin(th) + rand(-.02, .02), Math.max(g, 0.02), 0);
  }
}

function buildBustPoints(female) {
  const pts = [];
  sampleSmoothHead(pts, female);
  if (female) {
    sampleHairCap(pts, 5000, true);
    sampleHairFemaleLong(pts);
  } else {
    sampleHairCap(pts, 5200, false);
  }
  // Shortened natural neck (starts at 1.46 down to 1.18)
  const neckRows = female
    ? [[1.46, .135], [1.38, .145], [1.30, .18], [1.24, .28], [1.18, .38]]
    : [[1.46, .165], [1.38, .175], [1.30, .21], [1.24, .32], [1.18, .42]];
  sampleLoft(pts, 1400, neckRows, 0.88, 0.92, (y) => 0.55 * clamp((y - 1.18) / 0.28, 0, 1), null);

  // Bust / Torso
  const chestRows = female
    ? [[1.18, .52], [1.12, .76], [1.02, .88], [0.88, .90], [0.72, .84], [0.55, .76], [0.40, .66], [0.30, .58]]
    : [[1.18, .62], [1.12, .90], [1.02, 1.04], [0.88, 1.07], [0.72, .99], [0.55, .89], [0.40, .78], [0.30, .70]];
  const bustBump = female
    ? (x, y) => g2(x, y, .23, .72, .15, .13, .045) + g2(x, y, -.23, .72, .15, .13, .045)
    : null;
  sampleLoft(pts, 8500, chestRows, 0.55, 0.85, null, bustBump);

  // Both upper arms extending downwards
  sampleArms(pts, female, 3800);

  sampleDissipation(pts, 1800, chestRows);
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

function buildCustomPoints() {
  const pts = buildBustPoints(true);
  const CY = 1.95;
  for (let i = 0; i < 4000; i++) {
    const a = Math.random() * Math.PI * 2;
    const r = rand(0.55, 0.78);
    pushPt(pts, Math.cos(a) * r + rand(-0.02, 0.02), CY + rand(-0.06, 0.06), Math.sin(a) * r + rand(-0.02, 0.02), rand(0.95, 1.45), 0.5);
  }
  return pts;
}

function buildFigure(charType) {
  let pts;
  if (charType === 'core') pts = buildCorePoints();
  else if (charType === 'custom') pts = buildCustomPoints();
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

/* ----- Theme tint ----- */
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

/* ----- Three.js scene: floating figure, no pedestal ----- */
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
  camera.position.set(0, 1.7, 4.15);
  camera.lookAt(0, 1.48, 0);

  const world = new THREE.Group();
  scene.add(world);

  { // stars only — she floats in space
    const sp = [];
    for (let i = 0; i < 480; i++) sp.push(rand(-8, 8), rand(-0.6, 6.6), rand(-6, 2.5));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
    const m = new THREE.PointsMaterial({ color: 0x9fd8e8, size: 0.02, transparent: true, opacity: 0.45, depthWrite: false });
    m.userData.baseOp = 0.45; m.userData.lockColor = true;
    HOLO.accentMats.push(m);
    scene.add(new THREE.Points(g, m));
  }

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

  /* Shape-shift: snapshot where every dot is now, then flow to the new shape */
  HOLO.startMorph = (charType) => {
    if (!HOLO.bootDone) {   // still in the one-time boot formation — just retarget
      const b = buildFigure(charType);
      targets = b.targets; gray = b.gray; headW = b.headW; delay = b.delay;
      HOLO.formedChar = charType;
      applyTint();
      return;
    }
    const b = buildFigure(charType);
    HOLO.morph = {
      fromPos: geo.attributes.position.array.slice(),
      fromGray: gray.slice(),
      t: 0,
    };
    targets = b.targets; gray = b.gray; headW = b.headW; delay = b.delay;
    HOLO.formedChar = charType;
    applyTint();
  };

  let lastX = 0;
  const mouseParallax = { x: 0, y: 0, targetX: 0, targetY: 0 };
  canvas.addEventListener('pointerdown', (e) => { HOLO.dragging = true; lastX = e.clientX; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', (e) => {
    if (!HOLO.dragging) return;
    HOLO.targetRotY += (e.clientX - lastX) * 0.008;
    lastX = e.clientX;
  });
  const stopDrag = () => { HOLO.dragging = false; };
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);

  // Smooth 3D mouse parallax cursor tracking
  window.addEventListener('pointermove', (e) => {
    if (HOLO.dragging) return;
    const nx = (e.clientX / window.innerWidth) * 2 - 1;
    const ny = (e.clientY / window.innerHeight) * 2 - 1;
    mouseParallax.targetX = nx * 0.35;
    mouseParallax.targetY = ny * 0.18;
  });

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

    /* One-time boot formation; pauses while powered off */
    if (!HOLO.bootDone && HOLO.power) {
      HOLO.formT = Math.min(1, HOLO.formT + dt * 0.34);
      if (HOLO.formT >= 1) {
        HOLO.bootDone = true;
        setHoloStatus(idleStatus());
        logEvent('first formation complete');
      }
    }
    if (HOLO.morph && HOLO.power) {
      HOLO.morph.t += dt * 0.82;
      if (HOLO.morph.t >= 1.45) HOLO.morph = null;
    }
    const formT = HOLO.formT;
    const ff = HOLO.bootDone ? 1 : clamp((formT - 0.72) / 0.28, 0, 1); // life factor

    const sTarget = (HOLO.speaking && HOLO.power) ? 1 : 0;
    HOLO.speakBlend += (sTarget - HOLO.speakBlend) * 0.07;
    const sb = HOLO.speakBlend;

    // Smooth subtle breathing motion — NO violent bobbing/nodding on voice
    const nodA = (0.012 * Math.sin(t * 0.95)) * ff;
    const tiltA = (0.008 * Math.sin(t * 0.75 + 1)) * ff;
    const cosN = Math.cos(nodA), sinN = Math.sin(nodA);
    const cosT2 = Math.cos(tiltA), sinT2 = Math.sin(tiltA);
    const PIVOT_Y = 1.42;

    const scanCycle = t % 5.6;
    const scanY = scanCycle < 4.4 ? 0.05 + (scanCycle / 4.4) * 2.85 : -10;
    const scanOn = HOLO.power && formT > 0.25;
    const morph = HOLO.morph;

    const pos = geo.attributes.position.array;
    const col = geo.attributes.color.array;
    for (let i = 0; i < N; i++) {
      const i3 = i * 3;

      /* goal position: target + life shimmer + head motion */
      let gx = targets[i3], gy = targets[i3 + 1], gz = targets[i3 + 2];
      const ph = phase[i];
      const shim = Math.sin(t * 2.3 + ph) * (0.0036 + sb * 0.004 * headW[i]) * ff;
      const rl0 = Math.sqrt(gx * gx + gz * gz) || 1e-4;
      gx += (gx / rl0) * shim; gz += (gz / rl0) * shim;
      gy += Math.sin(t * 1.7 + ph * 1.3) * 0.0026 * ff;
      const w = headW[i] * ff;
      if (w > 0.01) {
        const cN = 1 + (cosN - 1) * w, sN = sinN * w;
        const dy = gy - PIVOT_Y;
        gy = PIVOT_Y + dy * cN - gz * sN;
        gz = dy * sN + gz * cN;
        const cT = 1 + (cosT2 - 1) * w, sT = sinT2 * w;
        const dy2 = gy - PIVOT_Y;
        const nx = gx * cT - dy2 * sT;
        gy = PIVOT_Y + gx * sT + dy2 * cT;
        gx = nx;
      }

      let x, y, z, brightScale;
      if (!HOLO.bootDone) {
        /* the one-time gathering: scattered cloud → shape */
        const p = clamp((formT - delay[i] * 0.45) / 0.55, 0, 1);
        const e = 1 - Math.pow(1 - p, 3);
        x = scatter[i3] + (gx - scatter[i3]) * e;
        y = scatter[i3 + 1] + (gy - scatter[i3 + 1]) * e;
        z = scatter[i3 + 2] + (gz - scatter[i3 + 2]) * e;
        const sw = (1 - e) * (1 - e) * orbit[i];
        if (sw > 0.001) {
          const c = Math.cos(sw), s2 = Math.sin(sw);
          const nx2 = x * c - z * s2, nz2 = x * s2 + z * c;
          x = nx2; z = nz2;
        }
        y += Math.sin(p * Math.PI) * (1 - p) * 0.12 * Math.sin(ph * 3 + t * 2);
        brightScale = 0.35 + 0.65 * e;
      } else if (morph) {
        /* shape-shift: dots disperse outward in a 3D cosmic burst then reassemble into new form */
        const p = clamp((morph.t - delay[i] * 0.35) / 0.65, 0, 1);
        const e = 1 - Math.pow(1 - p, 3);
        const burst = Math.sin(e * Math.PI) * 0.85;
        const dx = (morph.fromPos[i3] || 0.1);
        const dy = (morph.fromPos[i3 + 1] - 1.4);
        const dz = (morph.fromPos[i3 + 2] || 0.1);
        const dLen = Math.hypot(dx, dy, dz) || 1;
        const bx = (dx / dLen) * burst * (1 + ((i % 17) / 17) * 0.85);
        const by = (dy / dLen) * burst * (1 + ((i % 23) / 23) * 0.85);
        const bz = (dz / dLen) * burst * (1 + ((i % 19) / 19) * 0.85);

        x = morph.fromPos[i3] + (gx - morph.fromPos[i3]) * e + bx;
        y = morph.fromPos[i3 + 1] + (gy - morph.fromPos[i3 + 1]) * e + by;
        z = morph.fromPos[i3 + 2] + (gz - morph.fromPos[i3 + 2]) * e + bz;
        brightScale = 0.85 + 0.95 * Math.sin(e * Math.PI);
      } else {
        x = gx; y = gy; z = gz;
        brightScale = 1;
      }
      pos[i3] = x; pos[i3 + 1] = y; pos[i3 + 2] = z;

      let gVal = morph
        ? lerp(morph.fromGray[i], gray[i], clamp((morph.t - delay[i] * 0.35) / 0.65, 0, 1))
        : gray[i];
      let v = gVal * brightScale;
      if (scanOn) {
        const dyS = targets[i3 + 1] - scanY;
        v *= 1 + 0.95 * Math.exp(-(dyS * dyS) / 0.09) * ff;
      }
      col[i3] = v; col[i3 + 1] = v; col[i3 + 2] = v;
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;

    figure.position.y = Math.sin(t * 1.12) * 0.03;   // gentle floating
    const pulse = HOLO.formedChar === 'core' ? 1 + sb * 0.045 * Math.sin(t * 9) + 0.012 * Math.sin(t * 2.2) : 1;
    figure.scale.setScalar(pulse);

    // Smooth 3D mouse parallax tracking
    mouseParallax.x += (mouseParallax.targetX - mouseParallax.x) * 0.05;
    mouseParallax.y += (mouseParallax.targetY - mouseParallax.y) * 0.05;

    // Stays level facing forward, smoothly tracks mouse movement (no continuous 360 spinning)
    world.rotation.y += ((HOLO.targetRotY + mouseParallax.x) - world.rotation.y) * 0.08;
    world.rotation.x += (-mouseParallax.y - world.rotation.x) * 0.08;

    pMat.opacity += ((HOLO.power ? 0.88 : 0.03) - pMat.opacity) * 0.07;
    HOLO.accentMats.forEach((m) => {
      const bse = m.userData.baseOp !== undefined ? m.userData.baseOp : 0.9;
      m.opacity += ((HOLO.power ? bse : bse * 0.25) - m.opacity) * 0.08;
    });

    setHoloState(!HOLO.power ? 'OFFLINE' : (!HOLO.bootDone ? 'BOOTING…' : (sb > 0.35 ? 'SPEAKING' : 'IDLE // LISTENING')));
    renderer.render(scene, camera);
  })();
}

/* ----- Character switching (morph — no re-formation) ----- */
const IDLE_STATUS = {
  core: '⬢ Core online — listening',
  male: '🎩 JARVIS online. At your service, Sir.',
  female: "💗 I'm right here with you, dear… listening",
  custom: '✨ Custom companion online — listening',
};
function idleStatus() { return IDLE_STATUS[HOLO.char] || IDLE_STATUS.core; }

function syncCharUI() {
  document.querySelectorAll('[data-char]').forEach((el) => {
    el.classList.toggle('active', el.dataset.char === HOLO.char);
  });
  ['core', 'male', 'female', 'custom'].forEach((c) => {
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
  if (charType === HOLO.char && !HOLO.morph) return;
  HOLO.char = charType;
  localStorage.setItem('myra_char', charType);
  syncCharUI();
  if (HOLO.startMorph) HOLO.startMorph(charType);
  setHoloStatus('✨ Shifting into ' + charType.toUpperCase() + ' form…');
  setTimeout(() => { if (HOLO.power && !HOLO.speaking) setHoloStatus(idleStatus()); }, 1700);
  logEvent('character → ' + charType.toUpperCase() + ' (morph)');
}

/* =========================================================
   SAT-LINK dotted world map (fallback visual, own outlines)
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

/* ----- Attached live monitor (open-source worldmonitor.app) ----- */
const WM_URL = 'https://worldmonitor.app';
let wmMiniAttached = false, wmFullAttached = false, satLoaded = false;
function attachWorldMonitor() {
  if (!navigator.onLine) return;   // offline: canvas map + cached headlines carry the panel
  /* mini live preview in the left panel (scaled-down site) */
  if (!wmMiniAttached) {
    wmMiniAttached = true;
    const wrap = $('wmMiniWrap');
    if (wrap) {
      const ifr = document.createElement('iframe');
      ifr.className = 'wm-mini-frame';
      ifr.title = 'World Monitor — live preview';
      ifr.setAttribute('sandbox', 'allow-scripts');
      ifr.setAttribute('referrerpolicy', 'no-referrer');
      ifr.loading = 'lazy';
      ifr.src = WM_URL;
      wrap.appendChild(ifr);
      logEvent('world monitor: mini live preview attached');
    }
  }
}
function attachWorldMonitorFull() {
  if (wmFullAttached) return;
  wmFullAttached = true;
  const ifr = document.createElement('iframe');
  ifr.className = 'wm-live-frame';
  ifr.title = 'World Monitor — live dashboard';
  ifr.setAttribute('sandbox', 'allow-scripts allow-same-origin');
  ifr.setAttribute('referrerpolicy', 'no-referrer');
  ifr.loading = 'lazy';
  ifr.src = WM_URL;
  $('liveBox').appendChild(ifr);
  logEvent('world monitor: full live dashboard attached');
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
   ========================================================= */
const FEEDS = [
  { src: 'BBC', url: 'https://feeds.bbci.co.uk/news/world/rss.xml' },
  { src: 'Al Jazeera', url: 'https://www.aljazeera.com/xml/rss/all.xml' },
];
const OFFLINE_NEWS = [
  { title: "You're offline — live headlines will appear here the moment internet returns.", link: '#', src: 'OFFLINE', ts: Date.now() },
];
let newsItems = [], newsLive = false, newsRegion = 'all';

function timeAgo(ts) {
  const m = Math.floor((Date.now() - ts) / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return m + 'm ago';
  const h = Math.floor(m / 60);
  return h < 24 ? h + 'h ago' : Math.floor(h / 24) + 'd ago';
}
function setLiveBadge(state) {
  ['liveBadge', 'liveBadgeFull'].forEach((id) => {
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
  const items = newsItems.length ? newsItems : OFFLINE_NEWS;
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
  triggerOfficeAgent('research', true);
  if (!navigator.onLine) {
    setLiveBadge(loadNewsCache() ? 'cached' : 'off');
    renderNews();
    if (manual) toast('📡 You are offline — showing the last saved headlines.');
    logEvent('news: offline, cache shown');
    setTimeout(() => triggerOfficeAgent('research', false), 1500);
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
    if (manual) toast('📡 Could not reach the news service right now — showing ' + (had ? 'cached' : 'offline') + ' headlines.');
  } finally {
    setTimeout(() => triggerOfficeAgent('research', false), 2500);
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
    s += `<circle cx="${x1}" cy="${y1}" r="3" fill="${col}"/><circle cx="${x2}" cy="${y2}" r="2.6" fill="${col}"/>`;
  });
  svg.innerHTML = s;
}

/* =========================================================
   Full-screen windows navigation
   ========================================================= */
function setWorldTab(tab) {
  const tabs = { live: 'wmTabLive', globe: 'wmTabGlobe', sat: 'wmTabSat' };
  const boxes = { live: 'liveBox', globe: 'globeBox', sat: 'satBox' };
  Object.entries(tabs).forEach(([k, id]) => $(id).classList.toggle('active', k === tab));
  Object.entries(boxes).forEach(([k, id]) => $(id).classList.toggle('hidden', k !== tab));
  const worldOpen = !$('view-world').classList.contains('hidden');
  globeActive = tab === 'globe' && worldOpen;
  if (tab === 'live') attachWorldMonitorFull();
  if (tab === 'globe') initGlobe();
  if (tab === 'sat' && !satLoaded) {
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
    const tab = opt && opt.tab ? opt.tab : (navigator.onLine ? 'live' : 'globe');
    setWorldTab(tab);
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
function speechLangFor(text) {
  if (/[\u0980-\u09FF]/.test(text)) return 'bn-BD';
  if (/[\u0900-\u097F]/.test(text)) return 'hi-IN';
  return 'en-US';
}
let currentPlayingAudio = null;

function setWaveSpeaking(speaking) {
  const waveBox = $('holoWaveBox');
  if (waveBox) waveBox.classList.toggle('speaking-wave', Boolean(speaking));
}

let speechRunId = 0;
function characterVoiceGender() {
  return (HOLO.char === 'female' || HOLO.char === 'custom') ? 'female' : 'male';
}
function browserVoiceGender(voice) {
  const name = String((voice && voice.name) || '').toLowerCase();
  if (/female|zira|jenny|aria|ava|samantha|victoria|fiona|moira|veena|kalpana|swara|tanishaa|nabanita/.test(name)) return 'female';
  if (/male|david|guy|daniel|george|ravi|hemant|madhur|pradeep|bashkar/.test(name)) return 'male';
  return '';
}
function spokenMainText(raw, maxChars = 620) {
  let text = String(raw || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/^[#*>•\s-]+/gm, '')
    .replace(/\*{1,3}([^*]+)\*{1,3}/g, '$1')
    .replace(/[\u{10000}-\u{10FFFF}]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!text) return '';
  text = text.replace(/^(MYRA|Assistant|Answer|Reply)\s*:\s*/i, '');
  text = text.split(/\b(?:Sources?|References?|Background|Technical details?|Details?)\s*:\s*/i)[0].trim();
  const sentences = text.split(/(?<=[.!?।])\s+/).map((s) => s.trim()).filter(Boolean);
  const parts = sentences.length ? sentences : [text];
  if (parts.length > 1 && /^(sure|of course|certainly|okay|here(?:'s| is)(?: the answer)?)[.!।]?$/i.test(parts[0])) parts.shift();
  let out = '';
  for (const sentence of parts.slice(0, 4)) {
    const candidate = out ? `${out} ${sentence}` : sentence;
    if (candidate.length > maxChars && out) break;
    out = candidate;
    if (out.length >= maxChars) break;
  }
  if (out.length > maxChars) out = out.slice(0, maxChars).replace(/\s+\S*$/, '').trim() + '.';
  return out;
}

async function speakDemo(rawText) {
  const text = spokenMainText(rawText);
  if (!text) return;
  if (!HOLO.power) return;
  if (VOICE_MUTED) {
    setHoloStatus('🔇 Voice muted — tap 🔊 under the hologram to unmute');
    return;
  }

  stopSpeaking();
  const runId = ++speechRunId;
  pauseLiveListeningForSpeech();
  HOLO.speaking = true;
  setWaveSpeaking(true);
  updateMicWave(0);
  triggerOfficeAgent('voice', true);
  const lang = speechLangFor(text);
  setHoloStatus('🗣️ ' + (lang.startsWith('bn') ? 'মায়রা কথা বলছে…' : 'MYRA is speaking…'));

  let finished = false;
  const finish = () => {
    if (finished || runId !== speechRunId) return;
    finished = true;
    HOLO.speaking = false;
    setWaveSpeaking(false);
    setHoloStatus(idleStatus());
    currentPlayingAudio = null;
    updateMicWave(0);
    triggerOfficeAgent('voice', false);
    // Continuous live conversation: listen again after MYRA finishes.
    setTimeout(() => resumeLiveListening(), 350);
  };

  // 1. Backend neural voice. Send only the clean main answer, and let the
  // backend choose the Edge voice from the MYRA form (CORE/MALE male,
  // FEMALE female). A browser voice URI is not an Edge voice ID.
  try {
    const controller = 'AbortController' in window ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 12000) : null;
    const res = await fetch('/api/voice/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        character: HOLO.char,
        voice: 'auto',
        style: localStorage.getItem('myra_voice_style') || 'gentle',
      }),
      signal: controller ? controller.signal : undefined,
    });
    if (timeoutId) clearTimeout(timeoutId);
    if (runId !== speechRunId) return;

    if (res.ok && (res.headers.get('Content-Type') || '').includes('audio')) {
      const blob = await res.blob();
      if (runId !== speechRunId) return;
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      currentPlayingAudio = audio;
      audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        finish();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        finish();
      };
      await audio.play();
      return;
    }
  } catch (err) {
    // Fallback to browser SpeechSynthesis if offline
  }

  // 2. Safe Fallback to Browser Speech Synthesis
  setTimeout(finish, Math.min(800 + text.length * 55, 12000));
  if ('speechSynthesis' in window) {
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang;

      const savedPitch = parseFloat(localStorage.getItem('myra_voice_pitch'));
      const savedRate = parseFloat(localStorage.getItem('myra_voice_rate'));
      const gender = characterVoiceGender();
      const defaultPitch = gender === 'female' ? 1.16 : 0.84;
      u.pitch = !isNaN(savedPitch)
        ? (gender === 'male' ? Math.min(savedPitch, 0.98) : Math.max(savedPitch, 1.02))
        : defaultPitch;
      u.rate = !isNaN(savedRate) ? savedRate : 1.0;

      const voices = speechSynthesis.getVoices();
      const userVoiceUri = localStorage.getItem('myra_voice_uri') || 'auto';
      const sameGender = (v) => browserVoiceGender(v) === gender;
      const langPrefix = lang.slice(0, 2).toLowerCase();

      let match = null;
      if (userVoiceUri && userVoiceUri !== 'auto') {
        const chosen = voices.find((v) => v.voiceURI === userVoiceUri || v.name === userVoiceUri);
        if (chosen && sameGender(chosen)) match = chosen;
      }

      if (!match) {
        match = voices.find((v) => sameGender(v) && v.lang.toLowerCase().startsWith(langPrefix))
          || voices.find((v) => sameGender(v) && v.lang.toLowerCase().startsWith('en'))
          || voices.find((v) => sameGender(v));
      }

      if (match) u.voice = match;
      u.onend = finish;
      u.onerror = finish;
      speechSynthesis.speak(u);
    } catch (e) {
      finish();
    }
  }
}

function stopSpeaking() {
  speechRunId += 1;
  if (currentPlayingAudio) {
    try {
      currentPlayingAudio.pause();
      currentPlayingAudio.currentTime = 0;
    } catch (e) {}
    currentPlayingAudio = null;
  }
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  HOLO.speaking = false;
  setWaveSpeaking(false);
  setHoloStatus(idleStatus());
}

/* =========================================================
   Chat — real AI brain (Stage 3: Gemini → Groq fallback)
   ========================================================= */
const GREETINGS = {
  core: '⬢ Core online. I will use exactly the brain selected in the top BRAIN switcher — Auto picks the best configured brain. Ask me anything, or tap the mic and talk.',
  male: 'Good day, sir. 🎩 I am MYRA, at your service. I will use exactly the brain you select above, with a male voice in this form. How may I help?',
  female: "Hello, I'm MYRA — your personal desktop companion. 💗 I will use exactly the brain you select above, with a female voice in this form. Type below or tap the mic and talk to me!",
};
let chatContext = [];
let chatBusy = false;
const MAX_CHAT_CONTEXT = 14;

function currentPersonality() {
  const sel = $('personality');
  return (sel && sel.value) || localStorage.getItem('myra_personality') || 'Warm & friendly';
}
function setChatBusy(busy) {
  chatBusy = busy;
  const input = $('chatInput');
  const btn = $('sendBtn');
  if (input) input.disabled = busy;
  if (btn) {
    btn.disabled = busy;
    btn.textContent = busy ? '…' : '➤';
    btn.title = busy ? 'MYRA is thinking…' : 'Send';
  }
}
function finishAiBubble(bubble, text, meta) {
  bubble.textContent = '';
  bubble.appendChild(document.createTextNode(text));
  if (text) {
    const btn = document.createElement('button');
    btn.className = 'speak-btn';
    btn.textContent = '🔊';
    btn.title = 'Read aloud';
    btn.onclick = () => speakDemo(text);
    bubble.appendChild(btn);
  }
  if (meta) {
    const span = document.createElement('span');
    span.className = 'msg-meta';
    span.textContent = meta;
    bubble.appendChild(span);
  }
  $('chatLog').scrollTop = $('chatLog').scrollHeight;
}
function friendlyChatError(error, data) {
  if (location.protocol === 'file:') {
    return '👀 This one-file preview cannot run my real brain, because the Python backend is not running here. On your laptop, double-click start.bat, save your free keys in SETTING, and then talk to me there. Please never paste real keys into an online preview or chat.';
  }
  if (data && data.message) return data.message;
  if (error && error.name === 'AbortError') {
    return '⏳ The AI service took too long to answer. Please check the internet and try again.';
  }
  if (!navigator.onLine) {
    return '📡 You appear to be offline, so I cannot reach the selected cloud brain right now. Your local interface still works — reconnect and try again, or select Ollama Local if it is installed and running.';
  }
  return '⚠️ I could not reach MYRA\'s local backend. Please make sure start.bat (or run.py) is still running, then try again.';
}

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
async function sendChat(voiceText) {
  if (chatBusy) return;
  const input = $('chatInput');
  // Live speech is delivered directly to MYRA. It is never placed in the
  // typed-message box and it never needs a manual Send tap. A typed draft
  // already sitting in that box is left untouched during a voice turn.
  const directText = typeof voiceText === 'string' ? voiceText.trim() : '';
  const text = directText || input.value.trim();
  if (!text) return;
  if (!HOLO.power) {
    toast('⏻ System is off — press ACTIVATE first!');
    return;
  }

  addMsg(text, 'user');
  chatContext.push({ role: 'user', text });
  chatContext = chatContext.slice(-MAX_CHAT_CONTEXT);
  if (!directText) input.value = '';
  setChatBusy(true);
  setHoloStatus('🤔 MYRA is thinking…');
  setHoloState('THINKING…');

  const typing = addMsg('', 'ai', true);
  typing.innerHTML = '<span class="typing">•••</span>';
  const controller = 'AbortController' in window ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 65000) : null;

  try {
    if (location.protocol === 'file:') {
      const previewError = new Error('preview mode');
      previewError.code = 'preview_mode';
      throw previewError;
    }

    // Multimodal Vision capture: if camera or screen stream is live, capture frame
    let imageBase64 = null;
    if (VIS.cam || VIS.scr) {
      try {
        const video = $('vhVideo');
        if (video && video.videoWidth && video.videoHeight) {
          const snapCanvas = document.createElement('canvas');
          const maxDim = 800;
          const scale = Math.min(1, maxDim / Math.max(video.videoWidth, video.videoHeight));
          snapCanvas.width = Math.round(video.videoWidth * scale);
          snapCanvas.height = Math.round(video.videoHeight * scale);
          const ctx = snapCanvas.getContext('2d');
          ctx.drawImage(video, 0, 0, snapCanvas.width, snapCanvas.height);
          imageBase64 = snapCanvas.toDataURL('image/jpeg', 0.82);
        }
      } catch (err) {
        console.warn('Frame capture skipped', err);
      }
    }

    const payload = {
      messages: chatContext.slice(-MAX_CHAT_CONTEXT),
      character: HOLO.char,
      personality: currentPersonality(),
      assistant_name: localStorage.getItem('myra_name') || 'MYRA',
      owner_name: localStorage.getItem('myra_owner') || 'Saidul',
      provider: localStorage.getItem('myra_brain_provider') || 'auto',
      custom_prompt: HOLO.char === 'custom' ? (localStorage.getItem('myra_custom_persona_prompt') || '') : undefined,
      image: imageBase64 || undefined,
    };
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller ? controller.signal : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* handled below */ }

    if (!res.ok || !data || data.ok === false || !data.reply) {
      const err = new Error((data && data.message) || ('HTTP ' + res.status));
      err.data = data;
      err.status = res.status;
      throw err;
    }

    const reply = String(data.reply).trim();
    chatContext.push({ role: 'assistant', text: reply });
    chatContext = chatContext.slice(-MAX_CHAT_CONTEXT);
    const selectedBrain = payload.provider || 'auto';
    const meta = [
      data.provider_label ? 'via ' + data.provider_label : '',
      (selectedBrain !== 'auto' && data.provider && data.provider !== selectedBrain)
        ? 'selected brain: ' + selectedBrain
        : '',
      data.notice || '',
    ].filter(Boolean).join(' · ');
    finishAiBubble(typing, reply, meta);
    pushHistory('ai', reply);
    logEvent('chat answered by ' + (data.provider || 'AI'));
    if (data.memory_learned) {
      toast('🧠 মেমোরিতে সংরক্ষণ: ' + data.memory_learned, 5000);
      try { renderMemories(); } catch (e) {}
    }
    if (data.client_trigger) {
      if (data.action === 'open_camera') setVisual('cam', true);
      else if (data.action === 'open_screen') setVisual('scr', true);
      else if (data.action === 'shutdown_app') {
        toast('⏻ Closing MYRA Desktop... Good bye!', 4000);
        try { fetch('/api/system/shutdown', { method: 'POST' }); } catch (e) {}
        setTimeout(() => window.close(), 2200);
      }
    }
    if (data.notice) toast('ℹ️ ' + data.notice, 4200);
    speakDemo(reply);
  } catch (error) {
    const message = friendlyChatError(error, error.data);
    finishAiBubble(typing, message, '');
    pushHistory('ai', message);
    setHoloStatus('⚠️ Chat unavailable — check internet or API keys in SETTING');
    setHoloState(HOLO.power ? 'IDLE // LISTENING' : 'OFFLINE');
    logEvent('chat error: ' + ((error.data && error.data.error_code) || error.code || error.name || 'unknown'));
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    setChatBusy(false);
    const nextInput = $('chatInput');
    if (nextInput) nextInput.focus();
    setTimeout(() => resumeLiveListening(), 450);
  }
}
function newChat() {
  if (chatBusy) {
    toast('⏳ Please wait for the current reply before starting a new conversation.');
    return;
  }
  const log = $('chatLog');
  log.innerHTML = '';
  const ready = document.createElement('div');
  ready.className = 'sys-ready';
  ready.textContent = '✦ NEW CONVERSATION ✦';
  log.appendChild(ready);
  chatContext = [];
  addMsg(GREETINGS[HOLO.char] || GREETINGS.core, 'ai');
  logEvent('new conversation started');
}

/* =========================================================
   Power / TERMINATE — fade out/in (formation is once-only)
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
    setHoloStatus('⏻ System offline — press ACTIVATE to bring MYRA back');
    toast('⏻ MYRA powered down. Press ACTIVATE to wake her.');
    logEvent('power OFF (terminated)');
  } else {
    setHoloStatus(HOLO.bootDone ? idleStatus() : '✨ MYRA is waking up…');
    toast('🤖 MYRA online!');
    logEvent('power ON');
  }
}

/* =========================================================
   Stage controls: mic toggle + voice mute (Stage 5)
   Smart silence detection: automatically sends chat when user stops speaking.
   ========================================================= */
let MIC_ARMED = false;
let speechRecognizer = null;
let speechSilenceTimer = null;
let liveVoiceTranscript = '';
let liveVoiceMode = null; // 'browser' | 'backend'
let liveVoiceStatusCache = null;
let liveVoiceStatusAt = 0;
const BACKEND_MIC = {
  stream: null, recorder: null, chunks: [], ctx: null, analyser: null,
  timer: null, startedAt: 0, lastLoudAt: 0, heard: false,
  discard: false, restart: false, busy: false, starting: false,
};

function paintMicButton() {
  const btn = $('stageMicBtn');
  if (!btn) return;
  btn.classList.toggle('on', MIC_ARMED);
  btn.classList.toggle('mic-listening', MIC_ARMED);
  btn.textContent = MIC_ARMED ? '🔴' : '🎤';
  updateMicWave(MIC_ARMED ? 1 : 0);
}

function backendLiveVoiceReady(status) {
  const engines = (status && status.engines) || {};
  return Boolean(engines.faster_whisper_python_package && engines.faster_whisper_model_installed);
}

function paintLiveVoiceStatus(status) {
  const el = $('liveVoiceStatus');
  const btn = $('installVoiceModelBtn');
  if (!el) return;
  if (!status) {
    el.textContent = '⚠️ Could not check the live-voice engine. Make sure MYRA backend is running, then reopen this page.';
    if (btn) btn.classList.add('hidden');
    return;
  }
  const engines = status.engines || {};
  if (backendLiveVoiceReady(status)) {
    el.textContent = '✅ Live voice is ready on this PC. Tap the mic under the hologram, speak, and pause — MYRA will write your words and answer.';
    if (btn) btn.classList.add('hidden');
  } else if (!engines.faster_whisper_python_package) {
    el.textContent = '⚠️ The faster-whisper voice package is missing. Close and reopen MYRA once so its one-time setup can finish installing voice packages, then return here.';
    if (btn) btn.classList.add('hidden');
  } else {
    el.textContent = '⬇ One-time setup needed: download the Base speech model (~145 MB). MYRA never downloads it silently.';
    if (btn) btn.classList.remove('hidden');
  }
}

async function fetchLiveVoiceStatus(force = false) {
  if (!force && liveVoiceStatusCache && (Date.now() - liveVoiceStatusAt) < 15000) return liveVoiceStatusCache;
  if (location.protocol === 'file:') return null;
  try {
    const res = await fetch('/api/v1/voice/status');
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'voice status failed');
    liveVoiceStatusCache = data.voice || null;
    liveVoiceStatusAt = Date.now();
    paintLiveVoiceStatus(liveVoiceStatusCache);
    return liveVoiceStatusCache;
  } catch (e) {
    paintLiveVoiceStatus(null);
    return null;
  }
}

function promptLiveVoiceSetup(status) {
  MIC_ARMED = false;
  liveVoiceMode = null;
  paintMicButton();
  paintLiveVoiceStatus(status);
  setHoloState('VOICE SETUP');
  setHoloStatus('🎤 Live voice needs its one-time speech model setup first.');
  toast('🎤 Live voice setup: open CHARACTER → VOICE STUDIO and tap “INSTALL LIVE-VOICE MODEL” once (~145 MB). After that, the mic will hear you here in the desktop window.', 7000);
  try { openView('character'); } catch (e) {}
}

function cleanupBackendMicStream() {
  if (BACKEND_MIC.timer) { clearInterval(BACKEND_MIC.timer); BACKEND_MIC.timer = null; }
  if (BACKEND_MIC.stream) {
    BACKEND_MIC.stream.getTracks().forEach((t) => { try { t.stop(); } catch (e) {} });
    BACKEND_MIC.stream = null;
  }
  if (BACKEND_MIC.ctx) {
    try { BACKEND_MIC.ctx.close(); } catch (e) {}
    BACKEND_MIC.ctx = null;
  }
  BACKEND_MIC.analyser = null;
  BACKEND_MIC.recorder = null;
  BACKEND_MIC.heard = false;
}

function stopBackendMic(discard = false, restart = false) {
  BACKEND_MIC.discard = Boolean(discard);
  BACKEND_MIC.restart = Boolean(restart);
  const rec = BACKEND_MIC.recorder;
  if (rec && rec.state !== 'inactive') {
    try { rec.stop(); return; } catch (e) {}
  }
  cleanupBackendMicStream();
}

function pauseLiveListeningForSpeech() {
  liveVoiceTranscript = '';
  if (BACKEND_MIC.recorder) stopBackendMic(true, false);
  if (speechRecognizer && liveVoiceMode === 'browser') {
    try { speechRecognizer.stop(); } catch (e) {}
  }
}

function resumeLiveListening() {
  if (!MIC_ARMED || !HOLO.power || HOLO.speaking || chatBusy || BACKEND_MIC.busy) return;
  if (liveVoiceMode === 'backend') {
    startBackendLiveVoice();
  } else if (speechRecognizer) {
    try { speechRecognizer.start(); } catch (e) {}
    setHoloState('LISTENING…');
    setHoloStatus('🎤 Listening… I am right here.');
    updateMicWave(1);
  }
}

function audioBufferToWavBase64(buffer) {
  const targetRate = 16000;
  const channels = Math.max(1, buffer.numberOfChannels);
  const mono = new Float32Array(buffer.length);
  for (let ch = 0; ch < channels; ch += 1) {
    const data = buffer.getChannelData(ch);
    for (let i = 0; i < data.length; i += 1) mono[i] += data[i] / channels;
  }
  const ratio = buffer.sampleRate / targetRate;
  const outLen = Math.max(1, Math.floor(mono.length / ratio));
  const wav = new ArrayBuffer(44 + outLen * 2);
  const view = new DataView(wav);
  const writeText = (offset, value) => { for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i)); };
  writeText(0, 'RIFF'); view.setUint32(4, 36 + outLen * 2, true); writeText(8, 'WAVEfmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, targetRate, true); view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); writeText(36, 'data');
  view.setUint32(40, outLen * 2, true);
  for (let i = 0; i < outLen; i += 1) {
    const sample = Math.max(-1, Math.min(1, mono[Math.floor(i * ratio)] || 0));
    view.setInt16(44 + i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  const bytes = new Uint8Array(wav);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

async function blobToWavBase64(blob) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) throw new Error('Audio conversion is not available in this window.');
  const ctx = new AudioCtx();
  try {
    const decoded = await ctx.decodeAudioData((await blob.arrayBuffer()).slice(0));
    return audioBufferToWavBase64(decoded);
  } finally {
    try { await ctx.close(); } catch (e) {}
  }
}

async function transcribeBackendBlob(blob) {
  BACKEND_MIC.busy = true;
  setHoloState('HEARING…');
  setHoloStatus('✍️ Writing what you said…');
  try {
    const audioBase64 = await blobToWavBase64(blob);
    const savedSpeechLang = localStorage.getItem('myra_speech_lang') || '';
    const res = await fetch('/api/v1/voice/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_base64: audioBase64,
        language: savedSpeechLang ? savedSpeechLang.slice(0, 2).toLowerCase() : 'auto',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || 'MYRA could not transcribe that audio.');
    const text = String((data.transcript && data.transcript.text) || '').trim();
    BACKEND_MIC.busy = false;
    if (!MIC_ARMED) return;
    if (!text) {
      setHoloStatus('🎤 I did not catch words that time — listening again…');
      setTimeout(() => resumeLiveListening(), 300);
      return;
    }
    setHoloState('THINKING…');
    setHoloStatus('👂 ' + (isBengaliText(text) ? 'শুনেছি: “' : 'Heard: “') + text + '”');
    logEvent('live voice heard: ' + text.slice(0, 120));
    // Bypass the typed-message box completely: the finished utterance is
    // already a submitted voice turn, not a draft waiting for Send.
    sendChat(text);
  } catch (err) {
    BACKEND_MIC.busy = false;
    const message = String(err.message || err);
    logEvent('live voice transcription failed: ' + message);
    if (/faster-whisper model|not installed/i.test(message)) {
      promptLiveVoiceSetup(await fetchLiveVoiceStatus(true));
      return;
    }
    MIC_ARMED = false;
    liveVoiceMode = null;
    paintMicButton();
    setHoloState('VOICE ERROR');
    setHoloStatus('⚠️ Live voice stopped — check the message and tap the mic again.');
    toast('🎤 Live voice error: ' + message, 6500);
  }
}

async function startBackendLiveVoice() {
  if (BACKEND_MIC.starting) return true;
  BACKEND_MIC.starting = true;
  try {
    return await startBackendLiveVoiceOnce();
  } finally {
    BACKEND_MIC.starting = false;
  }
}

async function startBackendLiveVoiceOnce() {
  if (BACKEND_MIC.busy || (BACKEND_MIC.recorder && BACKEND_MIC.recorder.state !== 'inactive')) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    MIC_ARMED = false; liveVoiceMode = null; paintMicButton();
    toast('🎤 This window cannot access microphone recording. You can still type below.', 6000);
    return false;
  }
  const status = await fetchLiveVoiceStatus();
  if (!backendLiveVoiceReady(status)) {
    promptLiveVoiceSetup(status);
    return false;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    MIC_ARMED = false; liveVoiceMode = null; paintMicButton();
    setHoloState('MIC BLOCKED');
    setHoloStatus('⚠️ Microphone permission was blocked.');
    toast('🎤 MYRA could not open the microphone. Allow microphone access for MYRA in Windows Settings → Privacy & security → Microphone, then tap the mic again.', 8000);
    return false;
  }
  if (!MIC_ARMED || HOLO.speaking || chatBusy) {
    stream.getTracks().forEach((t) => t.stop());
    return false;
  }

  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', '']
    .find((item) => !item || (window.MediaRecorder && MediaRecorder.isTypeSupported(item))) || '';
  const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  BACKEND_MIC.stream = stream;
  BACKEND_MIC.recorder = recorder;
  BACKEND_MIC.chunks = [];
  BACKEND_MIC.discard = false;
  BACKEND_MIC.restart = false;
  BACKEND_MIC.heard = false;
  BACKEND_MIC.startedAt = Date.now();
  BACKEND_MIC.lastLoudAt = Date.now();
  recorder.ondataavailable = (event) => { if (event.data && event.data.size) BACKEND_MIC.chunks.push(event.data); };
  recorder.onstop = async () => {
    const chunks = BACKEND_MIC.chunks.slice();
    const discard = BACKEND_MIC.discard;
    const restart = BACKEND_MIC.restart;
    BACKEND_MIC.chunks = [];
    cleanupBackendMicStream();
    paintMicButton();
    if (!MIC_ARMED) return;
    if (discard) {
      if (restart) setTimeout(() => resumeLiveListening(), 250);
      return;
    }
    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    if (blob.size < 1200) {
      setTimeout(() => resumeLiveListening(), 250);
      return;
    }
    await transcribeBackendBlob(blob);
  };

  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      const ctx = new AudioCtx();
      if (ctx.state === 'suspended') { try { ctx.resume(); } catch (e) {} }
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      BACKEND_MIC.ctx = ctx;
      BACKEND_MIC.analyser = analyser;
      const samples = new Uint8Array(analyser.fftSize);
      BACKEND_MIC.timer = setInterval(() => {
        if (!BACKEND_MIC.analyser || !BACKEND_MIC.recorder) return;
        const now = Date.now();
        if (BACKEND_MIC.ctx && BACKEND_MIC.ctx.state !== 'running') {
          // If Chromium keeps the analyser suspended, do not lose the
          // utterance: transcribe a bounded segment anyway.
          if (now - BACKEND_MIC.startedAt > 7000) stopBackendMic(false, false);
          return;
        }
        BACKEND_MIC.analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (let i = 0; i < samples.length; i += 1) { const v = (samples[i] - 128) / 128; sum += v * v; }
        const rms = Math.sqrt(sum / samples.length);
        updateMicWave(1 + Math.min(3, rms * 10));
        if (rms > 0.025) { BACKEND_MIC.heard = true; BACKEND_MIC.lastLoudAt = now; }
        if (BACKEND_MIC.heard && now - BACKEND_MIC.lastLoudAt > 900) stopBackendMic(false, false);
        else if (now - BACKEND_MIC.startedAt > 15000) stopBackendMic(!BACKEND_MIC.heard, !BACKEND_MIC.heard);
      }, 120);
    }
  } catch (e) {
    BACKEND_MIC.timer = setTimeout(() => stopBackendMic(false, false), 7000);
  }

  recorder.start(250);
  liveVoiceMode = 'backend';
  setHoloState('LISTENING…');
  setHoloStatus('🎤 Listening live… speak, then pause for a moment.');
  paintMicButton();
  return true;
}

function updateMicWave(level) {
  const meter = $('micWaveMeter');
  if (!meter) return;
  const isListening = MIC_ARMED && !HOLO.speaking;
  meter.classList.toggle('mic-listening', isListening);
  const bars = meter.querySelectorAll('.meter-bar');
  if (bars && bars.length) {
    bars.forEach((b, idx) => {
      if (isListening) {
        const h = Math.min(15, Math.max(3, (level || 1) * (4 + (idx % 3) * 3)));
        b.style.height = `${h}px`;
      } else {
        b.style.height = '4px';
      }
    });
  }
}

function setupSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) return null;
  const rec = new SpeechRec();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = localStorage.getItem('myra_speech_lang') || 'bn-BD';

  rec.onresult = (event) => {
    clearTimeout(speechSilenceTimer);
    let interim = '';
    let final = '';
    let hasFinal = false;
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        final += event.results[i][0].transcript;
        hasFinal = true;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    const txt = (final || interim).trim();
    if (txt) {
      // Keep the live transcript in memory and on the hologram status only;
      // never copy it into the typed-message send box.
      liveVoiceTranscript = txt;
      setHoloStatus('👂 ' + (isBengaliText(txt) ? 'শুনছি: "' : 'Listening: "') + txt + '"');
      setHoloState('LISTENING…');
      updateMicWave(2.5);

      // Fast automatic delivery on silence (650ms if final, 1300ms interim).
      const silenceDelay = hasFinal ? 650 : 1300;
      speechSilenceTimer = setTimeout(() => {
        const val = liveVoiceTranscript.trim();
        if (val && !chatBusy) {
          liveVoiceTranscript = '';
          setHoloStatus(isBengaliText(val) ? 'মাইরা শুনেছে, উত্তর দিচ্ছে এক্ষুনি…' : 'MYRA has heard you, replying now…');
          sendChat(val);
          try { rec.stop(); } catch (err) {}
          updateMicWave(0);
        }
      }, silenceDelay);
    }
  };

  rec.onspeechend = () => {
    const val = liveVoiceTranscript.trim();
    if (val && !chatBusy) {
      clearTimeout(speechSilenceTimer);
      speechSilenceTimer = setTimeout(() => {
        const spoken = liveVoiceTranscript.trim();
        if (spoken && !chatBusy) {
          liveVoiceTranscript = '';
          setHoloStatus(isBengaliText(spoken) ? 'মাইরা শুনেছে, উত্তর দিচ্ছে এক্ষুনি…' : 'MYRA has heard you, replying now…');
          sendChat(spoken);
          try { rec.stop(); } catch (err) {}
          updateMicWave(0);
        }
      }, 500);
    }
  };

  rec.onerror = (e) => {
    logEvent('speech error: ' + e.error);
    if (MIC_ARMED && ['not-allowed', 'service-not-allowed', 'audio-capture', 'network'].includes(e.error)) {
      // WebView2/Chromium shells often expose the recognizer object but no
      // working speech service. Switch to MYRA's own mic→backend hearing.
      liveVoiceTranscript = '';
      liveVoiceMode = 'backend';
      setHoloStatus('🎤 Switching to MYRA live-voice engine…');
      setTimeout(() => startBackendLiveVoice(), 300);
      return;
    }
    if (e.error !== 'no-speech') updateMicWave(0);
  };

  rec.onend = () => {
    const val = liveVoiceTranscript.trim();
    if (val && !chatBusy && !HOLO.speaking) {
      clearTimeout(speechSilenceTimer);
      liveVoiceTranscript = '';
      setHoloStatus(isBengaliText(val) ? 'মাইরা শুনেছে, উত্তর দিচ্ছে এক্ষুনি…' : 'MYRA has heard you, replying now…');
      sendChat(val);
      updateMicWave(0);
    } else if (MIC_ARMED && !HOLO.speaking && liveVoiceMode !== 'backend') {
      try { rec.start(); } catch (err) {}
      updateMicWave(1);
    } else {
      updateMicWave(0);
    }
  };

  return rec;
}

async function setMic(on, silent) {
  MIC_ARMED = Boolean(on);
  paintMicButton();

  if (!on) {
    clearTimeout(speechSilenceTimer);
    liveVoiceTranscript = '';
    if (speechRecognizer) { try { speechRecognizer.stop(); } catch (err) {} }
    stopBackendMic(true, false);
    liveVoiceMode = null;
    updateMicWave(0);
    setHoloState(HOLO.power ? 'IDLE // ONLINE' : 'OFFLINE');
    setHoloStatus(idleStatus());
    if (!silent) toast('🎤 Mic off.');
    logEvent('mic stopped');
    return;
  }

  if (!HOLO.power) {
    MIC_ARMED = false;
    paintMicButton();
    toast('⏻ System is off — press ACTIVATE first!');
    return;
  }

  // Prefer instant browser recognition in a normal browser. Inside MYRA's
  // own desktop window (/?shell=desktop, WebView2), Web Speech recognition
  // is commonly absent/dead, so go straight to MYRA's local pipeline:
  // microphone → backend transcription → chat → character-matched TTS.
  const inDesktopShell = new URLSearchParams(location.search).get('shell') === 'desktop';
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec && !inDesktopShell) {
    if (!speechRecognizer) speechRecognizer = setupSpeechRecognition();
    if (speechRecognizer) {
      liveVoiceMode = 'browser';
      setHoloState('LISTENING…');
      setHoloStatus('🎤 Listening live… speak naturally, I will show your words and answer.');
      try { speechRecognizer.start(); } catch (err) { liveVoiceMode = 'backend'; }
      updateMicWave(1);
      if (liveVoiceMode === 'browser') {
        if (!silent) toast('🎤 Live voice active — speak, pause, and I will answer.');
        logEvent('mic armed (browser speech recognition)');
        return;
      }
    }
  }

  liveVoiceMode = 'backend';
  const ok = await startBackendLiveVoice();
  if (ok) {
    if (!silent) toast('🎤 Live voice active — speak, pause for a moment, and I will answer.');
    logEvent('mic armed (MYRA backend live voice)');
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
   Visual Hub — Camera and Screen Share (Stage 9)
   ========================================================= */
const VIS = { cam: false, scr: false };
let currentVisualStream = null;

async function setVisual(kind, on) {
  const vVideo = $('vhVideo');
  if (currentVisualStream) {
    currentVisualStream.getTracks().forEach((t) => t.stop());
    currentVisualStream = null;
  }
  if (vVideo) {
    vVideo.srcObject = null;
    vVideo.classList.add('hidden');
  }

  VIS.cam = false;
  VIS.scr = false;

  if (on) {
    try {
      let stream = null;
      if (kind === 'cam') {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 } } });
        VIS.cam = true;
        toast('📷 Camera active — MYRA is viewing the feed.');
      } else if (kind === 'scr') {
        stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        VIS.scr = true;
        toast('🖥️ Screen share active.');
        stream.getVideoTracks()[0].onended = () => setVisual('scr', false);
      }
      if (stream && vVideo) {
        currentVisualStream = stream;
        vVideo.srcObject = stream;
        vVideo.classList.remove('hidden');
      }
    } catch (err) {
      toast('⚠️ Could not open ' + (kind === 'cam' ? 'camera' : 'screen') + ': ' + err.message);
      VIS[kind] = false;
    }
  }

  $('camIndicator').classList.toggle('hidden', !(VIS.cam || VIS.scr));
  $('camChip').textContent = 'CAM · ' + (VIS.cam ? 'ON' : 'OFF');
  $('camChip').classList.toggle('on', VIS.cam);
  $('scrChip').textContent = 'SCREEN · ' + (VIS.scr ? 'ON' : 'OFF');
  $('scrChip').classList.toggle('on', VIS.scr);
  $('vhCamBtn').classList.toggle('on', VIS.cam);
  $('vhScrBtn').classList.toggle('on', VIS.scr);
  logEvent('visual hub: ' + kind + ' ' + (VIS[kind] ? 'LIVE' : 'OFF'));
}

/* =========================================================
   Memory window — SQLite local storage (Stage 4)
   ========================================================= */
let LOCAL_MEMORIES = [];
async function loadMemories() {
  if (location.protocol === 'file:') {
    try { return JSON.parse(localStorage.getItem('myra_memories_demo') || '[]'); }
    catch (e) { return []; }
  }
  try {
    const res = await fetch('/api/memory');
    const data = await res.json();
    return data.memories || [];
  } catch (e) {
    return [];
  }
}

async function renderMemories() {
  const list = $('memoryList');
  if (!list) return;
  LOCAL_MEMORIES = await loadMemories();
  list.innerHTML = '';
  LOCAL_MEMORIES.forEach((m) => {
    const li = document.createElement('li');
    const span = document.createElement('span');
    const text = typeof m === 'object' ? m.text : m;
    const cat = (typeof m === 'object' && m.category && m.category !== 'general') ? `[${m.category}] ` : '';
    const date = (typeof m === 'object' && m.created_at) ? ` · ${String(m.created_at).slice(0, 16)}` : '';
    const memId = typeof m === 'object' ? m.id : null;
    span.textContent = '🧠 ' + cat + text + date;
    const del = document.createElement('button');
    del.textContent = '🗑️';
    del.title = 'Forget this';
    del.onclick = async () => {
      if (memId && location.protocol !== 'file:') {
        await fetch('/api/memory/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: memId }),
        });
      } else {
        localStorage.removeItem('myra_memories_demo');
      }
      renderMemories();
      toast('🗑️ Memory removed.');
    };
    li.append(span, del);
    list.appendChild(li);
  });
  if ($('memoryEmpty')) $('memoryEmpty').classList.toggle('hidden', LOCAL_MEMORIES.length > 0);
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
   Deep Space Floating Starfield (Stonic AI Aesthetic)
   ========================================================= */
function initStarfield() {
  const canvas = $('starfieldCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let w = (canvas.width = window.innerWidth);
  let h = (canvas.height = window.innerHeight);

  const numStars = 180;
  const stars = [];
  for (let i = 0; i < numStars; i++) {
    stars.push({
      x: Math.random() * w,
      y: Math.random() * h,
      z: Math.random() * 1.6 + 0.3,
      r: Math.random() * 1.5 + 0.4,
      alpha: Math.random() * 0.8 + 0.2,
      fadeSpeed: (Math.random() * 0.008 + 0.004) * (Math.random() < 0.5 ? 1 : -1),
    });
  }

  window.addEventListener('resize', () => {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  });

  let mouseX = 0, mouseY = 0;
  window.addEventListener('pointermove', (e) => {
    mouseX = (e.clientX - w / 2) * 0.015;
    mouseY = (e.clientY - h / 2) * 0.015;
  });

  function drawStarfield() {
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < numStars; i++) {
      const s = stars[i];
      s.x += s.z * 0.12;
      s.alpha += s.fadeSpeed;
      if (s.alpha > 0.95 || s.alpha < 0.15) s.fadeSpeed = -s.fadeSpeed;
      if (s.x > w) s.x = 0;
      if (s.x < 0) s.x = w;

      const px = s.x - mouseX * s.z;
      const py = s.y - mouseY * s.z;

      ctx.beginPath();
      ctx.arc(px, py, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(180, 215, 255, ${Math.max(0, Math.min(1, s.alpha))})`;
      if (s.r > 1.2) {
        ctx.shadowBlur = 6;
        ctx.shadowColor = '#60a5fa';
      } else {
        ctx.shadowBlur = 0;
      }
      ctx.fill();
    }
    requestAnimationFrame(drawStarfield);
  }
  drawStarfield();
}

/* =========================================================
   Visual Hub: Sensors & Cyber Agent Office (Cartoonist 3-Cabin)
   ========================================================= */
function initVisualHubTabs() {
  const sensorBtn = $('vhSensorTabBtn');
  const officeBtn = $('vhOfficeTabBtn');
  const sensorView = $('vhSensorView');
  const officeView = $('vhOfficeView');

  if (sensorBtn && officeBtn && sensorView && officeView) {
    sensorBtn.addEventListener('click', () => {
      sensorBtn.classList.add('active');
      officeBtn.classList.remove('active');
      sensorView.classList.remove('hidden');
      officeView.classList.add('hidden');
    });
    officeBtn.addEventListener('click', () => {
      officeBtn.classList.add('active');
      sensorBtn.classList.remove('active');
      officeView.classList.remove('hidden');
      sensorView.classList.add('hidden');
    });
  }
}

function triggerOfficeAgent(cabinType, active) {
  const toggle = $('officeAnimToggle');
  if (toggle && !toggle.checked) return;
  const cabinMap = {
    research: { box: $('cabinResearch'), badge: $('badgeResearch'), text: 'ANALYZING' },
    coder: { box: $('cabinCoder'), badge: $('badgeCoder'), text: 'EXECUTING' },
    voice: { box: $('cabinVoice'), badge: $('badgeVoice'), text: 'COMMUNICATING' },
  };
  const target = cabinMap[cabinType];
  if (!target || !target.box) return;
  if (active) {
    target.box.classList.add('active-worker');
    if (target.badge) target.badge.textContent = target.text;
  } else {
    target.box.classList.remove('active-worker');
    if (target.badge) target.badge.textContent = cabinType === 'voice' ? 'READY' : 'STANDBY';
  }
}

/* =========================================================
   Direct Brain Switcher (Gemini / Groq / Auto)
   ========================================================= */
function setupBrainSwitcher() {
  const select = $('quickBrainSelect');
  if (!select) return;
  const saved = localStorage.getItem('myra_brain_provider') || 'auto';
  select.value = saved;
  select.addEventListener('change', () => {
    localStorage.setItem('myra_brain_provider', select.value);
    toast('⚡ AI Brain set to: ' + select.options[select.selectedIndex].text);
    logEvent('brain provider → ' + select.value);
  });
}

/* =========================================================
   Custom Persona Creator & Names
   ========================================================= */
function initCustomPersona() {
  const saveBtn = $('saveCustomPersonaBtn');
  const nameInput = $('customPersonaName');
  const promptInput = $('customPersonaPrompt');
  const customTitle = $('customCardTitle');

  const savedName = localStorage.getItem('myra_custom_persona_name');
  const savedPrompt = localStorage.getItem('myra_custom_persona_prompt');

  if (nameInput && savedName) nameInput.value = savedName;
  if (promptInput && savedPrompt) promptInput.value = savedPrompt;
  if (customTitle && savedName) customTitle.textContent = savedName.toUpperCase();

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const name = (nameInput.value || 'Custom Companion').trim();
      const prompt = (promptInput.value || '').trim();
      localStorage.setItem('myra_custom_persona_name', name);
      localStorage.setItem('myra_custom_persona_prompt', prompt);
      if (customTitle) customTitle.textContent = name.toUpperCase();
      toast('✅ Custom Persona saved! Shifting into custom form…');
      setChar('custom');
    });
  }

  const ownerInput = $('ownerNameChar');
  if (ownerInput) {
    ownerInput.value = localStorage.getItem('myra_owner') || 'Saidul';
  }
}

/* =========================================================
   Cinematic First-Run Onboarding Modal & Language Selection
   ========================================================= */
const ONBOARD_GREETINGS = {
  'bn-BD': "হ্যালো! আমি মায়রা, আপনার পার্সোনাল ডেস্কটপ এআই কম্প্যানিয়ন। আমি আপনার সাথে আছি।",
  'en-US': "Hello! I am MYRA, your personal desktop AI companion. I have been waiting for you.",
  'hi-IN': "नमस्ते! मैं मायरा हूँ, आपकी पर्सनल डेस्कटॉप साथी। मैं आपके साथ हूँ।",
  'es-ES': "¡Hola! Soy MYRA, tu asistente personal de escritorio. Estoy lista para ayudarte.",
  'ar-SA': "مرحباً! أنا مايرا، رفيقتك الذكية لسطح المكتب. أنا هنا معك.",
  'fr-FR': "Bonjour! Je suis MYRA, votre assistante personnelle de bureau.",
  'de-DE': "Hallo! Ich bin MYRA, Ihre persönliche Desktop-Assistentin.",
  'ja-JP': "こんにちは！私はMYRA、あなたのパーソナルAIコンパニオンです。",
};

function checkOnboarding() {
  const onboarded = localStorage.getItem('myra_onboarded');
  const modal = $('onboardModal');
  if (!modal) return;

  const langSelect = $('onboardLangSelect');
  const heroVoiceText = $('onboardHeroVoiceText');
  const styleSelect = $('onboardVoiceStyle');
  const closeBtn = $('onboardCloseBtn');
  const skipBtn = $('onboardSkipBtn');

  // Load saved preferences if any
  const currentLang = localStorage.getItem('myra_lang') || 'bn-BD';
  if (langSelect) langSelect.value = currentLang;
  if (styleSelect) styleSelect.value = localStorage.getItem('myra_voice_style') || 'gentle';

  const updateGreetingText = (lang) => {
    if (heroVoiceText) {
      heroVoiceText.textContent = `"${ONBOARD_GREETINGS[lang] || ONBOARD_GREETINGS['bn-BD']}"`;
    }
  };
  updateGreetingText(currentLang);

  if (langSelect) {
    langSelect.addEventListener('change', () => {
      const selected = langSelect.value;
      localStorage.setItem('myra_lang', selected);
      localStorage.setItem('myra_speech_lang', selected);
      if (speechRecognizer) speechRecognizer.lang = selected;
      updateGreetingText(selected);
    });
  }

  if (styleSelect) {
    styleSelect.addEventListener('change', () => {
      localStorage.setItem('myra_voice_style', styleSelect.value);
    });
  }

  const dismissModal = () => {
    modal.classList.add('hidden');
    localStorage.setItem('myra_onboarded', 'true');
  };

  if (closeBtn) closeBtn.addEventListener('click', dismissModal);
  if (skipBtn) {
    skipBtn.addEventListener('click', () => {
      dismissModal();
      toast('⚡ Started in Offline Desktop Mode! You can add keys anytime in SETTINGS.');
    });
  }

  if (!onboarded) {
    modal.classList.remove('hidden');
    const ownerName = localStorage.getItem('myra_owner') || 'Saidul';
    const userNameInput = $('onboardUserName');
    if (userNameInput) userNameInput.value = ownerName;

    const voiceTest = $('onboardVoiceTestBtn');
    if (voiceTest) {
      voiceTest.addEventListener('click', () => {
        const selLang = (langSelect && langSelect.value) || 'bn-BD';
        const txt = ONBOARD_GREETINGS[selLang] || ONBOARD_GREETINGS['bn-BD'];
        speakDemo(txt);
      });
    }

    const startBtn = $('onboardStartBtn');
    if (startBtn) {
      startBtn.addEventListener('click', async () => {
        const uName = ($('onboardUserName').value || 'Saidul').trim();
        const aName = ($('onboardAiName').value || 'MYRA').trim();
        const persona = $('onboardPersonaSelect').value || 'female';
        const apiKey = ($('onboardApiKey').value || '').trim();
        const lang = (langSelect && langSelect.value) || 'bn-BD';

        localStorage.setItem('myra_owner', uName);
        localStorage.setItem('myra_name', aName);
        localStorage.setItem('myra_lang', lang);
        localStorage.setItem('myra_speech_lang', lang);
        if (speechRecognizer) speechRecognizer.lang = lang;
        localStorage.setItem('myra_onboarded', 'true');

        if (apiKey) {
          try {
            const keyRes = await fetch('/api/settings/keys', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ gemini: apiKey }),
            });
            const keyData = await keyRes.json();
            const keyStatus = keyData.keys || keyData;
            if (!keyRes.ok || !(keyStatus.gemini && keyStatus.gemini.set)) {
              throw new Error((keyData && (keyData.message || keyData.error)) || 'Key was not confirmed saved');
            }
            toast('🔑 Gemini key confirmed saved locally.');
          } catch (e) {
            toast('⚠️ The onboarding key could not be confirmed saved. Please save it again in SETTING. (' + e.message + ')', 5600);
          }
        }

        setChar(persona);
        modal.classList.add('hidden');
        toast(`✨ Welcome ${uName}! MYRA is online.`);
        speakDemo(ONBOARD_GREETINGS[lang] || `Hello ${uName}! I am happy to meet you.`);
      });
    }
  }
}

/* =========================================================
   Mobile Phone Link QR Modal
   ========================================================= */
function initMobileLink() {
  const btn = $('mobileLinkBtn');
  const modal = $('mobileLinkModal');
  const closeBtn = $('mobileLinkCloseBtn');
  const doneBtn = $('mobileLinkDoneBtn');
  const copyBtn = $('copyMobileUrlBtn');
  const urlDisplay = $('mobileUrlDisplay');
  const qrBox = $('phoneQrBox');

  if (!btn || !modal) return;

  const closeModal = () => modal.classList.add('hidden');
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (doneBtn) doneBtn.addEventListener('click', closeModal);

  btn.addEventListener('click', async () => {
    modal.classList.remove('hidden');
    if (qrBox) qrBox.innerHTML = '';
    if (urlDisplay) urlDisplay.textContent = 'Scanning network address…';
    try {
      const res = await fetch('/api/system/network-info');
      const data = await res.json();
      const mobileUrl = data.mobile_url || `http://${location.hostname}:${location.port || 8765}`;
      if (urlDisplay) urlDisplay.textContent = mobileUrl;
      if (qrBox) {
        if (typeof QRCode !== 'undefined') {
          new QRCode(qrBox, {
            text: mobileUrl,
            width: 170,
            height: 170,
            colorDark: '#020b18',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.M,
          });
        } else {
          qrBox.innerHTML = `<a href="${mobileUrl}" target="_blank" style="color:var(--accent); font-weight:700;">${mobileUrl}</a>`;
        }
      }
    } catch (e) {
      const fallbackUrl = `http://${location.hostname}:${location.port || 8765}`;
      if (urlDisplay) urlDisplay.textContent = fallbackUrl;
    }
  });

  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const url = urlDisplay && urlDisplay.textContent;
      if (url && navigator.clipboard) {
        navigator.clipboard.writeText(url);
        toast('📋 Phone link copied to clipboard!');
      }
    });
  }
}

/* =========================================================
   Event wiring
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  document.body.dataset.theme = themeName;
  logEvent('MYRA shell boot · theme=' + themeName + ' · char=' + HOLO.char);

  initStarfield();
  initHologram();
  initMap();
  initVisualHubTabs();
  setupBrainSwitcher();
  initCustomPersona();
  initMobileLink();
  checkOnboarding();
  syncCharUI();

  const voiceStyleSel = $('voiceStyleSelect');
  if (voiceStyleSel) {
    voiceStyleSel.value = localStorage.getItem('myra_voice_style') || 'gentle';
    voiceStyleSel.addEventListener('change', () => {
      localStorage.setItem('myra_voice_style', voiceStyleSel.value);
      toast('🌸 Speech style updated!');
    });
  }
  renderMemories();
  loadNewsCache();
  renderNews();
  setTimeout(() => { fetchNews(false); attachWorldMonitor(); }, 900);
  setInterval(() => fetchNews(false), 10 * 60 * 1000);
  window.addEventListener('online', () => { fetchNews(false); attachWorldMonitor(); logEvent('network online'); });
  window.addEventListener('offline', () => { setLiveBadge('cached'); logEvent('network offline — cache mode'); });
  setTimeout(drawWires, 350);
  let rT = null;
  window.addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(drawWires, 160); });

  /* Assistant + owner names */
  const savedName = localStorage.getItem('myra_name');
  const npNameEl = $('npName');
  if (savedName) {
    if (npNameEl) npNameEl.textContent = savedName.toUpperCase();
    if ($('nameInput')) $('nameInput').value = savedName;
  } else if ($('nameInput')) {
    $('nameInput').value = 'MYRA';
  }
  $('nameSave')?.addEventListener('click', () => {
    const v = $('nameInput')?.value.trim() || 'MYRA';
    localStorage.setItem('myra_name', v);
    if (npNameEl) npNameEl.textContent = v.toUpperCase();
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
      ? '👁️ Awareness ON — in Stages 5 & 9 MYRA will proactively notice things, always within the permissions you grant.'
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
    toast(themeName === 'stonic' ? '⚡ Stonic AI Cyber Azure theme.' : themeName === 'normal' ? '⬛ Cyber cyan theme.' : themeName === 'friendly' ? '💚 Friendly green theme.' : '🔴 Hacker red theme.');
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
  $('stageMicBtn').addEventListener('click', () => {
    if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
    setMic(!MIC_ARMED);
  });
  $('muteBtn').addEventListener('click', () => setMute(!VOICE_MUTED));

  /* Character switch */
  document.querySelectorAll('[data-char]').forEach((el) => {
    el.addEventListener('click', () => {
      if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
      const c = el.dataset.char;
      setChar(c);
      toast(c === 'core' ? '⬢ CORE form — pure AI light.'
        : c === 'male' ? '♂ MALE form — your JARVIS-style assistant.'
        : c === 'female' ? '♀ FEMALE form — your companion. 💗'
        : '✨ CUSTOM form — tailored personal companion.');
    });
  });
  ['core', 'male', 'female', 'custom'].forEach((c) => {
    const card = $('card-' + c);
    if (card) {
      card.addEventListener('click', () => {
        if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
        setChar(c);
      });
    }
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
  $('wmTabLive').addEventListener('click', () => setWorldTab('live'));
  $('wmTabGlobe').addEventListener('click', () => setWorldTab('globe'));
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

  /* Agent Mode — MYRA Core bounded multi-step engine.
     The old /api/agent/run path only matched a few phrases and often just
     opened a browser. This panel now uses /api/v1/agent/tasks: MYRA plans
     one registered skill at a time, observes the result, shows each step,
     and pauses for APPROVE/DENY before change/control actions. */
  let currentAgentTask = null;
  let currentAgentTaskId = localStorage.getItem('myra_agent_task_id') || '';
  let agentPollTimer = null;
  let agentCreateBusy = false;
  let lastAgentTerminalKey = '';
  let windowsEmergencyStopped = false;

  const agentFetch = async (path, options = {}) => {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || ('Agent request failed (' + res.status + ')'));
    return data;
  };
  const paintAgentEmergencyBtn = () => {
    const btn = $('agentEmergencyBtn');
    if (!btn) return;
    btn.textContent = windowsEmergencyStopped ? '↩ RESET STOP' : '🛑 EMERGENCY';
    btn.title = windowsEmergencyStopped
      ? 'Allow MYRA Windows PC control again'
      : 'Immediately stop the agent task and block Windows PC control';
  };
  const refreshWindowsEmergency = async () => {
    if (location.protocol === 'file:') return;
    try {
      const data = await agentFetch('/api/v1/windows/status');
      windowsEmergencyStopped = Boolean(data.windows && data.windows.emergency_stopped);
      paintAgentEmergencyBtn();
    } catch (e) {}
  };
  const agentIsActive = (task) => Boolean(task && ['queued', 'running', 'paused', 'awaiting_confirmation'].includes(task.status));
  const agentShort = (value, limit = 320) => {
    const text = typeof value === 'string' ? value : JSON.stringify(value || '');
    return text.length > limit ? text.slice(0, limit - 1) + '…' : text;
  };
  const agentResultSummary = (result) => {
    if (!result || typeof result !== 'object') return agentShort(result, 240);
    if (result.error) return String(result.error);
    const bits = [];
    ['message', 'summary', 'text', 'title', 'url', 'path', 'filename', 'name'].forEach((key) => {
      if (result[key]) bits.push(String(result[key]));
    });
    if (Array.isArray(result.files)) bits.push(result.files.length + ' file(s) found');
    if (Array.isArray(result.sources)) bits.push(result.sources.length + ' source(s) checked');
    if (Array.isArray(result.windows)) bits.push(result.windows.length + ' window(s) observed');
    if (typeof result.verified === 'boolean') bits.push(result.verified ? 'verified ✓' : 'not verified');
    return agentShort(bits.join(' · ') || JSON.stringify(result), 340);
  };
  const renderAgentTask = (task) => {
    if (!task) return;
    currentAgentTask = task;
    currentAgentTaskId = task.id || currentAgentTaskId;
    if (currentAgentTaskId) localStorage.setItem('myra_agent_task_id', currentAgentTaskId);
    const log = $('agentLog');
    const icons = { queued: '⏳', running: '⚙️', paused: '⏸', awaiting_confirmation: '⚠️', completed: '✅', failed: '❌', cancelled: '■' };
    const steps = Array.isArray(task.steps) ? task.steps : [];
    const lines = [
      `${icons[task.status] || '🤖'} AGENT ${String(task.status || 'unknown').replace(/_/g, ' ').toUpperCase()} · ${steps.length}/${task.max_steps || 10} steps · brain: ${task.provider || 'auto'}`,
      `Goal: ${task.goal || ''}`,
      '',
    ];
    if (!steps.length && agentIsActive(task) && task.status !== 'awaiting_confirmation') {
      lines.push('🧠 Planning the first safe step…');
    }
    steps.forEach((step) => {
      const mark = step.status === 'completed' ? '✅' : (step.status === 'denied' ? '🚫' : '⚠️');
      lines.push(`${step.index || ''}. ${mark} ${step.skill_id || 'skill'} — ${step.status || ''}`);
      const summary = agentResultSummary(step.result);
      if (summary) lines.push('   ' + summary);
    });
    if (task.pending) {
      lines.push('', '⚠️ Waiting for your approval before the next action. Nothing has been executed yet for this step.');
    }
    if (task.error) lines.push('', '❌ ' + task.error);
    if (task.final_summary) lines.push('', '🏁 Result:', String(task.final_summary));
    if (log) {
      log.textContent = lines.join('\n');
      log.scrollTop = log.scrollHeight;
    }

    const approval = $('agentApproval');
    const approvalText = $('agentApprovalText');
    if (approval && approvalText) {
      if (task.status === 'awaiting_confirmation' && task.pending) {
        approval.classList.remove('hidden');
        approvalText.textContent = `${task.pending.skill_id || 'Next action'} (${task.pending.risk || 'risk'} risk). ${task.pending.description || ''} Details: ${agentShort(task.pending.arguments || {}, 260)}`;
      } else {
        approval.classList.add('hidden');
      }
    }
    const active = agentIsActive(task);
    if ($('agentBtn')) $('agentBtn').disabled = active || agentCreateBusy;
    if ($('agentPauseBtn')) $('agentPauseBtn').disabled = !(task.status === 'running' || task.status === 'queued');
    if ($('agentResumeBtn')) $('agentResumeBtn').disabled = task.status !== 'paused';
    if ($('agentCancelBtn')) $('agentCancelBtn').disabled = !active;

    triggerOfficeAgent('coder', task.status === 'running' || task.status === 'queued');
    if (['completed', 'failed', 'cancelled'].includes(task.status)) {
      const terminalKey = task.id + ':' + task.status + ':' + (task.updated_at || '');
      if (lastAgentTerminalKey !== terminalKey) {
        lastAgentTerminalKey = terminalKey;
        if (task.status === 'completed') {
          toast('✅ Agent task completed — see the step log.');
          if (task.final_summary) speakDemo(task.final_summary);
        } else if (task.status === 'failed') {
          toast('❌ Agent stopped safely: ' + (task.error || 'task failed'), 6500);
        }
        logEvent('agent task ' + task.status);
      }
    }
  };
  const startAgentPolling = () => {
    if (agentPollTimer || !currentAgentTaskId) return;
    agentPollTimer = setInterval(async () => {
      try {
        const data = await agentFetch('/api/v1/agent/tasks/' + encodeURIComponent(currentAgentTaskId));
        renderAgentTask(data.task);
        if (!agentIsActive(data.task)) {
          clearInterval(agentPollTimer);
          agentPollTimer = null;
        }
      } catch (err) {
        clearInterval(agentPollTimer);
        agentPollTimer = null;
        if ($('agentLog')) $('agentLog').textContent += '\n⚠️ Could not refresh agent status: ' + err.message;
      }
    }, 900);
  };
  const runAgentTask = async () => {
    const input = $('agentInput');
    const goal = input ? input.value.trim() : '';
    if (!goal || agentCreateBusy) return;
    if (agentIsActive(currentAgentTask)) {
      toast('🤖 An agent task is already active. Pause or STOP it before starting another.');
      return;
    }
    if (location.protocol === 'file:') {
      $('agentLog').textContent = '👀 This one-file preview cannot run Agent Mode because MYRA’s local backend is not running here. Use Agent Mode inside the MYRA desktop app on your laptop.';
      return;
    }
    agentCreateBusy = true;
    if ($('agentBtn')) $('agentBtn').disabled = true;
    $('agentLog').textContent = `🚀 Starting step-by-step Agent task:\n“${goal}”\n\nMYRA will observe → plan → act → verify, and ask before change/control actions.`;
    triggerOfficeAgent('coder', true);
    try {
      const data = await agentFetch('/api/v1/agent/tasks', {
        method: 'POST',
        body: JSON.stringify({
          goal,
          max_steps: 10,
          approval_mode: 'ask',
          provider: localStorage.getItem('myra_brain_provider') || 'auto',
          start: true,
        }),
      });
      input.value = '';
      renderAgentTask(data.task);
      startAgentPolling();
      logEvent('core agent task started');
    } catch (err) {
      $('agentLog').textContent += '\n\n❌ Agent could not start: ' + err.message;
      toast('❌ Agent could not start: ' + err.message, 6500);
      triggerOfficeAgent('coder', false);
    } finally {
      agentCreateBusy = false;
      if ($('agentBtn')) $('agentBtn').disabled = agentIsActive(currentAgentTask);
    }
  };
  const agentAction = async (action) => {
    if (!currentAgentTaskId) { toast('🤖 No agent task yet. Start a task first.'); return; }
    try {
      const data = await agentFetch('/api/v1/agent/tasks/' + encodeURIComponent(currentAgentTaskId) + '/' + action, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      renderAgentTask(data.task);
      if (agentIsActive(data.task)) startAgentPolling();
    } catch (err) {
      toast('❌ Agent ' + action + ' failed: ' + err.message, 6000);
    }
  };
  $('agentBtn')?.addEventListener('click', runAgentTask);
  $('agentInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') runAgentTask(); });
  $('agentApproveBtn')?.addEventListener('click', () => agentAction('approve'));
  $('agentDenyBtn')?.addEventListener('click', () => agentAction('deny'));
  $('agentPauseBtn')?.addEventListener('click', () => agentAction('pause'));
  $('agentResumeBtn')?.addEventListener('click', () => agentAction('resume'));
  $('agentCancelBtn')?.addEventListener('click', () => agentAction('cancel'));
  $('agentEmergencyBtn')?.addEventListener('click', async () => {
    stopSpeaking();
    if (windowsEmergencyStopped) {
      try {
        await agentFetch('/api/v1/windows/action', {
          method: 'POST',
          body: JSON.stringify({ action: 'reset_emergency_stop', arguments: {}, confirmed: true }),
        });
        windowsEmergencyStopped = false;
        paintAgentEmergencyBtn();
        toast('↩ Emergency stop reset. Agent Mode may request Windows PC control again — it will still ask for approval.', 6500);
        logEvent('windows emergency stop reset');
      } catch (err) {
        toast('❌ Could not reset emergency stop: ' + err.message, 6500);
      }
      return;
    }
    try {
      await agentFetch('/api/v1/windows/emergency-stop', { method: 'POST', body: JSON.stringify({}) });
      windowsEmergencyStopped = true;
      paintAgentEmergencyBtn();
    } catch (e) {}
    if (currentAgentTaskId && agentIsActive(currentAgentTask)) await agentAction('cancel');
    toast('🛑 Emergency stop active: Windows PC control is blocked and the current agent task was stopped. Tap RESET STOP when you want to allow it again.', 8000);
    logEvent('agent emergency stop');
  });
  refreshWindowsEmergency();
  if (currentAgentTaskId && location.protocol !== 'file:') {
    agentFetch('/api/v1/agent/tasks/' + encodeURIComponent(currentAgentTaskId))
      .then((data) => { renderAgentTask(data.task); if (agentIsActive(data.task)) startAgentPolling(); })
      .catch(() => {});
  }

  /* Agent Quick Action Chips */
  document.querySelectorAll('.action-chip[data-act]').forEach((chip) => {
    chip.addEventListener('click', () => {
      $('agentInput').value = chip.dataset.act;
      runAgentTask();
    });
  });

  /* Notes & Reminders Hub */
  $('tabNotesBtn')?.addEventListener('click', () => {
    $('tabNotesBtn').classList.add('active');
    $('tabRemindersBtn')?.classList.remove('active');
    $('notesSubPanel')?.classList.remove('hidden');
    $('remindersSubPanel')?.classList.add('hidden');
  });
  $('tabRemindersBtn')?.addEventListener('click', () => {
    $('tabRemindersBtn').classList.add('active');
    $('tabNotesBtn')?.classList.remove('active');
    $('notesSubPanel')?.classList.add('hidden');
    $('remindersSubPanel')?.classList.remove('hidden');
    loadReminders();
  });

  const loadReminders = async () => {
    if (location.protocol === 'file:') return;
    try {
      const res = await fetch('/api/reminders');
      const data = await res.json();
      const listEl = $('remindersList');
      if (!listEl) return;
      if (!data.reminders || !data.reminders.length) {
        listEl.innerHTML = '<div class="empty-note">No active reminders. Add one above ☝️</div>';
        return;
      }
      listEl.innerHTML = '';
      data.reminders.forEach((r) => {
        const item = document.createElement('div');
        item.className = 'reminder-item';
        item.innerHTML = `
          <div>
            <div class="reminder-text">⏰ ${r.text}</div>
            <div class="reminder-due">Due: ${r.due_str}</div>
          </div>
          <button class="icon-btn" style="color:var(--danger);" title="Delete reminder">✕</button>
        `;
        item.querySelector('button').onclick = async () => {
          await fetch('/api/reminders/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: r.id }),
          });
          loadReminders();
          toast('🗑️ Reminder deleted');
        };
        listEl.appendChild(item);
      });
    } catch (e) {}
  };

  $('remAdd')?.addEventListener('click', async () => {
    const text = $('remInput').value.trim();
    if (!text) return;
    try {
      const res = await fetch('/api/reminders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, minutes: 10 }),
      });
      $('remInput').value = '';
      loadReminders();
      toast('⏰ Reminder scheduled: ' + text);
    } catch (e) {}
  });

  const checkDueReminders = async () => {
    if (location.protocol === 'file:') return;
    try {
      const res = await fetch('/api/reminders/due');
      const data = await res.json();
      if (data.due && data.due.length) {
        data.due.forEach((r) => {
          const alertMsg = speechLangFor(r.text).startsWith('bn')
            ? `রিমাইন্ডার এলার্ট: ${r.text}`
            : `Reminder Alert: ${r.text}`;
          toast('⏰ ' + alertMsg, 8000);
          speakDemo(alertMsg);
          addMsg(alertMsg, 'ai');
        });
        loadReminders();
      }
    } catch (e) {}
  };
  setInterval(checkDueReminders, 12000);

  /* Visual Hub Snapshot */
  $('vhSnapBtn')?.addEventListener('click', () => {
    const video = $('vhVideo');
    if (!VIS.cam && !VIS.scr) {
      toast('📷 Turn on camera or screen share first to take a snapshot.');
      return;
    }
    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      document.querySelector('[data-mode="voice"]').click();
      $('chatInput').value = "Here is what I'm looking at right now (Snapshot captured).";
      $('chatInput').focus();
      toast('📸 Snapshot captured and attached to chat!');
      logEvent('visual snapshot captured');
    } catch (e) {
      toast('⚠️ Snapshot error: ' + e.message);
    }
  });

  /* Notes (Stage 7) */
  const loadNotes = async () => {
    if (location.protocol === 'file:') return;
    try {
      const res = await fetch('/api/notes');
      const data = await res.json();
      const list = $('notesList');
      list.innerHTML = '';
      (data.notes || []).forEach((n) => {
        const li = document.createElement('li');
        const span = document.createElement('span');
        span.textContent = '📌 ' + (n.title ? n.title + ': ' : '') + n.content;
        const del = document.createElement('button');
        del.textContent = '🗑️';
        del.onclick = async () => {
          await fetch('/api/notes/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: n.id }),
          });
          loadNotes();
          toast('🗑️ Note deleted');
        };
        li.append(span, del);
        list.appendChild(li);
      });
    } catch (e) {}
  };
  loadNotes();

  const addNote = async () => {
    const v = $('noteInput').value.trim();
    if (!v) return;
    if (location.protocol !== 'file:') {
      try {
        await fetch('/api/notes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: v }),
        });
        $('noteInput').value = '';
        loadNotes();
        toast('📌 Note saved to SQLite database');
        return;
      } catch (e) {}
    }
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

  /* Memory window (Stage 4) */
  const addMemory = async () => {
    const v = $('memoryInput').value.trim();
    if (!v) return;
    if (location.protocol !== 'file:') {
      try {
        await fetch('/api/memory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: v }),
        });
        $('memoryInput').value = '';
        renderMemories();
        toast('🧠 Saved permanently into MYRA\'s SQLite memory on this laptop!');
        logEvent('memory saved to SQLite');
        return;
      } catch (e) {}
    }
    const arr = await loadMemories();
    arr.unshift(v);
    localStorage.setItem('myra_memories_demo', JSON.stringify(arr));
    $('memoryInput').value = '';
    renderMemories();
  };
  $('memoryAdd').addEventListener('click', addMemory);
  $('memoryInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') addMemory(); });
  $('clearMemory').addEventListener('click', async () => {
    if (location.protocol !== 'file:') {
      await fetch('/api/memory/clear', { method: 'POST' });
    } else {
      localStorage.removeItem('myra_memories_demo');
    }
    renderMemories();
    toast('🗑️ All memories erased.');
  });

  /* API keys (Stage 2) — the backend saves them into .env on this laptop.
     The browser only receives masked status, never a full saved key. */
  const inPreviewFile = location.protocol === 'file:';
  const paintKeyStatus = (statusId, removeId, info) => {
    const badge = $(statusId);
    const btn = $(removeId);
    if (!badge || !btn) return;
    if (info && info.set) {
      badge.textContent = '✅ Saved (' + info.masked + ')';
      badge.classList.add('set');
      btn.classList.remove('hidden');
    } else {
      badge.textContent = '○ Not saved yet';
      badge.classList.remove('set');
      btn.classList.add('hidden');
    }
  };
  const refreshKeyStatus = async () => {
    if (inPreviewFile) {
      $('keysPreviewNote').classList.remove('hidden');
      paintKeyStatus('geminiKeyStatus', 'removeGemini', null);
      paintKeyStatus('groqKeyStatus', 'removeGroq', null);
      return;
    }
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      paintKeyStatus('geminiKeyStatus', 'removeGemini', data.gemini);
      paintKeyStatus('groqKeyStatus', 'removeGroq', data.groq);
      paintKeyStatus('openrouterKeyStatus', 'removeOpenrouter', data.openrouter);
      paintKeyStatus('openaiKeyStatus', 'removeOpenai', data.openai);
      paintKeyStatus('deepseekKeyStatus', 'removeDeepseek', data.deepseek);
      paintKeyStatus('ollamaKeyStatus', 'removeOllama', data.ollama);
      if (data.gemini && data.gemini.model && $('geminiModelSelect')) {
        $('geminiModelSelect').value = data.gemini.model;
      }
      if (data.groq && data.groq.model && $('groqModelSelect')) {
        $('groqModelSelect').value = data.groq.model;
      }
      if (data.ollama && data.ollama.model && $('ollamaModel')) {
        $('ollamaModel').value = data.ollama.model;
      }
    } catch (e) {
      const g = $('geminiKeyStatus');
      const q = $('groqKeyStatus');
      if (g) g.textContent = 'server offline';
      if (q) q.textContent = 'server offline';
    }
  };
  refreshKeyStatus();
  const settingsChip = document.querySelector('[data-view="setting"]');
  if (settingsChip) settingsChip.addEventListener('click', refreshKeyStatus);

  // Direct brain switcher synchronization
  const brainSelect = $('quickBrainSelect');
  if (brainSelect) {
    const saved = localStorage.getItem('myra_brain_provider') || 'auto';
    brainSelect.value = saved;
    brainSelect.addEventListener('change', () => {
      localStorage.setItem('myra_brain_provider', brainSelect.value);
      toast('🧠 AI Brain switched to: ' + brainSelect.options[brainSelect.selectedIndex].text, 4000);
    });
  }

  $('saveKeys').addEventListener('click', async () => {
    const gemini = $('geminiKey') ? $('geminiKey').value.trim() : '';
    const groq = $('groqKey') ? $('groqKey').value.trim() : '';
    const openrouter = $('openrouterKey') ? $('openrouterKey').value.trim() : '';
    const openai = $('openaiKey') ? $('openaiKey').value.trim() : '';
    const deepseek = $('deepseekKey') ? $('deepseekKey').value.trim() : '';
    const ollama = $('ollamaModel') ? $('ollamaModel').value.trim() : '';

    if (inPreviewFile) {
      if ($('geminiKey')) $('geminiKey').value = '';
      if ($('groqKey')) $('groqKey').value = '';
      toast('👀 Preview mode — run python run.py to save real keys locally.', 4500);
      return;
    }

    const body = {};
    if (gemini) body.gemini_key = gemini;
    if (groq) body.groq_key = groq;
    if (openrouter) body.openrouter_key = openrouter;
    if (openai) body.openai_key = openai;
    if (deepseek) body.deepseek_key = deepseek;
    if (ollama) body.ollama_model = ollama;
    if ($('geminiModelSelect')) body.gemini_model = $('geminiModelSelect').value;
    if ($('groqModelSelect')) body.groq_model = $('groqModelSelect').value;

    if (!Object.keys(body).length) {
      toast('🔑 Paste or enter at least one AI key or model to save.');
      return;
    }

    try {
      const res = await fetch('/api/settings/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
      if ($('geminiKey')) $('geminiKey').value = '';
      if ($('groqKey')) $('groqKey').value = '';
      if ($('openrouterKey')) $('openrouterKey').value = '';
      if ($('openaiKey')) $('openaiKey').value = '';
      if ($('deepseekKey')) $('deepseekKey').value = '';
      refreshKeyStatus();
      toast('🔑 AI Brain keys saved safely on your laptop (.env). You can chat with MYRA now!', 5500);
      logEvent('API keys saved');
    } catch (e) {
      toast('❌ Could not save (' + e.message + ')', 5000);
    }
  });

  const removeKey = async (which) => {
    if (inPreviewFile) return;
    try {
      const res = await fetch('/api/settings/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ which }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || ('HTTP ' + res.status));
      refreshKeyStatus();
      toast('🗑️ ' + which.toUpperCase() + ' key removed from this device.');
      logEvent(which + ' key removed');
    } catch (e) {
      toast('❌ Could not remove (' + e.message + ')', 4600);
    }
  };
  $('removeGemini')?.addEventListener('click', () => removeKey('gemini'));
  $('removeGroq')?.addEventListener('click', () => removeKey('groq'));
  $('removeOpenrouter')?.addEventListener('click', () => removeKey('openrouter'));
  $('removeOpenai')?.addEventListener('click', () => removeKey('openai'));
  $('removeDeepseek')?.addEventListener('click', () => removeKey('deepseek'));
  $('removeOllama')?.addEventListener('click', () => removeKey('ollama'));

  /* Reset preferences */
  $('resetPrefs').addEventListener('click', () => {
    ['myra_char', 'myra_name', 'myra_skills', 'myra_personality', 'myra_theme', 'myra_awareness', 'myra_owner', 'myra_voice_uri', 'myra_voice_pitch', 'myra_voice_rate']
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
      toast('👁️ Real vision arrives in Stage 9 — I placed your request in the chat box.');
    });
  });

  /* Skills toggles — wired to MYRA Core's real Agent skill registry. */
  const saved = JSON.parse(localStorage.getItem('myra_skills') || '{}');
  const CORE_SKILL_GROUPS = {
    browser_agent: ['browser.status', 'browser.snapshot', 'browser.screenshot', 'browser.click', 'browser.fill', 'web.open_url', 'web.research', 'web.fetch_text'],
    pc_control: ['app.launch_allowlisted', 'windows.list_windows', 'windows.observe', 'windows.focus', 'windows.invoke_control', 'windows.set_text', 'windows.send_keys', 'windows.click_point', 'windows.type_text', 'windows.hotkey'],
    news_reader: ['world.news'],
    note_helper: ['notes.create', 'notes.list', 'reminders.create', 'reminders.list', 'reminders.complete', 'reminders.delete'],
    camera_vision: ['multimodal.analyze_workspace_image'],
  };
  const setCoreSkillGroup = async (ids, enabled) => {
    await Promise.all(ids.map(async (id) => {
      const res = await fetch('/api/v1/skills/' + encodeURIComponent(id) + '/enabled', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || ('Could not update ' + id));
    }));
  };
  document.querySelectorAll('.skill-toggle').forEach((tg) => {
    if (tg.dataset.skill in saved) tg.checked = saved[tg.dataset.skill];
    tg.addEventListener('change', async () => {
      const enabled = tg.checked;
      saved[tg.dataset.skill] = enabled;
      localStorage.setItem('myra_skills', JSON.stringify(saved));
      const ids = CORE_SKILL_GROUPS[tg.dataset.skill];
      if (!ids || location.protocol === 'file:') {
        toast(`🧩 Skill ${enabled ? 'enabled ✅' : 'disabled ⛔'} — saved in this preview.`);
        return;
      }
      tg.disabled = true;
      try {
        await setCoreSkillGroup(ids, enabled);
        toast(tg.dataset.skill === 'pc_control'
          ? (enabled ? '🖥️ PC Control ON for Agent Mode. MYRA will still ask APPROVE before control skills run in a task.' : '🖥️ PC Control OFF. Agent Mode cannot control Windows apps.')
          : `🧩 Skill ${enabled ? 'enabled ✅' : 'disabled ⛔'} in MYRA's Agent engine.`);
        logEvent('core skill group ' + tg.dataset.skill + ' → ' + enabled);
      } catch (err) {
        tg.checked = !enabled;
        saved[tg.dataset.skill] = tg.checked;
        localStorage.setItem('myra_skills', JSON.stringify(saved));
        toast('❌ Could not update skill: ' + err.message, 6000);
      } finally {
        tg.disabled = false;
      }
    });
  });
  if (location.protocol !== 'file:') {
    fetch('/api/v1/skills')
      .then((r) => r.json())
      .then((data) => {
        const byId = {};
        (data.skills || []).forEach((skill) => { byId[skill.id] = Boolean(skill.enabled); });
        document.querySelectorAll('.skill-toggle').forEach((tg) => {
          const ids = CORE_SKILL_GROUPS[tg.dataset.skill];
          if (ids && ids.length && ids.every((id) => id in byId)) {
            tg.checked = ids.every((id) => byId[id]);
            saved[tg.dataset.skill] = tg.checked;
          }
        });
        localStorage.setItem('myra_skills', JSON.stringify(saved));
      })
      .catch(() => {});
  }

  /* Personality */
  const persSel = $('personality');
  const savedPers = localStorage.getItem('myra_personality');
  if (savedPers) persSel.value = savedPers;
  persSel.addEventListener('change', (e) => {
    localStorage.setItem('myra_personality', e.target.value);
    toast(`🎭 Personality set to "${e.target.value}" — it now shapes MYRA's real AI replies.`);
  });

  /* Voice Studio — Smart Bilingual Speech Engine */
  function initVoiceStudio() {
    const select = $('voiceStudioSelect');
    const pitchSlider = $('voicePitchSlider');
    const pitchVal = $('voicePitchVal');
    const speedSlider = $('voiceSpeedSlider');
    const speedVal = $('voiceSpeedVal');
    const testBtn = $('voiceTestBtn');
    const testNotice = $('voiceTestNotice');
    const statusBadge = $('voiceStudioStatus');

    if (!select) return;

    const savedPitch = localStorage.getItem('myra_voice_pitch');
    if (savedPitch && pitchSlider && pitchVal) {
      pitchSlider.value = savedPitch;
      pitchVal.textContent = parseFloat(savedPitch).toFixed(2) + 'x';
    }
    const savedRate = localStorage.getItem('myra_voice_rate');
    if (savedRate && speedSlider && speedVal) {
      speedSlider.value = savedRate;
      speedVal.textContent = parseFloat(savedRate).toFixed(2) + 'x';
    }

    if (pitchSlider) {
      pitchSlider.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value).toFixed(2);
        if (pitchVal) pitchVal.textContent = v + 'x';
        localStorage.setItem('myra_voice_pitch', v);
      });
    }

    if (speedSlider) {
      speedSlider.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value).toFixed(2);
        if (speedVal) speedVal.textContent = v + 'x';
        localStorage.setItem('myra_voice_rate', v);
      });
    }

    function populateVoices() {
      if (!('speechSynthesis' in window)) return;
      const voices = speechSynthesis.getVoices();
      if (!voices.length) return;

      const currentSaved = localStorage.getItem('myra_voice_uri') || 'auto';
      select.innerHTML = '<option value="auto">✨ Auto — form decides: CORE/MALE = male · FEMALE = female</option>';

      const bnGroup = document.createElement('optgroup');
      bnGroup.label = '🇧🇩 Bengali (বাংলা bn-BD / bn-IN)';
      const enGroup = document.createElement('optgroup');
      enGroup.label = '🇺🇸 English Natural / Neural';
      const otherGroup = document.createElement('optgroup');
      otherGroup.label = '🌐 Other Installed Voices';

      voices.forEach((v) => {
        const opt = document.createElement('option');
        opt.value = v.voiceURI;
        opt.textContent = `${v.name} (${v.lang})`;
        if (v.voiceURI === currentSaved) opt.selected = true;

        const langLow = v.lang.toLowerCase();
        if (langLow.startsWith('bn') || /bangla|bengali/i.test(v.name)) {
          bnGroup.appendChild(opt);
        } else if (langLow.startsWith('en')) {
          enGroup.appendChild(opt);
        } else {
          otherGroup.appendChild(opt);
        }
      });

      if (bnGroup.children.length) select.appendChild(bnGroup);
      if (enGroup.children.length) select.appendChild(enGroup);
      if (otherGroup.children.length) select.appendChild(otherGroup);
    }

    if ('speechSynthesis' in window) {
      populateVoices();
      speechSynthesis.onvoiceschanged = populateVoices;
    }

    select.addEventListener('change', () => {
      localStorage.setItem('myra_voice_uri', select.value);
      toast('🎙️ Voice Studio speaker preference updated.');
    });

    if (testBtn) {
      testBtn.addEventListener('click', () => {
        const sample = "হ্যালো! আমি মায়রা, আপনার ব্যক্তিগত এআই সহকারী। Hello! I am MYRA, your personal desktop AI companion.";
        if (testNotice) testNotice.textContent = "🗣️ Speaking test sample…";
        speakDemo(sample);
        setTimeout(() => {
          if (testNotice) testNotice.textContent = "Tap to test natural pronunciation";
        }, 4500);
      });
    }

    // Check backend voice status for local open-source TTS
    fetch('/api/voice/status')
      .then((r) => r.json())
      .then((d) => {
        if (statusBadge && d.ok) {
          if (d.local_tts_running) {
            statusBadge.textContent = 'LOCAL STUDIO ACTIVE';
            statusBadge.style.background = '#059669';
          } else {
            statusBadge.textContent = 'NEURAL READY';
          }
        }
      })
      .catch(() => {});

    fetchLiveVoiceStatus(true);
    const installBtn = $('installVoiceModelBtn');
    if (installBtn) {
      installBtn.addEventListener('click', async () => {
        const statusEl = $('liveVoiceStatus');
        const original = '⬇ INSTALL LIVE-VOICE MODEL · BASE (~145 MB)';
        if (installBtn.dataset.armed !== '1') {
          installBtn.dataset.armed = '1';
          installBtn.textContent = '✓ TAP AGAIN TO CONFIRM DOWNLOAD';
          if (statusEl) statusEl.textContent = 'One-time download: faster-whisper Base (~145 MB) from Hugging Face (Systran/faster-whisper-base), saved only on this PC. Tap the button again to confirm.';
          setTimeout(() => {
            if (installBtn.dataset.armed === '1') {
              installBtn.dataset.armed = '0';
              installBtn.textContent = original;
            }
          }, 9000);
          return;
        }
        installBtn.dataset.armed = '0';
        installBtn.disabled = true;
        installBtn.textContent = '⬇ DOWNLOADING… PLEASE WAIT';
        if (statusEl) statusEl.textContent = '⬇ Downloading the one-time live-voice model… keep MYRA open.';
        try {
          const res = await fetch('/api/v1/voice/models/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id: 'base', confirmed: true }),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false) throw new Error(data.error || 'Voice model download failed.');
          toast('✅ Live-voice model installed. Go Back and tap the mic under the hologram.', 6500);
          await fetchLiveVoiceStatus(true);
        } catch (err) {
          toast('❌ Live-voice setup failed: ' + err.message, 8000);
          if (statusEl) statusEl.textContent = '❌ Setup failed: ' + err.message;
        } finally {
          installBtn.disabled = false;
          installBtn.textContent = original;
        }
      });
    }
  }
  initVoiceStudio();

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

  /* Initial Setup Check & Connect Modal */
  const checkInitialSetup = async () => {
    if (location.protocol === 'file:') return;
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      if (!data.gemini.set && !data.groq.set) {
        $('connectModal').classList.remove('hidden');
      }
    } catch (e) {}
  };
  checkInitialSetup();

  /* Optional update notice. An update problem must never trap the owner:
     the popup can always be closed with ✕, Later, Escape, or by clicking
     outside it, and a dismissed version is not auto-opened again. */
  const UPDATE_DISMISSED_KEY = 'myra_update_dismissed_version';
  let latestUpdateVersion = '';
  let updateAutoShownVersion = '';
  let updateApplyBusy = false;

  const closeUpdateModal = (remember = true) => {
    const modal = $('updateModal');
    if (modal) modal.classList.add('hidden');
    if (remember && latestUpdateVersion) {
      try { localStorage.setItem(UPDATE_DISMISSED_KEY, latestUpdateVersion); } catch (e) {}
    }
    if (updateApplyBusy) {
      toast('⬇️ Update is continuing in the background. You can keep using MYRA.');
    }
  };
  const openUpdateModal = (force = false) => {
    const modal = $('updateModal');
    if (!modal) return;
    let dismissed = '';
    try { dismissed = localStorage.getItem(UPDATE_DISMISSED_KEY) || ''; } catch (e) {}
    if (!force && latestUpdateVersion && dismissed === latestUpdateVersion) return;
    modal.classList.remove('hidden');
    updateAutoShownVersion = latestUpdateVersion;
  };

  const checkAppUpdate = async () => {
    if (location.protocol === 'file:') return;
    try {
      const res = await fetch('/api/system/update-check');
      const data = await res.json().catch(() => ({}));
      if (data.update_available) {
        latestUpdateVersion = String(data.latest_version || '');
        $('updateChip').classList.remove('hidden');
        $('updateCurrentVer').textContent = data.current_version || 'local';
        $('updateLatestVer').textContent = latestUpdateVersion || 'unknown';
        // Notify once for this version in this session. After the owner
        // dismisses it, only the small UPDATE READY chip remains.
        if (updateAutoShownVersion !== latestUpdateVersion) openUpdateModal(false);
      } else {
        latestUpdateVersion = '';
        updateAutoShownVersion = '';
        $('updateChip').classList.add('hidden');
        $('updateModal').classList.add('hidden');
        try { localStorage.removeItem(UPDATE_DISMISSED_KEY); } catch (e) {}
      }
    } catch (e) {}
  };
  setTimeout(checkAppUpdate, 2500);
  setInterval(checkAppUpdate, 5 * 60 * 1000);

  $('updateChip').addEventListener('click', () => openUpdateModal(true));
  $('closeUpdateBtn')?.addEventListener('click', () => closeUpdateModal(true));
  $('dismissUpdateBtn')?.addEventListener('click', () => closeUpdateModal(true));
  $('updateModal')?.addEventListener('click', (event) => {
    if (event.target === $('updateModal')) closeUpdateModal(true);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('updateModal')?.classList.contains('hidden')) {
      closeUpdateModal(true);
    }
  });

  $('applyUpdateBtn').addEventListener('click', async () => {
    if (updateApplyBusy) return;
    const btn = $('applyUpdateBtn');
    const progress = $('updateProgressMsg');
    updateApplyBusy = true;
    btn.disabled = true;
    btn.textContent = '⬇️ Updating…';
    if (progress) progress.textContent = '⬇️ Downloading update from GitHub and refreshing files… You may close this popup and keep using MYRA.';
    const controller = 'AbortController' in window ? new AbortController() : null;
    const timeoutId = controller ? setTimeout(() => controller.abort(), 120000) : null;
    try {
      const res = await fetch('/api/system/update-apply', {
        method: 'POST',
        signal: controller ? controller.signal : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        const statusText = data.status === 'offline'
          ? 'GitHub could not be reached. Check the internet and try again later.'
          : 'The update did not finish. Your installed MYRA is still usable.';
        throw new Error(data.error || statusText);
      }
      if (data.status === 'current') {
        if (progress) progress.textContent = '✅ MYRA is already up to date.';
        $('updateChip').classList.add('hidden');
        try { localStorage.removeItem(UPDATE_DISMISSED_KEY); } catch (e) {}
        toast('✅ MYRA is already up to date.');
        closeUpdateModal(false);
        return;
      }
      if (progress) progress.textContent = '✅ Update complete! Reloading MYRA…';
      try { localStorage.removeItem(UPDATE_DISMISSED_KEY); } catch (e) {}
      toast('🚀 MYRA updated successfully! Reloading…');
      setTimeout(() => window.location.reload(), 1600);
    } catch (e) {
      const message = e && e.name === 'AbortError'
        ? 'Update took too long and was stopped. Check the internet and try again later.'
        : (e.message || 'Update failed.');
      if (progress) progress.textContent = '⚠️ Could not update: ' + message + ' Tap “Later — Continue MYRA” to keep using MYRA.';
      toast('⚠️ MYRA update failed, but MYRA is still usable. Close the popup with Later or ✕.', 6500);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      updateApplyBusy = false;
      btn.disabled = false;
      btn.textContent = '⬇️ Update MYRA Now';
    }
  });

  $('welcomeLaterBtn').addEventListener('click', () => $('connectModal').classList.add('hidden'));

  $('welcomeConnectBtn').addEventListener('click', async () => {
    const gemini = $('welcomeGeminiKey').value.trim();
    const groq = $('welcomeGroqKey').value.trim();
    const statusEl = $('welcomeStatus');
    const btn = $('welcomeConnectBtn');

    if (!gemini && !groq) {
      statusEl.textContent = '⚠️ Please enter at least your Gemini API key.';
      statusEl.style.color = '#f87171';
      return;
    }

    btn.disabled = true;
    statusEl.textContent = '🔄 Testing connection to AI brain…';
    statusEl.style.color = 'var(--accent)';

    try {
      const vRes = await fetch('/api/settings/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_key: gemini, groq_key: groq }),
      });
      const vData = await vRes.json();
      if (!vData.ok) {
        const gemErr = vData.results && vData.results.gemini && vData.results.gemini.message;
        const groqErr = vData.results && vData.results.groq && vData.results.groq.message;
        throw new Error(gemErr || groqErr || 'API key test failed. Please check the entered keys.');
      }

      const geminiModel = $('welcomeModelSelect') ? $('welcomeModelSelect').value : 'auto';
      const groqModel = $('welcomeGroqModelSelect') ? $('welcomeGroqModelSelect').value : 'auto';
      await fetch('/api/settings/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_key: gemini, groq_key: groq, gemini_model: geminiModel, groq_model: groqModel }),
      });

      const gemModel = (vData.results && vData.results.gemini && vData.results.gemini.model) || '';
      const groqModelActive = (vData.results && vData.results.groq && vData.results.groq.model) || '';
      const parts = [];
      if (gemModel) parts.push(`Gemini: ${gemModel}`);
      if (groqModelActive) parts.push(`Groq: ${groqModelActive}`);
      const modelInfo = parts.length ? ` (${parts.join(', ')})` : '';
      statusEl.textContent = '✅ Connected successfully! Brain is active' + modelInfo + '.';
      statusEl.style.color = '#4ade80';
      refreshKeyStatus();

      setTimeout(() => {
        $('connectModal').classList.add('hidden');
        const greet = "Hello! I am MYRA, your AI desktop companion. My brain is now connected and ready to assist you.";
        addMsg(greet, 'ai');
        speakDemo(greet);
        toast('🟢 Brain connected! Welcome to MYRA.');
      }, 1000);
    } catch (err) {
      statusEl.textContent = '❌ ' + err.message;
      statusEl.style.color = '#f87171';
    } finally {
      btn.disabled = false;
    }
  });

  pushHistory('ai', GREETINGS[HOLO.char] || GREETINGS.core);
  logEvent('shell ready · MYRA v1.0 complete');
  toast('🤖 MYRA v1.0 — Online & Ready! Complete Personal Desktop AI Assistant.', 6000);
});
