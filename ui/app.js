/* =========================================================
   Stonic AI — System Core UI (ধাপ ১, v2)
   পার্টিকেল বাস্ট হলোগ্রাম (বুক থেকে উপরে): ডটগুলো ছড়ানো
   মেঘ থেকে ঘুরে এসে ছেলে/মেয়ের আকারে গঠন হয়।
   ধাপ ৩ থেকে চ্যাট আসল API-তে যাবে; এখন ডেমো উত্তর।
   ========================================================= */
'use strict';

/* ---------- ছোট হেল্পার ---------- */
const $ = (id) => document.getElementById(id);
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
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rand = (a, b) => a + Math.random() * (b - a);

/* =========================================================
   CORE হলোগ্রাম — পার্টিকেল বাস্ট (formation animation)
   ========================================================= */
const N = 12000;                       // মোট পার্টিকেল সংখ্যা
const COLORS = { male: 0x22d3ee, female: 0xe879f9 };
const HOLO = {
  gender: localStorage.getItem('stonic_gender') || 'male',
  power: true,
  speaking: false,
  speakBlend: 0,
  formT: 0,            // 0 = ছড়ানো মেঘ, 1 = পূর্ণ আকার
  mode: 'in',          // 'in' গঠন হচ্ছে | 'out' ভাঙছে (তারপর নতুন আকার)
  pendingGender: null,
  targetRotY: 0,
  autoRot: 0,
  dragging: false,
  accentMats: [],      // ডিস্ক/রিং ম্যাটেরিয়াল (রঙ বদলের জন্য)
};

/* --- বাস্টের গায়ে পয়েন্ট স্যাম্পলিং --- */
function sampleHead(out, n, cfg, col) {
  // মাথা: এলিপসয়েড + চোয়াল/চিবুকের আকৃতি; সামনের দিকে (মুখ) ঘন
  let placed = 0, guard = 0;
  while (placed < n && guard++ < n * 40) {
    const u = Math.random() * 2 - 1;
    const th = Math.random() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const dx = s * Math.cos(th), dy = u, dz = s * Math.sin(th);
    if (Math.random() > 0.45 + 0.55 * Math.max(dz, 0)) continue; // মুখের দিকে ঘনত্ব বেশি
    let taper = 1;
    if (dy < 0) taper = 1 - cfg.jaw * Math.pow(-dy, 1.4);        // চিবুক সরু
    const x = cfg.cx + cfg.rx * dx * taper;
    const y = cfg.cy + cfg.ry * dy;
    let z = cfg.cz + cfg.rz * dz * (dy < 0 ? 1 - cfg.jaw * 0.5 * Math.pow(-dy, 1.4) : 1);
    if (dz > 0.8) z *= 0.97;                                     // মুখ সামান্য চ্যাপ্টা
    out.push([x + rand(-.006, .006), y + rand(-.006, .006), z + rand(-.006, .006), col, 1]);
    placed++;
  }
}

function sampleHairMale(out, n, cfg, col) {
  // ছেলেদের ছোট চুল: মাথার ওপরের ক্যাপ
  let placed = 0, guard = 0;
  while (placed < n && guard++ < n * 40) {
    const u = Math.random() * 2 - 1;
    const th = Math.random() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const dx = s * Math.cos(th), dy = u, dz = s * Math.sin(th);
    const ok = dy > 0.02 || (dz < -0.15 && dy > -0.45) || (Math.abs(dx) > 0.75 && dy > -0.25);
    if (!ok) continue;
    out.push([
      cfg.cx + cfg.rx * 1.09 * dx + rand(-.01, .01),
      cfg.cy + cfg.ry * 1.09 * dy + 0.025 + rand(-.01, .01),
      cfg.cz + cfg.rz * 1.09 * dz + rand(-.01, .01), col, 1]);
    placed++;
  }
}

function sampleHairFemale(out, n, cfg, col) {
  // মেয়েদের লম্বা চুল: ওপরের খোলস + দুই পাশে/পিছনে কাঁধ পর্যন্ত ঝোলা পর্দা
  const topN = Math.floor(n * 0.45), curtainN = n - topN;
  let placed = 0, guard = 0;
  while (placed < topN && guard++ < topN * 40) {
    const u = Math.random() * 2 - 1;
    const th = Math.random() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const dx = s * Math.cos(th), dy = u, dz = s * Math.sin(th);
    if (dy < -0.15 && dz > 0.25) continue; // মুখের জানালা খালি রাখো
    out.push([
      cfg.cx + cfg.rx * 1.11 * dx + rand(-.012, .012),
      cfg.cy + cfg.ry * 1.10 * dy + 0.03 + rand(-.012, .012),
      cfg.cz + cfg.rz * 1.11 * dz + rand(-.012, .012), col, 1]);
    placed++;
  }
  const prof = [[2.05, 0.54], [1.72, 0.63], [1.38, 0.61], [1.12, 0.55], [1.0, 0.5]];
  const rAt = (y) => {
    for (let i = 0; i < prof.length - 1; i++) {
      const [y1, r1] = prof[i], [y2, r2] = prof[i + 1];
      if (y <= y1 && y >= y2) return r1 + (r2 - r1) * ((y1 - y) / (y1 - y2));
    }
    return prof[prof.length - 1][1];
  };
  for (let i = 0; i < curtainN; i++) {
    const y = rand(1.0, 2.05);
    let phi = rand(-Math.PI, Math.PI);
    if (y < 1.92 && Math.abs(phi) < 0.82) phi = (phi < 0 ? -1 : 1) * rand(0.82, Math.PI); // সামনে মুখ খোলা
    const r = rAt(y) * rand(0.96, 1.05);
    const headW = 0.25 + 0.75 * clamp((y - 1.0) / 1.0, 0, 1); // ডগা কম নড়ে
    out.push([
      Math.sin(phi) * r + rand(-.015, .015),
      y + rand(-.012, .012),
      Math.cos(phi) * r * 0.94 - 0.03 + rand(-.015, .015), col, headW]);
  }
}

function sampleRings(out, n, yMin, yMax, profile, zScale, col, headWFn) {
  const rAt = (y) => {
    for (let i = 0; i < profile.length - 1; i++) {
      const [y1, r1] = profile[i], [y2, r2] = profile[i + 1];
      if (y <= y1 && y >= y2) return r1 + (r2 - r1) * ((y1 - y) / (y1 - y2));
    }
    return y > profile[0][0] ? profile[0][1] : profile[profile.length - 1][1];
  };
  for (let i = 0; i < n; i++) {
    const y = rand(yMin, yMax);
    const r = rAt(y) * rand(0.97, 1.03);
    const a = Math.random() * Math.PI * 2;
    out.push([
      r * Math.cos(a) + rand(-.008, .008),
      y,
      r * zScale * Math.sin(a) + rand(-.008, .008),
      col, headWFn ? headWFn(y) : 0]);
  }
}

/* সম্পূর্ণ বাস্টের target অবস্থান + রঙ + head-weight বানায় */
function buildBust(gender) {
  const female = gender === 'female';
  const base = new THREE.Color(COLORS[gender]);
  const faceCol = base.clone().multiplyScalar(1.12);
  const hairCol = base.clone(); hairCol.offsetHSL(female ? -0.035 : 0.02, 0.04, female ? -0.03 : 0.05);
  const chestCol = base.clone().multiplyScalar(0.8);

  const headCfg = {
    cx: 0, cy: 1.95, cz: 0,
    rx: female ? 0.47 : 0.50, ry: female ? 0.59 : 0.62, rz: female ? 0.52 : 0.55,
    jaw: female ? 0.36 : 0.2,
  };
  const pts = [];
  sampleHead(pts, 4300, headCfg, faceCol);
  if (female) sampleHairFemale(pts, 2800, headCfg, hairCol);
  else sampleHairMale(pts, 1700, headCfg, hairCol);
  // ঘাড়
  const neckR = female ? 0.14 : 0.165;
  sampleRings(pts, 500, 1.04, 1.44, [[1.44, neckR], [1.04, neckR * 1.12]], 0.88,
    base.clone().multiplyScalar(0.95), (y) => 0.1 + 0.5 * clamp((y - 1.04) / 0.4, 0, 1));
  // বুক + কাঁধ (ঢাল হয়ে ঘাড়ে মেশে)
  const chestProfile = female
    ? [[1.28, 0.5], [1.14, 0.84], [1.0, 0.91], [0.7, 0.81], [0.35, 0.63]]
    : [[1.28, 0.58], [1.14, 0.96], [1.0, 1.05], [0.7, 0.93], [0.35, 0.72]];
  sampleRings(pts, N - pts.length, 0.35, 1.28, chestProfile, 0.54, chestCol, null);

  const targets = new Float32Array(N * 3);
  const colors = new Float32Array(N * 3);
  const headW = new Float32Array(N);
  const delay = new Float32Array(N);
  pts.forEach((p, i) => {
    targets[i * 3] = p[0]; targets[i * 3 + 1] = p[1]; targets[i * 3 + 2] = p[2];
    // বাস্টের নিচের কিনারা হালকা ফেড
    const dim = p[1] < 0.52 ? 0.55 + (p[1] - 0.35) * 2.2 : 1;
    colors[i * 3] = p[3].r * dim; colors[i * 3 + 1] = p[3].g * dim; colors[i * 3 + 2] = p[3].b * dim;
    headW[i] = p[4];
    delay[i] = clamp((p[1] - 0.35) / 2.2, 0, 1) * 0.5 + Math.random() * 0.5; // নিচ থেকে উপরে গঠন
  });
  return { targets, colors, headW, delay };
}

function initHologram() {
  if (typeof THREE === 'undefined') {
    setHoloStatus('⚠️ Three.js লোড হয়নি — ui/vendor/three.min.js ফাইলটি আছে কিনা দেখো');
    return;
  }
  const canvas = $('holoCanvas');
  const wrap = canvas.parentElement;
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6)); // 8GB RAM-এ পারফরম্যান্স
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
  camera.position.set(0, 1.62, 4.4);
  camera.lookAt(0, 1.32, 0);

  const world = new THREE.Group();   // ড্র্যাগ/অটো-রোটেশন এখানে
  scene.add(world);

  /* তারা */
  {
    const sp = [];
    for (let i = 0; i < 420; i++) sp.push(rand(-8, 8), rand(-0.4, 6.4), rand(-6, 2.5));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
    const m = new THREE.PointsMaterial({ color: 0x7dd3fc, size: 0.02, transparent: true, opacity: 0.5, depthWrite: false });
    m.userData.baseOp = 0.5;
    HOLO.accentMats.push(m);
    scene.add(new THREE.Points(g, m));
  }

  /* প্রজেক্টর ডিস্ক + ঘূর্ণায়মান আর্ক + আলোর বীম */
  const accentMat = (op) => {
    const m = new THREE.MeshBasicMaterial({ color: COLORS[HOLO.gender], transparent: true, opacity: op, side: THREE.DoubleSide, depthWrite: false });
    m.userData.baseOp = op;
    HOLO.accentMats.push(m);
    return m;
  };
  const disc = new THREE.Group();
  const mkRing = (inner, outer, op, thetaLen) => {
    const mesh = new THREE.Mesh(
      new THREE.RingGeometry(inner, outer, 72, 1, 0, thetaLen || Math.PI * 2), accentMat(op));
    mesh.rotation.x = -Math.PI / 2;
    disc.add(mesh);
    return mesh;
  };
  mkRing(1.18, 1.25, 0.85);
  mkRing(0.86, 0.9, 0.5);
  const arc1 = mkRing(1.02, 1.08, 0.9, Math.PI * 0.7);
  const arc2 = mkRing(0.68, 0.73, 0.9, Math.PI * 0.5);
  const glowDisc = new THREE.Mesh(new THREE.CircleGeometry(0.66, 48), accentMat(0.1));
  glowDisc.rotation.x = -Math.PI / 2; glowDisc.position.y = 0.005;
  disc.add(glowDisc);
  const beam = new THREE.Mesh(
    new THREE.CylinderGeometry(0.98, 0.3, 0.38, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: COLORS[HOLO.gender], transparent: true, opacity: 0.05, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
  beam.material.userData.baseOp = 0.05;
  HOLO.accentMats.push(beam.material);
  beam.position.y = 0.19;
  disc.add(beam);
  world.add(disc);

  /* স্ক্যান রিং */
  const scan = new THREE.Mesh(new THREE.RingGeometry(1.12, 1.16, 72), accentMat(0.5));
  scan.rotation.x = -Math.PI / 2;
  world.add(scan);
  HOLO.scanMat = scan.material;

  /* --- পার্টিকেল বাস্ট --- */
  const built = buildBust(HOLO.gender);
  let targets = built.targets, headW = built.headW, delay = built.delay;

  const scatter = new Float32Array(N * 3);
  const orbit = new Float32Array(N);
  const phase = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    const r = rand(1.7, 3.3);
    scatter[i * 3] = r * s * Math.cos(th);
    scatter[i * 3 + 1] = 1.45 + r * u * 0.78;
    scatter[i * 3 + 2] = r * s * Math.sin(th);
    orbit[i] = rand(2.2, 4.6);              // একই দিকে ঘূর্ণি
    phase[i] = Math.random() * Math.PI * 2;
  }

  const positions = new Float32Array(scatter);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(built.colors, 3));
  const pMat = new THREE.PointsMaterial({
    size: 0.032, vertexColors: true, transparent: true, opacity: 0.95,
    blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
  });
  const bust = new THREE.Points(geo, pMat);
  world.add(bust);
  HOLO.bustGroup = world;

  /* gender বদলে নতুন টার্গেট বসানো (ভাঙার পর ডাকা হয়) */
  HOLO.applyBust = (gender) => {
    const b = buildBust(gender);
    targets = b.targets; headW = b.headW; delay = b.delay;
    geo.attributes.color.array.set(b.colors);
    geo.attributes.color.needsUpdate = true;
  };

  /* ড্র্যাগ রোটেশন */
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

    /* --- গঠন/ভাঙা স্টেট মেশিন --- */
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
      HOLO.formT = Math.min(1, HOLO.formT + dt * 0.42);
    }
    const formT = HOLO.formT;
    const formed = clamp((formT - 0.72) / 0.28, 0, 1); // মাথা নড়া শুরু হয় গঠন শেষের দিকে

    /* speaking ব্লেন্ড */
    const sTarget = (HOLO.speaking && HOLO.power) ? 1 : 0;
    HOLO.speakBlend += (sTarget - HOLO.speakBlend) * 0.07;
    const sb = HOLO.speakBlend;

    /* মাথার নড়াচড়া কোণ */
    const nodA = (0.02 * Math.sin(t * 1.2) + sb * 0.09 * Math.sin(t * 7.3)) * formed;
    const tiltA = (0.015 * Math.sin(t * 0.9 + 1) + sb * 0.05 * Math.sin(t * 3.0)) * formed;
    const cosN = Math.cos(nodA), sinN = Math.sin(nodA);
    const cosT2 = Math.cos(tiltA), sinT2 = Math.sin(tiltA);
    const PIVOT_Y = 1.3;

    /* --- প্রতিটা পার্টিকেলের অবস্থান --- */
    const pos = geo.attributes.position.array;
    for (let i = 0; i < N; i++) {
      const i3 = i * 3;
      let p = clamp((formT - delay[i] * 0.45) / 0.55, 0, 1);
      const e = 1 - Math.pow(1 - p, 3);
      let x = scatter[i3] + (targets[i3] - scatter[i3]) * e;
      let y = scatter[i3 + 1] + (targets[i3 + 1] - scatter[i3 + 1]) * e;
      let z = scatter[i3 + 2] + (targets[i3 + 2] - scatter[i3 + 2]) * e;

      /* ঘূর্ণি: গঠনের পথে প্যাঁচ খেয়ে আসে */
      const sw = (1 - e) * (1 - e) * orbit[i];
      if (sw > 0.001) {
        const c = Math.cos(sw), s2 = Math.sin(sw);
        const nx = x * c - z * s2, nz = x * s2 + z * c;
        x = nx; z = nz;
      }
      /* জীবন্ত ঝিলিক */
      const ph = phase[i];
      const shim = Math.sin(t * 2.3 + ph) * (0.006 + sb * 0.012 * headW[i]) * e;
      const rl = Math.sqrt(x * x + z * z) || 1e-4;
      x += (x / rl) * shim; z += (z / rl) * shim;
      y += Math.sin(t * 1.7 + ph * 1.3) * 0.004 * e;

      /* মাথার অংশে নড/টিল্ট প্রয়োগ */
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

    /* ভাসমান গতি + রোটেশন */
    bust.position.y = Math.sin(t * 1.15) * 0.03;
    if (!HOLO.dragging && HOLO.power) HOLO.autoRot += dt * 0.1;
    world.rotation.y += ((HOLO.targetRotY + HOLO.autoRot) - world.rotation.y) * 0.08;
    arc1.rotation.z = t * 0.5;
    arc2.rotation.z = -t * 0.7;

    /* স্ক্যান রিং */
    const cyc = (t * 0.4) % 1;
    scan.position.y = 0.35 + cyc * 2.3;
    HOLO.scanMat.opacity = (HOLO.power ? 0.5 : 0) * Math.sin(cyc * Math.PI) * formT;

    /* পাওয়ার অফ → সব ম্লান */
    pMat.opacity += ((HOLO.power ? 0.95 : 0.04) - pMat.opacity) * 0.08;
    HOLO.accentMats.forEach((m) => {
      if (m === HOLO.scanMat) return;
      const bse = m.userData.baseOp !== undefined ? m.userData.baseOp : 0.9;
      m.opacity += ((HOLO.power ? bse : bse * 0.06) - m.opacity) * 0.08;
    });

    /* স্টেট চিপ */
    setHoloState(!HOLO.power ? 'OFFLINE' : (formT < 0.985 ? 'FORMING…' : (sb > 0.35 ? 'SPEAKING' : 'IDLE // LISTENING')));

    renderer.render(scene, camera);
  })();
}

/* Male/Female বদল: ডটগুলো ভেঙে ছড়িয়ে নতুন আকারে গড়বে */
function syncGenderUI() {
  document.querySelectorAll('[data-gender]').forEach((el) => {
    el.classList.toggle('active', el.dataset.gender === HOLO.gender);
  });
  document.body.classList.toggle('female', HOLO.gender === 'female');
  HOLO.accentMats.forEach((m) => { if (m.color && m !== HOLO.scanMat) m.color.setHex(COLORS[HOLO.gender]); });
  if (HOLO.scanMat) HOLO.scanMat.color.setHex(COLORS[HOLO.gender]);
  if (window.GLOBE_MATS) window.GLOBE_MATS.forEach((m) => m.color && m.color.setHex(COLORS[HOLO.gender]));
}
function setGender(gender) {
  if (gender === HOLO.gender && HOLO.mode === 'in' && HOLO.formT > 0.9) return;
  HOLO.gender = gender;
  localStorage.setItem('stonic_gender', gender);
  HOLO.pendingGender = gender;
  HOLO.mode = 'out';
  syncGenderUI();
  drawWires();
  setHoloStatus(gender === 'female'
    ? '👩 Female কোর — ডটগুলো নতুন করে গঠন হচ্ছে…'
    : '👨 Male কোর — ডটগুলো নতুন করে গঠন হচ্ছে…');
}
function reform() {
  if (!HOLO.power) { toast('⏻ আগে Main সুইচ ON করো, তারপর আমি আবার গঠন হবো!'); return; }
  HOLO.pendingGender = HOLO.gender;
  HOLO.mode = 'out';
  setHoloStatus('✨ আবার গঠন হচ্ছি… ডটগুলোর খেলা দেখো!');
}

/* =========================================================
   SAT-LINK মিনি গ্লোব (World Monitor প্যানেলের সাজ — ধাপ ১০-এ লাইভ)
   ========================================================= */
function initGlobe() {
  const cv = $('globeCanvas');
  if (!cv || typeof THREE === 'undefined') return;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 50);
  camera.position.set(0, 0.4, 3.2);
  camera.lookAt(0, 0, 0);
  const group = new THREE.Group();
  group.rotation.x = 0.35;
  scene.add(group);
  window.GLOBE_MATS = [];

  const pts = [];
  const GA = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < 1500; i++) {
    const y = 1 - (i / 1499) * 2, r = Math.sqrt(1 - y * y), th = GA * i;
    pts.push(Math.cos(th) * r, y, Math.sin(th) * r);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  const gm = new THREE.PointsMaterial({ color: COLORS[HOLO.gender], size: 0.032, transparent: true, opacity: 0.9, depthWrite: false });
  window.GLOBE_MATS.push(gm);
  group.add(new THREE.Points(g, gm));

  const ring1 = new THREE.Mesh(new THREE.TorusGeometry(1.28, 0.008, 8, 90),
    new THREE.MeshBasicMaterial({ color: COLORS[HOLO.gender], transparent: true, opacity: 0.55 }));
  ring1.rotation.x = Math.PI / 2.4;
  window.GLOBE_MATS.push(ring1.material);
  group.add(ring1);
  const ring2 = ring1.clone();
  ring2.rotation.x = Math.PI / 1.6; ring2.rotation.y = 0.8;
  group.add(ring2);

  const hot = [];
  for (let i = 0; i < 9; i++) {
    const u = Math.random() * 2 - 1, th = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    hot.push(s * Math.cos(th), u, s * Math.sin(th));
  }
  const hg = new THREE.BufferGeometry();
  hg.setAttribute('position', new THREE.Float32BufferAttribute(hot, 3));
  group.add(new THREE.Points(hg, new THREE.PointsMaterial({ color: 0xffffff, size: 0.07, transparent: true, opacity: 0.95, depthWrite: false })));

  const resize = () => {
    const w = cv.clientWidth || 260, h = cv.clientHeight || 168;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(cv);
  resize();

  let vis = true;
  document.addEventListener('visibilitychange', () => { vis = !document.hidden; });
  const ck = new THREE.Clock();
  (function anim() {
    requestAnimationFrame(anim);
    if (!vis) return;
    group.rotation.y += ck.getDelta() * 0.28;
    renderer.render(scene, camera);
  })();
}

/* =========================================================
   সার্কিট লাইন — মডিউল কার্ড থেকে CORE স্টেজে সংযোগ
   ========================================================= */
function drawWires() {
  const layout = $('layout'), svg = $('wires'), stage = $('stage');
  if (!layout || !svg || !stage) return;
  if (window.innerWidth <= 1150) { svg.innerHTML = ''; return; }
  const lr = layout.getBoundingClientRect();
  const sr = stage.getBoundingClientRect();
  svg.setAttribute('viewBox', `0 0 ${lr.width} ${lr.height}`);
  const col = HOLO.gender === 'female' ? '#e879f9' : '#22d3ee';
  const fracs = { left: [0.22, 0.52], right: [0.2, 0.46, 0.72] };
  const count = { left: 0, right: 0 };
  let s = '';
  document.querySelectorAll('[data-wire]').forEach((card) => {
    const side = card.dataset.wire;
    const r = card.getBoundingClientRect();
    const idx = count[side]++;
    const f = (fracs[side] && fracs[side][idx]) || 0.5;
    const x1 = (side === 'left' ? r.right : r.left) - lr.left;
    const y1 = r.top - lr.top + 30;
    const x2 = (side === 'left' ? sr.left : sr.right) - lr.left;
    const y2 = sr.top - lr.top + sr.height * f;
    const mx = (x1 + x2) / 2;
    s += `<path d="M${x1},${y1} L${mx},${y1} L${mx},${y2} L${x2},${y2}" stroke="${col}"/>`;
    s += `<circle cx="${x1}" cy="${y1}" r="3.5" fill="${col}"/><circle cx="${x2}" cy="${y2}" r="3" fill="${col}"/>`;
  });
  svg.innerHTML = s;
}

/* =========================================================
   কথা বলার ডেমো (ধাপ ৫/৬-এর আভাস) — ব্রাউজারের ফ্রি TTS
   ========================================================= */
function speakDemo(text) {
  if (!HOLO.power) return;
  HOLO.speaking = true;
  setHoloStatus('🗣️ Stonic AI কথা বলছে…');
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    HOLO.speaking = false;
    setHoloStatus('🟢 প্রস্তুত — Stonic AI শুনছে');
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
   চ্যাট (ধাপ ১: ডেমো উত্তর — ধাপ ৩-এ আসল AI)
   ========================================================= */
const demoReplies = [
  'তোমার বার্তা পেয়েছি! তবে আমি এখনো শেখার পর্যায়ে আছি — ধাপ ৩-এ Gemini আর Groq যুক্ত হলেই সত্যিকারের উত্তর দিতে পারবো। আমার নতুন আকারটা কেমন লাগলো?',
  'দেখলে, কথা বলার সময় আমার মাথাটা নড়ে! ধাপ ৫-এ আসল ভয়েস আর ধাপ ৬-এ সম্পূর্ণ সিঙ্ক অ্যানিমেশন পাবো।',
  'একটু খেয়াল করো — ওপরের ♀ FEMALE / ♂ MALE বদলালে আমার ডটগুলো ভেঙে আবার নতুন রূপে গড়ে ওঠে। চেষ্টা করে দেখো!',
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
  setHoloStatus('🤔 Stonic AI ভাবছে…');
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
   ইভেন্ট ওয়্যারিং
   ========================================================= */
document.addEventListener('DOMContentLoaded', () => {
  initHologram();
  initGlobe();
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

  /* Main Power */
  $('powerSwitch').addEventListener('change', (e) => {
    HOLO.power = e.target.checked;
    document.body.classList.toggle('power-off', !HOLO.power);
    if (!HOLO.power) {
      HOLO.speaking = false;
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      setHoloStatus('⏻ বন্ধ আছে — Main সুইচ ON করলেই ডটগুলো আবার গঠন হবে');
      toast('⏻ Stonic AI বন্ধ হলো — ডটগুলো ছড়িয়ে হারিয়ে গেছে। আবার চালু করতে Main সুইচ ON করো।');
    } else {
      setHoloStatus('✨ ফিরে এসেছি — ডটগুলো জড়ো হচ্ছে…');
      toast('🤖 Stonic AI চালু! ডটগুলো আকার গঠন করতে দেখো।');
    }
  });

  /* Female/Male — টপবার পিল + Character বাটন দুটোই */
  document.querySelectorAll('[data-gender]').forEach((el) => {
    el.addEventListener('click', () => {
      setGender(el.dataset.gender);
      toast(el.dataset.gender === 'female'
        ? '👩 Female কোর — ডটগুলো ভেঙে মেয়ের আকারে গড়ে উঠছে!'
        : '👨 Male কোর — ডটগুলো ভেঙে ছেলের আকারে গড়ে উঠছে!');
    });
  });

  /* আবার গঠন হও বাটন */
  $('reformBtn').addEventListener('click', reform);

  /* মোড ট্যাব */
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.mode-panel').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      $('mode-' + tab.dataset.mode).classList.add('active');
      setTimeout(drawWires, 60);
    });
  });

  /* চ্যাট */
  $('sendBtn').addEventListener('click', sendChat);
  $('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });
  $('micBtn').addEventListener('click', () => {
    toast('🎤 ভয়েস সিস্টেম ধাপ ৫-এ আসবে — তখন মুখে বললেই হবে, কথা শেষ হলে তবেই আমি উত্তর দেবো!');
  });

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

  /* ক্যামেরা/স্ক্রিন টগল — ইন্ডিকেটর ডেমো (আসল অ্যাক্সেস ধাপ ৯) */
  const syncVisualHub = () => {
    const cam = $('cameraToggle').checked, scr = $('screenToggle').checked;
    $('camIndicator').classList.toggle('hidden', !(cam || scr));
    $('camChip').textContent = 'CAM · ' + (cam ? 'ON' : 'OFF');
    $('camChip').classList.toggle('on', cam);
    $('scrChip').textContent = 'SCREEN · ' + (scr ? 'ON' : 'OFF');
    $('scrChip').classList.toggle('on', scr);
  };
  [$('cameraToggle'), $('screenToggle')].forEach((tg) => {
    tg.addEventListener('change', () => {
      syncVisualHub();
      toast(tg.checked
        ? '🔴 এটি এখন শুধু ইন্ডিকেটর ডেমো — ক্যামেরা/স্ক্রিন অ্যাক্সেস হচ্ছে না। আসল অনুমতি-ভিত্তিক অ্যাক্সেস ধাপ ৯-এ আসবে, তখনও এই সতর্কতা জ্বলবে।'
        : '✅ বন্ধ করা হয়েছে।', 4600);
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

  /* World Monitor রিফ্রেশ (ধাপ ১০) */
  $('refreshNews').addEventListener('click', () => {
    toast('🌍 লাইভ নিউজ ধাপ ১০-এ আসবে — তখন SAT-LINK গ্লোবে হটস্পট আর নিচে আসল হেডলাইন থাকবে, চাইলে আমি পড়েও শোনাবো!');
  });

  /* Personality */
  $('personality').addEventListener('change', (e) => {
    toast(`🎭 ব্যক্তিত্ব সিলেক্ট: "${e.target.value}" — এই সেটিং ধাপ ৩ থেকে আমার উত্তরে প্রভাব ফেলবে।`);
  });

  toast('✨ দেখো — হাজার হাজার ডট জড়ো হয়ে আমার নতুন আকার গঠন করছে! ♀/♂ বদলে দেখো, "আবার গঠন হও" চাপো।', 5600);
});
