"""Boot gate for run_demo.bat: one STT, one TTS, one LLM call; prints tok/s + VRAM; exit 1 on failure.

    uv run python tools/selftest.py
"""

from __future__ import annotations

import sys
import time

import _env  # noqa: F401

import numpy as np
import soundfile as sf

sys.path.insert(0, str(_env.SERVER_DIR))


def main() -> int:
    ok = True
    t_all = time.perf_counter()
    # LLM
    from brain.llm import LLM

    llm = LLM()
    up, msg = llm.health()
    print(f"[selftest] LLM: {msg}")
    tok_s = None
    if up:
        try:
            text, st = llm.quick("Reply with the single word READY.", max_tokens=8)
            text, st = llm.quick("Count from one to twenty in words, comma separated.", max_tokens=60)
            tok_s = st.tok_s
            print(f"[selftest] LLM quick call: {st.completion_tokens} tok in {st.elapsed_s:.2f}s -> {tok_s and round(tok_s, 1)} tok/s")
        except Exception as exc:  # noqa: BLE001
            print(f"[selftest] LLM call FAILED: {exc!r}"); ok = False
    else:
        ok = False
    # STT
    try:
        from audio.stt import STT

        stt = STT()
        wav = _env.FIXTURES_DIR / "sample_answer_vague_16k.wav"
        a, sr = sf.read(wav, dtype="float32")
        tr = stt.transcribe(a[: sr * 10], sr)
        print(f"[selftest] STT ({stt.provider}): {len(tr.words)} words in {tr.latency_ms:.0f} ms: {tr.text[:70]!r}")
        if not tr.words:
            ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"[selftest] STT FAILED: {exc!r}"); ok = False
    # TTS
    try:
        from audio.tts import TTS

        tts = TTS()
        t0 = time.perf_counter()
        audio, vis = tts.synth("Hello, and welcome. Let us begin.")
        print(f"[selftest] TTS ({tts.device}): {len(audio) / 24000:.2f}s audio, {len(vis)} visemes in {(time.perf_counter() - t0) * 1000:.0f} ms")
        if not vis or len(audio) < 24000:
            ok = False
    except Exception as exc:  # noqa: BLE001
        print(f"[selftest] TTS FAILED: {exc!r}"); ok = False
    mem = _env.gpu_mem_mib()
    vram = f"{mem[0] / 1024:.1f} GB / {mem[1] / 1024:.1f} GB" if mem else "unknown"
    status = "READY" if ok else "FAILED"
    print(f"[selftest] LLM {tok_s and round(tok_s) or '?'} tok/s · VRAM {vram} · {time.perf_counter() - t_all:.1f}s · {status}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
