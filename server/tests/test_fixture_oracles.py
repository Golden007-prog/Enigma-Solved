"""The expected/*.json oracles driven through the draft gates and the agenda.

These complement test_rubric_gate.py / test_quote_gate.py / test_agenda.py: those pin the
gate semantics with inline data, these check that the *fixture* data the demo will run on
behaves as the oracles claim. Quotes come from the JSON, never re-typed here.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from brain.agenda import AgendaManager
from brain.quotegate import has_outcome_evidence, match_quote, ownership_stats, validate_analysis
from brain.rubric import find_quote_offsets, needs_reask, validate_rubric

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
RUB = json.loads((FIX / "expected/expected_rubric_hints.json").read_text(encoding="utf-8"))
ANA = json.loads((FIX / "expected/expected_analysis_hints.json").read_text(encoding="utf-8"))
JDS = {name: (FIX / name).read_text(encoding="utf-8") for name in RUB["jds"]}
JD_NAMES = list(RUB["jds"])
ANSWERS = list(ANA["answers"])
WORD_S = 60 / 155  # one word every 0.387 s: the same 155 wpm the hints assume


def _verify():
    spec = importlib.util.spec_from_file_location("verify_fixtures", FIX / "verify_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


VF = _verify()


def entries(jd_name: str) -> list[dict]:
    return RUB["jds"][jd_name]["competencies"]


def rubric_from_hints(jd_name: str, quotes_for=None) -> dict:
    """A Stage A rubric built from the oracle entries (ids C1.. in oracle order)."""
    quotes_for = quotes_for or (lambda e: [e["jd_quote"], *e["alt_quotes"]])
    comps = []
    for i, e in enumerate(entries(jd_name), 1):
        comps.append({
            "id": f"C{i}", "name": e["name"], "type": e["type"], "priority": e["priority"],
            "jd_quotes": [{"text": q} for q in quotes_for(e)],
            "evidence_expected": ["built it", "measured it", "explained a trade-off"],
            "difficulty_ladder": list(VF.LADDER),
        })
    n_beh = sum(c["type"] == "behavioral" for c in comps)
    return {
        "role_title": RUB["shared_title"], "seniority": RUB["shared_seniority"],
        "behavioral_technical_mix": {"behavioral": n_beh / len(comps), "technical": 1 - n_beh / len(comps)},
        "competencies": comps,
    }


def words_for(script: str) -> list[dict]:
    """A synthetic STT word list: one token per script word at 155 wpm."""
    return [
        {"word": w, "start": round(i * WORD_S, 3), "end": round(i * WORD_S + 0.33, 3)}
        for i, w in enumerate(script.split())
    ]


def script(key: str) -> str:
    return (FIX / ANA["answers"][key]["script_file"]).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage A gate against the rubric oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_every_oracle_quote_is_accepted_by_the_gate(jd_name):
    rubric, rejected = validate_rubric(JDS[jd_name], rubric_from_hints(jd_name))
    assert rejected == []
    for c, e in zip(rubric["competencies"], entries(jd_name)):
        assert [q["text"] for q in c["jd_quotes"]] == [e["jd_quote"], *e["alt_quotes"]]


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_gate_offsets_agree_with_the_oracle_offsets(jd_name):
    jd = JDS[jd_name]
    for e in entries(jd_name):
        start, end = e["jd_quote_offset"]
        assert jd[start:end] == e["jd_quote"]
        assert find_quote_offsets(jd, e["jd_quote"]) == (start, end)


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_paraphrases_are_rejected_and_trigger_a_reask(jd_name):
    paras = RUB["jds"][jd_name]["paraphrase_that_must_be_rejected"]
    rubric = rubric_from_hints(jd_name)
    rubric["competencies"] = [
        {"id": f"P{i}", "name": f"paraphrase {i}", "type": "technical", "priority": "must_have",
         "jd_quotes": [{"text": p}], "evidence_expected": ["x"], "difficulty_ladder": list(VF.LADDER)}
        for i, p in enumerate(paras, 1)
    ]
    rubric, rejected = validate_rubric(JDS[jd_name], rubric)
    assert rejected == [f"P{i}" for i in range(1, len(paras) + 1)]
    assert rubric["competencies"] == []
    assert needs_reask(rejected)


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_whitespace_and_case_mangled_quotes_are_accepted(jd_name):
    def mangle(q: str) -> str:
        parts = q.upper().split(" ")
        return "  " + "\n   ".join(parts[:3]) + "  " + "\t".join(parts[3:]) + " \n"

    rubric, rejected = validate_rubric(JDS[jd_name], rubric_from_hints(jd_name, lambda e: [mangle(e["jd_quote"])]))
    assert rejected == []
    for c, e in zip(rubric["competencies"], entries(jd_name)):
        s, t = c["jd_quotes"][0]["start"], c["jd_quotes"][0]["end"]
        assert JDS[jd_name][s:t] == e["jd_quote"]


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_fragment_examples_are_grounded_and_match_their_entry(jd_name):
    rubric, rejected = validate_rubric(
        JDS[jd_name], rubric_from_hints(jd_name, lambda e: e["fragment_examples_that_match"])
    )
    assert rejected == []
    for e in entries(jd_name):
        for frag in e["fragment_examples_that_match"]:
            assert VF.oracle_match(frag, e, RUB["min_match_words"]) is not None


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_mixed_competency_keeps_only_the_grounded_quote(jd_name):
    para = RUB["jds"][jd_name]["paraphrase_that_must_be_rejected"][0]
    rubric = rubric_from_hints(jd_name, lambda e: [para, e["jd_quote"]])
    rubric, rejected = validate_rubric(JDS[jd_name], rubric)
    assert rejected == []
    for c, e in zip(rubric["competencies"], entries(jd_name)):
        assert [q["text"] for q in c["jd_quotes"]] == [e["jd_quote"]]


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_degenerate_quotes_are_plain_substrings_the_sketch_would_accept(jd_name):
    """Documents why min_quote_words exists: the BLUEPRINT sketch grounds these."""
    jd_n = VF.plain_norm(JDS[jd_name])
    accepted = [q for q in RUB["jds"][jd_name]["degenerate_quotes_must_be_rejected"] if VF.plain_norm(q) in jd_n]
    assert len(accepted) >= 3
    assert all(len(VF.gate_norm(q).split()) < RUB["min_quote_words"] for q in accepted)


@pytest.mark.parametrize("jd_name", JD_NAMES)
def test_gate_rejects_degenerate_quotes(jd_name):
    degenerate = RUB["jds"][jd_name]["degenerate_quotes_must_be_rejected"]
    rubric = rubric_from_hints(jd_name)
    rubric["competencies"] = [
        {"id": f"D{i}", "name": f"degenerate {i}", "type": "technical", "priority": "must_have",
         "jd_quotes": [{"text": q}], "evidence_expected": ["x"], "difficulty_ladder": list(VF.LADDER)}
        for i, q in enumerate(degenerate, 1)
    ]
    _, rejected = validate_rubric(JDS[jd_name], rubric)
    assert rejected == [f"D{i}" for i in range(1, len(degenerate) + 1)]


def _unicode_variant():
    (name, v), = RUB["unicode_variants"].items()
    return name, v, (FIX / name).read_text(encoding="utf-8")


def test_plain_sketch_drops_ascii_quotes_against_a_pasted_jd():
    """The failure mode gate_norm fixes, pinned against the frozen sketch (not brain.rubric)."""
    _, v, text = _unicode_variant()
    for q in v["must_fail_under_plain_norm"]:
        assert VF.plain_norm(q) not in VF.plain_norm(text)
        assert VF.gate_norm(q) in VF.gate_norm(text)


def test_gate_grounds_ascii_quotes_in_the_unicode_jd():
    _, v, text = _unicode_variant()
    quotes = v["ascii_quotes_must_still_ground"]
    rubric = {
        "role_title": RUB["shared_title"], "seniority": "fresher",
        "behavioral_technical_mix": {"behavioral": 0.3, "technical": 0.7},
        "competencies": [
            {"id": f"U{i}", "name": f"unicode {i}", "type": "technical", "priority": "must_have",
             "jd_quotes": [{"text": q}], "evidence_expected": ["x"], "difficulty_ladder": list(VF.LADDER)}
            for i, q in enumerate(quotes, 1)
        ],
    }
    _, rejected = validate_rubric(text, rubric)
    assert rejected == []


# ---------------------------------------------------------------------------
# Stage C quote gate against the analysis oracle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ANSWERS)
def test_oracle_quote_substrings_match_the_transcript(key):
    a = ANA["answers"][key]
    words = words_for(script(key))
    duration = words[-1]["end"]
    quotes = list(a["quote_substrings"]) + list(a.get("hedges_quote_substrings", []))
    for part in a["star"].values():
        quotes += part.get("quote_substrings", [])
    for q in quotes:
        m = match_quote(q, words)
        assert m is not None, q
        assert m.score >= 90
        assert 0 <= m.t_start <= m.t_end <= duration


def test_overlapping_quotes_both_survive_the_gate():
    a = ANA["answers"]["vague"]
    q1, q2 = a["overlapping_quotes_both_valid"]
    words = words_for(script("vague"))
    m1, m2 = match_quote(q1, words), match_quote(q2, words)
    assert m1 and m2
    assert m1.word_start <= m2.word_start <= m1.word_end  # the spans really overlap
    analysis = {
        "answer_id": "A1",
        "star": {"action": {"present": True, "quote": q2, "t": [m2.t_start, m2.t_end], "ownership": "we"}},
        "hedges": [{"quote": q1, "t": [m1.t_start, m1.t_end]}],
    }
    result = validate_analysis(analysis, words, cheap_rules=False)
    assert result.dropped == []
    assert sorted(v.path for v in result.validated) == ["hedges[0]", "star.action"]
    (h,), (act,) = [v for v in result.validated if v.path == "hedges[0]"], [v for v in result.validated if v.path == "star.action"]
    assert h.t[0] < act.t[1] and act.t[0] < h.t[1]


@pytest.mark.parametrize("key, paraphrase", [
    ("vague", "we cached the responses to speed it up"),
    ("strong", "I introduced a caching layer in front of the database"),
    ("generic", "I am a dedicated engineer who writes good code"),
    ("team", "our team optimised the orders endpoint"),
])
def test_paraphrase_of_the_script_is_dropped(key, paraphrase):
    words = words_for(script(key))
    assert match_quote(paraphrase, words) is None
    result = validate_analysis({"answer_id": "A1", "hedges": [{"quote": paraphrase, "t": [0.0, 1.0]}]}, words, cheap_rules=False)
    assert result.validated == []
    assert [d.reason for d in result.dropped] == ["no_match"]
    assert result.analysis["hedges"] == []


@pytest.mark.parametrize("key", ANSWERS)
def test_ownership_stats_agree_with_the_hint(key):
    hint = ANA["answers"][key]["ownership_ratio_hint"]
    stats = ownership_stats(script(key))
    assert stats["i_count"] == hint["I"] and stats["we_count"] == hint["we"]
    assert abs((stats["we_ratio"] or 0.0) - hint["we_ratio"]) < 0.02
    assert stats["team_hiding"] is hint["team_hiding_flag"]


def test_result_rule_on_the_scripts():
    strong = ANA["answers"]["strong"]["star"]["result"]["quote_substrings"]
    assert all(has_outcome_evidence(q) for q in strong)
    # The answers whose oracle says result.present == false end without an outcome.
    assert not has_outcome_evidence("that was basically what we did")
    assert not has_outcome_evidence("we all worked on the bugs together before the demo")
    assert not has_outcome_evidence("always go the extra mile to deliver quality results")


# ---------------------------------------------------------------------------
# Agenda: swap the JD, the first target changes and stays provenance-linked
# ---------------------------------------------------------------------------


def test_swap_the_jd_changes_the_first_target_and_keeps_provenance():
    firsts = {}
    for jd_name in JD_NAMES:
        am = AgendaManager(rubric_from_hints(jd_name), "realistic")
        t = am.next_target()
        assert t is not None
        assert t["priority"] == "must_have"
        assert VF.gate_norm(t["jd_quote"]) in VF.gate_norm(JDS[jd_name])
        other = next(n for n in JD_NAMES if n != jd_name)
        assert VF.gate_norm(t["jd_quote"]) not in VF.gate_norm(JDS[other])
        firsts[jd_name] = t["jd_quote"]
    assert len(set(firsts.values())) == len(JD_NAMES)
