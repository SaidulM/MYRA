# MYRA 🤖 — Personal Desktop AI Assistant

**MYRA** is a personal desktop AI companion built to run light on an **8GB RAM** laptop — **100% free** to build and use, with no heavy local AI models.

- 🧠 **Brain:** Gemini API (primary) + Groq API (backup) on free tiers — the owner supplies both keys; **real text chat is live in Stage 3**
- ✨ **Particle character in 3 forms:** `CORE` (a living orb of light) · `MALE` (JARVIS-style assistant) · `FEMALE` (warm companion) — ~34,000 fine dots flow in waves and form a smooth futuristic figure, lit by a sweeping scan-light; drag to rotate in 3D
- 🎨 **Themes:** Normal (black) · Friendly (green) · Hacker (red) — plus an Awareness toggle, Profile, Feedback & Support in the top bar
- 💾 **Local memory** (SQLite) — persistent conversations, user-approved memories and notes stay in your Windows app-data folder
- 🤖 **Safe Agent Mode foundation:** typed registered skills, task approvals, pause/resume/cancel and verified local workspace actions
- 🎤 **Voice status:** browser read-aloud works; realtime native voice is not finished until its one-time speech models and Windows audio path pass physical tests
- 🌍 **World Monitor:** attaches the open-source live dashboard [worldmonitor.app](https://worldmonitor.app) (small live preview + full-screen tab), plus MYRA's own spinnable 3D Earth, a live satellite view, and real headlines that cache for offline reading
- 📷 Camera / screen: **OFF by default**. The web Visual Hub can now capture and analyze **one explicitly approved frame**, then immediately stops; continuous live sharing is not enabled yet
- 🪟 Every module (Memory, Skills, Character, Settings, World) opens its own full-screen window with a Back button

📄 **Full plan:** [BLUEPRINT.md](BLUEPRINT.md) — built in 11 stages; the owner tests and approves each stage before the next begins.

## 🚧 Current build status
- ✅ **Stage 1:** complete web interface and 3 particle characters
- ✅ **Stage 2:** API keys save locally with masked status; OS credential storage is used automatically when `keyring` is installed, otherwise private `.env`
- 🔄 **Stage 3:** real text chat — Gemini first, Groq fallback. A previously hidden Settings field-name bug that could make the UI claim a key saved when the backend ignored it is fixed on both sides and needs owner re-testing
- 🆕 **Core 2.0 foundation:** SQLite persistent chat/user-approved memory/notes, provider capability + Gemini/Groq tool adapters, 12 safe registered skills, bounded Agent Mode, API v1, one-frame Gemini vision, a PySide6 native operational shell and Windows packaging scaffold
- 🆕 **One-run Windows setup + auto-update:** install once, then every start refreshes MYRA from GitHub automatically
- ⏳ **Not finished yet:** realtime native voice/speech models, continuous live camera/screen, browser research automation, semantic Windows desktop control, native MALE/FEMALE hologram parity, and a physically tested signed EXE/installer

Detailed evidence and limits are in [`docs/REFERENCE_ANALYSIS.md`](docs/REFERENCE_ANALYSIS.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). MYRA does not label those unfinished items as working features.

## 🚀 Install & run it

### Windows — one-time install (recommended)
1. Download this repo once (GitHub → **Code → Download ZIP**) and extract it.
2. Double-click **`MYRA-Setup.bat`** — it installs Python automatically if needed, installs MYRA to `C:\Users\<you>\MYRA`, and puts a **MYRA icon on your Desktop + Start Menu**.
3. From then on, just double-click the **MYRA desktop icon**: every start checks GitHub, **downloads any new update by itself**, and opens MYRA. Your API keys (`.env`) and data are never overwritten, and if you're offline it simply starts the installed version.
   - `start.bat` / `MYRA.bat --no-update` starts instantly without the update check.
   - If something looks wrong at startup, check `launcher-log.txt` in the install folder.

### Any OS (manual)
Install Python 3.10+, then:
```bash
python launcher.py   # auto-update + start
# or: python run.py  # start only, no update check
```
Then open http://127.0.0.1:8765 in your browser.

### Native desktop shell from source (Windows test build)
The native PySide6 window uses the same backend and local data. It is ready for Windows testing from source, but the full Three.js MALE/FEMALE hologram has not been ported into Qt yet.

Easiest owner test: double-click **`MYRA-Desktop.bat`**. The first run clearly downloads PySide6 + keyring once from PyPI into `.venv-desktop`; later runs reuse them. Manual equivalent:
```powershell
py -m pip install -r requirements-desktop.txt
py run_desktop.py
```
For a future EXE/installer build on Windows, see `packaging/build_windows.ps1`, `packaging/MYRA.spec` and `packaging/MYRA.iss`. These packaging files still need a real Windows build/test before any release claim.

### Just want to see the UI?
Open **`MYRA-Preview.html`** in any browser — the whole interface (including the particle character) is inside that single file. No server is needed to view it, but **real AI chat and key-saving require the real app** (`start.bat` / `run.py`) because the Python backend must be running.

## 🔑 API Keys (Stages 2–3)
Easiest way: open MYRA → **SETTING** window → paste your free Gemini & Groq keys → **SAVE KEYS**. The UI now waits for backend confirmation and shows only masked status. If `keyring` is installed, new keys prefer Windows Credential Manager; otherwise they remain in the private local `.env`. Chat uses Gemini first and automatically falls back to Groq if Gemini is unavailable. (Manual route: copy `.env.example` to `.env` and paste the keys there.)
Get them free: Gemini → aistudio.google.com → *Get API key*; Groq → console.groq.com → *API Keys*.
⚠️ **Never commit real keys to GitHub** (`.env` is git-ignored) and never paste them into any chat or website.

## 📂 Project Layout
- `backend/` — Python server, service layer, provider/tool adapters, SQLite memory, safe skills and bounded Agent engine
- `desktop/` — native PySide6 shell (Chat, Agent, Skills, Memory, Notes, Settings, Diagnostics)
- `tests/` — automated provider, memory, skill, agent and secret-storage checks
- `ui/` — existing MYRA interface + particle hologram (Three.js, vendored locally)
- `docs/` — verified reference analysis and current architecture/honest capability status
- `packaging/` — PyInstaller and Inno Setup scaffolds for a future tested Windows build
- Personal Core 2.0 data defaults outside the repo/install folder: `%LOCALAPPDATA%\MYRA` on Windows
