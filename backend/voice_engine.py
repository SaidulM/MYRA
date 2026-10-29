"""MYRA realtime voice pipeline helpers.

Pipeline: microphone PCM -> VAD -> faster-whisper STT -> MYRA chat ->
Edge Neural TTS or Windows SAPI -> desktop speaker playback.

The Qt desktop owns the microphone/speaker objects.  This module remains
UI-independent and testable with injected fakes.
"""
from __future__ import annotations

import array
import base64
import binascii
import io
import math
import os
import threading
import wave
from pathlib import Path

import paths
from voice import VoiceModelManager


class VoiceEngineError(Exception):
    pass


def pcm16_rms(data):
    if not data:
        return 0.0
    samples = array.array("h")
    samples.frombytes(bytes(data[: len(data) - (len(data) % 2)]))
    if not samples:
        return 0.0
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def wav_bytes(pcm, sample_rate=16000, channels=1, sample_width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))
    return buffer.getvalue()


class VoiceActivitySegmenter:
    """Energy VAD that emits one utterance after trailing silence."""

    def __init__(self, sample_rate=16000, threshold=650, min_speech_ms=250, silence_ms=750, max_utterance_ms=30000):
        self.sample_rate = int(sample_rate)
        self.threshold = float(threshold)
        self.min_speech_bytes = int(self.sample_rate * 2 * (min_speech_ms / 1000))
        self.silence_bytes = int(self.sample_rate * 2 * (silence_ms / 1000))
        self.max_bytes = int(self.sample_rate * 2 * (max_utterance_ms / 1000))
        self._buffer = bytearray()
        self._speech_bytes = 0
        self._trailing_silence = 0
        self._active = False

    @property
    def active(self):
        return self._active

    def reset(self):
        self._buffer.clear()
        self._speech_bytes = 0
        self._trailing_silence = 0
        self._active = False

    def feed(self, frame):
        frame = bytes(frame or b"")
        if not frame:
            return None
        is_speech = pcm16_rms(frame) >= self.threshold
        if is_speech:
            self._active = True
            self._speech_bytes += len(frame)
            self._trailing_silence = 0
        if self._active:
            self._buffer.extend(frame)
            if not is_speech:
                self._trailing_silence += len(frame)
            if len(self._buffer) >= self.max_bytes:
                return self.flush()
            if self._speech_bytes >= self.min_speech_bytes and self._trailing_silence >= self.silence_bytes:
                result = bytes(self._buffer[:-self._trailing_silence]) if self._trailing_silence else bytes(self._buffer)
                self.reset()
                return result or None
        return None

    def flush(self):
        if self._speech_bytes < self.min_speech_bytes:
            self.reset()
            return None
        result = bytes(self._buffer)
        self.reset()
        return result or None


class FasterWhisperTranscriber:
    def __init__(self, model_path, device="cpu", compute_type="int8"):
        self.model_path = str(model_path)
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise VoiceEngineError("faster-whisper is not installed. Install requirements-voice.txt.") from exc
                self._model = WhisperModel(self.model_path, device=self.device, compute_type=self.compute_type)
            return self._model

    def transcribe_wav(self, audio_bytes, language=None):
        audio_bytes = bytes(audio_bytes or b"")
        if len(audio_bytes) < 100:
            raise VoiceEngineError("Audio is too short to transcribe.")
        model = self._load()
        temp_dir = paths.data_dir() / "voice-temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"utterance-{threading.get_ident()}.wav"
        try:
            temp_path.write_bytes(audio_bytes)
            kwargs = {"vad_filter": True, "beam_size": 1, "without_timestamps": True}
            if language and str(language).lower() not in {"auto", ""}:
                kwargs["language"] = str(language).split("-")[0].lower()
            segments, info = model.transcribe(str(temp_path), **kwargs)
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
            return {
                "text": text,
                "language": getattr(info, "language", language or "auto"),
                "language_probability": getattr(info, "language_probability", None),
                "duration": getattr(info, "duration", None),
                "engine": "faster-whisper",
                "model": Path(self.model_path).name,
            }
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


class VoiceEngine:
    def __init__(self, model_manager=None, transcriber=None):
        self.models = model_manager or VoiceModelManager(paths.data_dir())
        self._transcriber = transcriber
        self._transcriber_path = None

    def status(self):
        model_status = self.models.status()
        return {
            **model_status,
            "mode": "microphone -> faster-whisper -> MYRA chat -> Edge TTS/SAPI -> speaker",
            "native_provider_realtime_session": False,
            "turn_based_realtime_ready": bool(model_status.get("pipeline_ready")),
            "microphone_owned_by": "PySide6 desktop (QtMultimedia)",
            "speaker_owned_by": "PySide6 desktop (QtMultimedia) or Windows SAPI",
        }

    def installed_model_path(self, requested=""):
        requested = str(requested or "").strip()
        if requested and Path(requested).exists():
            return requested
        records = self.models.find_installed(engine="faster-whisper")
        existing = [record for record in records if record.get("exists")]
        if requested:
            for record in existing:
                if record.get("model_id") == requested:
                    return record["path"]
        if existing:
            # Prefer base/small for an 8 GB laptop over unexpectedly huge models.
            order = {"base": 0, "small": 1, "tiny": 2, "medium": 3}
            existing.sort(key=lambda record: order.get(record.get("model_id"), 9))
            return existing[0]["path"]
        return ""

    def transcriber(self, requested_model=""):
        path = self.installed_model_path(requested_model)
        if self._transcriber is not None and (not path or self._transcriber_path == path):
            return self._transcriber
        if not path:
            raise VoiceEngineError(
                "No faster-whisper model is installed. Open the Voice page and explicitly download the Base model."
            )
        self._transcriber = FasterWhisperTranscriber(path)
        self._transcriber_path = path
        return self._transcriber

    @staticmethod
    def decode_audio_base64(value, max_bytes=25 * 1024 * 1024):
        raw = str(value or "")
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VoiceEngineError("audio_base64 is not valid base64.") from exc
        if not data or len(data) > max_bytes:
            raise VoiceEngineError("Audio payload is empty or too large.")
        return data

    def transcribe_base64(self, audio_base64, language="auto", model=""):
        data = self.decode_audio_base64(audio_base64)
        return self.transcriber(model).transcribe_wav(data, language=language)

    def synthesize(self, text, character="core", voice=None, style="gentle"):
        import voice_studio

        audio = voice_studio.synthesize_speech(str(text or ""), character=character, voice=voice, style=style)
        if not audio:
            raise VoiceEngineError("Edge TTS could not synthesize speech (package/network unavailable).")
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "mime_type": "audio/mpeg",
            "engine": "edge-tts",
            "bytes": len(audio),
        }


class WindowsSapiSpeaker:
    """Windows SAPI speech without any shell/PowerShell process."""

    def __init__(self):
        if os.name != "nt":
            raise VoiceEngineError("Windows SAPI is available only on Windows.")
        try:
            import win32com.client
        except ImportError as exc:
            raise VoiceEngineError("pywin32 is required for Windows SAPI speech.") from exc
        self._voice = win32com.client.Dispatch("SAPI.SpVoice")

    def speak(self, text, rate=0, volume=100):
        self._voice.Rate = max(-10, min(10, int(rate)))
        self._voice.Volume = max(0, min(100, int(volume)))
        # 1 = asynchronous, 2 = purge pending speech.
        self._voice.Speak(str(text), 3)

    def stop(self):
        try:
            self._voice.Speak("", 2)
        except Exception:
            pass


class RealtimeVoiceSession:
    """Small orchestration state machine used by tests and the Qt UI."""

    def __init__(self, transcribe, chat, speak):
        self._transcribe = transcribe
        self._chat = chat
        self._speak = speak
        self.muted = False
        self.stopped = False
        self.speaking = False
        self._stop_speaking = None

    def set_muted(self, muted):
        self.muted = bool(muted)
        return self.muted

    def register_speech_stopper(self, stopper):
        self._stop_speaking = stopper

    def interrupt(self):
        self.speaking = False
        if self._stop_speaking:
            self._stop_speaking()

    def stop(self):
        self.stopped = True
        self.interrupt()

    def process_utterance(self, wav_audio, language="auto"):
        if self.stopped:
            raise VoiceEngineError("Voice session is stopped.")
        if self.muted:
            return {"muted": True, "transcript": "", "reply": ""}
        self.interrupt()
        transcript = self._transcribe(wav_audio, language)
        if isinstance(transcript, dict):
            text = str(transcript.get("text") or "").strip()
        else:
            text = str(transcript or "").strip()
            transcript = {"text": text}
        if not text:
            return {"muted": False, "transcript": transcript, "reply": ""}
        reply = self._chat(text)
        reply_text = str((reply or {}).get("reply") or "") if isinstance(reply, dict) else str(reply or "")
        if reply_text and not self.stopped:
            self.speaking = True
            try:
                self._speak(reply_text)
            finally:
                self.speaking = False
        return {"muted": False, "transcript": transcript, "reply": reply_text, "chat": reply}


_ENGINE = None


def get_voice_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = VoiceEngine()
    return _ENGINE
