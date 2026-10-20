import numpy as np
from faster_whisper import WhisperModel

from app.config import settings

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


def transcribe_pcm16(audio: bytes, sample_rate: int = 16000) -> str:
    """Recognize a single utterance from raw 16-bit mono PCM audio via a
    self-hosted faster-whisper model. The caller (media stream handler)
    already VAD-segments a complete utterance (capped at 15s) before
    calling this."""
    if not audio:
        return ""
    if sample_rate != 16000:
        raise ValueError(f"faster-whisper expects 16kHz audio, got {sample_rate}")

    samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
    # faster-whisper wants a bare ISO 639-1 code ("en"); stt_language is kept
    # in BCP-47 form ("en-US") since the same setting also used to feed
    # Azure Speech, which wants the locale tag.
    language = settings.stt_language.split("-")[0]
    segments, _ = _get_model().transcribe(
        samples,
        language=language,
        beam_size=1,
        vad_filter=False,  # utterance is already VAD-segmented upstream
    )
    return " ".join(segment.text.strip() for segment in segments).strip()
