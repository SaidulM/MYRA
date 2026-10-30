# MYRA 🤖 — Personal Desktop AI Assistant

**MYRA** is a complete personal desktop AI companion built to run ultra-light on an **8GB RAM** laptop — **100% free** to build and run, with no heavy local AI models.

---

## 🇧🇩 বাংলা নির্দেশিকা (Quick Setup & Guide in Bengali)

### 🚀 ল্যাপটপে ইনস্টল ও চালু করার সহজ নিয়ম:
১. **এক ক্লিকে ইনস্টল (`MYRA-Installer.bat`):**
   - GitHub থেকে শুধুমাত্র **`MYRA-Installer.bat`** (অথবা সম্পূর্ণ রিপোজিটরির ZIP) ডাউনলোড করুন।
   - **`MYRA-Installer.bat`** এর উপর ডাবল-ক্লিক করুন।
   - এটি স্বয়ংক্রিয়ভাবে পাইথন (Python) চেক করবে এবং না থাকলে নিজে থেকেই ইনস্টল করে নেবে।
   - এরপর গিটহাব (`https://github.com/SaidulM/MYRA`) থেকে প্রয়োজনীয় সমস্ত ফাইল স্বয়ংক্রিয়ভাবে ডাউনলোড করে আপনার ল্যাপটপে (`C:\Users\<user>\MYRA`) সেভ করবে।
   - আপনার Desktop এবং Start Menu-তে **MYRA** নামে শর্টকাট আইকন তৈরি করে দেবে।

২. **এপিআই (API Key) দেওয়া ও স্বয়ংক্রিয় মডেল নির্বাচন (Free & Paid Both Supported):**
   - সফটওয়্যারটি চালু হওয়ার সাথে সাথে স্ক্রিনে **"Connect MYRA AI Brain"** উইন্ডো আসবে।
   - সেখানে আপনার **Google Gemini API Key** (ফ্রি টিয়ার কিংবা পেইড/প্রো টিয়ার যেকোনো কি) পেস্ট করে **"Connect & Activate"** বাটনে ক্লিক করুন।
   - সিস্টেমটি ইন্টারনেটের মাধ্যমে স্বয়ংক্রিয়ভাবে গুগলের মডেল লিস্ট থেকে আপনার কি-এর জন্য সেরা মডেলটি (`gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash` ইত্যাদি) নিজে থেকেই বেছে নেবে।
   - পেইড এবং ফ্রি যেকোনো কি দিলেই এটি নিজে থেকে মডেল ডিটেক্ট করে কানেক্ট হয়ে যাবে।
   - (ফ্রি এপিআই কি পাওয়ার লিঙ্ক: [aistudio.google.com](https://aistudio.google.com))

৩. **অটোমেটিক আপডেট (Auto-Update System):**
   - **স্টার্টআপে আপডেট:** যখনই আপনি ডেস্কটপের MYRA আইকনটিতে ক্লিক করবেন, এটি গিটহাবের সাথে কানেক্ট হয়ে চেক করবে কোনো নতুন আপডেট এসেছে কিনা। নতুন আপডেট থাকলে আপনার সেভ করা এপিআই কি (`.env`) এবং মেমোরি ডেটা অক্ষত রেখে স্বয়ংক্রিয়ভাবে নতুন ফাইল ডাউনলোড ও আপডেট করে নেবে।
   - **চলমান অবস্থায় আপডেট:** সফটওয়্যারটি চলার সময়ও প্রতি ৫ মিনিট পর পর ব্যাকগ্রাউন্ডে চেক করবে। নতুন আপডেট থাকলে একটি অপশনাল আপডেট নোটিশ আসবে। চাইলে **"Update MYRA Now"** দিয়ে আপডেট করুন, অথবা **✕**, **"Later — Continue MYRA"**, **Escape** দিয়ে পপআপ বন্ধ করে বর্তমান সফটওয়্যারই ব্যবহার করুন। আপডেট ব্যর্থ হলেও MYRA বন্ধ হবে না এবং পপআপ আটকে থাকবে না।

---

## 🌟 Key Features

- 🧠 **Selected AI Brain, Used Exactly:** Gemini, Groq, OpenRouter, OpenAI, DeepSeek, Mistral or Ollama Local can be selected in the top BRAIN switcher. An explicit choice is authoritative — if that brain is missing/offline, MYRA says so instead of silently answering through another provider. `Auto` chooses the best configured brain.
- ⚡ **Short answers by default (v1.1):** MYRA normally gives the direct main answer in 1–3 short sentences and speaks only the first 1–2 sentences. It expands only when you ask for more (for example “বেশি করে বলো”, “একটু বড় করে বলো”, “ভালো করে বুঝিয়ে বলো” or “explain in detail”), or when you choose **Detailed explanations** in **SETTING → Answer length**.
- 🧰 **Every visible option is backed (v1.1):** **SETTING → System Files & Background** checks/creates the database, private `.env` starter, UI-settings backup, workspace, voice folders, offline-news file and feedback file behind the UI. Mistral key entry/status/removal and live Ollama running/model status are included.
- 🎙️ **Faster spoken replies (v1.1):** the installed hearing model warms up while you speak, pause detection is tighter, normal speech generation avoids a slow double attempt, and a matching Windows voice can Start if the neural voice is slow.
- ✨ **3D Hologram Particle Characters:**
  - `CORE` (living orb of light)
  - `MALE` (professional JARVIS-style assistant)
  - `FEMALE` (warm, caring companion)
  - Smooth wave-particle transitions, scan-light lighting, and 3D rotation.
- 🎤 **Live Voice Conversation:** In the desktop window, MYRA records the microphone, detects your pause, transcribes locally with faster-whisper, shows your words, answers, speaks only the clean main reply, then listens again. `CORE` and `MALE` use a male voice; `FEMALE` uses a female voice.
- 💾 **Local Memory Engine (SQLite):** Remembers facts and preferences about you in one unified database in Windows app data (`%LOCALAPPDATA%\MYRA\myra.db`); any older `data/myra.db` contents are imported automatically. Never uploaded to any cloud.
- 🤖 **Step-by-Step Agent Mode:** Give MYRA a real task and the Agent panel runs the bounded Core engine: observe → plan → one safe skill → observe/verify → next step. It shows every step and pauses for **APPROVE/DENY** before write/control skills, with pause, resume, stop and Windows emergency-stop controls.
- 📝 **Offline Notes Mode:** Create, view, and delete personal notes stored in local SQLite database.
- 🧩 **Built-in Skills Engine:** Safe math calculator, live weather reports, system diagnostics, and web search.
- 📷 **Visual Hub (Camera & Screen Share):** Permission-based camera and screen viewing with a clear red LIVE indicator.
- 🌍 **World Monitor:** Spinnable 3D Earth, interactive map, and live RSS news feed (cached for offline reading) with read-aloud support.
- 🛡️ **Zero Data Leakage:** Your `.env` and personal memory databases are strictly kept on your laptop.

### Smooth desktop app — the primary interface (Oct 2026)

MYRA's primary owner-facing interface is the familiar one-screen MYRA design, shown in its own desktop window through a GPU web shell (`desktop/web_shell.py`, WebView2 on Windows). The older all-Qt window is still included as an advanced fallback (`MYRA_UI=qt` / `--qt`), because the owner found the CPU-drawn Qt hologram stuttered on a low-power laptop.

- **No console windows, ever.** Source mode starts from `MYRA.pyw` (double-click, via `pythonw`); the packaged build is a windowed `MYRA.exe`. The backend runs in a thread inside the same process — no Command Prompt, PowerShell, child Python backend or external browser window is needed. A first-run/update Python setup window creates `.venv-desktop` and installs the pinned packages for you.
- **Original dotted hologram, GPU-rendered.** CORE, MALE and FEMALE chest-up point-cloud busts use the established Three.js/WebGL interface: one-time formation on first open, in-place morphing between forms, drag/parallax motion, bottom-to-top scan lighting, and Normal/Friendly/Hacker themes.
- **Advanced Qt fallback:** Chat, Agent, Voice, Live Vision, Research, Computer, Skills, Memory, Notes, Reminders, World, Settings and Diagnostics remain available in the PySide6 window when selected explicitly.
- **One unified local database.** Memories, notes, reminders, conversations, preferences and tasks live in a single SQLite store under Windows app data (`%LOCALAPPDATA%\MYRA`). Any legacy `data/myra.db` rows are imported once, idempotently and without data loss.
- **40 typed, permission-checked skills** behind `/api/v1`, with confirmation gates for write/control actions. Ordinary Chat never receives computer-control tools.
- **Realtime voice pipeline in the default window:** microphone → pause detection → local faster-whisper → selected AI brain → concise Edge TTS (or browser fallback) → speaker, then listening resumes. WebView2 does not need browser SpeechRecognition for this path. The one-time Base STT model (~145 MB) is installed only after confirmation in **CHARACTER → VOICE STUDIO**.
- **Core Agent in the original interface:** the **AGENT** tab now creates `/api/v1` tasks with visible steps, approval, pause/resume/cancel and emergency stop — not the old phrase matcher that mostly opened a browser. Windows PC-control skills stay OFF until enabled in **SKILLS → PC Control (Agent)**.
- **Consent-based live vision**, **cited web research**, optional **visible browser automation** (Playwright) and **semantic Windows app control** (UI Automation/pywinauto with confirmation and emergency stop) remain bounded. CAPTCHA/MFA/password steps are always refused and left to you.
- **Packaging:** `python packaging/build_windows.py` builds the windowed `MYRA.exe` (and optional Inno Setup installer) on Windows.
- API secrets prefer the OS credential store when `keyring` is available; the private `.env` remains the fallback. Settings responses are masked.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/WINDOWS_NATIVE.md`](docs/WINDOWS_NATIVE.md) and [`docs/REFERENCE_ANALYSIS.md`](docs/REFERENCE_ANALYSIS.md) for details and honest capability boundaries. Final microphone/camera/UI-Automation acceptance happens on the owner's Windows laptop.
---

## 💻 Installation & Usage (English)

**Already have the MYRA folder?** Your existing **MYRA** Desktop/Start-Menu shortcut opens the smooth desktop app after the usual auto-update, or double-click **`MYRA.pyw`** in the MYRA folder to start instantly with no console window. First run/updates may show a small Python setup window that prepares new packages once. Full day-to-day guide: [`docs/WINDOWS_NATIVE.md`](docs/WINDOWS_NATIVE.md).

### Option 1: 1-Click Installer (Recommended for Windows)
1. Download **`MYRA-Installer.bat`** (or download the full repository ZIP from GitHub and extract).
2. Double-click **`MYRA-Installer.bat`**.
3. The installer will:
   - Verify Python 3.8+ (installs it automatically via Windows winget if missing).
   - Download the latest files from GitHub and install to `%USERPROFILE%\MYRA`.
   - Prompt for your Gemini API key, test the connection in real time, and save securely.
   - Create a desktop shortcut **MYRA** on your Desktop and Start Menu.
   - Launch MYRA immediately!

### Option 2: 1-Line PowerShell Install
Open PowerShell and run:
```powershell
irm https://raw.githubusercontent.com/SaidulM/MYRA/main/install.ps1 | iex
```

### Option 3: Manual Start (Any OS)
Install Python 3.8+ and run:
```bash
python launcher.py   # checks GitHub updates + starts MYRA (desktop app on Windows)
# or
python run.py        # starts the legacy web version directly
```
For the web version, open `http://127.0.0.1:8765` in your browser (or `https://127.0.0.1:8765` only if you deliberately configured both `MYRA_TLS_CERT_FILE` and `MYRA_TLS_KEY_FILE`). For the native desktop app on Windows, double-click `MYRA.pyw` instead — no browser or console window is involved. The normal `127.0.0.1` connection stays inside your own laptop; cloud AI, GitHub, news and confirmed model downloads use HTTPS.

---

## 🔑 Free API Keys

MYRA requires no credit card and 0 cost:
1. **Google Gemini (Primary):** Go to [aistudio.google.com](https://aistudio.google.com) → Sign in → **Get API key** → **Create API key**.
2. **Groq (Backup):** Go to [console.groq.com](https://console.groq.com) → Sign in → **API Keys** → **Create API Key**.

Enter your key either during the initial setup wizard or inside the **SETTINGS** window in MYRA.

---

## 📂 Project Structure

```
MYRA/
├── MYRA-Installer.bat    ← 1-click standalone Windows installer
├── MYRA-Setup.bat        ← Local setup script
├── MYRA.bat              ← Main Windows start launcher (Desktop shortcut target)
├── start.bat             ← Instant start script
├── install.ps1           ← 1-line PowerShell installer
├── launcher.py           ← Smart GitHub auto-update sync, then opens the desktop app
├── auto_setup.py         ← Setup engine (copies files, stamps version, configures keys)
├── MYRA.pyw              ← Native desktop entry (pythonw, no console window)
├── run_desktop.py        ← Desktop GUI entry / first-run bootstrap trigger
├── run.py                ← Legacy web application runner (HTTP server + browser UI)
├── BLUEPRINT.md          ← Master architectural plan (all 11 stages completed)
├── README.md             ← Documentation and usage instructions
├── backend/
│   ├── server.py         ← Unified legacy HTTP server & API routing
│   ├── runtime_setup.py  ← Creates/checks local files, defaults and readiness behind every UI option
│   ├── api_v1.py         ← Core 2.0 `/api/v1` route mixin
│   ├── service.py        ← UI-independent Core service
│   ├── providers.py      ← Gemini/Groq Core planner/vision adapter
│   ├── skill_registry.py ← Typed Core skills and permissions
│   ├── core_agent.py     ← Bounded, confirmable Core Agent
│   ├── core_memory.py    ← App-data Core SQLite store
│   ├── chat.py           ← Multi-provider chat with key verification
│   ├── memory.py         ← Legacy SQLite local memory engine (Stage 4)
│   ├── notes.py          ← Legacy SQLite notes CRUD engine (Stage 7)
│   ├── skills_manager.py ← Legacy skills (Calculator, Web search, Weather, System)
│   ├── agent.py          ← Legacy multi-step research/local-intent agent (Stage 8)
│   ├── voice.py          ← Core voice-model records and consent-based downloads
│   ├── news.py           ← World Monitor RSS news feed & offline caching (Stage 10)
│   └── config.py         ← `.env` + OS credential-store configuration manager
├── desktop/              ← Smooth GPU web shell + PySide6 fallback (embedded backend)
├── packaging/            ← Python-only MYRA.exe builder, PyInstaller spec, Inno Setup
├── ui/
│   ├── index.html        ← UI shell + modals + 3D stages + full-screen windows
│   ├── style.css         ← Theme styling (Normal / Friendly / Hacker) & animations
│   ├── app.js            ← Three.js particle hologram, speech sync, Web Speech API
│   └── vendor/three.min.js ← Vendored Three.js (works offline)
├── tests/                ← Automated unittest test suite
└── data/                 ← myra.db (git-ignored, 100% private local data)
```

---

## 🔒 Security & Privacy

- Real API keys prefer the Windows/OS credential store when `keyring` is available, with the private local `.env` as fallback. Set `MYRA_SECRET_STORE=env` to force `.env`-only behavior.
- The UI never exposes full API keys (only masked tails like `••••a1b2`).
- The unified SQLite database lives in Windows app data (`%LOCALAPPDATA%\MYRA\myra.db`); it and any legacy `data/myra.db` are private/local and never committed.
- The server binds to `127.0.0.1` by default, so only your laptop can access it. In this normal mode, local HTTP never leaves the laptop; internet services (cloud AI, GitHub updates, RSS and confirmed model downloads) use verified HTTPS, while Ollama stays local.
- Optional local-server HTTPS is available for advanced setups by setting both `MYRA_TLS_CERT_FILE` and `MYRA_TLS_KEY_FILE` to a trusted certificate/key pair. Leave both empty for the normal desktop app.
- Phone Link is honestly **OFF** in local-only mode instead of showing a QR code that cannot work. `MYRA_HOST=0.0.0.0` is an explicit trusted-LAN opt-in: use trusted home Wi-Fi only and prefer HTTPS. A long `MYRA_API_TOKEN` is then required for Core API (`/api/v1/...`) action calls from other devices — but it is **not** a password for the whole web page, so never expose LAN mode beyond your own trusted network. MYRA's own screen on this laptop keeps working whether or not a token is set.
