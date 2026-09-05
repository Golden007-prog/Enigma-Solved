"""Phase 6.1: answer-end -> tts_start latency over >= 10 turns (several e2e rounds), p50/p95 written to
docs/PROGRESS.md between the <!-- bench:start --> / <!-- bench:end --> markers and to docs/logs/bench_latency.json.

    uv run python tools/bench_latency.py [--turns 10] [--pressure realistic] [--token ...]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import _env  # noqa: E402
from tools import e2e_client  # noqa: E402

PROGRESS = _env.SERVER_DIR.parent / "docs" / "PROGRESS.md"
LOGS = _env.SERVER_DIR.parent / "docs" / "logs"


def pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = max(0, min(len(sorted_vals) - 1, round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--per-round", type=int, default=5)
    ap.add_argument("--pressure", default="realistic", choices=["warmup", "realistic", "tough"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token")
    ap.add_argument("--jd", default=str(_env.FIXTURES_DIR / "jd_fintech.txt"))
    a = ap.parse_args()

    lat: list[float] = []
    rounds = 0
    t0 = time.time()
    while len(lat) < a.turns and rounds < 6:
        rounds += 1
        args = argparse.Namespace(host=a.host, port=a.port, token=a.token, jd=a.jd, questions=a.per_round, pressure=a.pressure, realtime=False, timeout=300.0, latencies=[])
        rc = asyncio.run(e2e_client.run(args))
        print(f"--- round {rounds}: rc={rc} latencies={[round(x * 1000) for x in args.latencies]}")
        lat.extend(args.latencies)
    s = sorted(lat)
    ms = lambda v: f"{v * 1000:.0f} ms"  # noqa: E731
    result = {
        "date": time.strftime("%Y-%m-%d %H:%M"), "pressure": a.pressure, "turns": len(s), "rounds": rounds,
        "p50_ms": round(statistics.median(s) * 1000), "p95_ms": round(pct(s, 95) * 1000), "min_ms": round(s[0] * 1000), "max_ms": round(s[-1] * 1000),
        "wall_s": round(time.time() - t0),
    }
    print(json.dumps(result))
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "bench_latency.json").write_text(json.dumps({"summary": result, "latencies_ms": [round(x * 1000) for x in lat]}, indent=2), encoding="utf-8")
    block = (f"<!-- bench:start -->\n| bench_latency.py ({result['date']}, {a.pressure}) | turns {result['turns']} in {rounds} rounds | "
             f"**p50 {ms(statistics.median(s))}** | **p95 {ms(pct(s, 95))}** | min {ms(s[0])} | max {ms(s[-1])} |\n<!-- bench:end -->")
    if PROGRESS.exists():
        txt = PROGRESS.read_text(encoding="utf-8")
        if "<!-- bench:start -->" in txt and "<!-- bench:end -->" in txt:
            pre, rest = txt.split("<!-- bench:start -->", 1)
            _, post = rest.split("<!-- bench:end -->", 1)
            txt = pre + block + post
        else:
            txt = txt.rstrip("\n") + "\n\n" + block + "\n"
        PROGRESS.write_text(txt, encoding="utf-8")
        print(f"PROGRESS.md updated: p50 {result['p50_ms']} ms, p95 {result['p95_ms']} ms over {result['turns']} turns")
    return 0 if len(s) >= a.turns else 1


if __name__ == "__main__":
    sys.exit(main())
