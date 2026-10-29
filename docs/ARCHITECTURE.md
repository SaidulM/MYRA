# MYRA Architecture (Core 3.0 — smooth desktop)

```text
┌──────────────────────────────────────────────────────────────┐
│ Original UI in GPU shell (ui/)   Qt fallback UI (desktop/)   │
└──────────────────┬───────────────────────┬───────────────────┘
                   │                       │
                   └──────────┬────────────┘
                              │ local HTTP (loopback by default)
                    ┌─────────▼─────────┐
                    │ server.py+api_v1.py│ legacy API + /api/v1
                    └─────────┬─────────┘
                    ┌─────────▼─────────┐
                    │ backend/service.py│  UI-independent service layer
                    └──┬──────┬──────┬──┘
                       │      │      │
              ┌────────▼─┐ ┌──▼──────▼──┐ ┌──────────────┐
              │ chat.py  │ │ core_agent.py   │ │ core_memory.py    │
              │ Gemini→  │ │ bounded    │ │ SQLite       │
              │ Groq     │ │ planner    │ │ conversations│
              └────┬─────┘ └──┬─────────┘ │ memories     │
                   │          │           │ notes/tasks  │
              ┌────▼──────────▼──┐        └──────────────┘
              │ providers.py     │
              │ capability/tool  │
              │ schemas + vision │
              └──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │ skill_registry.py │ typed, validated skills
                    └───────────────────┘
```

## Integration note (updated Oct 2026)

- The **default desktop window is `desktop/web_shell.py`**: the owner's original `ui/` interface rendered by the OS GPU web engine (WebView2 on Windows) in a native app window. `desktop/embedded_backend.py` runs `server.create_server(...)` in a daemon thread inside the same process (`MYRA.pyw`/`pythonw` in source mode, windowed `MYRA.exe` when packaged). No CMD/PowerShell, external browser window or child Python backend exists at runtime.
- The all-Qt PySide6 window remains an advanced fallback (`MYRA_UI=qt` / `--qt`); its QPainter hologram was CPU-bound and stuttered for the owner, so it is no longer the default. The auto-update `launcher.py` opens `MYRA.pyw` after updating (`--web` forces the legacy browser UI).
- **One unified SQLite store.** `backend/core_memory.py` (schema v2, app-data `myra.db`) owns conversations, memories, notes, reminders, preferences and tasks. Legacy `backend/memory.py`, `notes.py` and `reminders.py` keep their old APIs but delegate to this store, and legacy `data/myra.db` rows are imported once (idempotent, legacy IDs tracked in `legacy_id_map`). A note or memory created in either surface now appears in both.
- Core Chat calls the shared provider layer with legacy local-intent execution, silent auto-learning and legacy-memory injection disabled. The older web chat retains its existing behavior for compatibility, so its local actions are not the same confirmation boundary as Core Agent Mode.
- Provider layer (`backend/providers.py`) implements streaming, validated structured JSON, tool calling and vision across Gemini/Groq/OpenAI-compatible providers, advertising only capabilities each adapter actually implements.
- **Explicit brain selection is authoritative** in legacy chat, Core streaming fallback and Agent planning. If the owner selects Ollama (or any listed provider), MYRA uses only that provider or returns a provider-specific not-configured/unreachable error; it never silently labels a Gemini answer as the selected brain. `Auto` is the only mode that waterfalls across configured providers.
- The original interface's **AGENT** tab is wired to Core `/api/v1/agent/tasks` with polling, visible steps/results, approve/deny, pause/resume/cancel and Windows emergency-stop/reset. Its Skills window maps owner-friendly groups to the real registry; Windows PC-control skills remain opt-in.
- The original interface's live voice has a WebView2-safe chain: `getUserMedia` + `MediaRecorder` + browser-side pause detection/WAV conversion → `/api/v1/voice/transcribe` (faster-whisper) → existing chat → concise character-gendered TTS → listen again. Browser SpeechRecognition is still preferred only in a normal browser, not inside `/?shell=desktop`.
- **LangChain note:** MYRA does not add LangChain as a runtime dependency merely to name-check it. LangChain/LangGraph-style orchestration does not make a microphone, STT model, LLM or TTS service intrinsically faster, and the extra dependency surface would work against the 8GB-RAM goal. MYRA keeps the equivalent bounded chain natively in `providers.py`/`core_agent.py`/`voice_engine.py`, and addresses latency where it actually occurs: capture segmentation, local STT, provider choice, concise speech text and TTS timeout/fallback.

## Boundaries

- **Core Chat Mode** cannot execute tools. It uses persistent conversations and a small amount of relevant local memory supplied by MYRA.
- **Agent Mode** may request only registered, enabled skills. MYRA validates every argument, executes one skill at a time, records the observation and verifies built-in results where possible.
- Write/launch/open/control skills require confirmation unless the user explicitly approved that skill for the current task or chose the task-wide approval mode.
- Built-in file skills are restricted to `%LOCALAPPDATA%\MYRA\workspace` on Windows. They refuse traversal and absolute paths.
- There is no arbitrary shell skill, unrestricted file deletion, or CAPTCHA/MFA/password bypass. Browser automation is visible and refuses challenge/secret fields; Windows control prefers semantic UI Automation (pywinauto), offers a separately gated coordinate fallback (PyAutoGUI), shows a "MYRA IS CONTROLLING" banner and honours an emergency stop.
- Camera/screen capture is OFF by default, consent-gated, visibly indicated, sampled at a configurable interval, and released immediately on stop.
- Desktop background work in the Qt fallback uses worker threads whose Python wrappers are kept alive in `MyraWindow._workers` until they report (PySide6 does not keep QRunnable wrappers alive by itself). Its hologram now batches points with `drawPoints`, but the GPU shell remains the smooth default.

## Local data

Default Windows data path:

```text
%LOCALAPPDATA%\MYRA\
  myra.db
  workspace\
  models\
  backups\
  voice-models.json
```

`MYRA_DATA_DIR` overrides the location. SQLite stores conversations, messages, user-approved memories, notes, preferences, skill enablement and agent tasks. Secrets are not stored in SQLite.

## Secrets

When the optional `keyring` package has a working backend, provider keys from the integrated settings layer are saved in the OS credential store and any old plaintext copy is blanked from `.env`. Without it, MYRA keeps the private `.env` behavior. Effective secret lookup is environment → credential store → `.env`. API/UI status only receives `set`, a masked tail and the storage type; model names and other non-secret settings remain in `.env`.

## API v1 groups

- `GET /api/v1/health`, `/providers`, `/skills`, `/voice/status`
- `GET/POST /api/v1/conversations`, `GET/PUT/DELETE /api/v1/conversations/{id}`
- `POST /api/v1/chat`, `POST /api/v1/chat/stream` (NDJSON events), `POST /api/v1/structured`
- `GET/POST /api/v1/memories`, `PUT/DELETE /api/v1/memories/{id}`
- `GET/POST /api/v1/notes`, `PUT/DELETE /api/v1/notes/{id}`
- `GET/POST /api/v1/reminders`, due polling with `?mark=1`
- `POST /api/v1/skills/{id}/enabled`, `POST /api/v1/skills/{id}/run`
- `GET/POST /api/v1/agent/tasks`, task start/pause/resume/cancel/approve/deny
- `POST /api/v1/vision/analyze` (one explicitly consented frame)
- Live vision sessions (`/api/v1/live-vision/...`), voice turn + speech-model install/remove (`/api/v1/voice/...`)
- `POST /api/v1/research`, world headlines, browser control (`/api/v1/browser/...`), Windows control + emergency stop (`/api/v1/windows/...`)
- `POST /api/v1/data/migrate-legacy`, `GET /api/v1/export`, `POST /api/v1/backup`

If the server is not bound to loopback, state-changing/private API v1 calls require `MYRA_API_TOKEN` through `X-MYRA-Token`.

## Honest capability status

Validated by the automated suite (56 tests) plus prior offscreen GUI smoke tests. Items marked "owner acceptance" are code-complete but need the owner's physical Windows hardware to prove.

| Capability | Status |
|---|---|
| Persistent chat/memory/notes/reminders | Implemented in the unified app-data store; legacy data auto-imported |
| Text chat | Multi-provider; Core Chat uses the shared layer with legacy side effects disabled |
| Streaming replies | Implemented (`/api/v1/chat/stream`); desktop Chat consumes it |
| Structured JSON output | Implemented with schema validation |
| Provider tool calling | Gemini + OpenAI-compatible adapters; live keys owner-tested |
| Agent Mode | Implemented for 40 registered skills, bounded and confirmable; original UI shows live steps/approval/pause/stop |
| One screenshot/image frame | Implemented (Gemini, OpenAI/OpenRouter vision fallback) |
| Continuous live screen/camera | Implemented as consent-based sampled frames (not provider-native video); owner acceptance pending |
| Realtime voice | Default-window MediaRecorder/pause-detection → faster-whisper → selected AI → concise Edge/browser TTS → listen again; Qt pipeline also remains. Owner microphone acceptance pending |
| Web research | Implemented (SSRF-guarded search/fetch/extract with citations) |
| Browser automation | Implemented with optional Playwright (visible, gated); owner acceptance pending |
| Semantic Windows app control | Implemented with optional pywinauto + PyAutoGUI fallback; owner acceptance pending |
| Hologram | Original Three.js/WebGL busts are the default through the GPU shell; Qt point-cloud parity remains in the fallback window |
| Packaged EXE/installer | Builder + spec implemented and self-test wired; actual build runs on Windows |
