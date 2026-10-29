# MYRA Voice Evaluation

Status: evaluation and storage/manager foundation only. Realtime native voice is **not enabled** until it passes on the owner's Windows laptop.

## Current working voice

- The existing web UI uses browser `speechSynthesis` for read-aloud. It needs no model download, but voice quality/language depends on Windows/browser voices.
- MYRA now selects the utterance language from the reply text (`bn-BD`, `hi-IN`, or `en-US`) and prefers an installed voice for that language. This still is not microphone STT or a realtime conversation system.

## Speech-to-text candidates

| Candidate | Why it is attractive | Main concern | Decision |
|---|---|---|---|
| faster-whisper | Active, MIT project; CTranslate2 int8 can be CPU-efficient; multilingual Whisper models | Model download and Bengali/Hindi accuracy must be measured; `small` is much larger than `base` | First candidate for a Windows prototype |
| whisper.cpp | Active, MIT; native binary can avoid a large Python ML stack | Integration/build and model selection still need Windows testing | Keep as fallback candidate |

## Text-to-speech candidates

| Candidate | Assessment |
|---|---|
| Windows/browser voices | Zero download and already useful for read-aloud; quality and Bengali/Hindi availability depend on installed voices |
| Piper | Fast CPU design and small voices, but the original repo is archived and an active fork is GPL-3.0; every voice/model license must be checked before bundling |
| Coqui TTS / F5-TTS / Bark / CosyVoice / OpenVoice and similar research systems | Not selected for the first 8 GB realtime build: packaging size, CPU latency and Bengali/Hindi quality are unproven for MYRA; code license also does not automatically settle model/voice rights |

No TTS model will be bundled or silently downloaded based only on a repository star count or license badge.

## Required Windows acceptance tests

Before MYRA may advertise realtime voice:

1. Microphone permission/device selection works and capture stops immediately.
2. English, Hindi and Bengali sample phrases are transcribed with acceptable accuracy, or unsupported languages are labelled honestly.
3. End-to-end response latency feels conversational on the owner's 8 GB laptop without freezing the UI.
4. MYRA can be interrupted while speaking; mute/end controls work.
5. Speaker echo does not repeatedly trigger the microphone.
6. A downloaded model survives restart/update, has a recorded source/version/SHA-256, and can be removed/reinstalled.
7. Offline STT/TTS messaging makes clear that Gemini/Groq reasoning still needs internet.

`backend/voice.py` implements the model-record/checksum side of this plan. It intentionally reports `realtime_voice_ready: false` today.
