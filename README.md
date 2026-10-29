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
   - **চলমান অবস্থায় আপডেট:** সফটওয়্যারটি চলার সময়ও প্রতি ৫ মিনিট পর পর ব্যাকগ্রাউন্ডে চেক করবে। গিটহাবে কোনো নতুন আপডেট আসলে ল্যাপটপের স্ক্রিনে বড় আপডেট নোটিশ ভেসে উঠবে এবং **"Update MYRA Now"** বাটনে ক্লিক করলেই এক ক্লিকে সম্পূর্ণ আপডেট হয়ে সফটওয়্যারটি রিলোড নেবে।

---

## 🌟 Key Features

- 🧠 **Dual AI Brain:** Google Gemini (Free & Paid keys supported with dynamic auto-model discovery: 1.5-Flash, 1.5-Pro, 2.0-Flash) + Groq API (fallback) with live key verification.
- ✨ **3D Hologram Particle Characters:**
  - `CORE` (living orb of light)
  - `MALE` (professional JARVIS-style assistant)
  - `FEMALE` (warm, caring companion)
  - Smooth wave-particle transitions, scan-light lighting, and 3D rotation.
- 🎤 **Voice with Smart Silence Detection:** Talk naturally into your microphone; MYRA listens, detects when you stop speaking, and speaks her answer back aloud.
- 💾 **Local Memory Engine (SQLite):** Remembers facts and preferences about you on your laptop (`data/myra.db`). Never uploaded to any cloud.
- 🤖 **Autonomous Agent Mode:** Give a complex task or query, and MYRA's agent conducts multi-step web research, gathers sources, and generates a structured intelligence report.
- 📝 **Offline Notes Mode:** Create, view, and delete personal notes stored in local SQLite database.
- 🧩 **Built-in Skills Engine:** Safe math calculator, live weather reports, system diagnostics, and web search.
- 📷 **Visual Hub (Camera & Screen Share):** Permission-based camera and screen viewing with a clear red LIVE indicator.
- 🌍 **World Monitor:** Spinnable 3D Earth, interactive map, and live RSS news feed (cached for offline reading) with read-aloud support.
- 🛡️ **Zero Data Leakage:** Your `.env` and personal memory databases are strictly kept on your laptop.

### Core 2.0 service/native layer (integrated Oct 2026)

The existing web experience above remains intact. MYRA also now includes a separate service-oriented **Core 2.0 foundation**:

- `/api/v1` routes for persistent conversations, user-approved memories, notes, skills, bounded Agent tasks, one-frame vision, export/backup and voice-model status.
- Twelve typed, validated skills. Confirmable write/launch/open actions are limited to MYRA's safe workspace or an allowlist; Core Chat receives no computer-control tools.
- A PySide6 native operational window (`MYRA-Desktop.bat` for the source test build) using the same backend. Full Three.js MALE/FEMALE hologram parity in Qt and a physically tested EXE/installer are still future work.
- API secrets prefer the OS credential store when `keyring` is available; the private `.env` remains the fallback. Settings responses are masked and accept both current and older key field names.

For a safe merge, the legacy web memory/notes in `data/myra.db` and the Core database under Windows app data (`%LOCALAPPDATA%\MYRA`) currently remain separate. Unifying those stores without data loss is a later migration step. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/REFERENCE_ANALYSIS.md`](docs/REFERENCE_ANALYSIS.md) for the honest capability boundaries.

---

## 💻 Installation & Usage (English)

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
python launcher.py   # checks GitHub updates + starts MYRA
# or
python run.py        # starts MYRA directly
```
Then open `http://127.0.0.1:8765` in your browser.

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
├── launcher.py           ← Smart GitHub auto-update sync & runner
├── auto_setup.py         ← Setup engine (copies files, stamps version, configures keys)
├── run.py                ← Core application runner (HTTP server + app window)
├── BLUEPRINT.md          ← Master architectural plan (all 11 stages completed)
├── README.md             ← Documentation and usage instructions
├── backend/
│   ├── server.py         ← Unified legacy HTTP server & API routing
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
- The legacy SQLite database (`data/myra.db`) and Core app-data database are private/local and never committed.
- The server binds to `127.0.0.1` by default, so only your laptop can access it. `MYRA_HOST=0.0.0.0` is an explicit opt-in for trusted-LAN/mobile use; API v1 action routes then also require `MYRA_API_TOKEN`.
