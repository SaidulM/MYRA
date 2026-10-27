/* =========================================================
   Stonic AI — System Core UI (ধাপ ১, v3)
   ভাস্কর্যের মতো খোদাই করা পার্টিকেল বাস্ট (বুক থেকে উপরে):
   কপাল, ভ্রু, নাক, চোখ, ঠোঁট, চোয়ালসহ আসল মুখের গঠন —
   ২০,০০০ ডট ছড়ানো মেঘ থেকে ঘুরে এসে আকার গঠন করে।
   ধাপ ৩ থেকে চ্যাট আসল API-তে যাবে; এখন ডেমো উত্তর।
   ========================================================= */
'use strict';

/* ---------- হেল্পার ---------- */
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
   CORE হলোগ্রাম — খোদাই-করা মুখের পার্টিকেল বাস্ট
   ========================================================= */
const N = 20000;
const COLORS = { male: 0x22d3ee, female: 0xe879f9 };
const HOLO = {
  gender: localStorage.getItem('stonic_gender') || 'male',
  power: true,
  speaking: false,
  speakBlend: 0,
  formT: 0,
  mode: 'in',
  pendingGender: null,
  targetRotY: 0,
  autoRot: 0,
  dragging: false,
  accentMats: [],
};

/* নকল আলো: বাঁ-ওপর থেকে key light + ডান-পেছন থেকে rim light */
const LGT = (() => {
  const n = (x, y, z) => { const l = Math.hypot(x, y, z); return [x / l, y / l, z / l]; };
  return { key: n(-0.45, 0.78, 0.88), rim: n(0.85, 0.3, -0.72) };
})();
function shade(nx, ny, nz) {
  const l = Math.hypot(nx, ny, nz) || 1;
  nx /= l; ny /= l; nz /= l;
  const dKey = Math.max(0, nx * LGT.key[0] + ny * LGT.key[1] + nz * LGT.key[2]);
  const dRim = Math.max(0, nx * LGT.rim[0] + ny * LGT.rim[1] + nz * LGT.rim[2]);
  return clamp(0.42 + 0.72 * dKey + 0.6 * Math.pow(dRim, 3), 0.22, 1.55);
}

/* --- মাথার সেকশন প্রোফাইল [y, rx, rz, cz] : থুতনি → মাথার চূড়া --- */
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

/* মুখের বৈশিষ্ট্যের উচ্চতা-মাঠ (সামনের পৃষ্ঠে z ঠেলে দেয়) */
function faceFeatures(x, y, female) {
  const soft = female ? 0.9 : 1.06;
  let d = 0;
  d += g2(x, y, 0, 1.855, .055, .07, .13 * soft);            // নাকের ডগা
  d += g2(x, y, 0, 1.97, .04, .12, .065 * soft);             // নাকের সেতু
  d += g2(x, y, .062, 1.812, .048, .038, .042);              // নাসারন্ধ্র ডানা
  d += g2(x, y, -.062, 1.812, .048, .038, .042);
  d += g2(x, y, 0, 1.775, .07, .03, -.018);                  // নাকের নিচের ছায়া
  d += g2(x, y, EYE.x, 2.05, .088, .055, -.05);              // চোখের কোটর
  d += g2(x, y, -EYE.x, 2.05, .088, .055, -.05);
  const browA = female ? .038 : .06;
  d += g2(x, y, EYE.x + .005, 2.135, .105, .042, browA);     // ভ্রু হাড়
  d += g2(x, y, -EYE.x - .005, 2.135, .105, .042, browA);
  d += g2(x, y, 0, 2.125, .05, .05, .024);                   // দুই ভ্রুর মাঝ
  d += g2(x, y, .265, 1.93, .105, .085, .036);               // গালের হাড়
  d += g2(x, y, -.265, 1.93, .105, .085, .036);
  d += g2(x, y, 0, 1.755, .045, .035, .014);                 // ঠোঁটের ওপরের খাঁজ
  d += g2(x, y, 0, 1.705, .082, .027, .042);                 // ওপরের ঠোঁট
  d += g2(x, y, 0, 1.65, .068, .03, .052);                   // নিচের ঠোঁট
  d += g2(x, y, 0, 1.678, .088, .011, -.028);                // মুখের রেখা
  d += g2(x, y, 0, 1.585, .07, .05, .04);                    // থুতনি
  return d;
}

/* মাথার গায়ে একটা পয়েন্ট (শেডিং উজ্জ্বলতাসহ) */
function genHeadPoint(female) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  const y = rand(1.52, 2.62);
  const [rx, rz, cz] = rowAt(rows, y);
  let th;
  if (Math.random() < 0.55) th = Math.PI / 2 + rand(-0.88, 0.88);  // মুখের দিকে ঘন
  else th = Math.random() * Math.PI * 2;
  const fr = Math.sin(th);
  let x = rx * Math.cos(th);
  let z = cz + rz * fr;
  if (fr > 0.2) {
    z += faceFeatures(x, y, female) * clamp((fr - 0.2) / 0.5, 0, 1);
  }
  let b = shade(x * 1.7, (y - 2.02) * 0.85, z * 1.5);
  // চোখের কোটর ও মুখের রেখা গাঢ় ছায়া
  const de = Math.min(Math.hypot(x - EYE.x, y - 2.05), Math.hypot(x + EYE.x, y - 2.05));
  if (fr > 0.4 && de < 0.085) b *= 0.72;
  if (fr > 0.4 && Math.abs(y - 1.678) < 0.013 && Math.abs(x) < 0.15) b *= 0.5;
  return [x, y, z, b];
}

function pushPt(arr, x, y, z, col, bright, headW) {
  arr.push({
    x, y, z, headW,
    r: clamp(col.r * bright, 0, 2), g: clamp(col.g * bright, 0, 2), b: clamp(col.b * bright, 0, 2),
  });
}

function sampleHeadAll(out, female, faceCol) {
  for (let i = 0; i < 7600; i++) {
    const p = genHeadPoint(female);
    pushPt(out, p[0] + rand(-.004, .004), p[1] + rand(-.004, .004), p[2] + rand(-.004, .004), faceCol, p[3], 1);
  }
  // ঠোঁটে বাড়তি ঘনত্ব
  let lip = 0, guard = 0;
  while (lip < 500 && guard++ < 60000) {
    const p = genHeadPoint(female);
    if (p[1] > 1.615 && p[1] < 1.74 && Math.abs(p[0]) < 0.17 && p[2] > 0.12) {
      pushPt(out, p[0], p[1], p[2], faceCol, p[3] * 1.06, 1);
      lip++;
    }
  }
}

function sampleEyesBrows(out, female, faceCol, hairCol) {
  const rows = female ? HEAD_ROWS.female : HEAD_ROWS.male;
  const [rxE, rzE] = rowAt(rows, 2.03);
  const eyeCol = faceCol.clone().lerp(new THREE.Color(0xffffff), 0.72);
  for (const s of [1, -1]) {
    const cx = s * EYE.x;
    const zSock = rzE * Math.sqrt(Math.max(.05, 1 - (cx / rxE) ** 2)) - 0.05;
    // চোখের বল + আইরিস
    for (let i = 0; i < 150; i++) {
      const a = Math.random() * Math.PI * 2, rr = Math.sqrt(Math.random());
      const ex = cx + Math.cos(a) * rr * 0.052;
      const ey = EYE.y + Math.sin(a) * rr * 0.029;
      const ez = zSock + 0.006 + (1 - rr * rr) * 0.026;
      pushPt(out, ex, ey, ez, eyeCol, rr < 0.38 ? 1.85 : 1.25, 1);
    }
    // চোখের পাতার বাঁক (+মেয়েদের পাপড়ির দ্বিতীয় বাঁক)
    const arcs = female ? [0, 0.013] : [0];
    for (const off of arcs) {
      for (let i = 0; i < 45; i++) {
        const t = rand(0.12, 0.88) * Math.PI;
        const ex = cx + Math.cos(t) * (0.058 + off * 0.4);
        const ey = EYE.y + 0.006 + Math.sin(t) * (0.034 + off);
        pushPt(out, ex, ey, zSock + 0.012 + Math.sin(t) * 0.012, faceCol, 1.3, 1);
      }
    }
    // ভ্রু
    const [rxB, rzB] = rowAt(rows, 2.13);
    for (let i = 0; i < 200; i++) {
      const t = rand(-1, 1);
      const bx = cx + t * (female ? 0.082 : 0.096);
      const by = (female ? 2.155 : 2.142) + (female ? 0.03 : 0.014) * (1 - t * t) + rand(-1, 1) * (female ? 0.004 : 0.009);
      const bz = rzB * Math.sqrt(Math.max(.05, 1 - (bx / rxB) ** 2)) + (female ? 0.03 : 0.045);
      pushPt(out, bx, by, bz, hairCol, 1.18, 1);
    }
  }
  // কান (ছোট খোলস)
  const [rxEar] = rowAt(rows, 1.95);
  for (const s of [1, -1]) {
    for (let i = 0; i < 125; i++) {
      const a = Math.random() * Math.PI * 2, rr = Math.sqrt(Math.random());
      pushPt(out,
        s * (rxEar + 0.004 + rr * 0.02),
        1.95 + Math.sin(a) * rr * 0.085,
        -0.01 + Math.cos(a) * rr * 0.052,
        faceCol, 0.68, 1);
    }
  }
}

/* --- চুল --- */
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
      // কপালের চুলের লাইন — এর নিচে মুখ
      let hl;
      if (female) hl = 2.34 - 0.42 * Math.pow(clamp(Math.abs(x0) / 0.46, 0, 1), 1.6);
      else hl = 2.285 + 0.085 * Math.exp(-Math.pow((Math.abs(x0) - 0.27) / 0.09, 2));
      if (y < hl && guard < n * 45) continue;
    }
    const taper = y < 2.12 ? 1.045 : (female ? 1.1 : 1.09);
    let hx = x0 * taper + rand(-.01, .01);
    let hy = y + 0.03 + rand(-.01, .01);
    let hz = cz + rz * fr * taper - 0.012 + rand(-.01, .01);
    if (!female && fr > 0.3 && Math.abs(hx) < 0.3 && hy > 2.3) hy += 0.045 * (1 - Math.abs(hx) / 0.3); // ছেলেদের সামনের উঁচু ভাব
    const b = shade(hx * 1.6, (hy - 2.0), hz * 1.4) * 0.9;
    pushPt(out, hx, hy, hz, hairCol, b, 1);
    placed++;
  }
}

function sampleHairFemaleLong(out, hairCol) {
  // পেছনের ভলিউম খোলস
  let placed = 0, guard = 0;
  while (placed < 900 && guard++ < 60000) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const px = 0.52 * s * Math.cos(th), py = 1.82 + 0.8 * u, pz = -0.15 + 0.42 * s * Math.sin(th);
    if (pz > 0.1 || py < 1.02) continue;
    pushPt(out, px, py, pz, hairCol, shade(px * 1.5, py - 1.8, pz * 1.3) * 0.8, clamp((py - 0.9) / 1.3, 0.15, 1));
    placed++;
  }
  // ঢেউখেলানো গোছা (strands)
  const strands = [];
  for (let i = 0; i < 22; i++) {
    const phi = rand(-2.85, 2.85);
    if (Math.abs(phi) < 0.55) continue;               // মুখের সামনে ফাঁকা
    strands.push({ phi, len: rand(0.95, 1.35), waveF: rand(4.5, 7), waveP: rand(0, 6.28), hi: rand(0.82, 1.18), front: false });
  }
  strands.push({ phi: 0.66, len: 1.5, waveF: 5.2, waveP: 1.2, hi: 1.12, front: true });   // মুখের দুপাশের গোছা
  strands.push({ phi: -0.66, len: 1.5, waveF: 5.6, waveP: 4.0, hi: 1.12, front: true });
  const per = Math.floor(3000 / strands.length);
  strands.forEach((st) => {
    const ay = 2.32, R = 0.48;
    const ax = Math.sin(st.phi) * R, az = Math.cos(st.phi) * R * 0.92 - 0.03;
    const yEnd = ay - st.len;
    for (let i = 0; i < per; i++) {
      const t = Math.pow(Math.random(), 0.92);
      const y = ay + (yEnd - ay) * t;
      const radial = 1 + 0.14 * Math.sin(Math.min(t * 2.2, 1) * Math.PI * 0.5);
      let cx = ax * radial, cz = az * radial - 0.02 * t;
      if (st.front) { // কাঁধের সামনে এসে ঝোলে
        const k = clamp((t - 0.5) / 0.5, 0, 1);
        cz = lerp(cz, 0.3, k * k);
        cx = lerp(cx, Math.sign(ax) * 0.39, k * 0.6);
      }
      const wav = Math.sin(t * st.waveF + st.waveP) * 0.05 * (0.3 + t);
      cx += wav; cz += Math.cos(t * st.waveF + st.waveP) * 0.028 * (0.3 + t);
      const tubeR = 0.088 * (1 - t * 0.55);
      const ox = rand(-1, 1) * tubeR, oz = rand(-1, 1) * tubeR;
      const b = shade(cx * 1.5, (y - 1.9) * 0.8, cz * 1.4) * st.hi;
      pushPt(out, cx + ox, y + rand(-.02, .02), cz + oz, hairCol, b, clamp(1.12 - t * 1.02, 0.1, 1));
    }
  });
}

/* --- ঘাড় ও বুক (loft) --- */
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
    const r = rAt(y) * rand(0.98, 1.02);
    const th = Math.random() * Math.PI * 2;
    const fr = Math.sin(th);
    let x = r * Math.cos(th), z = r * zScale * fr;
    if (frontBumpFn && fr > 0.25) z += frontBumpFn(x, y) * clamp((fr - 0.25) / 0.5, 0, 1);
    const b = shade(Math.cos(th), 0.14, fr) * brightMul;
    const dim = y < 0.48 ? 0.55 + (y - 0.3) * 2.0 : 1;
    pushPt(out, x + rand(-.006, .006), y, z + rand(-.006, .006), col, b * clamp(dim, 0.5, 1), headWFn ? headWFn(y) : 0);
  }
  return rAt;
}

function buildBust(gender) {
  const female = gender === 'female';
  const base = new THREE.Color(COLORS[gender]);
  const faceCol = base.clone().multiplyScalar(1.08);
  const hairCol = base.clone(); hairCol.offsetHSL(female ? -0.035 : 0.02, 0.05, female ? -0.02 : 0.04);
  const chestCol = base.clone().multiplyScalar(0.85);

  const pts = [];
  sampleHeadAll(pts, female, faceCol);                 // 7600 + ঠোঁট 500
  sampleEyesBrows(pts, female, faceCol, hairCol);      // চোখ/পাতা/ভ্রু + কান
  if (female) {
    sampleHairCap(pts, 2100, true, hairCol);
    sampleHairFemaleLong(pts, hairCol);                // 900 খোলস + ~3000 গোছা
  } else {
    sampleHairCap(pts, 2600, false, hairCol);
  }

  const neckRows = female
    ? [[1.50, .135], [1.38, .14], [1.26, .165], [1.16, .26], [1.10, .34]]
    : [[1.50, .155], [1.38, .165], [1.26, .19], [1.16, .30], [1.10, .38]];
  sampleLoft(pts, 800, neckRows, 0.88, base.clone().multiplyScalar(0.95), 0.95,
    (y) => 0.55 * clamp((y - 1.12) / 0.38, 0, 1), null);

  const chestRows = female
    ? [[1.12, .52], [1.06, .78], [1.00, .88], [0.88, .90], [0.72, .84], [0.55, .76], [0.40, .66], [0.30, .58]]
    : [[1.12, .60], [1.06, .90], [1.00, 1.02], [0.88, 1.05], [0.72, .97], [0.55, .87], [0.40, .76], [0.30, .68]];
  const bustBump = female
    ? (x, y) => g2(x, y, .23, .72, .15, .13, .05) + g2(x, y, -.23, .72, .15, .13, .05)
    : null;
  const chestQuota = N - pts.length - 300;
  const rChest = sampleLoft(pts, Math.max(chestQuota, 100), chestRows, 0.55, chestCol, 0.9, null, bustBump);

  // কলারবোনের রেখা (উজ্জ্বল)
  for (const s of [1, -1]) {
    for (let i = 0; i < 150; i++) {
      const t = Math.random();
      const x = s * (0.07 + t * 0.52);
      const y = 1.145 - t * 0.05 + rand(-.007, .007);
      const rx = rChest(clamp(y, 0.3, 1.12));
      const z = rx * 0.55 * Math.sqrt(Math.max(.04, 1 - (x / rx) ** 2)) + 0.01;
      pushPt(pts, x, y, z, faceCol, 1.12, 0);
    }
  }
  // ঠিক N সংখ্যায় মেলানো
  while (pts.length > N) pts.pop();
  while (pts.length < N) {
    const p = genHeadPoint(female);
    pushPt(pts, p[0], p[1], p[2], faceCol, p[3], 1);
  }

  const targets = new Float32Array(N * 3);
  const colors = new Float32Array(N * 3);
  const headW = new Float32Array(N);
  const delay = new Float32Array(N);
  pts.forEach((p, i) => {
    targets[i * 3] = p.x; targets[i * 3 + 1] = p.y; targets[i * 3 + 2] = p.z;
    colors[i * 3] = p.r; colors[i * 3 + 1] = p.g; colors[i * 3 + 2] = p.b;
    headW[i] = p.headW;
    delay[i] = clamp((p.y - 0.3) / 2.35, 0, 1) * 0.5 + Math.random() * 0.5;
  });
  return { targets, colors, headW, delay };
}

/* --- Three.js দৃশ্য --- */
function initHologram() {
  if (typeof THREE === 'undefined') {
    setHoloStatus('⚠️ Three.js লোড হয়নি — ui/vendor/three.min.js আছে কিনা দেখো');
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

  { // তারা
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
    const m = new THREE.MeshBasicMaterial({ color: COLORS[HOLO.gender], transparent: true, opacity: op, side: THREE.DoubleSide, depthWrite: false });
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
    new THREE.MeshBasicMaterial({ color: COLORS[HOLO.gender], transparent: true, opacity: 0.05, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
  beam.material.userData.baseOp = 0.05;
  HOLO.accentMats.push(beam.material);
  beam.position.y = 0.17;
  disc.add(beam);
  world.add(disc);

  const scan = new THREE.Mesh(new THREE.RingGeometry(1.14, 1.18, 72), accentMat(0.5));
  scan.rotation.x = -Math.PI / 2;
  world.add(scan);
  HOLO.scanMat = scan.material;

  /* পার্টিকেল বাস্ট */
  const built = buildBust(HOLO.gender);
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
    size: 0.0235, vertexColors: true, transparent: true, opacity: 0.95,
    blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
  });
  const bust = new THREE.Points(geo, pMat);
  world.add(bust);

  HOLO.applyBust = (gender) => {
    const b = buildBust(gender);
    targets = b.targets; headW = b.headW; delay = b.delay;
    geo.attributes.color.array.set(b.colors);
    geo.attributes.color.needsUpdate = true;
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
      if (HOLO.formT <= 0 && HOLO.pendingGender) {
        HOLO.applyBust(HOLO.pendingGender);
        HOLO.pendingGender = null;
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
      const ph = phase[i];
      const shim = Math.sin(t * 2.3 + ph) * (0.0045 + sb * 0.01 * headW[i]) * e;
      const rl = Math.sqrt(x * x + z * z) || 1e-4;
      x += (x / rl) * shim; z += (z / rl) * shim;
      y += Math.sin(t * 1.7 + ph * 1.3) * 0.0032 * e;

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

    bust.position.y = Math.sin(t * 1.12) * 0.028;
    if (!HOLO.dragging && HOLO.power) HOLO.autoRot += dt * 0.09;
    world.rotation.y += ((HOLO.targetRotY + HOLO.autoRot) - world.rotation.y) * 0.08;
    arc1.rotation.z = t * 0.5;
    arc2.rotation.z = -t * 0.7;

    const cyc = (t * 0.38) % 1;
    scan.position.y = 0.3 + cyc * 2.4;
    HOLO.scanMat.opacity = (HOLO.power ? 0.5 : 0) * Math.sin(cyc * Math.PI) * formT;

    pMat.opacity += ((HOLO.power ? 0.95 : 0.04) - pMat.opacity) * 0.08;
    HOLO.accentMats.forEach((m) => {
      if (m === HOLO.scanMat) return;
      const bse = m.userData.baseOp !== undefined ? m.userData.baseOp : 0.9;
      m.opacity += ((HOLO.power ? bse : bse * 0.06) - m.opacity) * 0.08;
    });

    setHoloState(!HOLO.power ? 'OFFLINE' : (formT < 0.985 ? 'FORMING…' : (sb > 0.35 ? 'SPEAKING' : 'IDLE // LISTENING')));
    renderer.render(scene, camera);
  })();
}

function syncGenderUI() {
  document.querySelectorAll('[data-gender]').forEach((el) => {
    el.classList.toggle('active', el.dataset.gender === HOLO.gender);
  });
  document.body.classList.toggle('female', HOLO.gender === 'female');
  HOLO.accentMats.forEach((m) => { if (m.color && !m.userData.lockColor) m.color.setHex(COLORS[HOLO.gender]); });
}
function setGender(gender) {
  if (gender === HOLO.gender && HOLO.mode === 'in' && HOLO.formT > 0.9) return;
  HOLO.gender = gender;
  localStorage.setItem('stonic_gender', gender);
  HOLO.pendingGender = gender;
  HOLO.mode = 'out';
  syncGenderUI();
  setHoloStatus(gender === 'female'
    ? '👩 Female কোর — নতুন মুখে গঠন হচ্ছে…'
    : '👨 Male কোর — নতুন মুখে গঠন হচ্ছে…');
}
function reform() {
  if (!HOLO.power) { toast('⏻ আগে ACTIVATE চেপে চালু করো, তারপর আবার গঠন হবো!'); return; }
  HOLO.pendingGender = HOLO.gender;
  HOLO.mode = 'out';
  setHoloStatus('✨ আবার গঠন হচ্ছি… ডটগুলোর খেলা দেখো!');
}

/* =========================================================
   SAT-LINK ডটেড বিশ্ব মানচিত্র (নিজস্ব সরল মহাদেশ-রেখা)
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
    const sx = w / 200, sy = h / 100;
    const step = 3.4;
    for (let gy = 2; gy < h - 2; gy += step) {
      for (let gx = 2; gx < w - 2; gx += step) {
        const mx = gx / sx, my = gy / sy;
        let land = false;
        for (const poly of CONTINENTS) { if (inPoly(poly, mx, my)) { land = true; break; } }
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

/* =========================================================
   সার্কিট লাইন — মডিউল চিপ → হলোগ্রাম ফ্রেম
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
    const col = CHIP_COLORS[chip.dataset.pop] || '#22d3ee';
    const x1 = r.right - zr.left, y1 = r.top - zr.top + r.height / 2;
    const x2 = sr.left - zr.left, y2 = sr.top - zr.top + sr.height * (fracs[i] || 0.5);
    const mx = (x1 + x2) / 2;
    s += `<path d="M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}" stroke="${col}"/>`;
    s += `<circle cx="${x1}" cy="${y1}" r="3.2" fill="${col}"/><circle cx="${x2}" cy="${y2}" r="2.8" fill="${col}"/>`;
  });
  svg.innerHTML = s;
}

/* =========================================================
   কথা বলার ডেমো (ধাপ ৫/৬-এর আভাস)
   ========================================================= */
function speakDemo(text) {
  if (!HOLO.power) return;
  HOLO.speaking = true;
  setHoloStatus('🗣️ Stonic কথা বলছে…');
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    HOLO.speaking = false;
    setHoloStatus('🟢 Stonic শুনছে…');
  };
  setTimeout(finish, Math.min(900 + text.length * 65, 9000));
  if ('speechSynthesis' in window) {
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'bn-BD';
      u.pitch = HOLO.gender === 'female' ? 1.3 : 0.85;
      u.rate = 1.0;
      const voices = speechSynthesis.getVoices();
      const match = voices.find((v) => /^(bn|hi)/i.test(v.lang)) ||
        voices.find((v) => (HOLO.gender === 'female'
          ? /female|zira|samantha|Jenny|veena/i.test(v.name)
          : /male|david|daniel|ravi/i.test(v.name)));
      if (match) u.voice = match;
      u.onend = finish;
      u.onerror = finish;
      speechSynthesis.speak(u);
    } catch (e) { /* ভয়েস না থাকলেও অ্যানিমেশন চলবে */ }
  }
}

/* =========================================================
   চ্যাট ডেমো (আসল AI ধাপ ৩-এ)
   ========================================================= */
const demoReplies = [
  'তোমার বার্তা পেয়েছি! এখন আমি শেখার পর্যায়ে আছি — ধাপ ৩-এ Gemini আর Groq যুক্ত হলেই সত্যিকারের উত্তর দিতে পারবো। নতুন মুখটা কেমন লাগলো?',
  'দেখলে, কথা বলার সময় আমার মাথাটা নড়ে! ধাপ ৫-এ আসল ভয়েস আর ধাপ ৬-এ পুরো সিঙ্ক অ্যানিমেশন পাবো।',
  'ওপরের ♀ FEMALE / ♂ MALE বদলে দেখো — আমার ডটগুলো ভেঙে আবার নতুন মুখে গড়ে ওঠে!',
  'ধাপ ৪ থেকে তুমি যা বলবে — তোমার নাম, পছন্দ, অনুভূতি — সব মনে রাখবো, ঠিক তোমার ল্যাপটপের ভেতরে, নিরাপদে।',
];
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
    btn.title = 'পড়ে শোনাও (ডেমো)';
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
  setHoloStatus('🤔 Stonic ভাবছে…');
  setHoloState('THINKING…');
  const typing = addMsg('', 'ai');
  typing.innerHTML = '<span class="typing">•••</span>';
  setTimeout(() => {
    const reply = demoReplies[demoIdx++ % demoReplies.length];
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
   পাওয়ার / TERMINATE
   ========================================================= */
function setPower(on) {
  HOLO.power = on;
  document.body.classList.toggle('power-off', !on);
  const btn = $('terminateBtn');
  if (btn) {
    btn.textContent = on ? '⏻ TERMINATE — বন্ধ করো' : '▶ ACTIVATE — চালু করো';
    btn.classList.toggle('is-off', !on);
  }
  if (!on) {
    HOLO.speaking = false;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    closePopover();
    setHoloStatus('⏻ সিস্টেম বন্ধ — ACTIVATE চাপলেই ডটগুলো আবার গঠন হবে');
    toast('⏻ Stonic বন্ধ হলো — ডটগুলো ছড়িয়ে যাচ্ছে। আবার জাগাতে ACTIVATE চাপো।');
  } else {
    setHoloStatus('✨ ফিরে এসেছি — ডটগুলো জড়ো হচ্ছে…');
    toast('🤖 Stonic চালু! মুখটা গঠন হতে দেখো।');
  }
}

/* =========================================================
   পপওভার (মডিউল চিপ)
   ========================================================= */
const POP_TITLES = {
  memory: 'MEMORY — স্মৃতি',
  skills: 'SKILLS — দক্ষতা',
  character: 'CHARACTER — চরিত্র',
  setting: 'SETTING — সেটিংস',
};
let openPopName = null;
function openPopover(name) {
  openPopName = name;
  $('popover').classList.remove('hidden');
  $('popoverTitle').textContent = POP_TITLES[name] || name;
  document.querySelectorAll('.pop-body').forEach((el) => el.classList.add('hidden'));
  const body = $('pop-' + name);
  if (body) body.classList.remove('hidden');
  document.querySelectorAll('.mod-chip').forEach((c) => c.classList.toggle('active', c.dataset.pop === name));
}
function closePopover() {
  openPopName = null;
  const p = $('popover');
  if (p) p.classList.add('hidden');
  document.querySelectorAll('.mod-chip').forEach((c) => c.classList.remove('active'));
}

/* =========================================================
   Visual Hub — ক্যামেরা/স্ক্রিন স্টেট (আসল অ্যাক্সেস ধাপ ৯)
   ========================================================= */
function setVisual(kind, on, silent) {
  const camT = $('cameraToggle'), scrT = $('screenToggle');
  if (kind === 'cam') camT.checked = on; else scrT.checked = on;
  const cam = camT.checked, scr = scrT.checked;
  $('camIndicator').classList.toggle('hidden', !(cam || scr));
  $('camChip').textContent = 'CAM · ' + (cam ? 'ON' : 'OFF');
  $('camChip').classList.toggle('on', cam);
  $('scrChip').textContent = 'SCREEN · ' + (scr ? 'ON' : 'OFF');
  $('scrChip').classList.toggle('on', scr);
  $('vhCamBtn').classList.toggle('on', cam);
  $('vhScrBtn').classList.toggle('on', scr);
  if (!silent) {
    toast(on
      ? '🔴 এখন এটি শুধু ইন্ডিকেটর ডেমো — ক্যামেরা/স্ক্রিন সত্যিই চালু হচ্ছে না। আসল অনুমতি-ভিত্তিক অ্যাক্সেস ধাপ ৯-এ আসবে, তখনও ON থাকলে এই লাল সতর্কতা জ্বলবে।'
      : '✅ বন্ধ করা হয়েছে — এখন আমি কিছুই দেখতে পাচ্ছি না।', 4600);
  }
}

/* =========================================================
   ইভেন্ট ওয়্যারিং
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  initHologram();
  initMap();
  syncGenderUI();
  setTimeout(drawWires, 350);
  let rT = null;
  window.addEventListener('resize', () => { clearTimeout(rT); rT = setTimeout(drawWires, 160); });

  /* ঘড়ি */
  const tick = () => { const el = $('clock'); if (el) el.textContent = new Date().toLocaleTimeString('en-GB'); };
  tick(); setInterval(tick, 1000);

  /* সার্ভার হেলথ */
  const checkHealth = () => {
    if (location.protocol === 'file:') {
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = 'প্রিভিউ মোড (সার্ভার ছাড়া)';
      return;
    }
    fetch('/api/health').then((r) => r.json()).then((d) => {
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = `সার্ভার সংযুক্ত ✅ (ধাপ ${d.stage})`;
    }).catch(() => {
      $('serverDot').className = 'dot dot-off';
      $('serverText').textContent = 'সার্ভার সংযোগ নেই ❌';
    });
  };
  checkHealth();
  setInterval(checkHealth, 20000);

  /* TERMINATE / ACTIVATE */
  $('terminateBtn').addEventListener('click', () => setPower(!HOLO.power));

  /* Female/Male — পিল + পপওভারের বাটন */
  document.querySelectorAll('[data-gender]').forEach((el) => {
    el.addEventListener('click', () => {
      if (!HOLO.power) { toast('⏻ সিস্টেম বন্ধ আছে — আগে ACTIVATE চাপো!'); return; }
      setGender(el.dataset.gender);
      toast(el.dataset.gender === 'female'
        ? '👩 Female কোর — ডটগুলো ভেঙে মেয়ের মুখে গড়ে উঠছে!'
        : '👨 Male কোর — ডটগুলো ভেঙে ছেলের মুখে গড়ে উঠছে!');
    });
  });
  $('reformBtn').addEventListener('click', reform);

  /* মডিউল চিপ → পপওভার */
  document.querySelectorAll('.mod-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      if (openPopName === chip.dataset.pop) closePopover();
      else openPopover(chip.dataset.pop);
    });
  });
  $('popoverClose').addEventListener('click', closePopover);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePopover(); });

  /* মোড ট্যাব */
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.mode-panel').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      $('mode-' + tab.dataset.mode).classList.add('active');
    });
  });

  /* চ্যাট + মাইক */
  $('sendBtn').addEventListener('click', sendChat);
  $('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });
  const micNotice = () => toast('🎤 ভয়েস সিস্টেম ধাপ ৫-এ আসবে — তখন মুখে বললেই হবে, কথা শেষ হলে তবেই আমি উত্তর দেবো!');
  $('micBtn').addEventListener('click', micNotice);
  $('bigMicBtn').addEventListener('click', micNotice);

  /* Agent ডেমো */
  const runAgentDemo = () => {
    const task = $('agentInput').value.trim() || '(খালি নির্দেশ)';
    const log = $('agentLog');
    log.textContent = `📝 নির্দেশ পেয়েছি: "${task}"\n`;
    setTimeout(() => { log.textContent += '⏳ ধাপ ৮-এ চালু হলে আমি এখন ব্রাউজার খুলতাম…\n'; }, 600);
    setTimeout(() => { log.textContent += '🔍 নিজে সার্চ করে রেজাল্ট পড়ে সামারি রিপোর্ট দিতাম।\n✅ এখন এটি শুধু ডেমো লেআউট।'; }, 1400);
  };
  $('agentBtn').addEventListener('click', runAgentDemo);
  $('agentInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') runAgentDemo(); });

  /* Notes ডেমো */
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

  /* API Key (ধাপ ২) */
  $('saveKeys').addEventListener('click', () => {
    $('geminiKey').value = '';
    $('groqKey').value = '';
    toast('⚠️ ধাপ ১-এ Key কোথাও সেভ হচ্ছে না — সেভ সিস্টেম ধাপ ২-এ আসবে। নিরাপত্তার জন্য ইনপুট খালি করে দিলাম। আসল Key কারো সাথে শেয়ার কোরো না!', 5200);
  });

  /* ক্যামেরা/স্ক্রিন — সেটিংসের সুইচ ও Visual Hub বাটন একই স্টেট */
  $('cameraToggle').addEventListener('change', (e) => setVisual('cam', e.target.checked));
  $('screenToggle').addEventListener('change', (e) => setVisual('scr', e.target.checked));
  $('vhCamBtn').addEventListener('click', () => setVisual('cam', !$('cameraToggle').checked));
  $('vhScrBtn').addEventListener('click', () => setVisual('scr', !$('screenToggle').checked));
  document.querySelectorAll('.vh-suggest').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelector('[data-mode="voice"]').click();
      $('chatInput').value = btn.dataset.vh;
      $('chatInput').focus();
      toast('👁️ Visual Hub-এর আসল দেখার ক্ষমতা ধাপ ৯-এ আসবে — নির্দেশটা চ্যাটবাক্সে বসিয়ে দিলাম, চাইলে পাঠিয়ে ডেমো দেখো!');
    });
  });

  /* Skills টগল (localStorage) */
  const saved = JSON.parse(localStorage.getItem('stonic_skills') || '{}');
  document.querySelectorAll('.skill-toggle').forEach((tg) => {
    if (tg.dataset.skill in saved) tg.checked = saved[tg.dataset.skill];
    tg.addEventListener('change', () => {
      saved[tg.dataset.skill] = tg.checked;
      localStorage.setItem('stonic_skills', JSON.stringify(saved));
      toast(`🧩 স্কিল ${tg.checked ? 'চালু ✅' : 'বন্ধ ⛔'} — পছন্দটা ব্রাউজারে সেভ হলো (আসল স্কিল ইঞ্জিন ধাপ ৭-এ)।`);
    });
  });

  /* World ফিড রিফ্রেশ (ধাপ ১০) */
  $('refreshNews').addEventListener('click', () => {
    toast('🌍 লাইভ নিউজ ধাপ ১০-এ আসবে — তখন মানচিত্রের হটস্পটে আসল ঘটনা আর নিচে সত্যিকারের হেডলাইন থাকবে, চাইলে পড়েও শোনাবো!');
  });

  /* Personality */
  $('personality').addEventListener('change', (e) => {
    toast(`🎭 ব্যক্তিত্ব সিলেক্ট: "${e.target.value}" — এই সেটিং ধাপ ৩ থেকে আমার উত্তরে প্রভাব ফেলবে।`);
  });

  toast('✨ নতুন CORE জাগছে — ডটগুলো মুখের আকারে গঠন হওয়া দেখো! বামের চিপগুলোতে (MEMORY / SKILLS / CHARACTER / SETTING) চেপে প্যানেল খুলতে পারো।', 6200);
});
