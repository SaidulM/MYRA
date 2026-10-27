/* =========================================================
   Stonic AI — UI লজিক + Three.js ডটেড হলোগ্রাম (ধাপ ১)
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
function setHoloStatus(txt) { $('holoStatus').textContent = txt; }

/* =========================================================
   হলোগ্রাম — পয়েন্ট-ক্লাউড মানব আকৃতি (Three.js)
   ========================================================= */
const HOLO = {
  gender: localStorage.getItem('stonic_gender') || 'male',
  power: true,
  speaking: false,
  speakBlend: 0,
  parts: {},        // head, torso, armL, armR, legs — THREE.Points
  materials: [],
  group: null,
  scanRing: null,
  targetRotY: 0,
  dragging: false,
};

const COLORS = { male: 0x22d3ee, female: 0xe879f9 };

/* গায়ের মাপ — male: চওড়া কাঁধ; female: সরু কোমর, চওড়া হিপ, লম্বা চুল */
const PROFILES = {
  male:   { shoulder: 0.62, chest: 0.56, waist: 0.43, hip: 0.48, headR: [0.30, 0.36, 0.32], hair: false },
  female: { shoulder: 0.52, chest: 0.48, waist: 0.33, hip: 0.56, headR: [0.28, 0.34, 0.30], hair: true },
};

/* এলিপসয়েডের গায়ে র‌্যান্ডম পয়েন্ট */
function sampleEllipsoid(cx, cy, cz, rx, ry, rz, n, out, keepFn) {
  let placed = 0, guard = 0;
  while (placed < n && guard++ < n * 30) {
    const u = Math.random() * 2 - 1;
    const th = Math.random() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const p = [cx + rx * s * Math.cos(th), cy + ry * u, cz + rz * s * Math.sin(th)];
    if (keepFn && !keepFn(p)) continue;
    out.push(p[0], p[1], p[2]);
    placed++;
  }
}

/* দুই বিন্দুর মাঝে নলের মতো পয়েন্ট (হাত/পা) — pivot-relative */
function sampleTube(a, b, radius, n, out) {
  for (let i = 0; i < n; i++) {
    const t = Math.random();
    const cx = a[0] + (b[0] - a[0]) * t;
    const cy = a[1] + (b[1] - a[1]) * t;
    const cz = a[2] + (b[2] - a[2]) * t;
    const r = radius * (0.75 + Math.random() * 0.35);
    const ang = Math.random() * Math.PI * 2;
    out.push(cx + r * Math.cos(ang), cy, cz + r * Math.sin(ang) * 0.85);
  }
}

function makePoints(posArray, color, size) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(posArray, 3));
  const mat = new THREE.PointsMaterial({
    color, size, transparent: true, opacity: 0.92,
    blending: THREE.AdditiveBlending, depthWrite: false,
  });
  const pts = new THREE.Points(geo, mat);
  HOLO.materials.push(mat);
  return pts;
}

function buildBody(gender) {
  const P = PROFILES[gender];
  const color = COLORS[gender];
  const group = new THREE.Group();
  const parts = {};

  /* --- মাথা (+ মেয়েদের লম্বা চুল) — pivot ঘাড়ে যেন মাথা নাড়ানো যায় --- */
  const headPos = [];
  sampleEllipsoid(0, 0.42, 0, P.headR[0], P.headR[1], P.headR[2], 950, headPos);
  if (P.hair) {
    sampleEllipsoid(0, 0.18, -0.10, 0.34, 0.62, 0.33, 650, headPos, (p) => p[2] < 0.12);
  }
  parts.head = makePoints(headPos, color, 0.027);
  parts.head.position.set(0, 2.46, 0);           // ঘাড়ের গোড়ায় pivot
  group.add(parts.head);

  /* --- টর্সো: প্রোফাইল অনুযায়ী রিং --- */
  const torsoPos = [];
  const prof = [ [2.46, P.shoulder], [2.28, P.chest], [1.95, P.waist], [1.58, P.hip] ];
  const radiusAt = (y) => {
    for (let i = 0; i < prof.length - 1; i++) {
      const [y1, r1] = prof[i], [y2, r2] = prof[i + 1];
      if (y <= y1 && y >= y2) return r1 + (r2 - r1) * ((y1 - y) / (y1 - y2));
    }
    return prof[prof.length - 1][1];
  };
  for (let i = 0; i < 1700; i++) {
    const y = 1.58 + Math.random() * 0.88;
    const r = radiusAt(y) * (0.94 + Math.random() * 0.1);
    const a = Math.random() * Math.PI * 2;
    torsoPos.push(r * Math.cos(a), y, r * 0.62 * Math.sin(a));
  }
  /* ঘাড় */
  sampleTube([0, 2.42, 0], [0, 2.58, 0], 0.115, 130, torsoPos);
  parts.torso = makePoints(torsoPos, color, 0.027);
  group.add(parts.torso);

  /* --- হাত (কাঁধে pivot, তাই অ্যানিমেশনে দুলবে) --- */
  const mkArm = (side) => {
    const s = side; // +1 ডান, -1 বাম
    const pos = [];
    sampleTube([0, 0, 0], [s * 0.16, -0.48, 0.02], 0.125, 420, pos);   // উপরের হাত
    sampleTube([s * 0.16, -0.48, 0.02], [s * 0.12, -0.92, 0.07], 0.10, 380, pos); // কনুই→কব্জি
    const arm = makePoints(pos, color, 0.026);
    arm.position.set(s * P.shoulder * 0.92, 2.44, 0);
    return arm;
  };
  parts.armR = mkArm(1);
  parts.armL = mkArm(-1);
  group.add(parts.armR, parts.armL);

  /* --- পা --- */
  const legPos = [];
  sampleTube([ P.hip * 0.42, 1.56, 0], [ P.hip * 0.40, 0.10, 0.02], 0.155, 800, legPos);
  sampleTube([-P.hip * 0.42, 1.56, 0], [-P.hip * 0.40, 0.10, 0.02], 0.155, 800, legPos);
  parts.legs = makePoints(legPos, color, 0.027);
  group.add(parts.legs);

  return { group, parts };
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
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 1.95, 5.1);
  camera.lookAt(0, 1.55, 0);

  /* তারা — ব্যাকগ্রাউন্ড */
  const starPos = [];
  for (let i = 0; i < 420; i++) {
    starPos.push((Math.random() - 0.5) * 16, Math.random() * 7 - 0.5, (Math.random() - 0.5) * 10 - 2);
  }
  const stars = makePoints(starPos, 0x7dd3fc, 0.02, 0.55);
  stars.material.userData.lockColor = true; // তারার রঙ gender অনুযায়ী বদলাবে না
  scene.add(stars);

  /* হলোগ্রাম প্ল্যাটফর্ম (ঘূর্ণায়মান রিং) */
  const platform = new THREE.Group();
  const ringMat = (op) => {
    const m = new THREE.MeshBasicMaterial({
      color: COLORS[HOLO.gender], transparent: true, opacity: op, side: THREE.DoubleSide,
    });
    m.userData.baseOp = op;
    return m;
  };
  const mkRing = (inner, outer, op) => {
    const m = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 64), ringMat(op));
    m.rotation.x = -Math.PI / 2;
    platform.add(m);
    HOLO.materials.push(m.material);
    return m;
  };
  mkRing(1.05, 1.12, 0.8);
  mkRing(0.78, 0.82, 0.5);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.72, 48), ringMat(0.08));
  disc.rotation.x = -Math.PI / 2;
  platform.add(disc);
  HOLO.materials.push(disc.material);
  scene.add(platform);

  /* স্ক্যান রিং — নিচ থেকে উপরে যায় */
  HOLO.scanRing = new THREE.Mesh(new THREE.RingGeometry(0.92, 0.97, 64), ringMat(0.55));
  HOLO.scanRing.rotation.x = -Math.PI / 2;
  scene.add(HOLO.scanRing);
  HOLO.materials.push(HOLO.scanRing.material);

  /* শরীর */
  const built = buildBody(HOLO.gender);
  HOLO.group = built.group;
  HOLO.parts = built.parts;
  scene.add(HOLO.group);
  HOLO.scene = scene;
  HOLO.platform = platform;

  /* ড্র্যাগ করে ঘোরানো */
  let lastX = 0;
  canvas.addEventListener('pointerdown', (e) => { HOLO.dragging = true; lastX = e.clientX; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener('pointermove', (e) => {
    if (!HOLO.dragging) return;
    HOLO.targetRotY += (e.clientX - lastX) * 0.008;
    lastX = e.clientX;
  });
  canvas.addEventListener('pointerup', () => { HOLO.dragging = false; });
  canvas.addEventListener('pointercancel', () => { HOLO.dragging = false; });

  /* রিসাইজ */
  const resize = () => {
    const w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(wrap);
  resize();

  /* অ্যানিমেশন লুপ */
  const clock = new THREE.Clock();
  let running = true;
  document.addEventListener('visibilitychange', () => { running = !document.hidden; });

  (function animate() {
    requestAnimationFrame(animate);
    if (!running) return;
    const t = clock.getElapsedTime();
    const P = HOLO.parts;

    /* speaking ব্লেন্ড — মসৃণ ট্রানজিশন */
    const target = (HOLO.speaking && HOLO.power) ? 1 : 0;
    HOLO.speakBlend += (target - HOLO.speakBlend) * 0.06;
    const b = HOLO.speakBlend;

    /* শ্বাস/ভাসা (idle) + কথা বলার মুভমেন্ট */
    HOLO.group.position.y = Math.sin(t * (1.1 + b * 0.7)) * (0.035 + b * 0.02);
    HOLO.group.rotation.y += ((HOLO.targetRotY + (HOLO.dragging ? 0 : t * 0.12)) - HOLO.group.rotation.y) * 0.06;
    if (P.head) {
      P.head.rotation.x = Math.sin(t * 1.3) * 0.03 + b * Math.sin(t * 7.2) * 0.075;   // কথা বললে মাথা নড়ে
      P.head.rotation.z = Math.sin(t * 0.9) * 0.02 + b * Math.sin(t * 3.1) * 0.05;
    }
    if (P.armR) { P.armR.rotation.x = b * (-0.28 + Math.sin(t * 2.4) * 0.16); P.armR.rotation.z = -b * 0.10; }
    if (P.armL) { P.armL.rotation.x = b * (-0.28 + Math.sin(t * 2.4 + 1.7) * 0.16); P.armL.rotation.z = b * 0.10; }
    if (P.torso) P.torso.scale.setScalar(1 + Math.sin(t * 1.6) * 0.006);              // শ্বাস

    /* প্ল্যাটফর্ম + স্ক্যান */
    HOLO.platform.rotation.y = t * 0.25;
    if (HOLO.scanRing) {
      const cyc = (t * 0.45) % 1;
      HOLO.scanRing.position.y = cyc * 3.2;
      HOLO.scanRing.material.opacity = (HOLO.power ? 0.55 : 0) * Math.sin(cyc * Math.PI);
    }

    /* পাওয়ার অফ → সব ম্লান (প্রতিটা ম্যাটেরিয়াল নিজের base opacity রাখে) */
    HOLO.materials.forEach((m) => {
      if (m === HOLO.scanRing.material) return;
      const base = m.userData.baseOp !== undefined ? m.userData.baseOp : 0.9;
      m.opacity += ((HOLO.power ? base : base * 0.055) - m.opacity) * 0.08;
    });

    renderer.render(scene, camera);
  })();
}

/* Male/Female বদলালে শরীর নতুন করে বানানো */
function setGender(gender) {
  HOLO.gender = gender;
  localStorage.setItem('stonic_gender', gender);
  document.body.classList.toggle('female', gender === 'female');
  $('btnMale').classList.toggle('active', gender === 'male');
  $('btnFemale').classList.toggle('active', gender === 'female');
  if (HOLO.group) {
    const oldRotY = HOLO.targetRotY;
    HOLO.scene.remove(HOLO.group);
    HOLO.group.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    /* পুরনো body ম্যাটেরিয়াল সরিয়ে রঙ আপডেট (platform/stars নতুন রঙ পাবে) */
    HOLO.materials.forEach((m) => m.color && m.color.setHex(COLORS[gender]));
    const built = buildBody(gender);
    HOLO.group = built.group;
    HOLO.parts = built.parts;
    HOLO.targetRotY = oldRotY;
    HOLO.scene.add(HOLO.group);
  }
  setHoloStatus(gender === 'male'
    ? '👨 Male মোড — ছেলের আকৃতির হলোগ্রাম (কণ্ঠ ধাপ ৫-এ)'
    : '👩 Female মোড — মেয়ের আকৃতির হলোগ্রাম (কণ্ঠ ধাপ ৫-এ)');
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
    setHoloStatus('🟢 প্রস্তুত — Stonic AI অপেক্ষা করছে');
  };
  /* অ্যানিমেশন চলবে অন্তত পড়ার আনুমানিক সময় ধরে */
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
  'তোমার বার্তা পেয়েছি! তবে আমি এখনো শেখার 단계ে আছি — ধাপ ৩-এ Gemini আর Groq যুক্ত হলেই সত্যিকারের উত্তর দিতে পারবো। ততক্ষণ হলোগ্রামটা দেখো — কেমন লাগছে?',
  'ভালো প্রশ্ন! আমার মস্তিষ্ক (Gemini/Groq API) ধাপ ২-এ Key সেভ আর ধাপ ৩-এ সংযোগ পেলেই এসবের আসল উত্তর দিতে শিখবো। এখন শুধু UI টেস্ট হচ্ছে।',
  'শুনছি… কথা বলার সময় আমার হলোগ্রামটা নড়তে দেখছো? ধাপ ৫-এ আসল ভয়েস আর ধাপ ৬-এ পূর্ণ সিঙ্ক অ্যানিমেশন আসবে!',
  'এখন আমি শুধু তোমার কথা পড়ে ওপরের মুখটা নাড়াচ্ছি। ধাপ ৪ থেকে তুমি যা বলবে — নাম, পছন্দ, অনুভূতি — সব মনে রাখবো, তোমার ল্যাপটপের ভেতরেই নিরাপদে।',
];
let demoIdx = 0;

function addMsg(text, who) {
  const log = $('chatLog');
  const div = document.createElement('div');
  div.className = 'msg ' + (who === 'user' ? 'msg-user' : 'msg-ai');
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;
  if (who === 'ai') {
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

  /* সার্ভার হেলথ চেক */
  const checkHealth = () => {
    if (location.protocol === 'file:') {
      // সার্ভার ছাড়াই সরাসরি ফাইল খোলা হলে (এক-ফাইলের প্রিভিউ)
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = 'প্রিভিউ মোড — UI দেখার জন্য (সার্ভার ছাড়া)';
      return;
    }
    fetch('/api/health').then((r) => r.json()).then((d) => {
      $('serverDot').className = 'dot dot-on';
      $('serverText').textContent = `সার্ভার: সংযুক্ত ✅ (ধাপ ${d.stage})`;
    }).catch(() => {
      $('serverDot').className = 'dot dot-off';
      $('serverText').textContent = 'সার্ভার: সংযোগ নেই ❌ (run.py চালু আছে তো?)';
    });
  };
  checkHealth();
  setInterval(checkHealth, 20000);

  /* Main Power সুইচ */
  $('powerSwitch').addEventListener('change', (e) => {
    HOLO.power = e.target.checked;
    document.body.classList.toggle('power-off', !HOLO.power);
    if (!HOLO.power) {
      HOLO.speaking = false;
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      setHoloStatus('⏻ বন্ধ আছে — Main সুইচ ON করলেই জেগে উঠবো');
      toast('⏻ Stonic AI বন্ধ হলো। আবার চালু করতে টপ-বারের Main সুইচ ON করো।');
    } else {
      setHoloStatus('🟢 প্রস্তুত — Stonic AI অপেক্ষা করছে');
      toast('🤖 Stonic AI চালু হয়েছে!');
    }
  });

  /* Character — Male/Female */
  document.querySelectorAll('.gender-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setGender(btn.dataset.gender);
      toast(btn.dataset.gender === 'male'
        ? '👨 Male চরিত্র সিলেক্ট হলো — হলোগ্রামের আকৃতি ও রঙ বদলে গেছে!'
        : '👩 Female চরিত্র সিলেক্ট হলো — হলোগ্রামের আকৃতি ও রঙ বদলে গেছে!');
    });
  });
  setGender(HOLO.gender); // সেভ করা পছন্দ অনুযায়ী শুরু

  /* মোড ট্যাব */
  document.querySelectorAll('.mode-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.mode-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.mode-panel').forEach((p) => p.classList.remove('active'));
      tab.classList.add('active');
      $('mode-' + tab.dataset.mode).classList.add('active');
    });
  });

  /* চ্যাট পাঠানো */
  $('sendBtn').addEventListener('click', sendChat);
  $('chatInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

  /* মাইক (ধাপ ৫) */
  $('micBtn').addEventListener('click', () => {
    toast('🎤 ভয়েস সিস্টেম ধাপ ৫-এ আসবে — তখন মুখে বললেই হবে, কথা শেষ হলে তবেই উত্তর দেবে!');
  });

  /* Agent ডেমো */
  const runAgentDemo = () => {
    const task = $('agentInput').value.trim() || '(খালি নির্দেশ)';
    const log = $('agentLog');
    log.textContent = `📝 নির্দেশ পেয়েছি: "${task}"\n`;
    setTimeout(() => { log.textContent += '⏳ ধাপ ৮-এ চালু হলে আমি এখন ব্রাউজার খুলতাম…\n'; }, 600);
    setTimeout(() => { log.textContent += '🔍 তারপর নিজে সার্চ করে, রেজাল্ট পড়ে সামারি রিপোর্ট দিতাম।\n✅ এখন এটি শুধু ডেমো লেআউট।'; }, 1400);
  };
  $('agentBtn').addEventListener('click', runAgentDemo);
  $('agentInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') runAgentDemo(); });

  /* Notes ডেমো (শুধু এই সেশনে) */
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

  /* API Key সেভ (ধাপ ২) */
  $('saveKeys').addEventListener('click', () => {
    $('geminiKey').value = '';
    $('groqKey').value = '';
    toast('⚠️ সাবধান: ধাপ ১-এ Key কোথাও সেভ হচ্ছে না — সেভ সিস্টেম ধাপ ২-এ আসবে। নিরাপত্তার জন্য ইনপুট খালি করে দিলাম। আসল Key গোপন রেখো, কারো সাথে শেয়ার কোরো না!', 5200);
  });

  /* ক্যামেরা/স্ক্রিন টগল — শুধু ইন্ডিকেটর ডেমো (আসল অ্যাক্সেস ধাপ ৯) */
  const updateCamIndicator = () => {
    const any = $('cameraToggle').checked || $('screenToggle').checked;
    $('camIndicator').classList.toggle('hidden', !any);
  };
  [$('cameraToggle'), $('screenToggle')].forEach((tg) => {
    tg.addEventListener('change', () => {
      updateCamIndicator();
      toast(tg.checked
        ? '🔴 এটা শুধু ইন্ডিকেটর ডেমো — এখনো ক্যামেরা/স্ক্রিন অ্যাক্সেস হচ্ছে না। আসল অনুমতি-ভিত্তিক অ্যাক্সেস ধাপ ৯-এ আসবে, তখনও ON থাকলে এই লাল সতর্কতা জ্বলবে।'
        : '✅ বন্ধ করা হয়েছে।', 4600);
    });
  });

  /* Skills টগল (localStorage-এ সেভ) */
  const saved = JSON.parse(localStorage.getItem('stonic_skills') || '{}');
  document.querySelectorAll('.skill-toggle').forEach((tg) => {
    if (tg.dataset.skill in saved) tg.checked = saved[tg.dataset.skill];
    tg.addEventListener('change', () => {
      saved[tg.dataset.skill] = tg.checked;
      localStorage.setItem('stonic_skills', JSON.stringify(saved));
      toast(`🧩 স্কিল ${tg.checked ? 'চালু ✅' : 'বন্ধ ⛔'} — পছন্দটা এই ব্রাউজারে সেভ হলো (আসল স্কিল ইঞ্জিন ধাপ ৭-এ)।`);
    });
  });

  /* World Monitor রিফ্রেশ (ধাপ ১০) */
  $('refreshNews').addEventListener('click', () => {
    toast('🌍 লাইভ নিউজ ধাপ ১০-এ আসবে — তখন এখানে বাস্তব হেডলাইন থাকবে আর আমি চাইলেই পড়ে শোনাবো!');
  });

  /* Personality বদলালে শুভেচ্ছা ডেমো */
  $('personality').addEventListener('change', (e) => {
    toast(`🎭 ব্যক্তিত্ব সিলেক্ট: "${e.target.value}" — চরিত্রের এই সেটিং ধাপ ৩ থেকে উত্তরে প্রভাব ফেলবে।`);
  });

  toast('👋 ধাপ ১ প্রস্তুত! হলোগ্রাম ঘোরাও, Male/Female বদলে দেখো, চ্যাট বাক্সে লিখে ডেমো চালাও।', 5000);
});
