# MYRA Desktop (Windows) — Owner Guide

MYRA opens in its own smooth desktop window showing the familiar MYRA
interface. Windows' GPU WebView2 engine renders the hologram inside that
window, while the Python backend lives in the same app process. There is
**no Command Prompt, no PowerShell and no external browser window** when
it runs. The older all-Qt window remains available with `MYRA_UI=qt` if
the WebView2 runtime is unavailable or for the advanced native pages.

## Starting MYRA (daily use)

Pick whichever you already have:

1. **Desktop / Start-Menu "MYRA" shortcut** — checks GitHub for updates
   first (your keys and data are never overwritten), then opens the desktop
   app and closes its own window.
2. **`MYRA.pyw`** in the MYRA folder — double-click to open the desktop app
   immediately with the installed version (no update check).
3. **`MYRA.exe`** — if the packaged build has been created (see below).

The same interface can also be opened as the legacy browser UI with `MYRA.bat --web` if ever needed.

## First run on a fresh copy

The first double-click of `MYRA.pyw` opens a small **Python setup window**
that creates `.venv-desktop` and downloads the pinned packages (pywebview, PySide6 6.8.x,
keyring, Edge TTS, faster-whisper, pywinauto, Playwright) from PyPI. This is
a one-time download; later starts open directly. Keep the laptop online for
this step.

## API keys

1. Open MYRA → **SETTING**.
2. Paste and save the key/model for the brain you want to use.
3. Pick that brain in the top **BRAIN** switcher. An explicit choice is
   final: if you select **Ollama Local**, MYRA uses Ollama or clearly says
   it is not configured/running — it will not silently answer as Gemini.
   Choose **Auto** only when you want MYRA to pick the best configured
   brain. Keys are stored in Windows Credential Manager when available and
   are only ever shown masked (for example `••••a1b2`). Never paste a real
   key into chat, GitHub or screenshots.

Free keys: Gemini — <https://aistudio.google.com> · Groq —
<https://console.groq.com>.

## Voice, Live Vision and Computer control

The default smooth window now contains the live-voice and Core Agent
paths directly in MYRA's original interface:

- **Live voice (one-time setup)** — open **CHARACTER → VOICE STUDIO →
  Live Voice Hearing** and tap **INSTALL LIVE-VOICE MODEL · BASE** twice
  to confirm the ~145 MB faster-whisper download. It is saved on this PC
  and never downloads silently. After setup, tap the mic under the
  hologram, speak, and pause; MYRA shows the transcript, answers with
  the brain selected at the top, speaks only the main reply, then listens
  again. Tap the mic again to stop, or the speaker button to mute MYRA.
  **CORE/MALE = male voice, FEMALE = female voice.**
- **Agent Mode** — open the **AGENT** tab, describe a real task, and
  watch each step in the log. MYRA uses one registered skill at a time
  and stops for **APPROVE/DENY** before write/control skills. Use
  **PAUSE**, **RESUME**, **STOP**, or **EMERGENCY** (Windows control) at
  any time. To let it work inside Windows apps, first enable
  **SKILLS → PC Control (Agent)**. Password, OTP/MFA and CAPTCHA steps
  are always refused and left to you.
- **Live Vision** — capture is OFF by default; use the Visual Hub only
  after choosing camera/screen, and stop it to release the device.

Offline note: speech-to-text and an installed Ollama model can be local;
cloud brains and Edge neural voices still need internet.

## Your data

Everything private lives in `%LOCALAPPDATA%\MYRA\` (database, workspace,
speech models, backups, webview profile) — outside the install folder, so updates and
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

- **MYRA window does not open or stays blank** — close other MYRA copies
  (port 8765 may be busy), check that Microsoft Edge WebView2 Runtime is
  installed/updated, then try again. MYRA automatically falls back to the
  Qt window if the smooth shell cannot start.
- **Microphone/camera permission is denied** — allow the permission
  prompt inside MYRA and check Windows Settings → Privacy & security →
  Microphone/Camera for desktop apps.
- **Mic turns on but MYRA does not hear you** — first finish the one-time
  model setup in **CHARACTER → VOICE STUDIO → Live Voice Hearing**. If it
  says the voice package is missing, close MYRA, delete `.venv-desktop`,
  and double-click `MYRA.pyw` so first-run setup can reinstall packages.
  Also confirm Windows microphone privacy allows desktop apps.
- **Selected Ollama but MYRA reports it unavailable** — start the Ollama
  app, make sure the exact model shown in **SETTING** is installed, then
  try again. MYRA intentionally will not fall back to Gemini while
  Ollama is explicitly selected.
- **Update window reports no internet** — MYRA simply starts the installed
  version; nothing is broken. Updates require verified HTTPS to GitHub.
- **`launcher-log.txt`** in the MYRA folder records update/start messages.
