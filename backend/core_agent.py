"""MYRA bounded Agent Mode engine.

The model proposes one registered skill at a time.  MYRA validates it,
checks enabled state and task-scoped confirmation, executes it, stores the
observation, and only then asks for the next step.  A task has a hard step
budget and can be paused or cancelled between steps.

This first production-safe engine does not provide arbitrary shell access,
unrestricted filesystem access, CAPTCHA/MFA bypass, or blind full-desktop
control.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import providers
from chat import ChatError
from skill_registry import SkillContext, SkillError


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(word in lowered for word in ("password", "secret", "token", "api_key", "apikey")):
                out[key] = "[REDACTED]"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:6000]
    return value


class AgentEngine:
    def __init__(self, memory_store, registry, planner=None):
        self.memory = memory_store
        self.registry = registry
        self.planner = planner or self._default_planner
        self._threads = {}
        self._stop_events = {}
        self._run_events = {}
        self._lock = threading.Lock()
        self.memory.mark_interrupted_tasks()

    # --------------------------------------------------------------
    # Task control
    # --------------------------------------------------------------
    def create_task(self, goal, max_steps=6, approval_mode="ask", approved_skill_ids=None, provider="auto"):
        return self.memory.create_task(
            goal,
            max_steps=max_steps,
            approval_mode=approval_mode,
            approved_skill_ids=approved_skill_ids,
            provider=provider,
        )

    def get_task(self, task_id):
        task = self.memory.get_task(task_id)
        if not task:
            raise KeyError("agent task not found")
        return task

    def list_tasks(self, limit=50):
        return self.memory.list_tasks(limit=limit)

    def _events_for(self, task_id):
        with self._lock:
            if task_id not in self._stop_events:
                self._stop_events[task_id] = threading.Event()
            if task_id not in self._run_events:
                event = threading.Event()
                event.set()
                self._run_events[task_id] = event
            return self._stop_events[task_id], self._run_events[task_id]

    def start_task(self, task_id, background=True):
        task = self.get_task(task_id)
        if task["status"] in {"completed", "cancelled", "failed"}:
            return task
        stop_event, run_event = self._events_for(task_id)
        stop_event.clear()
        run_event.set()
        if not background:
            self._run_loop(task_id)
            return self.get_task(task_id)

        with self._lock:
            existing = self._threads.get(task_id)
            if existing and existing.is_alive():
                return self.memory.update_task(task_id, status="running", error="")
            thread = threading.Thread(
                target=self._run_loop,
                args=(task_id,),
                name=f"myra-agent-{task_id[:8]}",
                daemon=True,
            )
            self._threads[task_id] = thread
        self.memory.update_task(task_id, status="running", error="")
        thread.start()
        return self.get_task(task_id)

    def pause_task(self, task_id):
        task = self.get_task(task_id)
        _, run_event = self._events_for(task_id)
        run_event.clear()
        if task["status"] in {"running", "queued"}:
            return self.memory.update_task(task_id, status="paused")
        return task

    def resume_task(self, task_id):
        task = self.get_task(task_id)
        if task["status"] == "awaiting_confirmation":
            return task
        _, run_event = self._events_for(task_id)
        run_event.set()
        if task["status"] == "paused":
            self.memory.update_task(task_id, status="running", error="")
        return self.start_task(task_id, background=True)

    def cancel_task(self, task_id):
        task = self.get_task(task_id)
        stop_event, run_event = self._events_for(task_id)
        stop_event.set()
        run_event.set()
        if task["status"] not in {"completed", "failed"}:
            return self.memory.update_task(
                task_id, status="cancelled", pending=None, error="Cancelled by the user."
            )
        return task

    def approve_pending(self, task_id):
        task = self.get_task(task_id)
        pending = task.get("pending")
        if not pending:
            return task
        approved = list(task.get("approved_skill_ids") or [])
        skill_id = pending.get("skill_id")
        if skill_id and skill_id not in approved:
            approved.append(skill_id)
        self.memory.update_task(task_id, approved_skill_ids=approved, status="running")
        return self.start_task(task_id, background=True)

    def deny_pending(self, task_id):
        task = self.get_task(task_id)
        pending = task.get("pending")
        if not pending:
            return task
        transcript = list(task.get("transcript") or [])
        call = pending.get("tool_call") or {}
        transcript.append(
            {
                "type": "tool_call",
                "tool_call": call,
            }
        )
        transcript.append(
            {
                "type": "tool_result",
                "tool_call_id": call.get("id", "call"),
                "name": pending.get("skill_id", "tool"),
                "result": {
                    "ok": False,
                    "error": "The user denied confirmation for this action.",
                    "verified": False,
                },
            }
        )
        steps = list(task.get("steps") or [])
        steps.append(
            {
                "index": len(steps) + 1,
                "skill_id": pending.get("skill_id"),
                "arguments": _redact(pending.get("arguments") or {}),
                "status": "denied",
                "result": {"ok": False, "error": "Denied by the user."},
                "started_at": _now(),
                "finished_at": _now(),
            }
        )
        self.memory.update_task(
            task_id, transcript=transcript, steps=steps, pending=None, status="running"
        )
        return self.start_task(task_id, background=True)

    # --------------------------------------------------------------
    # Planner and execution loop
    # --------------------------------------------------------------
    def _default_planner(self, task, definitions):
        model_overrides = self.memory.get_preference("provider_models", {}) or {}
        system_prompt = "\n".join(
            [
                "You are MYRA Agent Mode's bounded planner.",
                "Use at most one registered tool per response.",
                "After each tool result, observe it before deciding the next step.",
                "Never claim an action succeeded unless the tool result says it succeeded.",
                "Do not request tools that are not listed.",
                "Do not ask for passwords, API keys, OTPs, CAPTCHA or MFA bypass.",
                "When the goal is complete, answer with a concise final summary and no tool call.",
                "If information is missing or a tool fails in a way you cannot safely recover from, stop with a clear explanation.",
                "Work like a careful human operator in small steps: observe first (browser snapshot or Windows window observation when relevant), act once, observe the result, then continue.",
                "Do not treat merely opening a browser as task completion when the goal requires searching, reading, filling, clicking, downloading or verifying something inside it.",
                "For local work, prefer the narrowest file/note/reminder/research skill that can verifiably finish the goal; use Windows coordinate control only after semantic observation and only when necessary.",
            ]
        )
        return providers.next_action(
            task.get("transcript") or [],
            system_prompt,
            definitions,
            model_overrides=model_overrides,
            provider=task.get("provider", "auto"),
        )

    def _needs_confirmation(self, task, definition):
        if not definition.requires_confirmation:
            return False
        if task.get("approval_mode") == "allow_all":
            return False
        return definition.id not in set(task.get("approved_skill_ids") or [])

    def _wait_until_runnable(self, task_id):
        stop_event, run_event = self._events_for(task_id)
        while not stop_event.is_set() and not run_event.wait(timeout=0.1):
            continue
        return not stop_event.is_set()

    def _execute_pending_or_call(self, task, call_data):
        skill_id = call_data.get("name", "")
        arguments = call_data.get("arguments") or {}
        started = _now()
        try:
            result = self.registry.execute(
                skill_id,
                arguments,
                context=SkillContext(
                    memory=self.memory,
                    task_id=task["id"],
                    service=getattr(self, "service", None),
                ),
            )
            status = "completed"
        except SkillError as exc:
            result = {
                "ok": False,
                "skill_id": skill_id,
                "error": exc.message,
                "code": exc.code,
                "verified": False,
            }
            status = "error"
        except Exception as exc:  # handler bug guard: report, never fake success
            result = {
                "ok": False,
                "skill_id": skill_id,
                "error": f"Unexpected skill failure: {exc.__class__.__name__}: {exc}",
                "code": "unexpected_skill_failure",
                "verified": False,
            }
            status = "error"

        finished = _now()
        transcript = list(task.get("transcript") or [])
        steps = list(task.get("steps") or [])
        transcript.append({"type": "tool_call", "tool_call": _redact(call_data)})
        transcript.append(
            {
                "type": "tool_result",
                "tool_call_id": call_data.get("id", "call"),
                "name": skill_id,
                "result": result,
            }
        )
        steps.append(
            {
                "index": len(steps) + 1,
                "skill_id": skill_id,
                "arguments": _redact(arguments),
                "status": status,
                "result": result,
                "started_at": started,
                "finished_at": finished,
            }
        )
        return self.memory.update_task(
            task["id"],
            transcript=transcript,
            steps=steps,
            pending=None,
            status="running",
            error="",
        )

    def _run_loop(self, task_id):
        stop_event, _ = self._events_for(task_id)
        try:
            while not stop_event.is_set():
                if not self._wait_until_runnable(task_id):
                    break
                task = self.memory.get_task(task_id)
                if not task or task["status"] in {"cancelled", "completed", "failed"}:
                    return
                if task["status"] == "paused":
                    time.sleep(0.1)
                    continue

                if len(task.get("steps") or []) >= int(task.get("max_steps") or 6):
                    self.memory.update_task(
                        task_id,
                        status="failed",
                        error="Task stopped because it reached its maximum action budget.",
                        final_summary="Stopped safely after reaching the maximum step limit. The task was not marked complete.",
                        pending=None,
                    )
                    return

                pending = task.get("pending")
                if pending:
                    definition = self.registry.get(pending.get("skill_id", ""))
                    if not definition:
                        self.memory.update_task(
                            task_id,
                            status="failed",
                            pending=None,
                            error="Pending skill is no longer registered.",
                        )
                        return
                    if self._needs_confirmation(task, definition):
                        self.memory.update_task(task_id, status="awaiting_confirmation")
                        return
                    self._execute_pending_or_call(task, pending.get("tool_call") or {})
                    continue

                definitions = self.registry.definitions(enabled_only=True)
                if not definitions:
                    self.memory.update_task(
                        task_id,
                        status="failed",
                        error="No skills are enabled for Agent Mode.",
                    )
                    return

                self.memory.update_task(task_id, status="running", error="")
                try:
                    decision = self.planner(self.memory.get_task(task_id), definitions)
                except ChatError as exc:
                    self.memory.update_task(
                        task_id,
                        status="failed",
                        error=exc.message,
                        final_summary="The planner could not continue, so MYRA stopped without claiming the task was complete.",
                    )
                    return
                except Exception as exc:
                    self.memory.update_task(
                        task_id,
                        status="failed",
                        error=f"Planner failure: {exc.__class__.__name__}: {exc}",
                    )
                    return

                if stop_event.is_set():
                    self.memory.update_task(task_id, status="cancelled", pending=None)
                    return

                # If the user pressed Pause while the provider was thinking,
                # hold this already-made decision until Resume instead of
                # executing one more action against the pause request.
                task_after_planner = self.memory.get_task(task_id)
                if task_after_planner and task_after_planner["status"] == "paused":
                    if not self._wait_until_runnable(task_id):
                        self.memory.update_task(task_id, status="cancelled", pending=None)
                        return
                    self.memory.update_task(task_id, status="running", error="")

                if decision.kind == "final":
                    task = self.memory.get_task(task_id)
                    transcript = list(task.get("transcript") or [])
                    transcript.append({"type": "assistant", "text": decision.text})
                    self.memory.update_task(
                        task_id,
                        status="completed",
                        transcript=transcript,
                        final_summary=decision.text,
                        pending=None,
                        error="",
                    )
                    return

                if decision.kind != "tool_call" or not decision.tool_call:
                    self.memory.update_task(
                        task_id,
                        status="failed",
                        error="Planner returned an unsupported decision.",
                    )
                    return

                call_data = {
                    "id": decision.tool_call.id,
                    "name": decision.tool_call.name,
                    "arguments": decision.tool_call.arguments or {},
                }
                definition = self.registry.get(call_data["name"])
                if not definition or not self.registry.is_enabled(definition.id):
                    # Let the planner observe the rejected call once, but
                    # count it as a step so an invalid loop reaches budget.
                    fake_task = self.memory.get_task(task_id)
                    fake_task["id"] = task_id
                    # Use direct step append rather than registry.execute.
                    transcript = list(fake_task.get("transcript") or [])
                    steps = list(fake_task.get("steps") or [])
                    result = {
                        "ok": False,
                        "skill_id": call_data["name"],
                        "error": "Skill is unknown or disabled; MYRA refused to execute it.",
                        "verified": False,
                    }
                    transcript.append({"type": "tool_call", "tool_call": _redact(call_data)})
                    transcript.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": call_data["id"],
                            "name": call_data["name"],
                            "result": result,
                        }
                    )
                    steps.append(
                        {
                            "index": len(steps) + 1,
                            "skill_id": call_data["name"],
                            "arguments": _redact(call_data["arguments"]),
                            "status": "rejected",
                            "result": result,
                            "started_at": _now(),
                            "finished_at": _now(),
                        }
                    )
                    self.memory.update_task(
                        task_id, transcript=transcript, steps=steps, status="running"
                    )
                    continue

                if self._needs_confirmation(task, definition):
                    self.memory.update_task(
                        task_id,
                        status="awaiting_confirmation",
                        pending={
                            "skill_id": definition.id,
                            "tool_call": _redact(call_data),
                            "arguments": _redact(call_data["arguments"]),
                            "permissions": definition.permissions,
                            "risk": definition.risk,
                            "description": definition.description,
                        },
                    )
                    return

                self._execute_pending_or_call(self.memory.get_task(task_id), call_data)

            current = self.memory.get_task(task_id)
            if current and current["status"] not in {"completed", "failed", "cancelled"}:
                self.memory.update_task(task_id, status="cancelled", pending=None)
        finally:
            with self._lock:
                current_thread = self._threads.get(task_id)
                if current_thread is threading.current_thread():
                    self._threads.pop(task_id, None)
