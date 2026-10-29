"""MYRA — Ultra-Realistic Neural Human Voice Studio (GitHub Open-Source).

Powered by Microsoft Edge Neural Speech engine (edge-tts).
Produces studio-quality human voice in MP3 with natural breathing,
human pacing, and authentic native Bengali (bn-BD / bn-IN) & English accents.
Zero API keys needed, 100% free and lightweight.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "voice_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:
    import edge_tts
    EDGE_AVAILABLE = True
except ImportError:
    edge_tts = None
    EDGE_AVAILABLE = False


VOICE_PRESETS = {
    # Bengali (Natural Bangladeshi & Indian Bengali Human Voices)
    "bn_female": "bn-BD-NabanitaNeural",
    "bn_male": "bn-BD-PradeepNeural",
    "bn_in_female": "bn-IN-TanishaaNeural",
    "bn_in_male": "bn-IN-BashkarNeural",
    # English (Natural Warm / JARVIS / Companion Human Voices)
    "en_female": "en-US-JennyNeural",
    "en_male": "en-US-GuyNeural",
    "en_core": "en-US-AriaNeural",
    # Hindi
    "hi_female": "hi-IN-SwaraNeural",
    "hi_male": "hi-IN-MadhurNeural",
}


def is_bengali_text(text: str) -> bool:
    """Detect if text contains Bengali Unicode characters."""
    return bool(re.search(r"[\u0980-\u09FF]", text))


def is_hindi_text(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text))


def pick_voice(text: str, character: str = "core", custom_voice: Optional[str] = None) -> str:
    """Select the best ultra-realistic neural voice for the given text and persona."""
    if custom_voice and custom_voice != "auto":
        return custom_voice

    char = (character or "core").lower()
    is_male = char == "male"

    if is_bengali_text(text):
        return VOICE_PRESETS["bn_male"] if is_male else VOICE_PRESETS["bn_female"]

    if is_hindi_text(text):
        return VOICE_PRESETS["hi_male"] if is_male else VOICE_PRESETS["hi_female"]

    # English voices
    if is_male:
        return VOICE_PRESETS["en_male"]
    if char == "female":
        return VOICE_PRESETS["en_female"]
    return VOICE_PRESETS["en_core"]


def _cache_key(text: str, voice: str, rate: str, pitch: str) -> Path:
    token = f"{voice}:{rate}:{pitch}:{text.strip()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.mp3"


async def _async_generate(text: str, voice: str, rate: str, pitch: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))


def synthesize_speech(
    text: str,
    character: str = "core",
    voice: Optional[str] = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Optional[bytes]:
    """Generate high-fidelity human speech MP3 audio.

    Returns MP3 bytes if successful, or None if edge-tts is unavailable or offline.
    """
    clean_text = " ".join(str(text).split()).strip()
    if not clean_text:
        return None

    if not EDGE_AVAILABLE:
        return None

    chosen_voice = pick_voice(clean_text, character=character, custom_voice=voice)
    cache_file = _cache_key(clean_text, chosen_voice, rate, pitch)

    # Return cached audio if present
    if cache_file.exists() and cache_file.stat().st_size > 500:
        try:
            return cache_file.read_bytes()
        except OSError:
            pass

    tmp_file = cache_file.with_suffix(".tmp")
    try:
        # Run async generation synchronously
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_async_generate(clean_text, chosen_voice, rate, pitch, tmp_file))
        finally:
            loop.close()

        if tmp_file.exists() and tmp_file.stat().st_size > 500:
            tmp_file.replace(cache_file)
            return cache_file.read_bytes()
    except Exception as exc:
        # If offline or temporary network glitch
        try:
            tmp_file.unlink(missing_ok=True)
        except OSError:
            pass
        return None

    return None


def get_voice_status() -> dict:
    return {
        "ok": True,
        "engine": "Edge Neural Human Voice Studio" if EDGE_AVAILABLE else "Browser Speech Engine",
        "neural": EDGE_AVAILABLE,
        "default_bengali_voice": VOICE_PRESETS["bn_female"],
        "default_english_voice": VOICE_PRESETS["en_female"],
        "supported_voices": list(VOICE_PRESETS.values()),
    }
