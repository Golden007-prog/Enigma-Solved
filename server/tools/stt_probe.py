"""Parakeet-TDT-0.6B-v2 probe via onnx-asr: transcript + word timestamps + latency.

Usage:  uv run python tools/stt_probe.py [--wav fixtures/sample_answer_1_16k.wav]
                                          [--providers cuda|cpu] [--quant int8]
Runs CUDA fp32 (default) and prints words with timestamps; compares against the
script text with rapidfuzz. Exit code 1 if the transcript is empty, timestamps
are missing, or similarity < 80.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import _env  # noqa: F401

import numpy as np
import soundfile as sf

MODEL_NAME = "nemo-parakeet-tdt-0.6b-v2"


def words_from_tokens(tokens: list[str], timestamps: list[float]) -> list[dict]:
    """Merge SentencePiece tokens ('▁' marks a word start) into word-level spans.

    onnx-asr gives one timestamp (seconds) per emitted token: the frame at which
    the token was emitted. A word's start = its first token's time; its end = the
    time of the token that follows the word (or the last token's time + 80 ms).
    """
    words: list[dict] = []
    for tok, ts in zip(tokens, timestamps):
        if not tok or tok == "<blk>":
            continue
        if tok.startswith("▁") or not words:
            words.append({"word": tok.lstrip("▁"), "start": float(ts), "end": float(ts)})
        else:
            words[-1]["word"] += tok
            words[-1]["end"] = float(ts)
    for i, w in enumerate(words):
        nxt = words[i + 1]["start"] if i + 1 < len(words) else w["end"] + 0.08
        w["end"] = max(w["end"], min(nxt, w["end"] + 0.6))  # cap a word at +600 ms past its last token
    return [w for w in words if w["word"].strip()]


def run(provider: str, quant: str | None, wav: Path, expected: str | None) -> tuple[bool, dict]:
    import onnx_asr
    import onnxruntime as ort

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if provider == "cuda" else ["CPUExecutionProvider"]
    avail = ort.get_available_providers()
    if provider == "cuda" and "CUDAExecutionProvider" not in avail:
        print(f"[stt] CUDAExecutionProvider not available (have {avail}); skipping cuda run")
        return False, {"skipped": True}
    t0 = time.perf_counter()
    model = onnx_asr.load_model(MODEL_NAME, quantization=quant, providers=providers).with_timestamps()
    load_s = time.perf_counter() - t0
    mem = _env.gpu_mem_mib()
    print(f"[stt] {provider}/{quant or 'fp32'} loaded in {load_s:.2f}s; VRAM {mem[0] if mem else '?'} MiB used")

    audio, sr = sf.read(wav, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    dur = len(audio) / sr
    # warm-up (first CUDA call compiles kernels)
    model.recognize(audio[: sr * 2], sample_rate=sr)
    t0 = time.perf_counter()
    res = model.recognize(audio, sample_rate=sr)
    dt = time.perf_counter() - t0
    text = res.text.strip()
    tokens, stamps = list(res.tokens or []), list(res.timestamps or [])
    words = words_from_tokens(tokens, stamps)
    print(f"[stt] {dur:.1f}s audio -> {len(words)} words in {dt * 1000:.0f}ms (RTFx {dur / max(dt, 1e-6):.0f})")
    print(f"[stt] text: {text[:200]}{'…' if len(text) > 200 else ''}")
    for w in words[:8]:
        print(f"       {w['start']:6.2f}-{w['end']:6.2f}  {w['word']}")
    sim = None
    if expected:
        from rapidfuzz import fuzz

        sim = fuzz.ratio(text.lower(), expected.lower())
        print(f"[stt] similarity to script: {sim:.1f}")
    ok = bool(text) and len(stamps) == len(tokens) and len(words) > 0 and (sim is None or sim >= 80)
    return ok, {"provider": provider, "quant": quant, "latency_ms": dt * 1000, "rtfx": dur / dt, "words": len(words), "sim": sim, "load_s": load_s}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", type=Path, default=_env.FIXTURES_DIR / "sample_answer_1_16k.wav")
    ap.add_argument("--providers", default="cuda,cpu-int8", help="comma list of cuda | cpu | cpu-int8 | cuda-int8")
    args = ap.parse_args()
    if not args.wav.exists():
        print(f"[stt] missing {args.wav} — run tools/tts_probe.py first")
        return 1
    print("[stt] dll preload:", _env.preload_cuda_dlls())
    expected = None
    script = args.wav.with_name(args.wav.stem.replace("_16k", "") + ".txt")
    if script.exists():
        expected = script.read_text(encoding="utf-8").strip()

    all_ok, first_ok = True, None
    for spec in [s.strip() for s in args.providers.split(",") if s.strip()]:
        provider, _, q = spec.partition("-")
        try:
            ok, info = run(provider, q or None, args.wav, expected)
        except Exception as exc:  # keep going so the fallback path is measured too
            print(f"[stt] {spec} failed: {exc!r}")
            ok, info = False, {}
        if first_ok is None and ok:
            first_ok = spec
        all_ok = all_ok and (ok or info.get("skipped", False))
    print(f"[stt] RESULT: {'PASS' if first_ok else 'FAIL'} (first working path: {first_ok})")
    return 0 if first_ok else 1


if __name__ == "__main__":
    sys.exit(main())
