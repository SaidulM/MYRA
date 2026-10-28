# MYRA 🤖 — Personal Desktop AI Assistant

**MYRA** is a personal desktop AI companion built to run light on an **8GB RAM** laptop — **100% free** to build and use, with no heavy local AI models.

- 🧠 **Brain:** Gemini API (primary) + Groq API (backup) on free tiers — the owner supplies both keys
- ✨ **Particle character in 3 forms:** `CORE` (a living orb of light) · `MALE` (JARVIS-style assistant) · `FEMALE` (warm companion) — ~34,000 fine dots flow in waves and form the figure; drag to rotate in 3D
- 💾 **Local memory** (SQLite) — remembers you, and everything stays on your laptop, never in the cloud
- 🎤 Voice + text conversation (smart silence detection) · 🤖 Browser Agent Mode · 📝 Notes
- 🌍 **World Monitor:** dotted world map + a spinnable 3D Earth with live headlines
- 📷 Camera / screen: **OFF by default** — only with your permission, with a clear red LIVE indicator
- 🪟 Every module (Memory, Skills, Character, Settings, World) opens its own full-screen window with a Back button

📄 **Full plan:** [BLUEPRINT.md](BLUEPRINT.md) — built in 11 stages; the owner tests and approves each stage before the next begins.

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
Open **`MYRA-Preview.html`** in any browser — the whole interface (including the particle character) is inside that single file. No server needed.

## 🔑 API Keys (from Stage 2)
Copy `.env.example` to `.env` and paste your free Gemini/Groq keys.
⚠️ **Never commit real keys to GitHub** — `.env` is git-ignored.

## 📂 Project Layout
- `backend/` — Python server & engines
- `ui/` — interface + particle hologram (Three.js, vendored locally — works offline)
- `skills/` — pluggable skills (Stage 7+)
- `data/` — private local data (git-ignored, never uploaded)
