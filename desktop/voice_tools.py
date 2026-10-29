"""Small pure-Python PCM helpers for the Qt realtime-voice page."""
from __future__ import annotations

import array
import io
import math
import wave


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
    def __init__(self, sample_rate=16000, threshold=650, min_speech_ms=250, silence_ms=750, max_utterance_ms=30000):
        self.sample_rate = int(sample_rate)
        self.threshold = float(threshold)
        self.min_speech_bytes = int(self.sample_rate * 2 * min_speech_ms / 1000)
        self.silence_bytes = int(self.sample_rate * 2 * silence_ms / 1000)
        self.max_bytes = int(self.sample_rate * 2 * max_utterance_ms / 1000)
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
        speech = pcm16_rms(frame) >= self.threshold
        if speech:
            self._active = True
            self._speech_bytes += len(frame)
            self._trailing_silence = 0
        if not self._active:
            return None
        self._buffer.extend(frame)
        if not speech:
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
