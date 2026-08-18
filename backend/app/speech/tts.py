import xml.sax.saxutils

import httpx

from app.config import settings

# Piper voice names already stored on existing agents (from before this
# provider switch) map to a similar Azure neural voice, so existing agent
# configs keep working without a data migration. An unrecognized value is
# assumed to already be a real Azure voice name and passed straight through.
_PIPER_TO_AZURE_VOICE = {
    "en_US-amy-medium": "en-US-JennyNeural",
    "en_US-ryan-medium": "en-US-GuyNeural",
    "en_GB-alan-medium": "en-GB-RyanNeural",
    "hi_IN-rohan-medium": "hi-IN-SwaraNeural",
}


def _resolve_voice(voice: str | None) -> str:
    if not voice:
        return settings.azure_default_voice
    return _PIPER_TO_AZURE_VOICE.get(voice, voice)


def synthesize_mulaw8k(text: str, voice: str) -> bytes:
    """Synthesize text to speech as raw 8kHz mu-law for Twilio Media
    Streams, via Azure AI Speech's REST API -- requesting mu-law output
    directly, so no local resampling/encoding step is needed."""
    azure_voice = _resolve_voice(voice)
    escaped_text = xml.sax.saxutils.escape(text)
    ssml = (
        "<speak version='1.0' xml:lang='en-US'>"
        f"<voice name='{azure_voice}'>{escaped_text}</voice>"
        "</speak>"
    )

    url = f"https://{settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    response = httpx.post(
        url,
        headers={
            "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "raw-8khz-8bit-mono-mulaw",
        },
        content=ssml.encode("utf-8"),
        timeout=15.0,
    )
    response.raise_for_status()
    return response.content
