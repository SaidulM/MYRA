# MYRA Native Desktop (Windows) — Owner Guide

MYRA's primary interface is a pure Python (PySide6) desktop window. There is
**no Command Prompt, no PowerShell and no browser window** when it runs: the
backend lives inside the same Python GUI process.

## Starting MYRA (daily use)

Pick whichever you already have:

1. **Desktop / Start-Menu "MYRA" shortcut** — checks GitHub for updates
   first (your keys and data are never overwritten), then opens the desktop
   app and closes its own window.
2. **`MYRA.pyw`** in the MYRA folder — double-click to open the desktop app
   immediately with the installed version (no update check).
3. **`MYRA.exe`** — if the packaged build has been created (see below).

The legacy web UI is still available with `MYRA.bat --web` if ever needed.

## First run on a fresh copy

The first double-click of `MYRA.pyw` opens a small **Python setup window**
that creates `.venv-desktop` and downloads the pinned packages (PySide6 6.8.x,
keyring, Edge TTS, faster-whisper, pywinauto, Playwright) from PyPI. This is
a one-time download; later starts open directly. Keep the laptop online for
this step.

## API keys

1. Open MYRA → **Settings** (left menu).
2. Choose a provider (Gemini is the free primary; Groq is the free backup).
3. Paste the key and save. Keys are stored in Windows Credential Manager
   when available and are only ever shown masked (for example `••••a1b2`).
   Never paste a real key into chat, GitHub or screenshots.

Free keys: Gemini — <https://aistudio.google.com> · Groq —
<https://console.groq.com>.

## Voice (realtime speaking)

1. Open **Voice**. The status box shows exactly which engines are ready.
2. Pick a Whisper model (`base` recommended for 8GB RAM) and press
   **Download STT model…** — MYRA asks first and shows the size (~145 MB).
   The model is downloaded once into app data and reused on every start.
3. Press **Start realtime**, allow the microphone, and just talk. MYRA
   listens, transcribes locally, answers with the cloud AI, and speaks.
   **Interrupt speech** (or simply talking over her) stops playback;
   **End call** releases the microphone.
4. Offline note: speech-to-text can be local, but the AI "brain" is a cloud
   API, so answers still need internet.

## Live Vision (screen / camera)

Capture is **OFF by default**. On the **Live Vision** page you choose the
source, see a local preview, and press **Start with consent**. A red LIVE
indicator stays visible while frames are sampled at your chosen interval.
**Pause** stops sending; **Stop & release** ends the session and frees the
camera/screen immediately. Nothing is captured after Stop.

## Computer control (Agent power, gated)

- The **Computer** page and Agent Mode can observe and operate Windows apps
  (semantic UI Automation first, coordinate clicks only as a fallback) and a
  visible browser (Playwright).
- Every control action needs the confirmation box ticked, shows a red
  **MYRA IS CONTROLLING** banner while it acts, and can be halted instantly
  with **EMERGENCY STOP**.
- MYRA always refuses password fields, OTP/MFA and CAPTCHA steps — she will
  ask you to do those parts yourself.

## Your data

Everything private lives in `%LOCALAPPDATA%\MYRA\` (database, workspace,
speech models, backups) — outside the install folder, so updates and
reinstalls keep it. Old `data\myra.db` contents are imported automatically
once; **Diagnostics → Import legacy data** can re-run the import safely.

## Building MYRA.exe (optional)

On the Windows laptop, from the MYRA folder:

```text
py -3 packaging\build_windows.py
```

This prepares `.venv-build`, runs the test suite, builds the windowed
`dist\MYRA\MYRA.exe`, verifies it with a self-test, and (if Inno Setup is
installed) produces an installer in `dist\installer\`. Personal data is not
bundled into the build.

## Troubleshooting

- **Window shows "Checking embedded MYRA backend…" and never finishes** —
  another program may be using port 8765. Close other MYRA copies, or set
  the environment variable `MYRA_PORT` to a free port (for example `8877`)
  before starting.
- **No microphone/camera listed** — check Windows Settings → Privacy &
  security → Microphone/Camera and allow desktop apps. The Live Vision
  page's device boxes show the exact QtMultimedia error when something is
  blocked.
- **"faster-whisper not installed" on the Voice page** — run the first-run
  setup again by deleting `.venv-desktop` and double-clicking `MYRA.pyw`,
  or install into that environment from `requirements-voice.txt`.
- **Update window reports no internet** — MYRA simply starts the installed
  version; nothing is broken. Updates require verified HTTPS to GitHub.
- **`launcher-log.txt`** in the MYRA folder records update/start messages.
