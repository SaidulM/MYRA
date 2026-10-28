# MYRA 🤖 — Personal Desktop AI Assistant

**MYRA** is a personal desktop AI companion built to run light on an **8GB RAM** laptop — **100% free** to build and use, with no heavy local AI models.

- 🧠 **Brain:** Gemini API (primary) + Groq API (backup) on free tiers — the owner supplies both keys; **real text chat is live in Stage 3**
- ✨ **Particle character in 3 forms:** `CORE` (a living orb of light) · `MALE` (JARVIS-style assistant) · `FEMALE` (warm companion) — ~34,000 fine dots flow in waves and form a smooth futuristic figure, lit by a sweeping scan-light; drag to rotate in 3D
- 🎨 **Themes:** Normal (black) · Friendly (green) · Hacker (red) — plus an Awareness toggle, Profile, Feedback & Support in the top bar
- 💾 **Local memory** (SQLite) — remembers you, and everything stays on your laptop, never in the cloud
- 🎤 Voice + text conversation (smart silence detection) · 🤖 Browser Agent Mode · 📝 Notes
- 🌍 **World Monitor:** attaches the open-source live dashboard [worldmonitor.app](https://worldmonitor.app) (small live preview + full-screen tab), plus MYRA's own spinnable 3D Earth, a live satellite view, and real headlines that cache for offline reading
- 📷 Camera / screen: **OFF by default** — only with your permission, with a clear red LIVE indicator
- 🪟 Every module (Memory, Skills, Character, Settings, World) opens its own full-screen window with a Back button

📄 **Full plan:** [BLUEPRINT.md](BLUEPRINT.md) — built in 11 stages; the owner tests and approves each stage before the next begins.

## 🚧 Current build status
- ✅ **Stage 1:** complete interface and 3 particle characters
- ✅ **Stage 2:** API keys save locally in `.env` with masked status
- 🔄 **Stage 3 (in review):** real text chat — Gemini first, Groq fallback, with safe offline/missing-key notices
- ⏳ **Still to build:** long-term memory (4), full voice (5), speech-sync polish (6), notes/skills engine (7), browser Agent Mode (8), camera/screen vision (9), World Monitor backend/read-aloud (10), and one-run setup + desktop shortcut (11)

So MYRA is **not the finished software yet** — the remaining stages above complete it step by step.

## 🚀 Run it

### Windows (easiest)
1. Install Python 3.10+ from python.org (tick **"Add Python to PATH"**)
2. Double-click **`start.bat`** — an app-like window opens

### Any OS
```bash
python run.py
```
Then open http://127.0.0.1:8765 in your browser.

### Just want to see the UI?
Open **`MYRA-Preview.html`** in any browser — the whole interface (including the particle character) is inside that single file. No server is needed to view it, but **real AI chat and key-saving require the real app** (`start.bat` / `run.py`) because the Python backend must be running.

## 🔑 API Keys (Stages 2–3)
Easiest way: open MYRA → **SETTING** window → paste your free Gemini & Groq keys → **SAVE KEYS**. They are stored on your laptop only in a private `.env` file, survive restarts, and afterwards only the last 4 characters are ever shown. Stage 3 chat then uses Gemini first and automatically falls back to Groq if Gemini is unavailable. (Manual route: copy `.env.example` to `.env` and paste the keys there.)
Get them free: Gemini → aistudio.google.com → *Get API key*; Groq → console.groq.com → *API Keys*.
⚠️ **Never commit real keys to GitHub** (`.env` is git-ignored) and never paste them into any chat or website.

## 📂 Project Layout
- `backend/` — Python server, settings and cloud-chat engines
- `tests/` — lightweight automated checks for the chat fallback logic
- `ui/` — interface + particle hologram (Three.js, vendored locally — works offline)
- `skills/` — pluggable skills (Stage 7+)
- `data/` — private local data (git-ignored, never uploaded)
