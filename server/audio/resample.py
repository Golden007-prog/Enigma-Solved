"""Sample-rate conversion without scipy: polyphase windowed-sinc FIR (numpy only).

Used for (a) the web test client, which sends float32 at the OS rate (44.1/48 kHz),
(b) turning Kokoro's 24 kHz output into 16 kHz STT/VAD fixtures, and (c) any client
that does not send exactly 16 kHz mono PCM16. Quality is far above what a VAD/STT front
end needs (Kaiser window, 0.45·Nyquist cutoff, ~60 dB stop band).
"""

from __future__ import annotations

from functools import lru_cache
from math import gcd

import numpy as np


@lru_cache(maxsize=16)
def _kernel(up: int, down: int, taps_per_phase: int = 24) -> np.ndarray:
    """Low-pass FIR for a polyphase up/down stage; cutoff at the lower Nyquist."""
    cutoff = 0.45 / max(up, down)  # cycles per (upsampled) sample
    n = taps_per_phase * max(up, down)
    if n % 2 == 0:
        n += 1
    t = np.arange(n) - (n - 1) / 2
    h = 2 * cutoff * np.sinc(2 * cutoff * t)
    h *= np.kaiser(n, beta=8.6)
    h /= h.sum()
    return (h * up).astype(np.float32)


def resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Resample a mono float32 signal from ``sr_in`` to ``sr_out`` (returns float32)."""
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr_in == sr_out or x.size == 0:
        return x
    g = gcd(sr_in, sr_out)
    up, down = sr_out // g, sr_in // g
    h = _kernel(up, down)
    # zero-stuff, filter, decimate — plain and fast enough for utterance-sized buffers
    stuffed = np.zeros(x.size * up, dtype=np.float32)
    stuffed[::up] = x
    y = np.convolve(stuffed, h, mode="same")
    return y[::down].astype(np.float32)


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def to_16k_pcm16(pcm: bytes, sr_in: int, fmt: str = "pcm16", channels: int = 1) -> bytes:
    """Normalise any client frame to 16 kHz mono PCM16 bytes."""
    if fmt == "f32le":
        x = np.frombuffer(pcm, dtype="<f4").astype(np.float32)
    else:
        x = pcm16_to_float(pcm)
    if channels > 1:
        x = x.reshape(-1, channels).mean(axis=1)
    if sr_in != 16000:
        x = resample(x, sr_in, 16000)
    return float_to_pcm16(x)
