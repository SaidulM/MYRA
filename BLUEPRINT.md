# 🤖 MYRA — BLUEPRINT (Master Plan)

> **Purpose of this file:** the complete blueprint of the project. Any future
> agent/developer reading this should know exactly what to build, how, and in
> which stage. The owner (Saidul Islam Mondal) does not write code himself —
> an AI coding agent writes code, the owner tests each stage and **approves**
> it; only then does the next stage begin.

---

## 1. Project Overview

| Item | Detail |
|---|---|
| Name | **MYRA** — Personal Desktop AI Assistant |
| Target machine | Windows laptop, **8GB RAM** — must stay lightweight, no hanging |
| Cost | **100% free** to build and to run |
| Local AI model | **No** — no heavy model downloads on the laptop |
| AI brain | Cloud APIs — **Gemini (primary)** + **Groq (fallback)**, both free tiers |
| API keys | **The owner supplies both free API keys** (entered in the Settings window / `.env`) |
| Online | Cloud AI chat / voice / agent work |
| Offline | Local memory, notes, settings still work (chat shows an "offline" notice) |
| UI language | **English** throughout the app and README |

---

## 2. Feature List (Owner Requirements)

1. **Particle character (3D hologram):** a **chest-up particle bust** (head +
   neck + shoulders, no full body) made of ~34,000 fine dots (Three.js). The
   dots flow in **waves** from a scattered cloud and **form** the figure;
   switching character scatters them and they re-form. The figure is a
   **smooth futuristic silhouette** — identity comes from body shape and
   hair (no carved eyes/lips), with soft light shading. A **scan-light**
   band sweeps through the dots bottom-to-top (no ring meshes). Head moves
   while speaking. Drag to rotate in 3D. Themes (Normal black / Friendly
   green / Hacker red) tint the whole UI and the character.
   - **CORE** → pure AI core: a living sphere of light with orbit rings
   - **MALE** → male bust (short hair, broad shoulders) + male voice;
     personality: professional **JARVIS-style assistant**
   - **FEMALE** → female bust (long wavy hair) + female voice;
     personality: warm, caring **companion**
   - The character switch lives in exactly ONE place: the selector above the
     hologram frame. **No duplicated controls anywhere in the UI.**
2. **Voice + text:** the assistant always listens, but replies only **after
   the user fully finishes speaking** (smart silence detection).
3. **Local memory (SQLite):** daily conversations and preferences stored on
   the laptop (not in the cloud); the assistant recognizes the user and bonds
   emotionally, improving over time.
4. **Skills system:** add new skills over time; each skill has its own ON/OFF.
5. **Camera & screen share:** **OFF by default**; only active when the user
   turns them on (in the Visual Hub — their only home); a clear red LIVE
   indicator shows while on.
6. **Agent Mode (browser control):** on command, MYRA opens the browser
   herself, searches/works and reports back (Playwright).
7. **Notes Mode:** create / view / edit / delete notes, saved locally.
8. **World Monitor:** a live-preview window (dotted world map + hotspots +
   top headlines) that expands into a full-screen monitor: spinnable **3D
   Earth**, a **live satellite** embed tab (internet only), region filters.
   Headlines come from free public RSS while online and are **cached
   locally** so the panel still shows the last copy offline (backend feed
   in Stage 10); on request MYRA reads today's headlines aloud.
9. **Interface layout (one compact screen, small dense labels — nothing
   oversized):**
   - Left: SAT-LINK feed (live monitor mini-preview + a few headlines +
     quick tabs into the full World Monitor)
   - Center: the particle CORE stage; module chips **MEMORY / SKILLS /
     CHARACTER / SETTING** wired into the frame with colored circuit lines;
     a **TERMINATE / ACTIVATE** power button sitting directly under the
     frame; below it the Visual Hub
   - Slim top bar: left = app name + **Feedback** + **Support**; right
     (compact, opposite them) = version, **Awareness** ON/OFF switch,
     **Theme** picker, **Profile** menu, server status, clock
   - Beside TERMINATE: mic ON/OFF + voice mute/stop buttons
   - Right: a narrow conversation panel with 3 tabs — **Voice / Agent /
     Notes** — plus a toolbar (new chat ＋, history, session console </>,
     full-view expand, and a clearly labelled **HIDE** button)
   - Every module (World, Memory, Skills, Character, Settings) opens its own
     **full-screen window** with a **← BACK** button returning to the main view

---

## 3. Tech Stack (light on 8GB RAM)

| Part | Technology | Notes |
|---|---|---|
| Backend | **Python (stdlib-first)** — `http.server` | serves UI + API, no extra packages |
| Frontend | HTML + CSS + vanilla JavaScript | runs in a browser / app window |
| 3D hologram & Earth | **Three.js r128** (vendored in `ui/vendor/` — works offline) | fine-dot particle figures |
| Database | **SQLite** (Python built-in) | memory, notes, settings |
| AI APIs | Gemini REST + Groq REST via `urllib` | no heavy SDKs |
| Speech-to-text | Web Speech API (browser built-in) | free, no install |
| Text-to-speech | Web Speech API `speechSynthesis` | male/female OS voices |
| Browser automation | **Playwright** (Stage 8) | Agent Mode |
| Launcher | `MYRA-Setup.bat` → `auto_setup.py` (one-time install + shortcuts); `MYRA.bat`/`start.bat` → `launcher.py` (GitHub auto-update, then `run.py`: server + app window) | Windows double-click start; updates download themselves at every start |

---

## 4. Folder Structure

```
MYRA/ (repo root)
├── BLUEPRINT.md          ← this file (master plan)
├── README.md
├── MYRA-Preview.html     ← single-file UI preview (no server needed)
├── .env.example          ← placeholders only (real keys are NEVER in Git)
├── .env                  ← real API keys (git-ignored)
├── .gitignore
├── requirements.txt      ← Playwright joins in Stage 8
├── run.py                ← core runner (server + app window)
├── launcher.py           ← smart start: GitHub auto-update → run.py
├── MYRA.bat              ← Windows start (Desktop shortcut points here)
├── start.bat             ← same start path (calls MYRA.bat)
├── MYRA-Setup.bat        ← ONE-TIME setup (installs Python if missing)
├── auto_setup.py         ← installer: copy to ~\MYRA + Desktop/Start-Menu shortcuts
├── tests/                ← lightweight automated backend checks
├── backend/
│   ├── server.py         ← light stdlib HTTP server (UI + API)
│   ├── config.py         ← loads settings from .env (Stage 2)
│   ├── chat.py           ← Gemini + Groq fallback (Stage 3)
│   ├── memory.py         ← SQLite memory (Stage 4)
│   ├── notes.py          ← notes CRUD (Stage 7)
│   ├── skills_manager.py ← skill ON/OFF registry (Stage 7)
│   ├── agent.py          ← Playwright browser automation (Stage 8)
│   └── news.py           ← World Monitor RSS feed (Stage 10)
├── ui/
│   ├── index.html        ← full interface (incl. full-screen windows)
│   ├── style.css
│   └── app.js            ← UI logic + Three.js particle characters + Earth
├── skills/               ← one .py file per skill (Stage 7+)
└── data/                 ← myra.db (git-ignored — private data)
```

---

## 5. Build Stages (STRICT ORDER — never skip a stage)

> **Rule: at the end of every stage the agent STOPS → the owner tests → only
> after the owner says "approved" does the next stage begin.**

| Stage | Work | How the owner verifies | Status |
|---|---|---|---|
| **1** | Folder structure + **complete UI** (3 particle characters with wave-formation, TERMINATE power, module chips + full-screen windows, SAT-LINK map + 3D Earth shell, Visual Hub, 3 conversation tabs) | `run.py` opens the window; characters form and can be rotated/switched; every window opens and goes Back (backend features are placeholders) | ✅ Approved (owner, Oct 2026) |
| **2** | Settings: save API keys (Gemini/Groq) via `.env` + UI (`backend/config.py`, `/api/settings`; UI only ever sees masked key status) | Keys persist across app restarts | ✅ Implemented (owner verification pending) |
| **3** | Text chat: Gemini first, Groq fallback (`backend/chat.py`, `/api/chat`), recent-conversation context, character/personality-aware replies, safe missing-key/offline/rate-limit notices | With keys saved on the laptop, chat answers like a real AI and shows which provider answered | 🔄 In review |
| **4** | Local memory (SQLite) — saves facts, uses them in replies | "My name is X" is remembered next session | ⏳ |
| **5** | Voice: listening (silence detection) + speaking (male/female voice) | Speak and hear a spoken reply | ⏳ |
| **6** | Hologram speech sync (movement while speaking) | Moves while talking, calm while silent | ⏳ |
| **7** | Notes Mode (CRUD) + Skills engine (ON/OFF) | Notes persist; skill toggles work | ⏳ |
| **8** | Agent Mode — Playwright: search → summary report | "Search this" makes the browser work alone | ⏳ |
| **9** | Camera & screen share (both default OFF, LIVE indicator when on) | Sees nothing until toggled; red indicator on | ⏳ |
| **10** | World Monitor — live headlines + read-aloud | Real news in the panel; reads on request | ⏳ |
| **11** | `auto_setup.py` + Windows desktop shortcut + auto-updating launcher | One run sets up everything; double-click starts | 🔄 Built early at owner's request (Oct 2026) — setup + GitHub auto-update done; final polish/approval with Stage 11 |

---

## 6. Security Rules (mandatory)

- API keys are **never** committed to GitHub — `.env` is in `.gitignore`.
- The repo only contains `.env.example` (empty placeholders).
- The `data/` folder (memory DB) never goes to Git — private data.
- Camera/screen default OFF; a clear 🔴 indicator shows while ON.
- The server binds to `127.0.0.1` by default (only this laptop can reach it).
- **Nobody needs the owner's GitHub password/token — ever.** Development
  happens through Arena's built-in GitHub connection on session branches,
  and the owner merges pull requests after reviewing them.

---

## 7. UI Customization

- The owner can reshape the UI freely: keep what's needed, remove what isn't.
- Each stage, the agent explains what every button/panel does and what will
  start working once that stage's backend lands.

---

## 8. Setup + auto-update (Stage 11 — built early, Oct 2026)

One-time: the owner downloads the repo ZIP once → double-clicks
`MYRA-Setup.bat` → it installs Python if missing (winget, else opens
python.org), runs `auto_setup.py`, which installs MYRA to
`%USERPROFILE%\MYRA`, creates Desktop + Start Menu shortcuts and stamps
the installed GitHub version in `.myra-version`.

Every start after that (Desktop icon / `MYRA.bat` / `start.bat`) runs
`launcher.py`: it checks GitHub `main` for a newer commit; if found, it
downloads the repo ZIP and refreshes the install — **never** overwriting
`.env` (API keys) or `data/` (private data) — then launches via `run.py`.
Offline or on any update error it simply starts the installed version.
`--no-update` skips the check; progress is logged to `launcher-log.txt`,
which the owner can show the agent when reporting a problem.

---

## 9. Future (not in the current build)

- **GitHub Control Skill** — added later as a separate skill so MYRA can
  manage GitHub repos herself. The skill registry keeps this pluggable.

---

## 10. Working Method (for future agents)

- One AI coding agent writes the code; MYRA does not build herself.
- Talk to the owner in **Bengali**, step by step, with clear test instructions.
  The app UI itself is in **English**.
- End of every stage: stop → give test steps → wait for approval.
