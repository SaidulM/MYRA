"""Consent-based continuous frame sessions for MYRA.

The desktop captures camera/screen frames locally.  Only sampled frames
explicitly submitted to a live session are analyzed, and duplicate frames
are de-duplicated by hash.  Stopping a session drops the last frame and
rejects further frames.  This is frame-based live understanding, not a
claim of a provider-native continuous video stream.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from datetime import datetime, timezone


class LiveVisionError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveVisionManager:
    def __init__(self, analyzer):
        if not callable(analyzer):
            raise ValueError("analyzer must be callable")
        self._analyzer = analyzer
        self._sessions = {}
        self._lock = threading.RLock()

    def _public(self, session):
        out = {key: value for key, value in session.items() if not key.startswith("_")}
        out["analyses"] = list(session.get("analyses", []))
        out["errors"] = list(session.get("errors", []))
        return out

    def start_session(self, source, consent=False, analysis_interval_seconds=4, prompt="", max_analyses=30):
        if consent is not True:
            raise PermissionError("Live vision requires explicit consent before start.")
        if source not in {"screen", "camera"}:
            raise ValueError("source must be screen or camera")
        interval = max(1.0, min(float(analysis_interval_seconds or 4), 60.0))
        session_id = uuid.uuid4().hex
        session = {
            "id": session_id,
            "source": source,
            "status": "running",
            "consent": True,
            "analysis_interval_seconds": interval,
            "prompt": str(prompt or "Describe important changes and help with what is visible.")[:2000],
            "max_analyses": max(1, min(int(max_analyses or 30), 200)),
            "frame_count": 0,
            "analyzed_count": 0,
            "last_frame_hash": "",
            "last_frame_at": "",
            "last_analysis_at": "",
            "analyses": [],
            "errors": [],
            "created_at": _now(),
            "updated_at": _now(),
            "_last_analysis_monotonic": 0.0,
            "_analyzing": False,
        }
        with self._lock:
            self._sessions[session_id] = session
        return self._public(session)

    def get_session(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("live vision session not found")
            return self._public(session)

    def list_sessions(self):
        with self._lock:
            return [self._public(session) for session in self._sessions.values()]

    def _set_status(self, session_id, status):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("live vision session not found")
            session["status"] = status
            session["updated_at"] = _now()
            if status == "stopped":
                session["last_frame_hash"] = ""
                session["consent"] = False
            return self._public(session)

    def pause_session(self, session_id):
        return self._set_status(session_id, "paused")

    def resume_session(self, session_id):
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("live vision session not found")
            if session["status"] == "stopped":
                raise LiveVisionError("A stopped live-vision session cannot be resumed; start a new consented session.")
        return self._set_status(session_id, "running")

    def stop_session(self, session_id):
        return self._set_status(session_id, "stopped")

    def stop_all(self):
        with self._lock:
            ids = list(self._sessions)
        return [self.stop_session(session_id) for session_id in ids]

    def submit_frame(self, session_id, image_base64, mime_type="image/jpeg", captured_at="", analyze_now=False):
        raw = str(image_base64 or "")
        digest = hashlib.sha256(raw.encode("ascii", errors="ignore")).hexdigest()
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("live vision session not found")
            if session["status"] == "stopped":
                raise LiveVisionError("This live-vision session is stopped; no frame was accepted.")
            session["frame_count"] += 1
            session["last_frame_at"] = captured_at or _now()
            session["updated_at"] = _now()
            duplicate = digest == session.get("last_frame_hash")
            session["last_frame_hash"] = digest
            if session["status"] != "running":
                return {"ok": True, "accepted": True, "analyzed": False, "reason": "paused", "session": self._public(session)}
            if duplicate and not analyze_now:
                return {"ok": True, "accepted": True, "analyzed": False, "reason": "duplicate_frame", "session": self._public(session)}
            now_mono = time.monotonic()
            due = analyze_now or (now_mono - float(session.get("_last_analysis_monotonic") or 0) >= session["analysis_interval_seconds"])
            if not due:
                return {"ok": True, "accepted": True, "analyzed": False, "reason": "analysis_interval", "session": self._public(session)}
            if session["analyzed_count"] >= session["max_analyses"]:
                session["status"] = "paused"
                session["errors"].append("Maximum analysis budget reached; session paused.")
                return {"ok": True, "accepted": True, "analyzed": False, "reason": "analysis_budget_reached", "session": self._public(session)}
            if session.get("_analyzing"):
                return {"ok": True, "accepted": True, "analyzed": False, "reason": "analysis_in_progress", "session": self._public(session)}
            session["_analyzing"] = True
            session["_last_analysis_monotonic"] = now_mono
            payload = {
                "image_base64": raw,
                "mime_type": mime_type,
                "prompt": session["prompt"],
                "consent": True,
                "source": session["source"],
                "frame_mode": "live_sampled_frame",
            }

        result, error = None, ""
        try:
            result = self._analyzer(payload)
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {exc}"[:500]
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError("live vision session not found")
            session["_analyzing"] = False
            session["updated_at"] = _now()
            if error:
                session["errors"].append(error)
                session["errors"] = session["errors"][-20:]
            else:
                item = {
                    "at": _now(),
                    "frame_hash": digest[:16],
                    "provider": (result or {}).get("provider"),
                    "model": (result or {}).get("model"),
                    "text": (result or {}).get("text") or (result or {}).get("reply") or "",
                }
                session["analyses"].append(item)
                session["analyses"] = session["analyses"][-50:]
                session["analyzed_count"] += 1
                session["last_analysis_at"] = item["at"]
            public = self._public(session)
        if error:
            return {"ok": False, "accepted": True, "analyzed": False, "error": error, "session": public}
        return {"ok": True, "accepted": True, "analyzed": True, "analysis": public["analyses"][-1] if public["analyses"] else None, "session": public}
