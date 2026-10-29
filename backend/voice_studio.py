"""MYRA — Ultra-Realistic Neural Human Voice Studio.

Powered by Microsoft Edge Neural Speech engine (edge-tts).
Produces studio-quality human voice in MP3 with natural breathing,
smooth human pacing, and authentic native Bengali (bn-BD / bn-IN) & English accents.
Zero API keys needed, 100% free and lightweight.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple

import paths

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = paths.data_dir() / "voice_cache"
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
    # English (Natural Whispering / Warm / JARVIS Human Voices)
    "en_whisper": "en-US-AvaNeural",
    "en_female": "en-US-JennyNeural",
    "en_male": "en-US-GuyNeural",
    "en_core": "en-US-AriaNeural",
    # Hindi
    "hi_female": "hi-IN-SwaraNeural",
    "hi_male": "hi-IN-MadhurNeural",
    # Spanish
    "es_female": "es-ES-ElviraNeural",
    "es_male": "es-ES-AlvaroNeural",
    # Arabic
    "ar_female": "ar-SA-ZariyahNeural",
    "ar_male": "ar-SA-HamedNeural",
    # French
    "fr_female": "fr-FR-DeniseNeural",
    "fr_male": "fr-FR-HenriNeural",
    # German
    "de_female": "de-DE-KatjaNeural",
    "de_male": "de-DE-ConradNeural",
    # Japanese
    "ja_female": "ja-JP-NanamiNeural",
    "ja_male": "ja-JP-KeitaNeural",
}


def clean_text_for_speech(raw: str) -> str:
    """Strip markdown, code blocks, URLs, and awkward characters that cause TTS to stutter or sound robotic."""
    if not raw:
        return ""
    text = str(raw)

    # 1. Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # 2. Remove markdown links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 3. Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)

    # 4. Remove headers, bold, italics, strikethrough, bullet points
    text = re.sub(r"^[#*>\-\s•]+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    text = re.sub(r"~{1,2}([^~]+)~{1,2}", r"\1", text)

    # 5. Remove emojis and symbols that speech synthesizers try to read out
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[🤖✨🧠💬⏰🎵📷⚙️🌐💡👋👂🔴🔊🔇⏻]", "", text)

    # 6. Normalize whitespace and punctuation
    text = re.sub(r"[\r\n]+", "। " if is_bengali_text(text) else ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_bengali_text(text: str) -> bool:
    """Detect if text contains Bengali Unicode characters."""
    return bool(re.search(r"[\u0980-\u09FF]", text))


def is_hindi_text(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text))


def is_arabic_text(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text))


def is_japanese_text(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", text))


def speech_text_for_reply(raw: str, max_chars: int = 700) -> str:
    """Return only the main answer for speech.

    The on-screen reply can contain a fuller report, sources or background
    detail.  Spoken replies should start with the actual answer and stay
    concise instead of reading every trailing section aloud.
    """
    text = clean_text_for_speech(raw)
    if not text:
        return ""

    text = re.sub(r"^(?:MYRA|Assistant|Answer|Reply)\s*:\s*", "", text, flags=re.IGNORECASE)
    # Keep the answer itself; do not read sources/background appendices.
    text = re.split(
        r"\b(?:Sources?|References?|Background|Technical details?|Details?)\s*:\s*",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    sentences = [part.strip() for part in re.split(r"(?<=[.!?।])\s+", text) if part.strip()]
    if not sentences:
        sentences = [text]

    # Drop a pure filler opening when the substantive answer follows it.
    if len(sentences) > 1 and re.fullmatch(
        r"(?:sure|of course|certainly|okay|here(?:'s| is)(?: the answer)?)[.!।]?",
        sentences[0],
        flags=re.IGNORECASE,
    ):
        sentences = sentences[1:]

    spoken = ""
    for sentence in sentences[:4]:
        candidate = f"{spoken} {sentence}".strip() if spoken else sentence
        if len(candidate) > max_chars and spoken:
            break
        spoken = candidate
        if len(spoken) >= max_chars:
            break
    if len(spoken) > max_chars:
        spoken = spoken[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "."
    return spoken.strip()


def character_gender(character: str = "core") -> str:
    """MYRA's fixed voice map: FEMALE/CUSTOM female; MALE and CORE male."""
    return "female" if (character or "core").lower() in {"female", "custom"} else "male"


def _preset_gender(voice: str) -> str:
    for key, value in VOICE_PRESETS.items():
        if value == voice:
            if key.endswith("_male"):
                return "male"
            if key.endswith("_female") or key in {"en_whisper", "en_core"}:
                return "female"
    return ""


def pick_voice(text: str, character: str = "core", custom_voice: Optional[str] = None, style: str = "gentle") -> str:
    """Select a neural voice; the selected MYRA form controls its gender."""
    char = (character or "core").lower()
    gender = character_gender(char)
    # Browser SpeechSynthesis URIs are not Edge voice IDs.  Accept a custom
    # value only when it is a known Edge preset of the character's gender;
    # this prevents an old female browser selection from leaking into MALE
    # or CORE speech after the owner switches form.
    if custom_voice and custom_voice != "auto" and _preset_gender(custom_voice) == gender:
        return custom_voice

    is_male = gender == "male"

    if is_bengali_text(text):
        return VOICE_PRESETS["bn_male"] if is_male else VOICE_PRESETS["bn_female"]

    if is_hindi_text(text):
        return VOICE_PRESETS["hi_male"] if is_male else VOICE_PRESETS["hi_female"]

    if is_arabic_text(text):
        return VOICE_PRESETS["ar_male"] if is_male else VOICE_PRESETS["ar_female"]

    if is_japanese_text(text):
        return VOICE_PRESETS["ja_male"] if is_male else VOICE_PRESETS["ja_female"]

    # English voices: CORE deliberately uses the male voice.
    if is_male:
        return VOICE_PRESETS["en_male"]
    if style == "whisper":
        return VOICE_PRESETS["en_whisper"]
    return VOICE_PRESETS["en_female"]


def _cache_key(text: str, voice: str, rate: str, pitch: str, style: str) -> Path:
    token = f"{voice}:{rate}:{pitch}:{style}:{text.strip()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{digest}.mp3"


def build_ssml(text: str, voice: str, style: str = "gentle", rate: str = "+0%", pitch: str = "+0Hz") -> str:
    parts = voice.split("-")
    xml_lang = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else "en-US"
    safe_text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    if style == "whisper" and ("Ava" in voice or "Aria" in voice):
        return f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='{xml_lang}'>
<voice name='{voice}'>
<mstts:express-as style='whispering'>
<prosody rate='{rate}' pitch='{pitch}' volume='soft'>{safe_text}</prosody>
</mstts:express-as>
</voice>
</speak>"""
    return f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='{xml_lang}'>
<voice name='{voice}'>
<prosody rate='{rate}' pitch='{pitch}' volume='medium'>{safe_text}</prosody>
</voice>
</speak>"""


async def _async_generate(text: str, voice: str, rate: str, pitch: str, style: str, out_path: Path):
    ssml = build_ssml(text, voice, style=style, rate=rate, pitch=pitch)
    try:
        communicate = edge_tts.Communicate(ssml, voice)
        await communicate.save(str(out_path))
    except Exception:
        # Fallback to plain text if SSML rejected
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(out_path))


def synthesize_speech(
    text: str,
    character: str = "core",
    voice: Optional[str] = None,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    style: str = "gentle",
) -> Optional[bytes]:
    """Generate high-fidelity human speech MP3 audio with soft human touch."""
    clean = speech_text_for_reply(text)
    if not clean:
        return None

    if not EDGE_AVAILABLE:
        return None

    char = (character or "core").lower()
    is_bn = is_bengali_text(clean)

    # Soft, human-tuned pitch and natural pacing
    actual_pitch = pitch
    actual_rate = rate
    if pitch == "+0Hz" or not pitch:
        if is_bn:
            actual_pitch = "+1Hz" if character_gender(char) == "female" else "-1Hz"
        else:
            actual_pitch = "+2Hz" if character_gender(char) == "female" else "-2Hz"

    if rate == "+0%" or not rate:
        # Bengali sounds best at a relaxed, gentle natural rate
        actual_rate = "-3%" if is_bn else "+0%"

    chosen_voice = pick_voice(clean, character=char, custom_voice=voice, style=style)
    cache_file = _cache_key(clean, chosen_voice, actual_rate, actual_pitch, style)

    # Return cached audio if present
    if cache_file.exists() and cache_file.stat().st_size > 500:
        try:
            return cache_file.read_bytes()
        except OSError:
            pass

    tmp_file = cache_file.with_suffix(".tmp")
    try:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_async_generate(clean, chosen_voice, actual_rate, actual_pitch, style, tmp_file))
        finally:
            loop.close()

        if tmp_file.exists() and tmp_file.stat().st_size > 500:
            tmp_file.replace(cache_file)
            return cache_file.read_bytes()
    except Exception:
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
        "default_bengali_voice": VOICE_PRESETS["bn_male"],
        "default_english_voice": VOICE_PRESETS["en_male"],
        "voice_map": {
            "core": {"gender": "male", "english": VOICE_PRESETS["en_male"], "bengali": VOICE_PRESETS["bn_male"]},
            "male": {"gender": "male", "english": VOICE_PRESETS["en_male"], "bengali": VOICE_PRESETS["bn_male"]},
            "female": {"gender": "female", "english": VOICE_PRESETS["en_female"], "bengali": VOICE_PRESETS["bn_female"]},
        },
        "supported_voices": list(VOICE_PRESETS.values()),
    }
