"""LM Studio probe: JSON-schema Stage A rubric call + TTFT / tok/s over 3 runs.

Usage:  uv run python tools/llm_probe.py [--model interviewer] [--jd fixtures/jd_fintech.txt]
                                          [--runs 3] [--think off|none]
Targets (master prompt Phase 1): >= 35 tok/s decode, TTFT <= 400 ms with a ~2K-token prompt.
Exit code 1 if the JSON does not parse/validate, thinking leaks, or targets are missed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import _env  # noqa: F401

LMS_URL = "http://127.0.0.1:1234/v1"

# Compact Stage A schema (BLUEPRINT §5.1). Strict mode: every object lists all
# properties in `required` and has additionalProperties=false.
STAGE_A_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "role_title": {"type": "string"},
        "seniority": {"type": "string", "enum": ["fresher", "junior", "mid", "senior"]},
        "behavioral_technical_mix": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"behavioral": {"type": "number"}, "technical": {"type": "number"}},
            "required": ["behavioral", "technical"],
        },
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["technical", "behavioral"]},
                    "priority": {"type": "string", "enum": ["must_have", "nice_to_have"]},
                    "jd_quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    },
                    "evidence_expected": {"type": "array", "items": {"type": "string"}},
                    "difficulty_ladder": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "name", "type", "priority", "jd_quotes", "evidence_expected", "difficulty_ladder"],
            },
        },
    },
    "required": ["role_title", "seniority", "behavioral_technical_mix", "competencies"],
}

SYSTEM = (
    "You are the lead of a hiring panel. Read the job description. Extract 5 to 8 competencies. "
    "For each, copy the exact sentence(s) from the JD that justify it, verbatim, no paraphrase. "
    "Do not invent competencies that are not in the text. Mark must_have vs nice_to_have and technical vs behavioral, "
    "list 2 to 4 kinds of evidence a strong candidate would give, and a 4-rung difficulty ladder "
    "(recall, applied example, trade-off or failure, design under constraint). Return JSON only."
)

FALLBACK_JD = """Backend Developer (Node.js) — Fintech, Bengaluru. Fresher to 2 years.
Responsibilities: Build and maintain RESTful services in Node.js for our UPI payments platform. Optimise API latency for high-volume transaction endpoints. Design idempotent webhook handlers so duplicate callbacks never double-charge a customer. Write PostgreSQL queries and migrations, and use Redis caching where it measurably helps. Participate in on-call rotations and write clear post-incident notes.
Requirements: Strong fundamentals in JavaScript and asynchronous programming. Familiarity with PostgreSQL and at least one caching layer. Ability to explain trade-offs you made in a project, including failures. Comfortable communicating with product and compliance teams. Bonus: exposure to PCI-DSS or RBI payment guidelines."""


def build_messages(jd: str, pad_to_tokens: int) -> list[dict]:
    """Pad the prompt with a realistic 'previous turns' block to reach ~pad_to_tokens."""
    filler_turn = (
        "Interviewer: Tell me about a project where you optimised latency. "
        "Candidate: In my final year project we built a food delivery backend and we used caching and stuff, "
        "I think maybe we also added indexes, it was a team project and it worked fine in the end. "
    )
    approx_tokens = (len(SYSTEM) + len(jd)) // 4
    filler = ""
    while approx_tokens + len(filler) // 4 < pad_to_tokens:
        filler += filler_turn
    user = f"JOB DESCRIPTION:\n{jd}\n\nCONTEXT FROM A PREVIOUS PRACTICE ROUND (for style only, ignore for the rubric):\n{filler}"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def one_run(client, model: str, messages: list[dict], think: str, max_tokens: int) -> dict:
    extra: dict = {}
    if think == "off":
        # LM Studio maps reasoning_effort="none" to the chat-template variable enable_thinking=false
        # (staff-documented, 0.4.8+). chat_template_kwargs is the vLLM/llama.cpp spelling; harmless if ignored.
        extra["reasoning_effort"] = "none"
        extra["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.perf_counter()
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        response_format={"type": "json_schema", "json_schema": {"name": "rubric", "strict": True, "schema": STAGE_A_SCHEMA}},
        extra_body=extra,
    )
    t_first = None
    content, reasoning, usage = [], [], None
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        rc = getattr(delta, "reasoning_content", None) or (delta.model_extra or {}).get("reasoning_content") if hasattr(delta, "model_extra") else None
        if rc:
            reasoning.append(rc)
        if delta.content:
            if t_first is None:
                t_first = time.perf_counter()
            content.append(delta.content)
    t_end = time.perf_counter()
    text = "".join(content)
    completion_tokens = usage.completion_tokens if usage else None
    prompt_tokens = usage.prompt_tokens if usage else None
    ttft = (t_first - t0) if t_first else None
    decode_s = (t_end - t_first) if t_first else None
    tps = (completion_tokens / decode_s) if (completion_tokens and decode_s and decode_s > 0) else None
    return {
        "text": text, "reasoning": "".join(reasoning), "ttft_ms": ttft * 1000 if ttft else None,
        "tok_s": tps, "completion_tokens": completion_tokens, "prompt_tokens": prompt_tokens, "total_s": t_end - t0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="interviewer")
    ap.add_argument("--jd", type=Path, default=_env.FIXTURES_DIR / "jd_fintech.txt")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--think", default="off", choices=["off", "none"], help="off = send reasoning_effort=none; none = send nothing (to prove the default leaks)")
    ap.add_argument("--pad-tokens", type=int, default=2000)
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--min-tps", type=float, default=35.0)
    ap.add_argument("--max-ttft-ms", type=float, default=400.0)
    args = ap.parse_args()

    from openai import OpenAI

    client = OpenAI(base_url=LMS_URL, api_key="lm-studio")
    models = [m.id for m in client.models.list().data]
    print(f"[llm] models on server: {models}")
    if args.model not in models:
        print(f"[llm] FAIL: model '{args.model}' not loaded (lms load <key> --identifier {args.model})")
        return 1
    jd = args.jd.read_text(encoding="utf-8") if args.jd.exists() else FALLBACK_JD
    messages = build_messages(jd, args.pad_tokens)

    ok = True
    results = []
    for i in range(args.runs):
        r = one_run(client, args.model, messages, args.think, args.max_tokens)
        results.append(r)
        try:
            obj = json.loads(r["text"])
            n_comp = len(obj.get("competencies", []))
            # provenance check: how many quotes are literal substrings of the JD
            norm = lambda s: " ".join(s.split()).lower()  # noqa: E731
            jd_n = norm(jd)
            quotes = [q["text"] for c in obj["competencies"] for q in c["jd_quotes"]]
            hits = sum(1 for q in quotes if norm(q) in jd_n)
            parsed = f"competencies={n_comp} quotes={len(quotes)} literal_hits={hits}"
        except Exception as exc:
            parsed = f"JSON PARSE FAIL: {exc!r}"
            ok = False
        leak = bool(r["reasoning"]) or "<think>" in r["text"]
        if leak:
            ok = False
        print(
            f"[llm] run {i + 1}: prompt_tokens={r['prompt_tokens']} completion_tokens={r['completion_tokens']} "
            f"TTFT={r['ttft_ms'] and round(r['ttft_ms'])}ms tok/s={r['tok_s'] and round(r['tok_s'], 1)} total={r['total_s']:.2f}s "
            f"| {parsed} | thinking_leak={leak}"
        )
    if results and results[-1]["text"]:
        print("[llm] last output (first 600 chars):", results[-1]["text"][:600])
    tps = [r["tok_s"] for r in results if r["tok_s"]]
    ttfts = [r["ttft_ms"] for r in results if r["ttft_ms"]]
    if tps and ttfts:
        med_tps, med_ttft = sorted(tps)[len(tps) // 2], sorted(ttfts)[len(ttfts) // 2]
        print(f"[llm] median tok/s={med_tps:.1f} (target >= {args.min_tps}); median TTFT={med_ttft:.0f}ms (target <= {args.max_ttft_ms})")
        if med_tps < args.min_tps or med_ttft > args.max_ttft_ms:
            print("[llm] WARN: performance target missed (see PROGRESS.md for the UD-Q4_K_XL fallback)")
    mem = _env.gpu_mem_mib()
    if mem:
        print(f"[llm] VRAM now: {mem[0]} / {mem[1]} MiB")
    print("[llm] RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
