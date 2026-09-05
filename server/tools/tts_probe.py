"""Kokoro-82M probe: synthesise the scripted candidate answers, prove token timestamps.

Usage:  uv run python tools/tts_probe.py [--device cuda|cpu] [--voice af_heart]

Writes fixtures/sample_answer_1.wav (24 kHz, vague answer), sample_answer_2.wav
(strong answer, male voice) and 16 kHz copies for the STT/VAD probes.
Asserts result.tokens[i].start_ts is populated and prints time-to-first-audio.
Exit code 1 on any failure.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import _env  # noqa: F401  (must be first: HF cache + espeak env)

import numpy as np
import soundfile as sf

SR_OUT = 24000

FALLBACK_TEXT = {
    "sample_answer_generic": "I am a hard-working engineer who learns fast and always goes the extra mile to deliver quality results.",
    "sample_answer_team": "Our team built the orders endpoint together and we all worked on the bugs before the demo.",
    "sample_answer_vague": (
        "So in my final year project we built a backend for a food delivery app. "
        "We used caching and stuff to make it faster, and I think maybe we also added some indexes. "
        "It was a team project so we all worked on everything together. "
        "In the end it worked fine and the professor liked it."
    ),
    "sample_answer_strong": (
        "In my internship at a payments startup I owned the order status API. "
        "The p ninety-five latency was about nine hundred milliseconds because every request hit Postgres. "
        "I added a Redis cache with a thirty second TTL keyed on order id, and invalidated it on every status webhook. "
        "That brought p ninety-five down to one hundred and twenty milliseconds and cut database load by roughly sixty percent. "
        "I also wrote an idempotency check so duplicate webhooks could not double-update an order."
    ),
}


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    from audio.resample import resample

    return resample(audio, sr, 16000)


def load_script(name: str) -> str:
    p = _env.FIXTURES_DIR / f"{name}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return FALLBACK_TEXT[name]


def synth(pipeline, text: str, voice: str) -> tuple[np.ndarray, list, float, float]:
    """Return (audio, tokens, time_to_first_audio_s, total_s)."""
    t0 = time.perf_counter()
    chunks, tokens, t_first = [], [], None
    offset_s = 0.0  # Kokoro timestamps are relative to each yielded chunk; stitch them onto one timeline
    for result in pipeline(text, voice=voice, speed=1.0, split_pattern=r"\n+"):
        if result.audio is None:
            continue
        if t_first is None:
            t_first = time.perf_counter() - t0
        audio_np = result.audio.detach().cpu().numpy().astype(np.float32)
        chunks.append(audio_np)
        for tk in result.tokens or []:
            if getattr(tk, "start_ts", None) is not None:
                tk.start_ts = tk.start_ts + offset_s
            if getattr(tk, "end_ts", None) is not None:
                tk.end_ts = tk.end_ts + offset_s
            tokens.append(tk)
        offset_s += len(audio_np) / SR_OUT
    total = time.perf_counter() - t0
    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return audio, tokens, (t_first or 0.0), total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--male-voice", default="am_michael")
    ap.add_argument("--repo", default="hexgrad/Kokoro-82M")
    args = ap.parse_args()

    import torch
    from kokoro import KPipeline

    device = args.device if (args.device == "cpu" or torch.cuda.is_available()) else "cpu"
    t0 = time.perf_counter()
    pipeline = KPipeline(lang_code="a", repo_id=args.repo, device=device)
    print(f"[tts] KPipeline ready on {device} in {time.perf_counter() - t0:.2f}s")
    mem = _env.gpu_mem_mib()
    if mem:
        print(f"[tts] VRAM after load: {mem[0]} / {mem[1]} MiB")

    _env.FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    # Output names follow fixtures/expected/expected_analysis_hints.json (sample_answer_<key>.wav);
    # sample_answer_1/2 are the master prompt's names for the same vague/strong clips.
    jobs = [
        ("sample_answer_vague", args.voice, "sample_answer_vague"),
        ("sample_answer_strong", args.male_voice, "sample_answer_strong"),
        ("sample_answer_generic", args.voice, "sample_answer_generic"),
        ("sample_answer_team", args.male_voice, "sample_answer_team"),
    ]
    aliases = {"sample_answer_vague": "sample_answer_1", "sample_answer_strong": "sample_answer_2"}
    synth(pipeline, "Warm up.", args.voice)  # first CUDA call compiles kernels; keep it out of the numbers
    for script_name, voice, out_name in jobs:
        text = load_script(script_name)
        audio, tokens, t_first, total = synth(pipeline, text, voice)
        dur = len(audio) / SR_OUT
        ts_ok = [t for t in tokens if getattr(t, "start_ts", None) is not None and getattr(t, "end_ts", None) is not None]
        print(
            f"[tts] {out_name}: voice={voice} audio={dur:.1f}s tokens={len(tokens)} with_ts={len(ts_ok)} "
            f"first_audio={t_first * 1000:.0f}ms total={total:.2f}s RTF={total / max(dur, 1e-6):.3f}"
        )
        if tokens[:5]:
            for t in ts_ok[:5]:
                print(f"       {t.text!r:14} {t.phonemes!r:14} {t.start_ts:.2f}-{t.end_ts:.2f}s")
        if not ts_ok or len(ts_ok) < 0.8 * len([t for t in tokens if t.text.strip()]):
            print(f"[tts] FAIL: token timestamps missing for {out_name}")
            ok = False
        if dur < 5:
            print(f"[tts] FAIL: audio too short for {out_name}")
            ok = False
        sf.write(_env.FIXTURES_DIR / f"{out_name}.wav", audio, SR_OUT, subtype="PCM_16")
        sf.write(_env.FIXTURES_DIR / f"{out_name}_16k.wav", resample_to_16k(audio, SR_OUT), 16000, subtype="PCM_16")
        if out_name in aliases:
            sf.write(_env.FIXTURES_DIR / f"{aliases[out_name]}.wav", audio, SR_OUT, subtype="PCM_16")
            sf.write(_env.FIXTURES_DIR / f"{aliases[out_name]}_16k.wav", resample_to_16k(audio, SR_OUT), 16000, subtype="PCM_16")

    print("[tts] RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
