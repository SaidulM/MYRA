# MYRA Core 2.0 Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│ Existing Web UI (ui/)          Native Desktop UI (desktop/) │
└──────────────────┬───────────────────────┬───────────────────┘
                   │                       │
                   └──────────┬────────────┘
                              │ local HTTP (loopback by default)
                    ┌─────────▼─────────┐
                    │ backend/server.py │  legacy API + /api/v1
                    └─────────┬─────────┘
                    ┌─────────▼─────────┐
                    │ backend/service.py│  UI-independent service layer
                    └──┬──────┬──────┬──┘
                       │      │      │
              ┌────────▼─┐ ┌──▼──────▼──┐ ┌──────────────┐
              │ chat.py  │ │ agent.py   │ │ memory.py    │
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

## Boundaries

- **Chat Mode** cannot execute tools. It uses persistent conversations and a small amount of relevant local memory supplied by MYRA.
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

When the optional `keyring` package has a working backend, new Gemini/Groq keys are saved in the OS credential store and blanked from `.env`. Without it, MYRA keeps the previous private `.env` behavior. API/UI status only receives `set`, a masked tail and the storage type.

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
| Persistent chat/memory/notes | Implemented with SQLite |
| Gemini/Groq text chat | Existing real APIs retained |
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
