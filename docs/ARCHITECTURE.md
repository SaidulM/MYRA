# MYRA Core 2.0 Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Existing Web UI (ui/)          Native Desktop UI (desktop/) │
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

## Main integration note (Oct 2026)

Core 2.0 was merged beside the newer `main` web experience rather than replacing it:

- The main web UI continues to use its legacy routes/modules (`backend/memory.py`, `backend/notes.py`, `backend/agent.py`, `backend/skills_manager.py`, etc.).
- The native desktop and `/api/v1` use the Core modules (`backend/core_memory.py`, `backend/core_agent.py`, `backend/service.py`, `backend/skill_registry.py`).
- The legacy web database (`data/myra.db`) and Core app-data database are currently separate. A lossless migration/unification is a later step; do not assume a note or memory created in one surface automatically appears in the other yet.
- Core Chat calls the shared provider layer with legacy local-intent execution, silent auto-learning and legacy-memory injection disabled. The older web chat retains its existing behavior for compatibility, so its local actions are not the same confirmation boundary as Core Agent Mode.
- The shared legacy chat supports MAIN's wider provider list for text chat. The Core tool planner/vision capability registry only advertises the implemented Gemini/Groq adapters.

## Boundaries

- **Core Chat Mode** cannot execute tools. It uses persistent conversations and a small amount of relevant local memory supplied by MYRA.
- **Agent Mode** may request only registered, enabled skills. MYRA validates every argument, executes one skill at a time, records the observation and verifies built-in results where possible.
- Write/launch/open skills require confirmation unless the user explicitly approved that skill for the current task or chose the task-wide approval mode.
- Built-in file skills are restricted to `%LOCALAPPDATA%\MYRA\workspace` on Windows. They refuse traversal and absolute paths.
- There is no arbitrary shell skill, unrestricted file deletion, CAPTCHA/MFA bypass or blind coordinate desktop control in this foundation.

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
- `POST /api/v1/chat`
- `GET/POST /api/v1/memories`, `PUT/DELETE /api/v1/memories/{id}`
- `GET/POST /api/v1/notes`, `PUT/DELETE /api/v1/notes/{id}`
- `POST /api/v1/skills/{id}/enabled`, `POST /api/v1/skills/{id}/run`
- `GET/POST /api/v1/agent/tasks`, task start/pause/resume/cancel/approve/deny
- `POST /api/v1/vision/analyze` (one explicitly consented frame)
- `GET /api/v1/export`, `POST /api/v1/backup`

If the server is not bound to loopback, state-changing/private API v1 calls require `MYRA_API_TOKEN` through `X-MYRA-Token`.

## Honest capability status

| Capability | Status in Core 2.0 foundation |
|---|---|
| Persistent Core chat/memory/notes | Implemented with the Core SQLite store; legacy web store remains separate for now |
| Text chat | MAIN's multi-provider legacy chat retained; Core Chat uses the shared layer with legacy side effects disabled |
| Provider tool calling | Gemini/Groq adapters implemented; real keys still owner-tested |
| Agent Mode | Implemented for safe registered skills, bounded and confirmable |
| One screenshot/image frame | Gemini service implemented; native desktop can send one explicit frame |
| Continuous live screen | Not implemented yet |
| Camera live understanding | Not implemented yet |
| Streaming token UI | Not implemented; providers report it as false |
| Realtime native voice | Not implemented yet; model manager/state foundation only (see `VOICE_EVALUATION.md`) |
| Browser navigation/research | Not implemented yet; `web.open_url` only opens a URL for the user |
| Semantic Windows app control | Not implemented yet; pywinauto is the later candidate |
| Native three.js bust parity | Not reproduced in Qt yet; existing web UI remains available |
