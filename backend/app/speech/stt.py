import io
import wave

import httpx

from app.config import settings

_AZURE_STT_PATH = "/speech/recognition/conversation/cognitiveservices/v1"


def transcribe_pcm16(audio: bytes, sample_rate: int = 16000) -> str:
    """Recognize a single utterance from raw 16-bit mono PCM audio via
    Azure AI Speech's short-audio REST API. The caller (media stream
    handler) already VAD-segments a complete utterance (capped at 15s)
    before calling this, well within this endpoint's limits."""
    if not audio:
        return ""

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio)

    url = f"https://{settings.azure_speech_region}.stt.speech.microsoft.com{_AZURE_STT_PATH}"
    response = httpx.post(
        url,
        params={"language": settings.stt_language, "format": "simple"},
        headers={
            "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
            "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={sample_rate}",
            "Accept": "application/json",
        },
        content=wav_buffer.getvalue(),
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("RecognitionStatus") != "Success":
        return ""
    return data.get("DisplayText", "").strip()
