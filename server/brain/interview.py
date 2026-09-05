"""The interview brain: Stage A → B → C → D orchestration on top of the gated modules.

Everything the LLM says is checked in code before it is used: rubric quotes by the
substring gate, analysis quotes by the fuzzy/timestamp gate, report bullets by the
validated-pair filter. The Agenda Manager decides *what* to ask; the LLM only words it.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Any

from brain import prompts, schemas
from brain.agenda import AgendaManager
from brain.llm import LLM, LLMStats
from brain.quotegate import GateResult, validate_analysis
from brain.report_gate import filter_report
from brain.rubric import needs_reask, validate_rubric

log = logging.getLogger("brain.interview")

_STOP = set("the and for with that this from your you our are will have has into onto upon over under about across a an of to in on at by or as be is it its".split())


def _keywords(comp: dict[str, Any], limit: int = 8) -> list[str]:
    """Tech-ish terms from a competency's JD quotes + evidence items for the Stage C prompt."""
    seen: list[str] = []
    text = " ".join(q.get("text", "") for q in comp.get("jd_quotes", [])) + " " + " ".join(comp.get("evidence_expected", []))
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9.+#/-]{2,}", text):
        low = tok.lower().strip(".,;:")
        if low in _STOP or len(low) < 4 and not tok.isupper():
            continue
        if tok[0].isupper() or any(ch.isdigit() for ch in tok) or "-" in tok or len(low) >= 6:
            if low not in [s.lower() for s in seen]:
                seen.append(tok.strip(".,;:"))
        if len(seen) >= limit:
            break
    return seen


@dataclass
class Turn:
    idx: int
    question: dict[str, Any]          # schemas.Question dump
    target: dict[str, Any]            # agenda record
    answer_id: str
    transcript: str = ""
    words: list[dict[str, Any]] = field(default_factory=list)
    analysis: dict[str, Any] | None = None
    gate: GateResult | None = None
    prosody: dict[str, Any] | None = None
    clip_path: str | None = None
    duration_s: float = 0.0


class InterviewBrain:
    def __init__(self, llm: LLM, jd_text: str, dial: str = "realistic", session_id: str = "s"):
        if not jd_text or not jd_text.strip():
            raise ValueError("empty JD")
        self.llm = llm
        self.jd_text = jd_text.strip()
        self.dial = dial if dial in prompts.PRESSURE_DIAL else "realistic"
        self.dial_cfg = prompts.PRESSURE_DIAL[self.dial]
        self.session_id = session_id
        self.rubric: dict[str, Any] | None = None
        self.agenda: AgendaManager | None = None
        self.turns: list[Turn] = []
        self.stats: list[LLMStats] = []
        self.rejected_ids: list[str] = []
        self.reasked = False

    # ------------------------------------------------------------------ Stage A
    @staticmethod
    def _normalise_ids(rubric: dict[str, Any]) -> None:
        seen: set[str] = set()
        for i, c in enumerate(rubric.get("competencies", []), 1):
            cid = str(c.get("id") or "").strip()
            if not re.fullmatch(r"C\d+", cid) or cid in seen:
                cid = f"C{i}"
                while cid in seen:
                    i += 1
                    cid = f"C{i}"
            c["id"] = cid
            seen.add(cid)
            c.setdefault("difficulty_ladder", list(prompts.LADDER))
            if not c.get("difficulty_ladder"):
                c["difficulty_ladder"] = list(prompts.LADDER)

    def _reask_fields(self, raw: dict[str, Any], kept: dict[str, Any], rejected: list[str]) -> dict[str, str]:
        by_id = {c["id"]: c for c in raw.get("competencies", [])}
        rej_lines = []
        for rid in rejected:
            c = by_id.get(rid, {})
            for q in c.get("jd_quotes", []):
                rej_lines.append(f'- {rid} {c.get("name", "")}: "{q.get("text", "")}"')
        kept_lines = [f'- {c["id"]} {c["name"]}: "{q["text"]}"' for c in kept.get("competencies", []) for q in c.get("jd_quotes", [])]
        return {"rejected_list": "\n".join(rej_lines) or "(none)", "kept_list": "\n".join(kept_lines) or "(none)"}

    async def build_rubric(self) -> dict[str, Any]:
        raw, st = await self.llm.ajson("stage_a", {"jd_text": self.jd_text}, schemas.Rubric)
        self.stats.append(st)
        self._normalise_ids(raw)
        import copy

        kept, rejected = validate_rubric(self.jd_text, copy.deepcopy(raw))
        self.rejected_ids = list(rejected)
        if needs_reask(rejected) or not kept["competencies"]:
            log.info("Stage A re-ask: %d competencies rejected (%s)", len(rejected), rejected)
            fields = {"jd_text": self.jd_text, **self._reask_fields(raw, kept, rejected)}
            raw2, st2 = await self.llm.ajson("stage_a_reask", fields, schemas.Rubric)
            self.stats.append(st2)
            self._normalise_ids(raw2)
            kept2, rejected2 = validate_rubric(self.jd_text, copy.deepcopy(raw2))
            self.reasked = True
            if len(kept2["competencies"]) >= len(kept["competencies"]):
                kept, self.rejected_ids = kept2, list(rejected2)
        if not kept["competencies"]:
            raise RuntimeError("Stage A produced no grounded competency after the re-ask")
        self._normalise_ids(kept)
        self.rubric = schemas.Rubric.model_validate(kept).model_dump(mode="json")
        self.agenda = AgendaManager(self.rubric, self.dial)
        return self.rubric

    def rubric_chips(self) -> list[dict[str, Any]]:
        return [{"id": c["id"], "name": c["name"], "priority": c["priority"], "type": c["type"]} for c in (self.rubric or {}).get("competencies", [])]

    def opener_text(self) -> str:
        return prompts.OPENER_TEMPLATE.format(role_title=(self.rubric or {}).get("role_title", "this"))

    # ------------------------------------------------------------------ Stage B
    def _coverage_summary(self) -> str:
        assert self.agenda is not None
        rows = []
        for r in self.agenda.coverage_report()["competencies"]:
            star = "*" if r["priority"] == "must_have" else " "
            cells = ", ".join(f"{k}={v}" for k, v in r["cells"].items())
            rows.append(f"{star}{r['competency_id']} {r['name']} (asked {r['asked_count']}): {cells}")
        return "\n".join(rows) or "(nothing asked yet)"

    def _last_two_turns(self) -> str:
        done = [t for t in self.turns if t.transcript][-2:]
        if not done:
            return prompts.NO_TURNS
        return "\n".join(prompts.TURN_FORMAT.format(n=t.idx, question=t.question["text"], answer=t.transcript[:600]) for t in done)

    @staticmethod
    def _trigger_line(target: dict[str, Any]) -> str:
        tb = target.get("triggered_by") or {}
        if tb.get("quote") and tb.get("t"):
            return prompts.TRIGGER_LINE_FORMAT.format(quote=tb["quote"], t0=float(tb["t"][0]))
        return prompts.NO_TRIGGER

    def next_target(self) -> dict[str, Any] | None:
        assert self.agenda is not None
        return self.agenda.next_target()

    def provisional_target(self, transcript_text: str) -> dict[str, Any] | None:
        assert self.agenda is not None
        return self.agenda.provisional_target(transcript_text)

    @staticmethod
    def needs_swap(provisional: dict[str, Any] | None, final: dict[str, Any] | None) -> bool:
        return AgendaManager.needs_swap(provisional, final)

    async def word_question(self, target: dict[str, Any]) -> dict[str, Any]:
        """Stage B: the LLM words one question for an agenda target. Returns a schemas.Question dump."""
        assert self.agenda is not None
        qid = f"Q{self.agenda.total_asked + 1}"
        strategy = target.get("strategy", "open_probe")
        rung = target.get("ladder_rung", "recall")
        values = {
            "competency_name": target.get("competency_name", ""),
            "coverage_summary": self._coverage_summary(),
            "evidence_gap": target.get("evidence_gap", ""),
            "jd_quote": target.get("jd_quote", ""),
            "ladder_hint": prompts.LADDER_HINTS.get(rung, ""),
            "ladder_rung": rung,
            "last_two_turns": self._last_two_turns(),
            "pressure_dial": self.dial_cfg["label"],
            "question_id": qid,
            "strategy": strategy,
            "strategy_hint": prompts.STRATEGY_HINTS.get(strategy, ""),
            "tone": self.dial_cfg["tone"],
            "trigger_line": self._trigger_line(target),
        }
        draft, st = await self.llm.ajson("stage_b", values, schemas.QuestionDraft)
        self.stats.append(st)
        tb = target.get("triggered_by") or {}
        triggered = None
        if tb.get("quote") and tb.get("t") and tb.get("answer_id"):
            triggered = {"answer_id": tb["answer_id"], "quote": tb["quote"], "t": [float(tb["t"][0]), float(tb["t"][1])]}
        question = {
            "question_id": qid,
            "text": draft["text"].strip(),
            "why": {"competency_id": target["competency_id"], "jd_quote": target.get("jd_quote", ""), "ladder_rung": rung, "strategy": strategy, "triggered_by": triggered},
            "time_limit_s": target.get("time_limit_s"),
            "reaction_before": target.get("reaction_before", "neutral"),
        }
        q = schemas.Question.model_validate(question).model_dump(mode="json")
        q["evidence_item"] = draft.get("evidence_item")
        return q

    def commit_question(self, question: dict[str, Any], target: dict[str, Any]) -> Turn:
        """Mark the target asked and open a turn (call right before the question is spoken)."""
        assert self.agenda is not None
        record = self.agenda.mark_asked(target, question["question_id"])
        idx = record["asked_index"]
        turn = Turn(idx=idx, question=question, target=record, answer_id=f"A{idx}")
        self.turns.append(turn)
        return turn

    def should_stop(self) -> tuple[bool, str | None]:
        assert self.agenda is not None
        v = self.agenda.should_stop
        return v() if callable(v) else v  # AgendaManager exposes it as a method

    # ------------------------------------------------------------------ Stage C
    def _prior_claims(self, upto: Turn) -> tuple[str, dict[str, list[dict[str, Any]]]]:
        lines, prior_words = [], {}
        for t in self.turns:
            if t is upto or not t.gate:
                continue
            prior_words[t.answer_id] = t.words
            for v in t.gate.validated:
                if v.path in ("key_quote", "star.action", "star.result", "star.situation"):
                    lines.append(prompts.CLAIM_FORMAT.format(answer_id=t.answer_id, t0=v.span_t[0], t1=v.span_t[1], quote=v.quote))
        return ("\n".join(lines[-12:]) or prompts.NO_CLAIMS), prior_words

    async def analyse(self, turn: Turn, transcript: str, words: list[dict[str, Any]]) -> tuple[dict[str, Any], GateResult, dict[str, Any] | None]:
        """Stage C + quote gate + agenda update. Returns (validated analysis, gate, pending follow-up target)."""
        assert self.agenda is not None and self.rubric is not None
        turn.transcript, turn.words = transcript, words
        comp = next((c for c in self.rubric["competencies"] if c["id"] == turn.target["competency_id"]), self.rubric["competencies"][0])
        transcript_words = prompts.WORD_SEP.join(prompts.WORD_FORMAT.format(word=w["word"], start=float(w["start"])) for w in words) or "(silence)"
        prior_claims, prior_words = self._prior_claims(turn)
        values = {
            "answer_id": turn.answer_id,
            "competency_id": comp["id"],
            "competency_name": comp["name"],
            "evidence_expected": ", ".join(comp.get("evidence_expected", [])),
            "jd_keywords": ", ".join(_keywords(comp)),
            "ladder_rung": turn.target.get("ladder_rung", "recall"),
            "prior_claims": prior_claims,
            "question_id": turn.question["question_id"],
            "question_text": turn.question["text"],
            "strategy": turn.target.get("strategy", "open_probe"),
            "transcript_words": transcript_words,
            "trigger_line": self._trigger_line(turn.target),
        }
        if not words:
            analysis = self._empty_analysis(turn, comp)
            gate = validate_analysis(analysis, words, answer_id=turn.answer_id, cheap_rules=False)
        else:
            raw, st = await self.llm.ajson("stage_c", values, schemas.Analysis)
            self.stats.append(st)
            raw["answer_id"] = turn.answer_id
            gate = validate_analysis(raw, words, answer_id=turn.answer_id, prior_words=prior_words)
        turn.analysis, turn.gate = gate.analysis, gate
        pending = self.agenda.apply_analysis(gate.analysis)
        return gate.analysis, gate, pending

    def _empty_analysis(self, turn: Turn, comp: dict[str, Any]) -> dict[str, Any]:
        absent = {"present": False, "quote": None, "t": None, "ownership": None}
        return {
            "answer_id": turn.answer_id,
            "star": {"situation": dict(absent), "task": dict(absent), "action": dict(absent), "result": dict(absent)},
            "specificity": {"score": 0, "scale": "0-3", "missing": ["an answer"]},
            "jd_keyword_coverage": {"hit": [], "missed": _keywords(comp)},
            "hedges": [], "contradictions": [],
            "verdict": "vague",
            "evidence_updates": {comp["id"]: {}},
            "next_strategy": "dig_deeper_vague",
            "reaction": "thinking",
        }

    def reaction_for(self, analysis: dict[str, Any]) -> str:
        assert self.agenda is not None
        return self.agenda.suggested_reaction(analysis.get("reaction"))

    @staticmethod
    def reaction_line(mood: str) -> str:
        return random.choice(prompts.REACTION_LINES.get(mood, prompts.REACTION_LINES["neutral"]))

    @staticmethod
    def interrupt_line(kind: str = "timeout") -> str:
        return random.choice(prompts.INTERRUPT_LINES.get(kind, prompts.INTERRUPT_LINES["timeout"]))

    # ------------------------------------------------------------------ Stage D
    def _coverage_text(self) -> str:
        assert self.agenda is not None
        rows = []
        for r in self.agenda.coverage_report()["competencies"]:
            star = "*" if r["priority"] == "must_have" else " "
            cells = "; ".join(f"{k}: {v}" for k, v in r["cells"].items())
            rows.append(f"{star} {r['competency_id']} {r['name']} — {cells}")
        return "\n".join(rows)

    def _validated_analyses_text(self) -> str:
        out = []
        for t in self.turns:
            if not t.analysis:
                continue
            a = dict(t.analysis)
            a["question"] = t.question["text"]
            a["verified_quotes"] = [{"path": v.path, "quote": v.quote, "t": [round(v.span_t[0], 1), round(v.span_t[1], 1)]} for v in (t.gate.validated if t.gate else [])]
            out.append(json.dumps(a, ensure_ascii=False))
        return "\n".join(out) or "(no answers)"

    async def build_report(self, delivery: dict[str, Any]) -> dict[str, Any]:
        assert self.agenda is not None and self.rubric is not None
        validated = [v for t in self.turns if t.gate for v in t.gate.validated]
        answer_ids = {t.question["question_id"]: t.answer_id for t in self.turns}
        n_answers = sum(1 for t in self.turns if t.transcript)
        values = {
            "coverage_matrix": self._coverage_text(),
            "delivery_metrics": json.dumps({k: v for k, v in delivery.items() if k != "per_answer"}, ensure_ascii=False),
            "n_answers": n_answers,
            "pressure_dial": self.dial_cfg["label"],
            "role_title": self.rubric.get("role_title", ""),
            "validated_analyses": self._validated_analyses_text(),
        }
        report_dict: dict[str, Any]
        if validated and n_answers:
            draft, st = await self.llm.ajson("stage_d", values, schemas.ReportDraft)
            self.stats.append(st)
            filtered, dropped = filter_report(draft, validated, answer_ids=answer_ids, min_ratio=90)
            if dropped:
                log.info("report gate dropped %d bullet(s): %s", len(dropped), [(d.path, d.reason) for d in dropped])
            if not filtered.get("top_fixes"):
                filtered["top_fixes"] = self._fallback_fixes(validated)[:3]
            draft_model = schemas.ReportDraft.model_validate(filtered)
        else:
            draft_model = schemas.ReportDraft.model_validate({
                "top_fixes": self._fallback_fixes(validated)[:3] or [self._no_evidence_fix()],
                "per_question": [{"answer_id": t.answer_id, "star": {"S": False, "T": False, "A": False, "R": False}, "verdict": "vague", "key_quote": None} for t in self.turns],
                "overall_band": "not yet ready",
                "band_mover": "Give one concrete example with a number in every answer.",
            })
        coverage = schemas.CoverageMatrix.from_state(schemas.Rubric.model_validate(self.rubric), self.agenda.coverage)
        report = schemas.Report.from_draft(draft_model, coverage, schemas.DeliveryMetrics.model_validate(delivery))
        report_dict = report.model_dump(mode="json")
        report_dict["empty_must_haves"] = [r.competency_id for r in coverage.empty_must_haves()]
        report_dict["llm_stats"] = [{"stage": s.stage, "tok_s": round(s.tok_s, 1) if s.tok_s else None, "elapsed_s": round(s.elapsed_s, 2)} for s in self.stats]
        return report_dict

    def _fallback_fixes(self, validated: list[Any]) -> list[dict[str, Any]]:
        """Code-only fixes from the gate when the LLM report has nothing usable."""
        fixes = []
        for t in self.turns:
            a = t.analysis or {}
            star = a.get("star", {})
            if not star.get("result", {}).get("present") and t.gate and t.gate.validated:
                v = t.gate.validated[0]
                fixes.append({
                    "behaviour": "No result stated", "answer_id": t.answer_id, "quote": v.quote, "t": [v.span_t[0], v.span_t[1]],
                    "rubric_line": f"{t.target.get('competency_name', '')}: {t.target.get('evidence_gap', '')}",
                    "why_it_matters": "Interviewers score outcomes, not effort; an action without a result reads as unfinished.",
                    "stronger_version": "After we made that change, [metric] went from [before] to [after] within [time frame].",
                })
        return fixes

    @staticmethod
    def _no_evidence_fix() -> dict[str, Any]:
        return {
            "behaviour": "No answer was captured", "answer_id": "A1", "quote": "", "t": [0.0, 0.0],
            "rubric_line": "all: evidence", "why_it_matters": "Nothing was said that the interviewer could score.",
            "stronger_version": "Start with the situation in one sentence, then what you personally did, then the number that changed.",
        }
