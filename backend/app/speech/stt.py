import io
import wave

import httpx

from app.config import settings

_DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def transcribe_pcm16(audio: bytes, sample_rate: int = 16000) -> str:
    """Recognize a single utterance from raw 16-bit mono PCM audio via
    Deepgram's pre-recorded transcription API. The caller (media stream
    handler) already VAD-segments a complete utterance before calling this,
    so batch transcription is the right fit -- not Deepgram's separate
    real-time streaming API, which is for continuous unsegmented audio."""
    if not audio:
        return ""

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)

    response = httpx.post(
        _DEEPGRAM_URL,
        params={
            "model": "nova-2",
            "language": settings.stt_language,
            "punctuate": "true",
            "smart_format": "true",
        },
        headers={
            "Authorization": f"Token {settings.deepgram_api_key}",
            "Content-Type": "audio/wav",
        },
        content=wav_buffer.getvalue(),
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
    return transcript.strip()
