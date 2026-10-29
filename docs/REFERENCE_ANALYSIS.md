# MYRA Reference Analysis

Checked: 29 October 2026.

> Integration update: `main` advanced in parallel with a larger web feature set while Core 2.0 was being built. The merge preserves MAIN's web modules/UI and adds Core 2.0 beside them as `core_memory.py`, `core_agent.py`, `service.py`, `providers.py`, `skill_registry.py` and `/api/v1`. References below to “before Core 2.0” describe the base inspected before that integration; `docs/ARCHITECTURE.md` describes the merged boundaries.

## Owner-supplied GitHub Gists

| Reference | Actual supplied content | What is proven | What is not proven |
|---|---|---|---|
| [`f17a0159…`](https://gist.github.com/KaushikShresth07/f17a01594763df25a5f3115a929f8b06) | `config.py`, 234 lines | Central `.env` loading; multiple Groq key names; optional Tavily; local MiniLM settings; chunking limits; bounded history/message sizes; database paths | No tool calling, agent loop, voice, camera, screen or desktop-control code |
| [`fe0c7af6…`](https://gist.github.com/KaushikShresth07/fe0c7af6b700c183c257f65a62aa84de) | `Lecture01Readme.md`, 552 lines | Describes a FastAPI + LangChain + Groq + Tavily + FAISS service, JSON sessions and routes such as `/chat`, `/chat/realtime`, `/chat/history/{session_id}` | The referenced `app/main.py` and service files are absent, so implementation details cannot be verified |
| [`20a420ec…`](https://gist.github.com/KaushikShresth07/20a420ecfd0a262678b71054cb54b8a8) | `test.py`, 283 lines | A `requests` CLI client shares one session across general/realtime text modes and handles timeout/connection errors | No agent/tool/voice/multimodal implementation |

### Security and license notes

- The reference README explicitly allows all CORS origins and states that there is no authentication. MYRA does **not** copy that posture.
- The README says MIT for the broader project, but the supplied Gists do not contain a separate license file or license headers. MYRA therefore uses behavioral patterns only and does not copy code or prompt text.
- The supplied config loads keys from `.env`; MYRA now prefers an OS credential store when `keyring` is installed and keeps `.env` only as a no-dependency fallback.
- The described `all-MiniLM-L6-v2` + FAISS design adds a local embedding model and heavier dependencies. It is not adopted for MYRA's 8 GB/no-local-LLM target. MYRA currently uses bounded SQLite lexical retrieval.

## Feature comparison

| Area | Current MYRA before Core 2.0 | Reference JARVIS | MYRA direction |
|---|---|---|---|
| Runtime | Python stdlib server + browser UI | FastAPI/LangChain backend + CLI/browser | Keep lightweight service core; add native PySide6 UI |
| Providers | Gemini, then Groq | Groq only | Provider adapters + capability registry |
| Conversation | Browser-session context | JSON files by session | Local SQLite conversations |
| Memory | localStorage demo | Text files + FAISS | User-approved SQLite memories + lexical retrieval |
| Tools | Demo toggles only | Described search use, code absent | Typed skill registry, validation, confirmations |
| Agent | Timed demo text | Not proven | Bounded one-step planner loop with pause/cancel |
| Voice | Browser `speechSynthesis` only | Not supplied | Explicit voice-model manager; Windows audio test required |
| Camera/screen | Visual labels only | Not supplied | Explicit one-frame vision now; live mode later |
| Security | Keys in local `.env`, masked status | All-origin CORS, no auth stated | Loopback/token gates, credential-store path, tool confirmation |

## External candidates reviewed

Repository metadata was checked through the GitHub API as a maintenance/license signal only. Metadata does not prove correctness, language quality or Windows packaging fit.

| Candidate | Signal | MYRA decision |
|---|---|---|
| OpenAI Agents SDK | MIT, actively updated | Do not adopt yet; MYRA needs provider-independent Gemini/Groq adapters and a small auditable agent boundary |
| AutoGen | Active; metadata license is not sufficient for embedding decisions | Too heavy/multi-agent for the first safe laptop build |
| LangGraph | MIT, active | Possible later orchestration; currently unnecessary dependency weight |
| Browser Use | MIT, active | Re-evaluate in the browser-agent stage against direct Playwright; never combine blindly with desktop control |
| Playwright Python | Apache-2.0 | Preferred first browser-automation layer when Stage 8 browser work begins |
| pywinauto | BSD-3-Clause | Preferred candidate for semantic Windows UI Automation later |
| PyAutoGUI | BSD-3-Clause | Last-resort coordinate control only, behind visible control/confirmation |
| faster-whisper | MIT, active | First offline STT candidate; model chosen only after size/language tests |
| whisper.cpp | MIT, active | Alternative STT binary candidate |
| Piper | Original repository archived; active fork reports GPL-3.0 | Do not bundle blindly; model/voice and fork licenses require review |
| PySide6 | Official Qt for Python product | Chosen for the native Windows shell; packaging must include applicable Qt license notices |
| keyring | Standard OS-backends abstraction | Optional dependency; `.env` fallback remains |

## Integration map

Patterns adopted from the references:

1. One service core shared by Chat and Agent.
2. Shared local conversation identity rather than losing context when the page closes.
3. Bounded message/history/context sizes.
4. A distinct realtime/search concept—but MYRA keeps live web access out of ordinary Chat until a real browser/search skill is separately permissioned.
5. Clear timeout and provider-failure messages.

Patterns deliberately not adopted:

- Multiple-key rotation as a quota workaround.
- Loading an entire learning folder into every prompt.
- All-origin CORS or unauthenticated action endpoints.
- Unverified claims about tools, voice, screen, camera or computer control.
- Heavy local embedding/LLM runtime for the owner's 8 GB target.
