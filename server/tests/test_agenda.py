"""Tests for brain/agenda.py - the Stage B Agenda Manager (BLUEPRINT section 5.2 / 5.3 / 5.6).

Pure Python, no LLM. Each test drives the manager the way server.py will:
next_target() -> mark_asked() -> apply_analysis() -> ...
"""

from __future__ import annotations

import pytest

from brain.agenda import (
    DIALS,
    FOLLOWUP_STRATEGIES,
    VAGUE_THRESHOLD,
    AgendaManager,
    vague_score,
    vagueness_features,
)

LADDER = ["recall", "applied example", "trade-off or failure", "design under constraint"]


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def comp(cid, *, ctype="technical", priority="must_have", evidence=3, name=None, quote=None):
    """A Stage A competency with `evidence` synthetic evidence items."""
    if isinstance(evidence, int):
        evidence = [f"{cid} evidence {i + 1}" for i in range(evidence)]
    return {
        "id": cid,
        "name": name or f"Competency {cid}",
        "type": ctype,
        "priority": priority,
        "jd_quotes": [{"text": quote or f"JD sentence for {cid}", "start": 0, "end": 10}],
        "evidence_expected": evidence,
        "difficulty_ladder": list(LADDER),
    }


def rubric(*comps, mix=None):
    return {
        "role_title": "Backend Developer (Node.js)",
        "seniority": "fresher",
        "behavioral_technical_mix": mix or {"behavioral": 0.5, "technical": 0.5},
        "competencies": list(comps),
    }


def analysis(
    answer_id="A1",
    *,
    verdict="adequate",
    updates=None,
    next_strategy=None,
    quote=None,
    t=None,
    competency_id=None,
    contradictions=None,
    hits=None,
):
    """A minimal validated Stage C result (section 5.3 shape)."""
    a = {
        "answer_id": answer_id,
        "star": {
            "situation": {"present": False},
            "task": {"present": False},
            "action": {"present": quote is not None, "quote": quote, "t": t, "ownership": "we"},
            "result": {"present": False},
        },
        "specificity": {"score": 1, "scale": "0-3", "missing": ["number"]},
        "jd_keyword_coverage": {"hit": hits or [], "missed": []},
        "hedges": [],
        "contradictions": contradictions or [],
        "verdict": verdict,
        "evidence_updates": updates or {},
        "next_strategy": next_strategy,
        "reaction": "neutral",
    }
    if competency_id:
        a["competency_id"] = competency_id
    return a


def ask(mgr):
    """next_target() + mark_asked(); returns the committed record."""
    t = mgr.next_target()
    assert t is not None, "expected a target but the manager wants to stop"
    return mgr.mark_asked(t)


# --------------------------------------------------------------------------------------
# policy (2): least-covered must-have, respecting mix debt
# --------------------------------------------------------------------------------------


def test_least_covered_must_have_chosen_first():
    mgr = AgendaManager(
        rubric(comp("C1", evidence=2), comp("C2", evidence=3), comp("C3", priority="nice_to_have", evidence=5)),
        "realistic",
    )
    t = mgr.next_target()
    assert t["competency_id"] == "C2"  # most "none" cells among must-haves; C3 has more but is nice-to-have
    assert t["strategy"] == "open_probe"
    assert t["is_followup"] is False
    assert t["triggered_by"] is None
    assert t["ladder_rung"] == "recall"
    assert t["evidence_gap"] == "C2 evidence 1"
    # the six keys Stage B's prompt consumes are always present
    for key in ("competency_id", "evidence_gap", "ladder_rung", "strategy", "is_followup", "triggered_by"):
        assert key in t
    assert t["jd_quote"] == "JD sentence for C2"


def test_evidence_moves_priority_to_the_next_gap():
    mgr = AgendaManager(rubric(comp("C1", evidence=3), comp("C2", evidence=3)), "realistic")
    ask(mgr)  # C1 (tie broken by rubric order)
    mgr.apply_analysis(analysis("A1", updates={"C1": {"C1 evidence 1": "weak", "C1 evidence 2": "weak"}}))
    t = mgr.next_target()
    assert t["competency_id"] == "C2"  # C2 now has 3 none vs C1's 1
    assert mgr.counts("C1") == {"none": 1, "weak": 2, "strong": 0}


def test_mix_debt_alternates_toward_jd_mix():
    mgr = AgendaManager(
        rubric(
            comp("B1", ctype="behavioural", evidence=4),
            comp("T1", ctype="technical", evidence=4),
            mix={"behavioral": 0.4, "technical": 0.6},
        ),
        "realistic",
    )
    order = []
    for i in range(4):
        rec = ask(mgr)
        order.append(rec["competency_type"])
        mgr.apply_analysis(
            analysis(f"A{i + 1}", updates={rec["competency_id"]: {rec["evidence_gap"]: "weak"}})
        )
    # 40/60 => technical first, then alternate: T B T B
    assert order == ["technical", "behavioral", "technical", "behavioral"]
    assert mgr.mix_debt["technical"] > mgr.mix_debt["behavioral"]  # 5th question owed to technical


def test_mix_never_picks_a_fully_covered_competency_just_for_balance():
    mgr = AgendaManager(
        rubric(
            comp("B1", ctype="behavioral", evidence=1),
            comp("T1", ctype="technical", evidence=3),
            mix={"behavioral": 0.5, "technical": 0.5},
        ),
        "realistic",
    )
    ask(mgr)  # T1 (more none cells; debts equal)
    mgr.apply_analysis(analysis("A1", updates={"T1": {"T1 evidence 1": "weak"}}))
    ask(mgr)  # B1 (behavioral owed)
    mgr.apply_analysis(analysis("A2", updates={"B1": {"B1 evidence 1": "weak"}}))
    # behavioral is owed again at question 4 but B1 has no "none" cell left => T1
    t = mgr.next_target()
    assert t["competency_id"] == "T1"


def test_next_target_is_pure():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    a, b = mgr.next_target(), mgr.next_target()
    assert a == b
    assert mgr.total_asked == 0 and mgr.asked_count == {"C1": 0, "C2": 0}


# --------------------------------------------------------------------------------------
# policy (1): follow-up after a vague answer
# --------------------------------------------------------------------------------------


def test_followup_after_vague_analysis():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    q1 = ask(mgr)
    assert q1["competency_id"] == "C1" and q1["question_id"] == "Q1"
    pending = mgr.apply_analysis(
        analysis(
            "A1",
            verdict="vague",
            next_strategy="dig_deeper_vague",
            quote="we used caching and stuff",
            t=[8.2, 11.9],
            updates={"C1": {"C1 evidence 1": "weak"}},
        )
    )
    assert pending is not None
    t = mgr.next_target()
    assert t["is_followup"] is True
    assert t["competency_id"] == "C1"  # stays on the competency even though C2 has more gaps
    assert t["strategy"] == "dig_deeper_vague"
    assert t["ladder_rung"] == q1["ladder_rung"]  # follow-ups stay on the same rung
    assert t["triggered_by"] == {"answer_id": "A1", "quote": "we used caching and stuff", "t": [8.2, 11.9]}
    assert t["hint"] == "Give me one specific instance."
    q2 = mgr.mark_asked(t)
    assert q2["question_id"] == "Q2"
    assert mgr.followups_asked["C1"] == 1
    assert mgr.pending_followup is None  # consumed


@pytest.mark.parametrize(
    "strategy,expected_hint",
    [
        ("dig_deeper_generic", "What was *your* part in that?"),
        ("quantify_result", "What changed because of it - any number?"),
        ("ownership_probe", "What did you personally do, as opposed to the team?"),
    ],
)
def test_every_followup_strategy_is_honoured(strategy, expected_hint):
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    mgr.apply_analysis(analysis("A1", verdict="generic", next_strategy=strategy, quote="we did it", t=[1.0, 2.0]))
    t = mgr.next_target()
    assert t["is_followup"] and t["strategy"] == strategy
    assert t["hint"] == expected_hint
    assert strategy in FOLLOWUP_STRATEGIES


def test_evidence_probe_followup_names_the_claimed_keyword():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    mgr.apply_analysis(
        analysis("A1", verdict="vague", next_strategy="evidence_probe", quote="I did caching", t=[1, 2], hits=["caching"])
    )
    t = mgr.next_target()
    assert t["is_followup"] and t["strategy"] == "evidence_probe"
    assert t["hint"] == "Walk me through how you did caching."


def test_open_probe_or_escalate_next_strategy_is_not_a_followup():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    assert mgr.apply_analysis(analysis("A1", verdict="adequate", next_strategy="open_probe")) is None
    assert mgr.next_target()["is_followup"] is False


# --------------------------------------------------------------------------------------
# policy (3): ladder escalates after strong
# --------------------------------------------------------------------------------------


def test_ladder_escalates_after_strong():
    # both technical so mix debt never steers away from C1; C2 keeps the round alive
    mgr = AgendaManager(
        rubric(comp("C1", evidence=4), comp("C2", evidence=1), mix={"technical": 1.0, "behavioral": 0.0}),
        "realistic",
    )
    q1 = ask(mgr)
    assert q1["competency_id"] == "C1" and q1["ladder_rung"] == "recall"
    mgr.apply_analysis(analysis("A1", verdict="strong", updates={"C1": {"C1 evidence 1": "strong"}}))
    assert mgr.ladder_pos["C1"] == 1
    assert mgr.escalation_pending["C1"] is True

    q2 = ask(mgr)
    assert q2["competency_id"] == "C1"  # still the biggest gap (3 none vs 1)
    assert q2["ladder_rung"] == "applied example"
    assert q2["strategy"] == "escalate"
    assert mgr.escalation_pending["C1"] is False  # consumed by asking the escalated question

    mgr.apply_analysis(analysis("A2", verdict="strong", updates={"C1": {"C1 evidence 2": "strong"}}))
    q3 = ask(mgr)
    assert (q3["competency_id"], q3["ladder_rung"], q3["strategy"]) == ("C1", "trade-off or failure", "escalate")

    mgr.apply_analysis(analysis("A3", verdict="strong", updates={"C1": {"C1 evidence 3": "strong"}}))
    assert mgr.ladder_pos["C1"] == 3
    # clamps at the top rung
    mgr.apply_analysis(analysis("A3b", verdict="strong", competency_id="C1", updates={"C1": {"C1 evidence 4": "strong"}}))
    assert mgr.ladder_pos["C1"] == 3


def test_non_strong_verdicts_do_not_escalate():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    for verdict in ("vague", "generic", "adequate"):
        mgr.apply_analysis(analysis(verdict=verdict, competency_id="C1", updates={"C1": {"C1 evidence 1": "weak"}}))
    assert mgr.ladder_pos["C1"] == 0


def test_strong_verdict_without_strong_cell_marks_the_targeted_gap():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    q1 = ask(mgr)
    mgr.apply_analysis(analysis("A1", verdict="strong"))  # small-model inconsistency: no evidence_updates
    assert mgr.coverage["C1"][q1["evidence_gap"]] == "strong"
    assert mgr.notes  # the guard is logged


# --------------------------------------------------------------------------------------
# policy (4): stop rules
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("dial,n", [("warmup", 6), ("realistic", 8), ("tough", 10)])
def test_stops_at_n_per_dial(dial, n):
    assert DIALS[dial].max_questions == n
    # 4 must-haves x 6 cells: plenty of gaps, and weak-only updates never satisfy the strong rule
    mgr = AgendaManager(rubric(*[comp(f"C{i}", evidence=6) for i in range(1, 5)]), dial)
    asked = 0
    while (t := mgr.next_target()) is not None:
        rec = mgr.mark_asked(t)
        asked += 1
        mgr.apply_analysis(analysis(f"A{asked}", updates={rec["competency_id"]: {rec["evidence_gap"]: "weak"}}))
        assert asked <= n
    assert asked == n == mgr.total_asked
    assert mgr.should_stop() == (True, "max_questions")


def test_pending_followup_does_not_exceed_n():
    mgr = AgendaManager(rubric(comp("C1", evidence=6), comp("C2", evidence=6)), "warmup")
    for i in range(6):
        rec = ask(mgr)
        strategy = "dig_deeper_vague" if i == 5 else None  # a follow-up demanded on the last answer
        mgr.apply_analysis(
            analysis(f"A{i + 1}", verdict="vague", next_strategy=strategy, quote="we did stuff", t=[0, 1])
        )
    assert mgr.pending_followup is not None  # budget allowed it ...
    assert mgr.next_target() is None  # ... but the N cap is a hard guard
    assert mgr.should_stop() == (True, "max_questions")


def test_stops_when_all_must_haves_strong():
    mgr = AgendaManager(
        rubric(comp("C1"), comp("C2"), comp("C3", priority="nice_to_have", evidence=4)),
        "realistic",
    )
    q1 = ask(mgr)
    assert q1["competency_id"] == "C1"
    mgr.apply_analysis(analysis("A1", verdict="strong", updates={"C1": {"C1 evidence 1": "strong"}}))
    assert mgr.should_stop() == (False, None)  # C2 has no strong yet
    q2 = ask(mgr)
    assert q2["competency_id"] == "C2"
    mgr.apply_analysis(analysis("A2", verdict="strong", updates={"C2": {"C2 evidence 2": "strong"}}))
    assert mgr.next_target() is None
    assert mgr.should_stop() == (True, "must_haves_strong")
    assert mgr.total_asked == 2 < DIALS["realistic"].max_questions
    assert mgr.counts("C3")["none"] == 4  # nice-to-have gaps do not keep the round alive


def test_stops_when_coverage_is_exhausted():
    mgr = AgendaManager(rubric(comp("C1", evidence=1), comp("C2", evidence=1)), "realistic")
    for i in range(2):
        rec = ask(mgr)
        mgr.apply_analysis(analysis(f"A{i + 1}", updates={rec["competency_id"]: {rec["evidence_gap"]: "weak"}}))
    # weak cells get re-probed once each ...
    for i in range(2):
        t = mgr.next_target()
        assert t is not None and t["strategy"] == "evidence_probe"
        rec = mgr.mark_asked(t)
        mgr.apply_analysis(analysis(f"A{i + 3}", updates={rec["competency_id"]: {rec["evidence_gap"]: "weak"}}))
    # ... and then there is nothing left: weak never becomes strong, so we would loop forever otherwise
    mgr.coverage["C1"]["C1 evidence 1"] = "strong"
    mgr.coverage["C2"]["C2 evidence 1"] = "weak"
    mgr.coverage["C2"]["C2 evidence 1"] = "strong"
    assert mgr.should_stop()[0] is True


def test_all_nice_to_have_rubric_treats_everything_as_must_have():
    mgr = AgendaManager(rubric(comp("C1", priority="nice_to_have"), comp("C2", priority="nice_to_have")), "realistic")
    assert mgr.must_have_ids == ["C1", "C2"]
    assert mgr.next_target() is not None  # not a vacuous "all must-haves strong" stop


# --------------------------------------------------------------------------------------
# follow-up budget
# --------------------------------------------------------------------------------------


def test_max_two_followups_per_competency():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    assert mgr.max_followups == 2
    ask(mgr)  # Q1 -> C1
    vague = dict(verdict="vague", next_strategy="dig_deeper_vague", quote="we did stuff", t=[0.0, 1.0])
    mgr.apply_analysis(analysis("A1", **vague))
    q2 = ask(mgr)
    assert q2["is_followup"] and q2["competency_id"] == "C1"
    mgr.apply_analysis(analysis("A2", **vague))
    q3 = ask(mgr)
    assert q3["is_followup"] and q3["competency_id"] == "C1"
    assert mgr.followups_asked["C1"] == 2
    # third vague answer in a row: the follow-up is dropped and the agenda moves on
    assert mgr.apply_analysis(analysis("A3", **vague)) is None
    assert mgr.dropped_followups and mgr.dropped_followups[-1]["competency_id"] == "C1"
    q4 = ask(mgr)
    assert q4["is_followup"] is False
    assert q4["competency_id"] == "C2"
    assert mgr.followups_asked["C1"] == 2


def test_warmup_allows_one_followup_per_competency():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "warm-up")
    assert mgr.max_followups == 1
    ask(mgr)
    vague = dict(verdict="vague", next_strategy="dig_deeper_vague", quote="we did stuff", t=[0.0, 1.0])
    mgr.apply_analysis(analysis("A1", **vague))
    assert ask(mgr)["is_followup"] is True
    assert mgr.apply_analysis(analysis("A2", **vague)) is None
    assert mgr.next_target()["is_followup"] is False


def test_followup_budget_is_per_competency():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2"), comp("C3")), "realistic", max_questions=20)
    vague = dict(verdict="vague", next_strategy="dig_deeper_vague", quote="we did stuff", t=[0.0, 1.0])
    ask(mgr)  # C1
    mgr.apply_analysis(analysis("A1", **vague))
    ask(mgr)  # C1 follow-up 1
    mgr.apply_analysis(analysis("A2", **vague))
    ask(mgr)  # C1 follow-up 2
    mgr.apply_analysis(analysis("A3", **vague))
    q = ask(mgr)  # moves to C2
    assert q["competency_id"] == "C2" and not q["is_followup"]
    mgr.apply_analysis(analysis("A4", **vague))
    q = ask(mgr)  # C2 still has its own budget
    assert q["competency_id"] == "C2" and q["is_followup"]


def test_contradiction_probe_only_in_tough_and_exempt_from_budget():
    contradiction = [{"quote": "I led the migration", "t": [3.0, 4.5], "earlier": {"quote": "we all did it", "t": [1.0, 2.0]}}]
    # Realistic: ignored
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    assert mgr.apply_analysis(analysis("A1", next_strategy="contradiction_probe", contradictions=contradiction)) is None
    assert mgr.next_target()["is_followup"] is False
    # Tough: allowed, quote comes from the contradiction, and it does not eat the 2 dig-deeper follow-ups
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "tough")
    ask(mgr)
    vague = dict(verdict="vague", next_strategy="dig_deeper_vague", quote="we did stuff", t=[0.0, 1.0])
    for aid in ("A1", "A2"):
        mgr.apply_analysis(analysis(aid, **vague))
        assert ask(mgr)["is_followup"]
    assert mgr.followups_asked["C1"] == 2
    t = mgr.apply_analysis(analysis("A3", next_strategy="contradiction_probe", contradictions=contradiction))
    assert t is not None and t["strategy"] == "contradiction_probe"
    assert t["triggered_by"]["quote"] == "I led the migration"
    ask(mgr)
    assert mgr.contradiction_probes_asked["C1"] == 1
    # capped at one per competency
    assert mgr.apply_analysis(analysis("A4", next_strategy="contradiction_probe", contradictions=contradiction)) is None


# --------------------------------------------------------------------------------------
# coverage matrix semantics
# --------------------------------------------------------------------------------------


def test_coverage_is_monotonic_and_tolerant_to_paraphrased_items():
    mgr = AgendaManager(
        rubric(comp("C1", evidence=["designed endpoints", "handled auth or versioning", "measured latency"]), comp("C2")),
        "realistic",
    )
    ask(mgr)
    mgr.apply_analysis(analysis("A1", updates={"C1": {"measured latency": "strong", "designed endpoints": "weak"}}))
    mgr.apply_analysis(
        analysis("A1b", competency_id="C1", updates={"C1": {"Measured the latency": "none", "designed endpoints": "none"}})
    )
    assert mgr.coverage["C1"]["measured latency"] == "strong"  # never downgraded
    assert mgr.coverage["C1"]["designed endpoints"] == "weak"
    mgr.apply_analysis(analysis("A1c", competency_id="C1", updates={"C1": {"handled auth / versioning": "weak"}}))
    assert mgr.coverage["C1"]["handled auth or versioning"] == "weak"  # fuzzy-matched
    mgr.apply_analysis(analysis("A1d", competency_id="C1", updates={"C9": {"x": "strong"}, "C1": {"unrelated item": "strong"}}))
    assert mgr.counts("C1") == {"none": 0, "weak": 2, "strong": 1}  # unknown ids/items ignored, and logged
    assert any("unknown" in n for n in mgr.notes)


def test_rubric_normalisation():
    mgr = AgendaManager(
        {
            "behavioral_technical_mix": {"behavioural": 30, "technical": 70},
            "competencies": [
                {"id": "C1", "name": "x", "type": "Behavioural", "priority": "must-have", "jd_quotes": [], "evidence_expected": []},
                {"id": "C2", "name": "y", "type": "technical", "priority": "nice to have", "evidence_expected": ["a", "a", " b "]},
            ],
        },
        "Realistic",
    )
    assert mgr.rubric.behavioral_technical_mix == {"behavioral": 0.3, "technical": 0.7}
    assert mgr.rubric.competencies[0].type == "behavioral"
    assert mgr.rubric.competencies[1].priority == "nice_to_have"
    assert list(mgr.coverage["C1"]) == ["one concrete example"]  # empty evidence list gets a default cell
    assert list(mgr.coverage["C2"]) == ["a", "b"]  # de-duplicated, stripped
    assert mgr.rubric.competencies[0].difficulty_ladder == LADDER


# --------------------------------------------------------------------------------------
# vagueness heuristic + critical-path trick (section 5.3)
# --------------------------------------------------------------------------------------


VAGUE = "we used caching and stuff"
MIDDLING = "I worked on the backend API and we optimised the latency by adding a cache layer, and it worked fine."
SPECIFIC = (
    "In my final-year project I built the order service in Node.js with Redis caching; "
    "I set a 30-second TTL after measuring that p95 latency dropped from 800 ms to 120 ms."
)


def test_vague_score_orders_the_examples():
    assert vague_score(VAGUE) >= VAGUE_THRESHOLD
    assert vague_score(MIDDLING) >= VAGUE_THRESHOLD
    assert vague_score(SPECIFIC) < 0.3
    assert vague_score("") == 1.0
    assert vague_score(SPECIFIC) < vague_score(MIDDLING) < vague_score(VAGUE)
    f = vagueness_features(VAGUE)
    assert f["we_ratio"] == 1.0 and f["has_number"] is False and f["has_name"] is False and f["vague_markers"] == 1
    s = vagueness_features(SPECIFIC)
    assert s["has_number"] and s["has_name"] and s["we_ratio"] == 0.0


def test_we_heavy_but_specific_answer_triggers_ownership_style_followup():
    text = (
        "We migrated the service to Postgres 14 and we cut the p99 to 300 ms; our team shipped it in two weeks "
        "and we monitored it with Grafana."
    )
    f = vagueness_features(text)
    assert f["score"] < VAGUE_THRESHOLD and f["we_ratio"] > 0.7
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    t = mgr.provisional_target(text)
    assert t["is_followup"] and t["strategy"] == "dig_deeper_generic" and t["provisional"] is True


def test_provisional_followup_then_no_swap_when_stage_c_agrees():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    prov = mgr.provisional_target(VAGUE)
    assert prov["is_followup"] and prov["strategy"] == "dig_deeper_vague" and prov["competency_id"] == "C1"
    assert prov["provisional"] is True
    assert prov["triggered_by"]["answer_id"] == "A1" and prov["triggered_by"]["quote"] is None
    assert prov["triggered_by"]["heuristic"]["score"] >= VAGUE_THRESHOLD
    assert mgr.total_asked == 1 and mgr.pending_followup is None  # provisional planning changes nothing
    mgr.apply_analysis(analysis("A1", verdict="vague", next_strategy="dig_deeper_vague", quote=VAGUE, t=[8.2, 11.9]))
    final = mgr.next_target()
    assert AgendaManager.needs_swap(prov, final) is False
    assert final["triggered_by"]["quote"] == VAGUE  # server copies this into the why-trace


def test_provisional_fresh_target_swapped_when_stage_c_demands_followup():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(mgr)
    prov = mgr.provisional_target(SPECIFIC)
    assert prov["is_followup"] is False and prov["competency_id"] == "C2"  # prefers a different competency
    mgr.apply_analysis(analysis("A1", verdict="adequate", next_strategy="quantify_result", quote="I built it", t=[0, 1]))
    final = mgr.next_target()
    assert final["is_followup"] and final["strategy"] == "quantify_result"
    assert AgendaManager.needs_swap(prov, final) is True


def test_no_swap_on_fresh_target_mismatch_unless_strict():
    prov = {"competency_id": "C2", "strategy": "open_probe", "is_followup": False}
    final = {"competency_id": "C1", "strategy": "evidence_probe", "is_followup": False}
    assert AgendaManager.needs_swap(prov, final) is False
    assert AgendaManager.needs_swap(prov, final, strict=True) is True
    assert AgendaManager.needs_swap(prov, None) is True  # round over: do not ask the pre-planned question
    assert AgendaManager.needs_swap(None, final) is True


def test_provisional_respects_followup_budget():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "warmup")
    ask(mgr)
    mgr.apply_analysis(analysis("A1", verdict="vague", next_strategy="dig_deeper_vague", quote=VAGUE, t=[0, 1]))
    ask(mgr)  # the one Warm-up follow-up
    prov = mgr.provisional_target(VAGUE)
    assert prov["is_followup"] is False and prov["competency_id"] == "C2"


# --------------------------------------------------------------------------------------
# dial extras, persistence
# --------------------------------------------------------------------------------------


def test_tough_unimpressed_after_second_vague_answer():
    mgr = AgendaManager(rubric(comp("C1"), comp("C2")), "tough")
    ask(mgr)
    mgr.apply_analysis(analysis("A1", verdict="vague", next_strategy="dig_deeper_vague", quote="stuff", t=[0, 1]))
    assert mgr.suggested_reaction("neutral") == "neutral"
    ask(mgr)
    mgr.apply_analysis(analysis("A2", verdict="vague", next_strategy="dig_deeper_vague", quote="stuff", t=[0, 1]))
    assert mgr.suggested_reaction("neutral") == "unimpressed"
    # never in Warm-up / Realistic (section 5.6)
    soft = AgendaManager(rubric(comp("C1"), comp("C2")), "realistic")
    ask(soft)
    for aid in ("A1", "A2"):
        soft.apply_analysis(analysis(aid, verdict="vague", competency_id="C1"))
    assert soft.suggested_reaction("unimpressed") == "neutral"


def test_time_limits_follow_the_dial():
    for dial, beh, tech in (("warmup", None, None), ("realistic", 90, 60), ("tough", 90, 60)):
        mgr = AgendaManager(rubric(comp("B1", ctype="behavioral"), comp("T1", ctype="technical")), dial)
        assert mgr.target_for("B1")["time_limit_s"] == beh
        assert mgr.target_for("T1")["time_limit_s"] == tech


def test_snapshot_roundtrip_reproduces_the_plan():
    rb = rubric(comp("C1"), comp("C2", ctype="behavioral"), comp("C3", priority="nice_to_have"))
    mgr = AgendaManager(rb, "tough")
    ask(mgr)
    mgr.apply_analysis(analysis("A1", verdict="strong", updates={"C1": {"C1 evidence 1": "strong"}}))
    ask(mgr)
    mgr.apply_analysis(analysis("A2", verdict="vague", next_strategy="dig_deeper_vague", quote="stuff", t=[0, 1]))
    snap = mgr.snapshot()
    clone = AgendaManager.restore(rb, snap)
    assert clone.snapshot() == snap
    assert clone.next_target() == mgr.next_target()
    assert clone.mix_debt == mgr.mix_debt
    report = clone.coverage_report()
    assert report["dial"]["name"] == "tough" and report["total_asked"] == 2
    assert {r["competency_id"]: r["has_strong"] for r in report["competencies"]} == {"C1": True, "C2": False, "C3": False}
