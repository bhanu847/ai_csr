import io
import wave
from pathlib import Path

from piper import PiperVoice

from app.config import settings
from app.telephony.audio_codec import pcm16_to_mulaw8k

_voices: dict[str, PiperVoice] = {}


def _get_voice(voice_name: str) -> PiperVoice:
    voice = _voices.get(voice_name)
    if voice is None:
        model_path = Path(settings.piper_voices_dir) / f"{voice_name}.onnx"
        voice = PiperVoice.load(str(model_path))
        _voices[voice_name] = voice
    return voice


def synthesize_mulaw8k(text: str, voice: str) -> bytes:
    """Synthesize text to speech as raw 8kHz mu-law for Twilio Media Streams."""
    piper_voice = _get_voice(voice or settings.piper_default_voice)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        piper_voice.synthesize_wav(text, wav_file)

    buffer.seek(0)
    with wave.open(buffer, "rb") as wav_file:
        pcm16 = wav_file.readframes(wav_file.getnframes())
        sample_rate = wav_file.getframerate()

    return pcm16_to_mulaw8k(pcm16, sample_rate)
