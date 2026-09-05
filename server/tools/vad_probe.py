"""Silero VAD probe (ONNX, CPU): speech segments + end-of-turn latency with a 700 ms rule.

Usage:  uv run python tools/vad_probe.py [fixtures/sample_answer_1_16k.wav]
Exit code 1 if no speech is detected or the streaming iterator never fires speech_end.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import _env  # noqa: F401

import numpy as np
import soundfile as sf

SR = 16000
CHUNK = 512  # samples per Silero window at 16 kHz (32 ms)
SILENCE_MS = 700


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _env.FIXTURES_DIR / "sample_answer_1_16k.wav"
    if not path.exists():
        print(f"[vad] missing {path} — run tools/tts_probe.py first")
        return 1
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        print(f"[vad] expected 16 kHz, got {sr}")
        return 1
    # Append 1.5 s of silence so the end-of-turn rule has something to detect.
    audio = np.concatenate([audio, np.zeros(int(1.5 * SR), dtype=np.float32)])

    import torch
    from silero_vad import VADIterator, get_speech_timestamps, load_silero_vad

    t0 = time.perf_counter()
    model = load_silero_vad(onnx=True)
    print(f"[vad] silero (onnx) loaded in {time.perf_counter() - t0:.2f}s")
    wav = torch.from_numpy(audio)

    t0 = time.perf_counter()
    segs = get_speech_timestamps(wav, model, sampling_rate=SR, return_seconds=True, min_silence_duration_ms=SILENCE_MS)
    dt = time.perf_counter() - t0
    dur = len(audio) / SR
    print(f"[vad] offline: {len(segs)} segment(s) in {dt * 1000:.0f}ms for {dur:.1f}s audio (RTF {dt / dur:.4f})")
    for s in segs[:8]:
        print(f"       speech {s['start']:.2f}s -> {s['end']:.2f}s")
    if not segs:
        print("[vad] FAIL: no speech detected")
        return 1
    true_end = segs[-1]["end"]

    # Streaming: feed 32 ms chunks like the server will, measure when speech_end fires.
    vad_iter = VADIterator(model, sampling_rate=SR, threshold=0.5, min_silence_duration_ms=SILENCE_MS, speech_pad_ms=30)
    fired_start = fired_end = None
    per_chunk = []
    for i in range(0, len(audio) - CHUNK + 1, CHUNK):
        chunk = torch.from_numpy(audio[i : i + CHUNK])
        t1 = time.perf_counter()
        ev = vad_iter(chunk, return_seconds=True)
        per_chunk.append(time.perf_counter() - t1)
        now_s = (i + CHUNK) / SR
        if ev and "start" in ev and fired_start is None:
            fired_start = now_s
        if ev and "end" in ev:
            fired_end = now_s
    vad_iter.reset_states()
    cpu_ms = np.mean(per_chunk) * 1000
    print(f"[vad] streaming: per-chunk {cpu_ms:.2f}ms mean, {np.max(per_chunk) * 1000:.2f}ms max (chunk = 32ms audio)")
    if fired_end is None:
        print("[vad] FAIL: streaming iterator never emitted speech_end")
        return 1
    latency = fired_end - true_end
    print(f"[vad] speech_start fired at {fired_start:.2f}s; speech_end fired at {fired_end:.2f}s; true end {true_end:.2f}s")
    print(f"[vad] end-of-turn decision latency = {latency * 1000:.0f}ms audio-time (rule: {SILENCE_MS}ms silence)")
    print("[vad] RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
