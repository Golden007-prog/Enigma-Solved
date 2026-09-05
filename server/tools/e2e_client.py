"""Fake candidate: connects, streams fixture answers as 20 ms PCM16 frames, checks the event order.

Usage:  uv run python tools/e2e_client.py --questions 4 --pressure realistic [--host 127.0.0.1 --port 8765]
        [--token <token>] [--jd fixtures/jd_fintech.txt] [--realtime]
Reads the token from GET /pair.json when not given. Prints per-turn latency (last audio frame
sent → tts_start received) and exits non-zero on a protocol ordering violation or timeout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import _env  # noqa: F401

import httpx
import numpy as np
import soundfile as sf

sys.path.insert(0, str(_env.SERVER_DIR))
import protocol as P  # noqa: E402

FRAME = P.FRAME_BYTES
ANSWERS = ["sample_answer_vague_16k.wav", "sample_answer_strong_16k.wav", "sample_answer_generic_16k.wav", "sample_answer_team_16k.wav"]


def pcm16(path: Path) -> bytes:
    a, sr = sf.read(path, dtype="float32")
    assert sr == 16000, path
    return (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()


async def run(args: argparse.Namespace) -> int:
    import websockets

    base = f"http://{args.host}:{args.port}"
    token = args.token
    if not token:
        token = httpx.get(f"{base}/pair.json", timeout=5).json()["token"]
    jd = Path(args.jd).read_text(encoding="utf-8")
    answers = [pcm16(_env.FIXTURES_DIR / n) for n in ANSWERS]
    silence = b"\x00" * FRAME * 60  # 1.2 s

    events: list[dict] = []
    latencies: list[float] = []
    n_questions = 0
    audio_bytes_in_span = 0
    tts_start_wall = 0.0
    last_frame_sent = 0.0
    report_url = None
    pending_question = False

    async with websockets.connect(f"ws://{args.host}:{args.port}/ws", max_size=8 * 1024 * 1024) as ws:
        hello = {"type": "hello", "token": token, "mode": "interview", "in": {"fmt": "pcm16", "sr": 16000, "ch": 1},
                 "out": {"fmt": "pcm16", "sr": 24000}, "jd": jd, "pressure": args.pressure}
        await ws.send(json.dumps(hello))

        async def stream_answer(pcm: bytes) -> None:
            nonlocal last_frame_sent
            for i in range(0, len(pcm), FRAME):
                await ws.send(pcm[i : i + FRAME])
                if args.realtime:
                    await asyncio.sleep(0.02)
            for i in range(0, len(silence), FRAME):
                await ws.send(silence[i : i + FRAME])
                if args.realtime:
                    await asyncio.sleep(0.02)
            last_frame_sent = time.monotonic()

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=args.timeout)
            except asyncio.TimeoutError:
                print("TIMEOUT waiting for server"); return 2
            if isinstance(raw, (bytes, bytearray)):
                audio_bytes_in_span += len(raw)
                continue
            m = json.loads(raw)
            events.append(m)
            t = m["type"]
            if t not in ("viseme",):
                print(f"<- {json.dumps(m)[:160]}")
            if t == "error" and m.get("fatal"):
                return 3
            if t == "question":
                n_questions += 1
                pending_question = True
            elif t == "tts_start":
                tts_start_wall = time.monotonic(); audio_bytes_in_span = 0
                if last_frame_sent:
                    latencies.append(tts_start_wall - last_frame_sent); last_frame_sent = 0.0
                    print(f"   latency answer-end -> tts_start: {latencies[-1] * 1000:.0f} ms")
            elif t == "tts_end":
                # the server's echo gate is measured from its estimate of playback end: wait it out
                dur = audio_bytes_in_span / 2 / 24000
                wait = max(0.0, tts_start_wall + dur - time.monotonic()) + 0.8
                await asyncio.sleep(wait)
                if pending_question and report_url is None:
                    pending_question = False
                    if n_questions <= args.questions:
                        idx = (n_questions - 1) % len(answers)
                        print(f"-> answering Q{n_questions} with {ANSWERS[idx]}")
                        await stream_answer(answers[idx])
                    else:
                        await ws.send(json.dumps({"type": "cancel"}))
            elif t == "report":
                report_url = m["url"]
                break
        args.latencies = latencies  # bench_latency.py reads these
        spans = P.check_tts_ordering(events)
        types = [e["type"] for e in events]
        assert types[0] == "ready", types[:3]
        assert "rubric" in types and "question" in types and "stt" in types and "reaction" in types, types
        print(f"\nOK: {n_questions} question(s), {spans} tts span(s), {len(latencies)} answers; report: {report_url}")
        if latencies:
            s = sorted(latencies)
            print(f"latency ms: median={s[len(s) // 2] * 1000:.0f} min={s[0] * 1000:.0f} max={s[-1] * 1000:.0f}")
        if report_url:
            rep = httpx.get(report_url, timeout=10).json()
            r = rep.get("report") or {}
            print(f"report: band={r.get('overall_band')} fixes={len(r.get('top_fixes', []))} per_question={len(r.get('per_question', []))} stop={r.get('stop_reason')}")
            # every quote must exist in its answer's transcript (fuzzy)
            from rapidfuzz import fuzz
            bad = 0
            tr = {t["idx"]: (t.get("transcript") or "") for t in rep["turns"]}
            for f in r.get("top_fixes", []):
                idx = int(f["answer_id"][1:]) if f.get("answer_id", "A0")[1:].isdigit() else 0
                if f.get("quote") and fuzz.partial_ratio(f["quote"].lower(), tr.get(idx, "").lower()) < 85:
                    bad += 1
                    print(f"   UNGROUNDED FIX QUOTE: {f['quote']!r} not in A{idx}")
            print(f"quote check: {len(r.get('top_fixes', [])) - bad}/{len(r.get('top_fixes', []))} fixes grounded")
            return 0 if bad == 0 else 4
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token")
    ap.add_argument("--jd", default=str(_env.FIXTURES_DIR / "jd_fintech.txt"))
    ap.add_argument("--questions", type=int, default=4)
    ap.add_argument("--pressure", default="realistic", choices=["warmup", "realistic", "tough"])
    ap.add_argument("--realtime", action="store_true", help="pace frames at 20 ms (default: burst)")
    ap.add_argument("--timeout", type=float, default=240.0)
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
