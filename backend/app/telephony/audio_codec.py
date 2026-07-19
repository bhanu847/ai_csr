import numpy as np

# Python's stdlib `audioop` (which used to do this) was removed in 3.13,
# so mu-law decoding is done by hand here using the standard G.711 formula.
_MULAW_BIAS = 0x84


def mulaw_to_pcm16(mulaw: bytes) -> np.ndarray:
    """Decode G.711 mu-law bytes to 16-bit signed PCM samples."""
    u = np.frombuffer(mulaw, dtype=np.uint8)
    u = (~u).astype(np.int32)
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    magnitude = ((mantissa << 3) + _MULAW_BIAS) << exponent
    magnitude -= _MULAW_BIAS
    sample = np.where(sign != 0, -magnitude, magnitude)
    return np.clip(sample, -32768, 32767).astype(np.int16)


def upsample_8k_to_16k(pcm16_8k: np.ndarray) -> np.ndarray:
    """Linear-interpolate 8kHz PCM samples to 16kHz."""
    if len(pcm16_8k) == 0:
        return pcm16_8k
    x_old = np.arange(len(pcm16_8k))
    x_new = np.linspace(0, len(pcm16_8k) - 1, len(pcm16_8k) * 2)
    return np.interp(x_new, x_old, pcm16_8k.astype(np.float32)).astype(np.int16)


def mulaw8k_to_pcm16_16k_bytes(mulaw: bytes) -> bytes:
    pcm_8k = mulaw_to_pcm16(mulaw)
    pcm_16k = upsample_8k_to_16k(pcm_8k)
    return pcm_16k.tobytes()
