"""Speech-to-text: nvidia/parakeet-tdt-0.6b-v2 through onnx-asr, word timestamps included.

onnx-asr returns one emission timestamp per sub-word token on an 80 ms grid; words are
rebuilt by grouping tokens on the SentencePiece word boundary (a token that starts with a
space begins a word). Answers longer than ~20 s go through onnx-asr's built-in Silero VAD
long-form path so the encoder never sees more than ``max_speech_duration_s`` at once.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger("audio.stt")

MODEL_NAME = "nemo-parakeet-tdt-0.6b-v2"
SR = 16000
WORD_TAIL_S = 0.08   # a word's last token lasts at least one 80 ms frame
WORD_MAX_S = 0.60    # never let a word run more than 600 ms past its last token


@dataclass
class Word:
    word: str
    start: float
    end: float

    def as_dict(self) -> dict[str, Any]:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}


@dataclass
class Transcript:
    text: str
    words: list[Word] = field(default_factory=list)
    duration_s: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""

    def word_dicts(self) -> list[dict[str, Any]]:
        return [w.as_dict() for w in self.words]


def words_from_tokens(tokens: list[str], timestamps: list[float], offset_s: float = 0.0) -> list[Word]:
    words: list[Word] = []
    for tok, ts in zip(tokens, timestamps):
        if not tok or tok == "<blk>":
            continue
        starts_word = tok.startswith(" ") or tok.startswith("▁")
        piece = tok.lstrip(" ▁")
        t = float(ts) + offset_s
        if starts_word or not words:
            words.append(Word(piece, t, t))
        else:
            words[-1].word += piece
            words[-1].end = t
    for i, w in enumerate(words):
        nxt = words[i + 1].start if i + 1 < len(words) else w.end + WORD_TAIL_S
        w.end = max(w.end + WORD_TAIL_S, min(nxt, w.end + WORD_MAX_S))
    return [w for w in words if w.word.strip()]


class STT:
    """Loads once; ``transcribe`` is synchronous (run it in a thread from the event loop)."""

    def __init__(self, prefer_cuda: bool = True, quantization: str | None = None, model_name: str = MODEL_NAME,
                 long_form_s: float = 18.0):
        import onnx_asr
        import onnxruntime as ort

        from tools import _env  # noqa: F401  (HF cache + DLL preload)

        _env.preload_cuda_dlls()
        avail = ort.get_available_providers()
        # fp16 encoder (tools/convert_parakeet_fp16.py) halves the CUDA footprint at equal accuracy
        fp16_dir = _env.MODELS_DIR / "parakeet-tdt-0.6b-v2-fp16"
        attempts: list[tuple[list[str], str | None, str | None]] = []
        if prefer_cuda and "CUDAExecutionProvider" in avail:
            if (fp16_dir / "encoder-model.onnx").exists() and quantization is None:
                attempts.append((["CUDAExecutionProvider", "CPUExecutionProvider"], None, str(fp16_dir)))
            attempts.append((["CUDAExecutionProvider", "CPUExecutionProvider"], quantization, None))
        attempts.append((["CPUExecutionProvider"], "int8", None))
        last_exc: Exception | None = None
        for providers, quant, path in attempts:
            try:
                t0 = time.perf_counter()
                base = onnx_asr.load_model(model_name, path, quantization=quant, providers=providers)
                self._short = base.with_timestamps()
                vad = onnx_asr.load_vad("silero")
                self._long = base.with_vad(vad, max_speech_duration_s=long_form_s, batch_size=4).with_timestamps()
                self.provider = f"{providers[0]}/{'fp16' if path else (quant or 'fp32')}"
                # warm-up compiles CUDA kernels; keep it out of the first real answer
                self._short.recognize(np.zeros(SR, dtype=np.float32), sample_rate=SR)
                log.info("STT ready: %s in %.1fs", self.provider, time.perf_counter() - t0)
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning("STT load failed on %s: %r", providers[0], exc)
        else:
            raise RuntimeError(f"no STT backend loaded: {last_exc!r}")
        self.long_form_s = long_form_s

    def transcribe(self, audio: np.ndarray, sr: int = SR) -> Transcript:
        if sr != SR:
            from audio.resample import resample

            audio = resample(audio, sr, SR)
        audio = np.asarray(audio, dtype=np.float32)
        dur = len(audio) / SR
        t0 = time.perf_counter()
        words: list[Word] = []
        texts: list[str] = []
        if dur <= self.long_form_s:
            res = self._short.recognize(audio, sample_rate=SR)
            texts.append(res.text or "")
            words = words_from_tokens(list(res.tokens or []), list(res.timestamps or []))
        else:
            for seg in self._long.recognize(audio, sample_rate=SR):
                seg_start = float(getattr(seg, "start", 0.0))
                stamps = list(seg.timestamps or [])
                # onnx-asr stamps are relative to the segment it decoded; add the offset unless
                # they already look absolute (first stamp beyond the segment start).
                offset = 0.0 if (stamps and seg_start > 1.0 and stamps[0] >= seg_start - 0.5) else seg_start
                words.extend(words_from_tokens(list(seg.tokens or []), stamps, offset))
                texts.append(seg.text or "")
        text = " ".join(t.strip() for t in texts if t and t.strip())
        return Transcript(text=text, words=words, duration_s=dur, latency_ms=(time.perf_counter() - t0) * 1000, provider=self.provider)
