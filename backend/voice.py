"""MYRA Voice Model Manager state.

Speech models are never downloaded silently.  This manager records what is
actually installed, where it lives, its version and SHA-256 checksum, and
can perform an explicit HTTPS download only when a future voice-setup UI
passes a manifest plus confirmation.  It does not claim realtime voice is
ready until both speech engines and the Windows audio pipeline are tested.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import paths


class VoiceModelError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class VoiceModelManager:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else paths.data_dir()
        self.models_dir = self.data_dir / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "voice-models.json"

    def _load_state(self):
        if not self.state_path.exists():
            return {"installed": []}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"installed": []}
            data.setdefault("installed", [])
            return data
        except ValueError:
            return {"installed": []}

    def _save_state(self, state):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def catalog(self):
        return [
            {
                "id": "faster-whisper",
                "kind": "speech-to-text",
                "recommended_models": [
                    {"id": "base", "approx_size_mb": 145, "languages": "multilingual (quality varies)"},
                    {"id": "small", "approx_size_mb": 488, "languages": "multilingual (better accuracy)"},
                ],
                "license_note": "faster-whisper project is MIT; confirm selected model terms during setup.",
                "offline_recognition_after_setup": True,
            },
            {
                "id": "piper",
                "kind": "text-to-speech",
                "recommended_models": [],
                "license_note": "Original Piper is archived; any active fork and every voice need license review before bundling.",
                "offline_speech_after_setup": True,
            },
        ]

    def status(self):
        state = self._load_state()
        installed = []
        for item in state.get("installed", []):
            path = Path(item.get("path", ""))
            installed.append({**item, "exists": path.exists()})
        return {
            "download_policy": "explicit-user-confirmation-only",
            "models_directory": str(self.models_dir),
            "engines": {
                "faster_whisper_python_package": importlib.util.find_spec("faster_whisper") is not None,
                "piper_executable": shutil.which("piper") or "",
                "browser_speech_synthesis": "available only in the existing web UI",
            },
            "catalog": self.catalog(),
            "installed": installed,
            "realtime_voice_ready": False,
            "readiness_note": (
                "Voice model storage/manager is ready, but realtime microphone "
                "capture, interruption and speaker playback must still be "
                "installed and physically tested on Windows."
            ),
        }

    def register_existing_model(self, engine, model_id, path, version=""):
        path = Path(path).expanduser()
        if not path.exists():
            raise VoiceModelError("Model file or folder does not exist.")
        digest = _sha256(path) if path.is_file() else ""
        record = {
            "engine": engine,
            "model_id": model_id,
            "path": str(path),
            "version": version,
            "sha256": digest,
            "registered_at": _now(),
            "source": "existing-local-file",
        }
        state = self._load_state()
        state["installed"] = [
            item
            for item in state.get("installed", [])
            if not (item.get("engine") == engine and item.get("model_id") == model_id)
        ]
        state["installed"].append(record)
        self._save_state(state)
        return record

    def remove_model_record(self, engine, model_id, delete_file=False):
        state = self._load_state()
        removed = None
        remaining = []
        for item in state.get("installed", []):
            if item.get("engine") == engine and item.get("model_id") == model_id:
                removed = item
            else:
                remaining.append(item)
        if not removed:
            raise VoiceModelError("Voice model record was not found.")
        if delete_file:
            path = Path(removed.get("path", ""))
            models_root = self.models_dir.resolve()
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved != models_root and models_root not in resolved.parents:
                raise VoiceModelError("Refusing to delete a file outside MYRA's model directory.")
            if resolved.is_dir():
                shutil.rmtree(resolved)
            elif resolved.exists():
                resolved.unlink()
        state["installed"] = remaining
        self._save_state(state)
        return removed

    def download_model(self, manifest, confirmed=False, opener=None):
        """Download one explicitly confirmed HTTPS model file.

        ``manifest`` must contain engine, model_id, url, filename and
        sha256.  This method is intentionally not called during startup.
        """
        if not confirmed:
            raise VoiceModelError("Voice model download requires explicit user confirmation.")
        if not isinstance(manifest, dict):
            raise VoiceModelError("Invalid voice model manifest.")
        engine = str(manifest.get("engine", "")).strip()
        model_id = str(manifest.get("model_id", "")).strip()
        url = str(manifest.get("url", "")).strip()
        filename = Path(str(manifest.get("filename", ""))).name
        expected_hash = str(manifest.get("sha256", "")).strip().lower()
        if not engine or not model_id or not filename or len(expected_hash) != 64:
            raise VoiceModelError("Manifest must include engine, model_id, filename and sha256.")
        if urlparse(url).scheme != "https":
            raise VoiceModelError("Voice models may only be downloaded over HTTPS.")

        destination_dir = self.models_dir / engine.replace("/", "_") / model_id.replace("/", "_")
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / filename
        temp = destination.with_suffix(destination.suffix + ".part")
        open_url = opener or urllib.request.urlopen
        try:
            with open_url(url, timeout=60) as response, temp.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            actual = _sha256(temp)
            if actual != expected_hash:
                temp.unlink(missing_ok=True)
                raise VoiceModelError("Downloaded voice model failed SHA-256 verification.")
            os.replace(temp, destination)
        except VoiceModelError:
            raise
        except Exception as exc:
            temp.unlink(missing_ok=True)
            raise VoiceModelError(f"Voice model download failed: {exc}") from exc

        record = {
            "engine": engine,
            "model_id": model_id,
            "path": str(destination),
            "version": str(manifest.get("version", "")),
            "sha256": expected_hash,
            "registered_at": _now(),
            "source": url,
            "license": str(manifest.get("license", "")),
        }
        state = self._load_state()
        state["installed"] = [
            item
            for item in state.get("installed", [])
            if not (item.get("engine") == engine and item.get("model_id") == model_id)
        ]
        state["installed"].append(record)
        self._save_state(state)
        return record
