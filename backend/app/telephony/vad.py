import numpy as np

from app.config import settings

# Twilio media events cover ~20ms each. These thresholds are a starting
# point for typical PSTN call audio and may need tuning against real calls.
SPEECH_RMS_THRESHOLD = 500
SILENCE_RMS_THRESHOLD = 350
FRAME_MS = 20
SILENCE_DURATION_MS = 700
MIN_UTTERANCE_MS = 300
MAX_UTTERANCE_MS = 15000


def _rms(pcm16_bytes: bytes) -> float:
    samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))


class UtteranceBuffer:
    """Segments a continuous stream of 16kHz PCM16 frames into utterances
    using energy-based silence detection (no push-to-talk on phone calls)."""

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._speaking = False
        self._silence_ms = 0
        self._speech_ms = 0

    def add_frame(self, pcm16_frame: bytes) -> bytes | None:
        rms = _rms(pcm16_frame)

        if not self._speaking:
            if rms >= SPEECH_RMS_THRESHOLD:
                self._speaking = True
                self._frames = [pcm16_frame]
                self._speech_ms = FRAME_MS
                self._silence_ms = 0
            return None

        self._frames.append(pcm16_frame)
        self._speech_ms += FRAME_MS

        if rms < SILENCE_RMS_THRESHOLD:
            self._silence_ms += FRAME_MS
        else:
            self._silence_ms = 0

        if self._silence_ms >= SILENCE_DURATION_MS or self._speech_ms >= MAX_UTTERANCE_MS:
            return self._finalize()

        return None

    def _finalize(self) -> bytes | None:
        utterance = b"".join(self._frames)
        self._frames = []
        self._speaking = False
        self._silence_ms = 0
        speech_ms = self._speech_ms
        self._speech_ms = 0
        if speech_ms < MIN_UTTERANCE_MS:
            return None
        return utterance


class BargeInDetector:
    """Watches caller audio while the AI's reply is playing out over the
    Twilio stream. Requires settings.barge_in_ms of *consecutive* frames
    above settings.barge_in_rms_threshold (no gaps) before signaling an
    interruption, so a click, a cough, or the AI's own voice leaking back
    as speakerphone echo doesn't cut it off mid-sentence."""

    def __init__(self) -> None:
        self._frames: list[bytes] = []
        self._speech_ms = 0

    def add_frame(self, pcm16_frame: bytes) -> list[bytes] | None:
        """Returns the buffered speech frames once sustained speech is
        confirmed (the caller has barged in), else None."""
        if _rms(pcm16_frame) >= settings.barge_in_rms_threshold:
            self._frames.append(pcm16_frame)
            self._speech_ms += FRAME_MS
            if self._speech_ms >= settings.barge_in_ms:
                frames = self._frames
                self.reset()
                return frames
        else:
            self.reset()
        return None

    def reset(self) -> None:
        self._frames = []
        self._speech_ms = 0
