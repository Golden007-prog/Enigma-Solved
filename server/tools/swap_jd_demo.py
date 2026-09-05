"""Criterion 1 demo: the same title, two JDs, visibly different first questions with JD quotes.

    uv run python tools/swap_jd_demo.py [--questions 3] [--pressure realistic]
No audio: runs Stage A + the first N Stage B questions per JD (no answers given, so the agenda
walks the must-haves) and prints them side by side with their why-trace quotes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap

import _env  # noqa: F401

sys.path.insert(0, str(_env.SERVER_DIR))
from brain.interview import InterviewBrain  # noqa: E402
from brain.llm import LLM  # noqa: E402


async def first_questions(llm: LLM, jd_path: str, n: int, dial: str) -> dict:
    jd = (_env.FIXTURES_DIR / jd_path).read_text(encoding="utf-8")
    brain = InterviewBrain(llm, jd, dial)
    rubric = await brain.build_rubric()
    out = {"role_title": rubric["role_title"], "competencies": [(c["id"], c["name"], c["priority"]) for c in rubric["competencies"]],
           "rejected": brain.rejected_ids, "reasked": brain.reasked, "questions": []}
    for _ in range(n):
        target = brain.next_target()
        if target is None:
            break
        q = await brain.word_question(target)
        brain.commit_question(q, target)
        out["questions"].append((q["question_id"], q["text"], q["why"]["competency_id"], q["why"]["jd_quote"], q["why"]["strategy"]))
    return out


def col(s: str, w: int) -> list[str]:
    return textwrap.wrap(s, w) or [""]


async def main_async(args: argparse.Namespace) -> int:
    llm = LLM()
    ok, msg = llm.health()
    if not ok:
        print(msg); return 1
    a, b = await asyncio.gather(first_questions(llm, args.a, args.questions, args.pressure), first_questions(llm, args.b, args.questions, args.pressure))
    w = 58
    print(f"{'JD A: ' + args.a:<{w}}   {'JD B: ' + args.b}")
    print(f"{a['role_title'][:w]:<{w}}   {b['role_title'][:w]}")
    print(f"{'competencies: ' + ', '.join(n for _, n, _ in a['competencies'])[:w-14]:<{w}}   competencies: {', '.join(n for _, n, _ in b['competencies'])[:w-14]}")
    print(f"{'(rejected by gate: ' + str(a['rejected']) + ', reasked=' + str(a['reasked']) + ')':<{w}}   (rejected by gate: {b['rejected']}, reasked={b['reasked']})")
    print("-" * (2 * w + 3))
    for i in range(max(len(a["questions"]), len(b["questions"]))):
        qa = a["questions"][i] if i < len(a["questions"]) else ("", "", "", "", "")
        qb = b["questions"][i] if i < len(b["questions"]) else ("", "", "", "", "")
        la = col(f"{qa[0]} [{qa[2]} · {qa[4]}] {qa[1]}", w) + [f"  ↳ JD: “{x}”" for x in col(qa[3], w - 8)]
        lb = col(f"{qb[0]} [{qb[2]} · {qb[4]}] {qb[1]}", w) + [f"  ↳ JD: “{x}”" for x in col(qb[3], w - 8)]
        for j in range(max(len(la), len(lb))):
            print(f"{(la[j] if j < len(la) else ''):<{w}}   {(lb[j] if j < len(lb) else '')}")
        print()
    same = {q[1] for q in a["questions"]} & {q[1] for q in b["questions"]}
    print(f"identical questions across JDs: {len(same)} (want 0)")
    return 0 if not same else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="jd_fintech.txt")
    ap.add_argument("--b", default="jd_edtech.txt")
    ap.add_argument("--questions", type=int, default=3)
    ap.add_argument("--pressure", default="realistic")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
