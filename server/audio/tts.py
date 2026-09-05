"""Text-to-speech: Kokoro-82M, streamed per sentence, with viseme tracks from token timestamps.

Kokoro yields one chunk per text segment; its token ``start_ts/end_ts`` are relative to that
chunk, so they are shifted onto the utterance timeline here. Each chunk becomes PCM16 24 kHz
bytes plus ``{"t_ms","id"}`` viseme events (BLUEPRINT §6.2), ready to interleave on the socket.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import numpy as np

from audio.resample import float_to_pcm16
from audio.visemes import rms_mouth_events, mouth_events_to_visemes, visemes_from_tokens

log = logging.getLogger("audio.tts")

SR = 24000
DEFAULT_VOICE = "af_heart"
VOICES = {"af_heart": "female, warm", "af_bella": "female, bright", "am_michael": "male, calm", "bm_george": "male, British"}
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


@dataclass
class TTSChunk:
    audio: np.ndarray                 # float32 24 kHz
    pcm16: bytes
    visemes: list[dict[str, Any]]     # absolute t_ms on the utterance timeline
    start_s: float
    end_s: float
    text: str
    tokens: list[Any] = field(default_factory=list)


class TTS:
    def __init__(self, voice: str = DEFAULT_VOICE, device: str = "cuda", repo_id: str = "hexgrad/Kokoro-82M", lang_code: str = "a"):
        import torch
        from kokoro import KPipeline

        from tools import _env  # noqa: F401  (HF cache + espeak env)

        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        t0 = time.perf_counter()
        self.pipeline = KPipeline(lang_code=lang_code, repo_id=repo_id, device=device)
        self.voice = voice
        self.device = device
        # warm-up: first synthesis compiles kernels / loads the voice tensor
        for _ in self.pipeline("Ready.", voice=voice):
            pass
        log.info("TTS ready on %s (%s) in %.1fs", device, voice, time.perf_counter() - t0)

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        parts = [p.strip() for p in _SENTENCE.split(text.strip()) if p.strip()]
        return parts or [text.strip()]

    def stream(self, text: str, voice: str | None = None, speed: float = 1.0) -> Iterator[TTSChunk]:
        """Yield chunks sentence by sentence so the first audio leaves in ~100 ms."""
        voice = voice or self.voice
        offset = 0.0
        for sentence in self.split_sentences(text):
            for result in self.pipeline(sentence, voice=voice, speed=speed, split_pattern=r"\n+"):
                if result.audio is None:
                    continue
                audio = result.audio.detach().cpu().numpy().astype(np.float32)
                tokens = list(result.tokens or [])
                for tk in tokens:
                    if getattr(tk, "start_ts", None) is not None:
                        tk.start_ts = tk.start_ts + offset
                    if getattr(tk, "end_ts", None) is not None:
                        tk.end_ts = tk.end_ts + offset
                dur = len(audio) / SR
                if any(getattr(tk, "start_ts", None) is not None for tk in tokens):
                    # tokens already carry the utterance offset; total_ms pins a trailing rest at the chunk end
                    vis = visemes_from_tokens(tokens, offset_ms=0, total_ms=int((offset + dur) * 1000))
                else:  # no timestamps (non-English voice): RMS fallback per §6.3
                    vis = mouth_events_to_visemes(rms_mouth_events(float_to_pcm16(audio), SR))
                    for ev in vis:
                        ev["t_ms"] = int(ev["t_ms"] + offset * 1000)
                # never let the track go backwards across chunks (Kokoro's first token can sit before the
                # previous chunk's trailing rest by a frame) — the client schedules by t_ms
                floor = int(offset * 1000)
                fixed = []
                for ev in vis:
                    t = max(int(ev["t_ms"]), floor)
                    if fixed and t < fixed[-1]["t_ms"]:
                        t = fixed[-1]["t_ms"]
                    fixed.append({"t_ms": t, "id": int(ev["id"])})
                vis = fixed
                yield TTSChunk(audio=audio, pcm16=float_to_pcm16(audio), visemes=vis, start_s=offset, end_s=offset + dur, text=sentence, tokens=tokens)
                offset += dur

    def synth(self, text: str, voice: str | None = None) -> tuple[np.ndarray, list[dict[str, Any]]]:
        chunks = list(self.stream(text, voice))
        audio = np.concatenate([c.audio for c in chunks]) if chunks else np.zeros(0, dtype=np.float32)
        vis = [ev for c in chunks for ev in c.visemes]
        return audio, vis
