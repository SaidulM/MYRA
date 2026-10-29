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

1. Open MYRA → **SETTINGS**.
2. Choose a provider (Gemini is the free primary; Groq is the free backup).
3. Paste the key and save. Keys are stored in Windows Credential Manager
   when available and are only ever shown masked (for example `••••a1b2`).
   Never paste a real key into chat, GitHub or screenshots.

Free keys: Gemini — <https://aistudio.google.com> · Groq —
<https://console.groq.com>.

## Voice, Live Vision and Computer control

The default smooth window keeps MYRA's established voice, Visual Hub,
Agent, Notes and World controls from the original interface. The newer
advanced native pages remain in the Qt fallback window (`MYRA_UI=qt`):

- **Realtime native voice** — microphone → local faster-whisper → cloud AI
  → Edge TTS / Windows SAPI → speaker, with **Download STT model…**,
  mute, barge-in and **End call**. The Whisper `base` model (~145 MB) is
  recommended for 8GB RAM and is downloaded only after confirmation.
- **Live Vision** — capture is OFF by default; choose screen/camera, see
  the local preview, press **Start with consent**, and use **Stop &
  release** to free the device immediately.
- **Computer control** — every action needs confirmation, shows the red
  **MYRA IS CONTROLLING** banner, can be halted with **EMERGENCY STOP**,
  and always refuses password, OTP/MFA and CAPTCHA steps.

Offline note: speech-to-text can be local, but the AI "brain" is a cloud
API, so answers still need internet.

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
- **"faster-whisper not installed" on the Voice page** — run the first-run
  setup again by deleting `.venv-desktop` and double-clicking `MYRA.pyw`,
  or install into that environment from `requirements-voice.txt`.
- **Update window reports no internet** — MYRA simply starts the installed
  version; nothing is broken. Updates require verified HTTPS to GitHub.
- **`launcher-log.txt`** in the MYRA folder records update/start messages.
