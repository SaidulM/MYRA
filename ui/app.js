/* =========================================================
   MYRA — System Core UI (Stage 1, v4)
   Three particle characters (CORE / MALE / FEMALE), each
   formed by ~34,000 fine dots flowing in waves out of a
   scattered cloud. Face is sculpted with real proportions
   (brow, nose, eyes, lips, jaw, chin) + soft light shading.
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

/* =========================================================
   CORE HOLOGRAM — particle figures with formation waves
   ========================================================= */
const N = 34000;
const CHAR_COLORS = { core: 0x22d3ee, male: 0x38bdf8, female: 0xe879f9 };
function savedChar() {
  const c = localStorage.getItem('myra_char');
  if (c === 'core' || c === 'male' || c === 'female') return c;
  const old = localStorage.getItem('stonic_gender'); // migrate from v3
  return old === 'male' ? 'male' : 'female';
}
const HOLO = {
  char: savedChar(),
  formedChar: null,      // which figure is currently built into targets
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
};

/* Soft fake lighting: key light + gentle rim */
const LGT = (() => {
  const nrm = (x, y, z) => { const l = Math.hypot(x, y, z); return [x / l, y / l, z / l]; };
  return { key: nrm(-0.45, 0.78, 0.88), rim: nrm(0.85, 0.3, -0.72) };
})();
function shade(nx, ny, nz) {
  const l = Math.hypot(nx, ny, nz) || 1;
  nx /= l; ny /= l; nz /= l;
  const dKey = Math.max(0, nx * LGT.key[0] + ny * LGT.key[1] + nz * LGT.key[2]);
  const dRim = Math.max(0, nx * LGT.rim[0] + ny * LGT.rim[1] + nz * LGT.rim[2]);
  return clamp(0.55 + 0.55 * dKey + 0.35 * Math.pow(dRim, 3), 0.3, 1.35);
}

/* ----- Head cross-sections [y, rx, rz, cz] chin → crown ----- */
const HEAD_ROWS = {
  female: [
    [1.52, .15, .13, .10], [1.60, .245, .205, .055], [1.70, .315, .26, .03],
    [1.80, .365, .30, .012], [1.92, .405, .33, 0], [2.03, .41, .335, 0],
    [2.13, .415, .345, .005], [2.26, .435, .355, -.008], [2.40, .43, .365, -.03],
    [2.52, .35, .30, -.05], [2.62, .17, .15, -.06],
  ],
  male: [
    [1.52, .18, .15, .10], [1.60, .28, .23, .055], [1.70, .34, .275, .03],
    [1.80, .385, .315, .012], [1.92, .42, .345, 0], [2.03, .43, .35, 0],
    [2.13, .44, .36, .008], [2.26, .445, .365, -.012], [2.40, .44, .375, -.035],
    [2.52, .36, .31, -.05], [2.62, .18, .16, -.06],
  ],
};
const EYE = { x: 0.168, y: 2.045 };

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

/* Face feature height-field (gentle — over-carving looks cartoonish) */
function faceFeatures(x, y, female) {
  const soft = female ? 0.78 : 0.9;
  let d = 0;
  d += g2(x, y, 0, 1.855, .052, .068, .11 * soft);           // nose tip
  d += g2(x, y, 0, 1.97, .04, .12, .055 * soft);             // nose bridge
  d += g2(x, y, .06, 1.812, .046, .037, .036);               // nostril wings
  d += g2(x, y, -.06, 1.812, .046, .037, .036);
  d += g2(x, y, 0, 1.775, .07, .03, -.015);                  // under-nose shadow
  d += g2(x, y, EYE.x, 2.05, .088, .055, -.036);             // eye sockets
  d += g2(x, y, -EYE.x, 2.05, .088, .055, -.036);
  const browA = female ? .03 : .048;
  d += g2(x, y, EYE.x + .005, 2.135, .105, .042, browA);     // brow ridge
  d += g2(x, y, -EYE.x - .005, 2.135, .105, .042, browA);
  d += g2(x, y, 0, 2.125, .05, .05, .02);                    // glabella
  d += g2(x, y, .265, 1.93, .105, .085, .03);                // cheekbones
  d += g2(x, y, -.265, 1.93, .105, .085, .03);
  d += g2(x, y, 0, 1.755, .045, .035, .011);                 // philtrum
  d += g2(x, y, 0, 1.705, .08, .026, .035);                  // upper lip
  d += g2(x, y, 0, 1.65, .066, .029, .044);                  // lower lip
  d += g2(x, y, 0, 1.678, .086, .011, -.024);                // mouth line
  d += g2(x, y, 0, 1.585, .07, .05, .034);                   // chin
  return d;
}

function genHeadPoint(female) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  const y = rand(1.52, 2.62);
  const [rx, rz, cz] = rowAt(rows, y);
  let th;
  if (Math.random() < 0.58) th = Math.PI / 2 + rand(-0.88, 0.88);  // face denser
  else th = Math.random() * Math.PI * 2;
  const fr = Math.sin(th);
  const x = rx * Math.cos(th);
  let z = cz + rz * fr;
  if (fr > 0.2) z += faceFeatures(x, y, female) * clamp((fr - 0.2) / 0.5, 0, 1);
  let b = shade(x * 1.7, (y - 2.02) * 0.85, z * 1.5);
  const de = Math.min(Math.hypot(x - EYE.x, y - 2.05), Math.hypot(x + EYE.x, y - 2.05));
  if (fr > 0.4 && de < 0.085) b *= 0.78;
  if (fr > 0.4 && Math.abs(y - 1.678) < 0.013 && Math.abs(x) < 0.15) b *= 0.55;
  return [x, y, z, b];
}

function pushPt(arr, x, y, z, col, bright, headW) {
  arr.push({
    x, y, z, headW,
    r: clamp(col.r * bright, 0, 2), g: clamp(col.g * bright, 0, 2), b: clamp(col.b * bright, 0, 2),
  });
}

function sampleHeadAll(out, female, faceCol) {
  const J = 0.0022;
  for (let i = 0; i < 13000; i++) {
    const p = genHeadPoint(female);
    pushPt(out, p[0] + rand(-J, J), p[1] + rand(-J, J), p[2] + rand(-J, J), faceCol, p[3], 1);
  }
  let lip = 0, guard = 0;
  while (lip < 900 && guard++ < 90000) {
    const p = genHeadPoint(female);
    if (p[1] > 1.615 && p[1] < 1.74 && Math.abs(p[0]) < 0.17 && p[2] > 0.12) {
      pushPt(out, p[0], p[1], p[2], faceCol, p[3] * 1.05, 1);
      lip++;
    }
  }
}

function sampleEyesBrows(out, female, faceCol, hairCol) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  const [rxE, rzE] = rowAt(rows, 2.03);
  const eyeCol = faceCol.clone().lerp(new THREE.Color(0xffffff), 0.55);
  for (const s of [1, -1]) {
    const cx = s * EYE.x;
    const zSock = rzE * Math.sqrt(Math.max(.05, 1 - (cx / rxE) ** 2)) - 0.036;
    for (let i = 0; i < 230; i++) {           // eyeball + iris (subtle)
      const a = Math.random() * Math.PI * 2, rr = Math.sqrt(Math.random());
      pushPt(out,
        cx + Math.cos(a) * rr * 0.052,
        EYE.y + Math.sin(a) * rr * 0.029,
        zSock + 0.004 + (1 - rr * rr) * 0.024,
        eyeCol, rr < 0.38 ? 1.45 : 1.02, 1);
    }
    const arcs = female ? [0, 0.012] : [0];
    for (const off of arcs) {                 // eyelid / lashes
      for (let i = 0; i < 70; i++) {
        const t = rand(0.12, 0.88) * Math.PI;
        pushPt(out,
          cx + Math.cos(t) * (0.058 + off * 0.4),
          EYE.y + 0.006 + Math.sin(t) * (0.034 + off),
          zSock + 0.01 + Math.sin(t) * 0.011,
          faceCol, 1.18, 1);
      }
    }
    const [rxB, rzB] = rowAt(rows, 2.13);
    for (let i = 0; i < 320; i++) {           // brows
      const t = rand(-1, 1);
      const bx = cx + t * (female ? 0.082 : 0.096);
      const by = (female ? 2.155 : 2.142) + (female ? 0.03 : 0.014) * (1 - t * t) + rand(-1, 1) * (female ? 0.0035 : 0.008);
      const bz = rzB * Math.sqrt(Math.max(.05, 1 - (bx / rxB) ** 2)) + (female ? 0.024 : 0.038);
      pushPt(out, bx, by, bz, hairCol, 1.1, 1);
    }
  }
  const [rxEar] = rowAt(rows, 1.95);
  for (const s of [1, -1]) {
    for (let i = 0; i < 200; i++) {
      const a = Math.random() * Math.PI * 2, rr = Math.sqrt(Math.random());
      pushPt(out, s * (rxEar + 0.004 + rr * 0.02), 1.95 + Math.sin(a) * rr * 0.085, -0.01 + Math.cos(a) * rr * 0.052, faceCol, 0.7, 1);
    }
  }
}

function sampleHairCap(out, n, female, hairCol) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  let placed = 0, guard = 0;
  while (placed < n && guard++ < n * 60) {
    const y = rand(1.96, 2.66);
    const [rx, rz, cz] = rowAt(rows, Math.min(y, 2.62));
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x0 = rx * Math.cos(th);
    if (fr > 0.22) {
      let hl;
      if (female) hl = 2.34 - 0.42 * Math.pow(clamp(Math.abs(x0) / 0.46, 0, 1), 1.6);
      else hl = 2.285 + 0.085 * Math.exp(-Math.pow((Math.abs(x0) - 0.27) / 0.09, 2));
      if (y < hl && guard < n * 45) continue;
    }
    const taper = y < 2.12 ? 1.045 : (female ? 1.1 : 1.09);
    const hx = x0 * taper + rand(-.008, .008);
    let hy = y + 0.03 + rand(-.008, .008);
    const hz = cz + rz * fr * taper - 0.012 + rand(-.008, .008);
    if (!female && fr > 0.3 && Math.abs(hx) < 0.3 && hy > 2.3) hy += 0.045 * (1 - Math.abs(hx) / 0.3);
    pushPt(out, hx, hy, hz, hairCol, shade(hx * 1.6, hy - 2.0, hz * 1.4) * 0.92, 1);
    placed++;
  }
}

function sampleHairFemaleLong(out, hairCol) {
  let placed = 0, guard = 0;
  while (placed < 1600 && guard++ < 90000) {   // back volume shell
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const px = 0.52 * s * Math.cos(th), py = 1.82 + 0.8 * u, pz = -0.15 + 0.42 * s * Math.sin(th);
    if (pz > 0.1 || py < 1.02) continue;
    pushPt(out, px, py, pz, hairCol, shade(px * 1.5, py - 1.8, pz * 1.3) * 0.82, clamp((py - 0.9) / 1.3, 0.15, 1));
    placed++;
  }
  const strands = [];
  for (let i = 0; i < 34; i++) {
    const phi = rand(-2.85, 2.85);
    if (Math.abs(phi) < 0.55) continue;
    strands.push({ phi, len: rand(0.95, 1.4), waveF: rand(4.5, 7), waveP: rand(0, 6.28), hi: rand(0.82, 1.18), front: false });
  }
  strands.push({ phi: 0.66, len: 1.52, waveF: 5.2, waveP: 1.2, hi: 1.12, front: true });
  strands.push({ phi: -0.66, len: 1.52, waveF: 5.6, waveP: 4.0, hi: 1.12, front: true });
  strands.push({ phi: 0.45, len: 0.95, waveF: 6.2, waveP: 2.4, hi: 1.05, front: true });
  strands.push({ phi: -0.45, len: 0.95, waveF: 6.0, waveP: 5.1, hi: 1.05, front: true });
  const per = Math.floor(5600 / strands.length);
  strands.forEach((st) => {
    const ay = 2.32, R = 0.48;
    const ax = Math.sin(st.phi) * R, az = Math.cos(st.phi) * R * 0.92 - 0.03;
    const yEnd = ay - st.len;
    for (let i = 0; i < per; i++) {
      const t = Math.pow(Math.random(), 0.92);
      const y = ay + (yEnd - ay) * t;
      const radial = 1 + 0.14 * Math.sin(Math.min(t * 2.2, 1) * Math.PI * 0.5);
      let cx = ax * radial, cz = az * radial - 0.02 * t;
      if (st.front) {
        const k = clamp((t - 0.5) / 0.5, 0, 1);
        cz = lerp(cz, 0.3, k * k);
        cx = lerp(cx, Math.sign(ax) * 0.39, k * 0.6);
      }
      cx += Math.sin(t * st.waveF + st.waveP) * 0.05 * (0.3 + t);
      cz += Math.cos(t * st.waveF + st.waveP) * 0.028 * (0.3 + t);
      const tubeR = 0.062 * (1 - t * 0.5);
      const b = shade(cx * 1.5, (y - 1.9) * 0.8, cz * 1.4) * st.hi;
      pushPt(out, cx + rand(-1, 1) * tubeR, y + rand(-.018, .018), cz + rand(-1, 1) * tubeR, hairCol, b, clamp(1.12 - t * 1.02, 0.1, 1));
    }
  });
}

function sampleLoft(out, n, rows, zScale, col, brightMul, headWFn, frontBumpFn) {
  const yMin = rows[rows.length - 1][0], yMax = rows[0][0];
  const rAt = (y) => {
    for (let i = 0; i < rows.length - 1; i++) {
      const a = rows[i], b = rows[i + 1];
      if (y <= a[0] && y >= b[0]) return lerp(a[1], b[1], (a[0] - y) / (a[0] - b[0]));
    }
    return rows[rows.length - 1][1];
  };
  for (let i = 0; i < n; i++) {
    const y = rand(yMin, yMax);
    const r = rAt(y) * rand(0.985, 1.015);
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    const x = r * Math.cos(th);
    let z = r * zScale * fr;
    if (frontBumpFn && fr > 0.25) z += frontBumpFn(x, y) * clamp((fr - 0.25) / 0.5, 0, 1);
    const b = shade(Math.cos(th), 0.14, fr) * brightMul;
    const dim = y < 0.48 ? 0.55 + (y - 0.3) * 2.0 : 1;
    pushPt(out, x + rand(-.004, .004), y, z + rand(-.004, .004), col, b * clamp(dim, 0.5, 1), headWFn ? headWFn(y) : 0);
  }
  return rAt;
}

function buildBustPoints(female, baseCol) {
  const base = baseCol;
  const faceCol = base.clone().multiplyScalar(1.05);
  const hairCol = base.clone(); hairCol.offsetHSL(female ? -0.035 : 0.02, 0.05, female ? -0.02 : 0.04);
  const chestCol = base.clone().multiplyScalar(0.85);

  const pts = [];
  sampleHeadAll(pts, female, faceCol);
  sampleEyesBrows(pts, female, faceCol, hairCol);
  if (female) {
    sampleHairCap(pts, 3800, true, hairCol);
    sampleHairFemaleLong(pts, hairCol);
  } else {
    sampleHairCap(pts, 4600, false, hairCol);
  }

  const neckRows = female
    ? [[1.50, .135], [1.38, .14], [1.26, .165], [1.16, .26], [1.10, .34]]
    : [[1.50, .155], [1.38, .165], [1.26, .19], [1.16, .30], [1.10, .38]];
  sampleLoft(pts, 1400, neckRows, 0.88, base.clone().multiplyScalar(0.95), 0.95,
    (y) => 0.55 * clamp((y - 1.12) / 0.38, 0, 1), null);

  const chestRows = female
    ? [[1.12, .52], [1.06, .78], [1.00, .88], [0.88, .90], [0.72, .84], [0.55, .76], [0.40, .66], [0.30, .58]]
    : [[1.12, .60], [1.06, .90], [1.00, 1.02], [0.88, 1.05], [0.72, .97], [0.55, .87], [0.40, .76], [0.30, .68]];
  const bustBump = female
    ? (x, y) => g2(x, y, .23, .72, .15, .13, .045) + g2(x, y, -.23, .72, .15, .13, .045)
    : null;
  const chestQuota = N - pts.length - 500;
  const rChest = sampleLoft(pts, Math.max(chestQuota, 200), chestRows, 0.55, chestCol, 0.9, null, bustBump);

  for (const s of [1, -1]) {   // collarbones
    for (let i = 0; i < 250; i++) {
      const t = Math.random();
      const x = s * (0.07 + t * 0.52);
      const y = 1.145 - t * 0.05 + rand(-.006, .006);
      const rx = rChest(clamp(y, 0.3, 1.12));
      const z = rx * 0.55 * Math.sqrt(Math.max(.04, 1 - (x / rx) ** 2)) + 0.01;
      pushPt(pts, x, y, z, faceCol, 1.08, 0);
    }
  }
  return pts;
}

function buildCorePoints(baseCol) {
  const pts = [];
  const CY = 1.55, R = 0.95;
  const white = baseCol.clone().lerp(new THREE.Color(0xffffff), 0.6);
  // Outer shell
  for (let i = 0; i < 15000; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = R * rand(0.96, 1.03);
    const x = r * s * Math.cos(th), y = CY + r * u, z = r * s * Math.sin(th);
    pushPt(pts, x, y, z, baseCol, shade(x, u, z), 0);
  }
  // Inner glowing heart (denser & brighter toward center)
  for (let i = 0; i < 7000; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = R * 0.55 * Math.pow(Math.random(), 0.6);
    const bright = lerp(1.6, 0.7, r / (R * 0.55));
    pushPt(pts, r * s * Math.cos(th), CY + r * u, r * s * Math.sin(th), white, bright, 0);
  }
  // Three orbit rings
  const rings = [
    { tiltX: 1.25, tiltZ: 0.3, rad: 1.28 },
    { tiltX: 0.5, tiltZ: -0.7, rad: 1.38 },
    { tiltX: 1.8, tiltZ: 1.1, rad: 1.22 },
  ];
  rings.forEach((rg) => {
    for (let i = 0; i < 3000; i++) {
      const a = Math.random() * Math.PI * 2;
      let x = Math.cos(a) * rg.rad, y = 0, z = Math.sin(a) * rg.rad;
      let y1 = y * Math.cos(rg.tiltX) - z * Math.sin(rg.tiltX);
      let z1 = y * Math.sin(rg.tiltX) + z * Math.cos(rg.tiltX);
      const x2 = x * Math.cos(rg.tiltZ) - y1 * Math.sin(rg.tiltZ);
      const y2 = x * Math.sin(rg.tiltZ) + y1 * Math.cos(rg.tiltZ);
      pushPt(pts, x2 + rand(-.015, .015), CY + y2 + rand(-.015, .015), z1 + rand(-.015, .015), baseCol, 1.15, 0);
    }
  });
  // Equatorial sparkle disc
  for (let i = 0; i < 3000; i++) {
    const a = Math.random() * Math.PI * 2, r = rand(1.0, 1.55);
    pushPt(pts, Math.cos(a) * r, CY + rand(-.05, .05), Math.sin(a) * r, baseCol, rand(0.35, 0.8), 0);
  }
  return pts;
}

function buildFigure(charType) {
  const base = new THREE.Color(CHAR_COLORS[charType]);
  let pts;
  if (charType === 'core') pts = buildCorePoints(base);
  else pts = buildBustPoints(charType === 'female', base);

  while (pts.length > N) pts.pop();
  while (pts.length < N) {   // pad with faint halo sparks
    const a = Math.random() * Math.PI * 2, r = rand(1.3, 1.9);
    pushPt(pts, Math.cos(a) * r, rand(0.4, 2.6), Math.sin(a) * r, base, 0.3, 0);
  }

  const targets = new Float32Array(N * 3);
  const colors = new Float32Array(N * 3);
  const headW = new Float32Array(N);
  const delay = new Float32Array(N);
  pts.forEach((p, i) => {
    targets[i * 3] = p.x; targets[i * 3 + 1] = p.y; targets[i * 3 + 2] = p.z;
    colors[i * 3] = p.r; colors[i * 3 + 1] = p.g; colors[i * 3 + 2] = p.b;
    headW[i] = p.headW;
    // Wave delay: rises bottom-up with diagonal ripples
    const normY = clamp((p.y - 0.3) / 2.35, 0, 1);
    const rr = Math.hypot(p.x, p.z);
    delay[i] = clamp(normY * 0.5 + (Math.sin(p.y * 3.2 + rr * 2.5) * 0.5 + 0.5) * 0.26 + Math.random() * 0.24, 0, 1);
  });
  return { targets, colors, headW, delay };
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
    const m = new THREE.PointsMaterial({ color: 0x7dd3fc, size: 0.02, transparent: true, opacity: 0.5, depthWrite: false });
    m.userData.baseOp = 0.5; m.userData.lockColor = true;
    HOLO.accentMats.push(m);
    scene.add(new THREE.Points(g, m));
  }

  const accentMat = (op) => {
    const m = new THREE.MeshBasicMaterial({ color: CHAR_COLORS[HOLO.char], transparent: true, opacity: op, side: THREE.DoubleSide, depthWrite: false });
    m.userData.baseOp = op;
    HOLO.accentMats.push(m);
    return m;
  };
  const disc = new THREE.Group();
  const mkRing = (inner, outer, op, thetaLen) => {
    const mesh = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 72, 1, 0, thetaLen || Math.PI * 2), accentMat(op));
    mesh.rotation.x = -Math.PI / 2;
    disc.add(mesh);
    return mesh;
  };
  mkRing(1.16, 1.23, 0.85);
  mkRing(0.85, 0.89, 0.5);
  const arc1 = mkRing(1.0, 1.06, 0.9, Math.PI * 0.7);
  const arc2 = mkRing(0.66, 0.71, 0.9, Math.PI * 0.5);
  const glowDisc = new THREE.Mesh(new THREE.CircleGeometry(0.64, 48), accentMat(0.1));
  glowDisc.rotation.x = -Math.PI / 2; glowDisc.position.y = 0.005;
  disc.add(glowDisc);
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.95, 0.3, 0.34, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: CHAR_COLORS[HOLO.char], transparent: true, opacity: 0.05, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
  beam.material.userData.baseOp = 0.05;
  HOLO.accentMats.push(beam.material);
  beam.position.y = 0.17;
  disc.add(beam);
  world.add(disc);

  const scan = new THREE.Mesh(new THREE.RingGeometry(1.14, 1.18, 72), accentMat(0.5));
  scan.rotation.x = -Math.PI / 2;
  world.add(scan);
  HOLO.scanMat = scan.material;

  /* Particle figure */
  const built = buildFigure(HOLO.char);
  HOLO.formedChar = HOLO.char;
  let targets = built.targets, headW = built.headW, delay = built.delay;

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
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(built.colors, 3));
  const pMat = new THREE.PointsMaterial({
    size: 0.0165, vertexColors: true, transparent: true, opacity: 0.9,
    blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
  });
  const figure = new THREE.Points(geo, pMat);
  world.add(figure);

  HOLO.applyFigure = (charType) => {
    const b = buildFigure(charType);
    targets = b.targets; headW = b.headW; delay = b.delay;
    geo.attributes.color.array.set(b.colors);
    geo.attributes.color.needsUpdate = true;
    HOLO.formedChar = charType;
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
      HOLO.formT = Math.min(1, HOLO.formT + dt * 0.4);
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

    const pos = geo.attributes.position.array;
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
      // gentle wave while flying in
      y += Math.sin(p * Math.PI) * (1 - p) * 0.12 * Math.sin(phase[i] * 3 + t * 2);

      const ph = phase[i];
      const shim = Math.sin(t * 2.3 + ph) * (0.0038 + sb * 0.009 * headW[i]) * e;
      const rl = Math.sqrt(x * x + z * z) || 1e-4;
      x += (x / rl) * shim; z += (z / rl) * shim;
      y += Math.sin(t * 1.7 + ph * 1.3) * 0.0028 * e;

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
    }
    geo.attributes.position.needsUpdate = true;

    figure.position.y = Math.sin(t * 1.12) * 0.028;
    // CORE pulses while speaking (it has no head to nod)
    const pulse = HOLO.formedChar === 'core' ? 1 + sb * 0.045 * Math.sin(t * 9) + 0.012 * Math.sin(t * 2.2) : 1;
    figure.scale.setScalar(pulse);

    if (!HOLO.dragging && HOLO.power) HOLO.autoRot += dt * 0.09;
    world.rotation.y += ((HOLO.targetRotY + HOLO.autoRot) - world.rotation.y) * 0.08;
    arc1.rotation.z = t * 0.5;
    arc2.rotation.z = -t * 0.7;

    const cyc = (t * 0.38) % 1;
    scan.position.y = 0.3 + cyc * 2.4;
    HOLO.scanMat.opacity = (HOLO.power ? 0.5 : 0) * Math.sin(cyc * Math.PI) * formT;

    pMat.opacity += ((HOLO.power ? 0.9 : 0.04) - pMat.opacity) * 0.08;
    HOLO.accentMats.forEach((m) => {
      if (m === HOLO.scanMat) return;
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
  document.body.classList.toggle('char-male', HOLO.char === 'male');
  document.body.classList.toggle('char-female', HOLO.char === 'female');
  HOLO.accentMats.forEach((m) => { if (m.color && !m.userData.lockColor) m.color.setHex(CHAR_COLORS[HOLO.char]); });
  ['core', 'male', 'female'].forEach((c) => {
    const card = $('card-' + c);
    if (card) {
      card.classList.toggle('is-active', c === HOLO.char);
      const badge = card.querySelector('.cc-badge');
      if (badge) badge.classList.toggle('hidden', c !== HOLO.char);
    }
  });
}
function setChar(charType) {
  if (charType === HOLO.char && HOLO.mode === 'in' && HOLO.formT > 0.9) return;
  HOLO.char = charType;
  localStorage.setItem('myra_char', charType);
  HOLO.pendingChar = charType;
  HOLO.mode = 'out';
  syncCharUI();
  setHoloStatus('✨ Re-forming into ' + charType.toUpperCase() + '…');
}
function reform() {
  if (!HOLO.power) { toast('⏻ System is off — press ACTIVATE first!'); return; }
  HOLO.pendingChar = HOLO.char;
  HOLO.mode = 'out';
  setHoloStatus('✨ Forming again — watch the waves of dots!');
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
    const sx = w / 200, sy = h / 100, step = 3.4;
    for (let gy = 2; gy < h - 2; gy += step) {
      for (let gx = 2; gx < w - 2; gx += step) {
        const land = isLand(gx / sx, gy / sy);
        ctx.fillStyle = land ? 'rgba(94,234,212,0.55)' : 'rgba(94,234,212,0.05)';
        ctx.beginPath();
        ctx.arc(gx, gy, land ? 1.05 : 0.55, 0, 6.2832);
        ctx.fill();
      }
    }
  };
  new ResizeObserver(draw).observe(box);
  draw();
}

/* ----- 3D dotted Earth (World Monitor full view) ----- */
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
  const landMat = new THREE.PointsMaterial({ color: 0x2dd4bf, size: 0.021, transparent: true, opacity: 0.95, depthWrite: false });
  group.add(new THREE.Points(g, landMat));

  // faint ocean sphere + graticule rings
  const ocean = new THREE.Mesh(
    new THREE.SphereGeometry(0.985, 40, 28),
    new THREE.MeshBasicMaterial({ color: 0x0a2e2a, transparent: true, opacity: 0.5 }));
  group.add(ocean);
  [[1.18, Math.PI / 2.3, 0.4], [1.3, Math.PI / 1.7, -0.6]].forEach(([rad, rx, ry]) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(rad, 0.004, 8, 110),
      new THREE.MeshBasicMaterial({ color: 0x2dd4bf, transparent: true, opacity: 0.4 }));
    ring.rotation.set(rx, ry, 0);
    group.add(ring);
  });

  // hotspots (lon, lat)
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
    if (!dragging) userRot += dt * 0.12;
    group.rotation.y = userRot;
    renderer.render(scene, camera);
  })();
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
function openView(name) {
  document.querySelectorAll('.fullview').forEach((v) => v.classList.add('hidden'));
  const v = $('view-' + name);
  if (v) v.classList.remove('hidden');
  document.body.classList.add('view-open');
  globeActive = name === 'world';
  if (name === 'world') initGlobe();
}
function closeViews() {
  document.querySelectorAll('.fullview').forEach((v) => v.classList.add('hidden'));
  document.body.classList.remove('view-open');
  globeActive = false;
  setTimeout(drawWires, 60);
}

/* =========================================================
   Speaking demo (real voice in Stage 5)
   ========================================================= */
function speakDemo(text) {
  if (!HOLO.power) return;
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
    } catch (e) { /* animation still plays without a voice */ }
  }
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
let demoIdx = 0;

function addMsg(text, who) {
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
  const typing = addMsg('', 'ai');
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
    speakDemo(reply);
  }, 900);
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
    HOLO.speaking = false;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    closeViews();
    setHoloStatus('⏻ System offline — press ACTIVATE and the dots will form again');
    toast('⏻ MYRA powered down — particles scattered. Press ACTIVATE to wake her.');
  } else {
    setHoloStatus('✨ Waking up — particles gathering…');
    toast('🤖 MYRA online! Watch the figure form.');
  }
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
   Event wiring
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  initHologram();
  initMap();
  syncCharUI();
  renderMemories();
  setTimeout(drawWires, 350);
  let rT = null;
  window.addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(drawWires, 160); });

  /* Assistant name */
  const savedName = localStorage.getItem('myra_name');
  if (savedName) { $('npName').textContent = savedName.toUpperCase(); $('nameInput').value = savedName; }
  else $('nameInput').value = 'MYRA';
  $('nameSave').addEventListener('click', () => {
    const v = $('nameInput').value.trim() || 'MYRA';
    localStorage.setItem('myra_name', v);
    $('npName').textContent = v.toUpperCase();
    toast('✨ Name saved — say hello to ' + v + '!');
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

  /* Power */
  $('terminateBtn').addEventListener('click', () => setPower(!HOLO.power));
  $('reformBtn').addEventListener('click', reform);

  /* Character switch — the ONLY place (top selector) */
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
  document.querySelectorAll('[data-back]').forEach((b) => b.addEventListener('click', closeViews));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeViews(); });

  /* Conversation tabs */
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.mode-panel').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      $('mode-' + tab.dataset.mode).classList.add('active');
    });
  });

  /* Chat + mic (single mic, in the input bar) */
  $('sendBtn').addEventListener('click', sendChat);
  $('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });
  $('micBtn').addEventListener('click', () => {
    toast('🎤 Voice arrives in Stage 5 — then just speak; MYRA will listen fully and answer only after you finish.');
  });

  /* Agent demo */
  const runAgentDemo = () => {
    const task = $('agentInput').value.trim() || '(empty task)';
    const log = $('agentLog');
    log.textContent = `📝 Task received: "${task}"\n`;
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
    ['myra_char', 'myra_name', 'myra_skills', 'myra_personality'].forEach((k) => localStorage.removeItem(k));
    toast('🧹 Preferences reset — reload the page to start fresh.', 4200);
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

  /* World refresh */
  $('refreshNews').addEventListener('click', () => {
    toast('🌍 Live news arrives in Stage 10 — then hotspots will mark real events and I can read the headlines aloud!');
  });

  setHoloStatus(idleStatus());
  toast('✨ MYRA is forming — try CORE / MALE / FEMALE above, click a module chip to open its window, and spin the Earth in WORLD MONITOR!', 6400);
});
