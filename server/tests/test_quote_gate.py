"""Stage C quote gate (BLUEPRINT §5.3) and Stage D report gate (§5.5)."""
import copy
import json

import pytest

from brain.quotegate import (
    GateResult, ValidatedQuote, has_outcome_evidence, match_quote, ownership_stats, validate_analysis,
)
from brain.report_gate import filter_report

# Word i starts at i*0.5 s and ends at i*0.5+0.4 s; punctuation stays attached as STT emits it.
SENTENCE = ("So in my final-year project, I think maybe we used caching and stuff "
            "to make the API faster and it worked fine.")


def words_of(sentence, step=0.5, dur=0.4, offset=0.0):
    return [{"word": w, "start": round(offset + i * step, 3), "end": round(offset + i * step + dur, 3)}
            for i, w in enumerate(sentence.split())]


WORDS = words_of(SENTENCE)
# indices: 8..12 = "we used caching and stuff" -> 4.0..6.4 ; 5..7 = "I think maybe" -> 2.5..3.9
# 1..4 = "in my final-year project," -> 0.5..2.4 ; 19..21 = "it worked fine." -> 9.5..10.9
ACTION = {"present": True, "quote": "we used caching and stuff", "t": [4.0, 6.4], "ownership": "we"}


def analysis(**overrides):
    base = {
        "answer_id": "A3",
        "star": {
            "situation": {"present": True, "quote": "in my final-year project", "t": [0.5, 2.4]},
            "task": {"present": False},
            "action": copy.deepcopy(ACTION),
            "result": {"present": False},
        },
        "specificity": {"score": 1, "scale": "0-3", "missing": ["named technology", "number"]},
        "jd_keyword_coverage": {"hit": ["caching"], "missed": ["latency", "TTL", "Redis"]},
        "hedges": [{"quote": "I think maybe", "t": [2.5, 3.9]}],
        "contradictions": [],
        "verdict": "vague",
        "evidence_updates": {"C3": {"measured latency": "none"}},
        "next_strategy": "dig_deeper_vague",
        "reaction": "neutral",
    }
    base.update(overrides)
    return base


def question(trigger_quote="we used caching and stuff"):
    return {
        "question_id": "Q4",
        "text": "You mentioned caching. What exactly did you cache, and how did you decide the TTL?",
        "why": {
            "competency_id": "C3", "jd_quote": "optimise API latency", "ladder_rung": "trade-off or failure",
            "strategy": "dig_deeper_vague",
            "triggered_by": {"answer_id": "A3", "quote": trigger_quote, "t": [4.0, 6.4]},
        },
        "time_limit_s": 90,
        "reaction_before": "interested",
    }


def by_path(items, path):
    return next(d for d in items if d.path == path)


def paths(items):
    return {d.path for d in items}


# --- matching ---------------------------------------------------------------------------

def test_span_match_yields_word_indices_and_timestamps():
    m = match_quote("we used caching and stuff", WORDS)
    assert m is not None and m.score >= 90
    assert (m.word_start, m.word_end) == (8, 12)
    assert (m.t_start, m.t_end) == (4.0, 6.4)
    assert m.text == "we used caching and stuff"


def test_match_ignores_stt_punctuation_and_hyphens():
    m = match_quote("in my final year project", WORDS)
    assert m is not None and (m.word_start, m.word_end) == (1, 4)
    assert (m.t_start, m.t_end) == (0.5, 2.4)


def test_small_transcription_differences_still_match_the_right_words():
    m = match_quote("we used cacheing and stuf", WORDS)
    assert m is not None and m.score >= 90
    assert (m.word_start, m.word_end) == (8, 12)


def test_paraphrase_does_not_match():
    assert match_quote("we cached things", WORDS) is None
    best = match_quote("we cached things", WORDS, min_ratio=None)
    assert best is not None and best.score < 90


def test_quote_longer_than_transcript_is_not_spuriously_accepted():
    tiny = words_of("yes it did")
    assert match_quote("yes it did and I single-handedly rebuilt the entire platform", tiny) is None


def test_empty_transcript_matches_nothing():
    assert match_quote("anything", []) is None


# --- validate_analysis -------------------------------------------------------------------

def test_validated_quotes_are_untouched_and_recorded_with_spans():
    res = validate_analysis(analysis(), WORDS)
    assert isinstance(res, GateResult) and res.dropped == []
    out = res.analysis
    assert out["star"]["action"]["quote"] == "we used caching and stuff"
    assert out["star"]["action"]["t"] == [4.0, 6.4]
    v = by_path(res.validated, "star.action")
    assert isinstance(v, ValidatedQuote)
    assert (v.answer_id, v.word_start, v.word_end, v.span_t) == ("A3", 8, 12, (4.0, 6.4))
    assert paths(res.validated) == {"star.situation", "star.action", "hedges[0]"}
    assert v.key == ("A3", "we used caching and stuff")


def test_result_unpacks_as_a_tuple_too():
    out, validated, dropped, ownership = validate_analysis(analysis(), WORDS)
    assert out["answer_id"] == "A3" and len(validated) == 3 and dropped == []
    assert ownership["we_count"] == 1


def test_mismatched_t_nulls_the_field_not_the_object():
    a = analysis()
    a["star"]["action"]["t"] = [30.0, 32.0]
    res = validate_analysis(a, WORDS)
    action = res.analysis["star"]["action"]
    assert action["quote"] is None and action["t"] is None
    assert action["present"] is True  # the object survives, only the evidence is gone
    assert "star.action" not in paths(res.validated)
    d = by_path(res.dropped, "star.action")
    assert d.reason == "t_outside" and d.quote == "we used caching and stuff" and d.t == [30.0, 32.0]
    assert d.score is not None and d.score >= 90


@pytest.mark.parametrize("t, ok", [
    ([4.0, 6.4], True),
    ([3.8, 6.6], True),    # 0.2 s outside both ends: within the 0.25 s tolerance
    ([3.7, 6.4], False),   # 0.3 s early
    ([4.0, 6.7], False),   # 0.3 s late
    ([4.5, 5.5], True),    # strictly inside
])
def test_timestamp_containment_with_tolerance(t, ok):
    a = analysis()
    a["star"]["action"]["t"] = t
    res = validate_analysis(a, WORDS)
    assert ("star.action" in paths(res.validated)) is ok
    assert (res.analysis["star"]["action"]["quote"] is not None) is ok


def test_paraphrased_quote_is_dropped_as_no_match():
    a = analysis()
    a["star"]["action"]["quote"] = "we cached things"
    res = validate_analysis(a, WORDS)
    assert res.analysis["star"]["action"]["quote"] is None
    d = by_path(res.dropped, "star.action")
    assert d.reason == "no_match" and d.score < 90


def test_failed_hedges_are_removed_from_the_list():
    a = analysis(hedges=[
        {"quote": "I think maybe", "t": [2.5, 3.9]},
        {"quote": "perhaps sort of", "t": [2.5, 3.9]},      # never said
        {"quote": "I think maybe", "t": [50.0, 51.0]},      # said, wrong time
    ])
    res = validate_analysis(a, WORDS)
    assert res.analysis["hedges"] == [{"quote": "I think maybe", "t": [2.5, 3.9]}]
    assert {d.path: d.reason for d in res.dropped} == {"hedges[1]": "no_match", "hedges[2]": "t_outside"}


def test_missing_t_is_dropped_unless_fill_requested():
    a = analysis()
    del a["star"]["action"]["t"]
    res = validate_analysis(a, WORDS)
    assert res.analysis["star"]["action"]["quote"] is None
    assert by_path(res.dropped, "star.action").reason == "missing_t"

    res = validate_analysis(a, WORDS, fill_missing_t=True)
    assert res.dropped == []
    assert res.analysis["star"]["action"]["t"] == [4.0, 6.4]


def test_malformed_t_is_dropped_as_bad_t():
    a = analysis()
    a["star"]["action"]["t"] = [6.4, 4.0]
    res = validate_analysis(a, WORDS)
    assert by_path(res.dropped, "star.action").reason == "bad_t"


def test_result_rule_rejects_an_outcome_without_number_or_outcome_verb():
    a = analysis()
    a["star"]["result"] = {"present": True, "quote": "it worked fine", "t": [9.5, 10.9]}
    res = validate_analysis(a, WORDS)
    result = res.analysis["star"]["result"]
    assert result["present"] is False and result["quote"] is None and result["t"] is None
    assert by_path(res.dropped, "star.result").reason == "result_no_outcome"
    assert "star.result" not in paths(res.validated)


def test_result_rule_accepts_numbers_and_outcome_verbs():
    words = words_of("After the change I reduced the p95 latency by 40 percent and the team shipped it.")
    a = analysis()
    a["star"]["action"] = {"present": False}
    a["star"]["result"] = {"present": True, "quote": "I reduced the p95 latency by 40 percent", "t": [1.5, 4.9]}
    res = validate_analysis(a, words)
    assert res.analysis["star"]["result"]["present"] is True
    assert "star.result" in paths(res.validated)
    assert not any(d.path == "star.result" for d in res.dropped)


def test_result_claim_with_no_quote_is_unsupported():
    a = analysis()
    a["star"]["result"] = {"present": True}
    res = validate_analysis(a, WORDS)
    assert res.analysis["star"]["result"]["present"] is False
    assert by_path(res.dropped, "star.result").reason == "result_no_outcome"


@pytest.mark.parametrize("text, expected", [
    ("it worked fine", False),
    ("everyone was happy with it", False),
    ("we reduced latency", True),
    ("latency went from 2 seconds to 200 ms", True),
    ("response time went down a lot", True),
    ("we got twice the throughput", True),
    ("I shipped it before the deadline", True),
])
def test_has_outcome_evidence(text, expected):
    assert has_outcome_evidence(text) is expected


def test_ownership_ratio_flags_team_hiding():
    we_words = words_of("we built it and we tested it and our team shipped it and we were happy")
    own = validate_analysis(analysis(), we_words).ownership
    assert own["we_count"] == 4 and own["i_count"] == 0  # we, we, our, we
    assert own["we_ratio"] == 1.0 and own["team_hiding"] is True

    i_words = words_of("I designed the schema, I wrote the migrations and my tests caught the bug we missed")
    own = validate_analysis(analysis(), i_words).ownership
    assert own["i_count"] == 3 and own["we_count"] == 1
    assert own["i_ratio"] == 0.75 and own["team_hiding"] is False


def test_ownership_stays_out_of_the_analysis_dict():
    res = validate_analysis(analysis(), WORDS)
    assert "ownership" not in res.analysis
    assert res.ownership == ownership_stats(" ".join(w["word"] for w in WORDS))


def test_action_ownership_label_comes_from_the_rule_not_the_llm():
    a = analysis()
    a["star"]["action"]["ownership"] = "I"  # the LLM's claim contradicts the quote's own pronoun
    res = validate_analysis(a, WORDS)
    assert res.analysis["star"]["action"]["ownership"] == "we"
    assert res.ownership["team_hiding"] is False  # whole answer: my, I / we -> mixed
    assert ownership_stats("we we we I")["team_hiding"] is True
    # No pronoun anywhere -> no label, which the schema allows (Ownership | None).
    res = validate_analysis(analysis(), words_of("the cache was warmed and the api got faster"))
    assert res.analysis["star"]["action"]["ownership"] is None


def test_triggered_by_in_a_question_why_trace_is_validated():
    res = validate_analysis(question(), WORDS)  # unlabelled words fall back to the trigger's answer
    assert res.dropped == [] and [v.path for v in res.validated] == ["why.triggered_by"]
    assert res.ownership is None  # cheap rules only apply to an answer analysis

    res = validate_analysis(question(), [], prior_words={"A3": WORDS})
    assert res.dropped == [] and res.validated[0].answer_id == "A3"

    res = validate_analysis(question("we cached lots of things"), WORDS)
    assert res.analysis["why"]["triggered_by"] is None  # a bare quote object is nulled at its parent
    assert res.analysis["why"]["strategy"] == "dig_deeper_vague"
    assert by_path(res.dropped, "why.triggered_by").reason == "no_match"


def test_quote_naming_an_unknown_answer_is_dropped():
    a = analysis(contradictions=[{
        "quote": "we used caching and stuff", "t": [4.0, 6.4],
        "conflicts_with": {"answer_id": "A1", "quote": "I never used caching", "t": [1.0, 2.0]},
        "why": "claims caching now, denied it earlier",
    }])
    res = validate_analysis(a, WORDS)
    assert res.analysis["contradictions"] == []
    assert by_path(res.dropped, "contradictions[0].conflicts_with").reason == "unknown_answer"


def test_contradiction_survives_only_when_both_sides_validate():
    a1 = words_of("Honestly I never used caching in that project at all", offset=100.0)
    item = {
        "quote": "we used caching and stuff", "t": [4.0, 6.4],
        "conflicts_with": {"answer_id": "A1", "quote": "I never used caching", "t": [100.5, 102.4]},
        "why": "claims caching now, denied it earlier",
    }
    res = validate_analysis(analysis(contradictions=[copy.deepcopy(item)]), WORDS, prior_words={"A1": a1})
    assert res.dropped == [] and len(res.analysis["contradictions"]) == 1
    assert by_path(res.validated, "contradictions[0].conflicts_with").answer_id == "A1"

    item["conflicts_with"]["quote"] = "I used caching everywhere"
    res = validate_analysis(analysis(contradictions=[item]), WORDS, prior_words={"A1": a1})
    assert res.analysis["contradictions"] == []
    assert by_path(res.dropped, "contradictions[0].conflicts_with").reason == "no_match"


def test_input_is_not_mutated_and_json_string_is_accepted():
    a = analysis()
    a["star"]["action"]["quote"] = "we cached things"
    snapshot = copy.deepcopy(a)
    validate_analysis(a, WORDS)
    assert a == snapshot
    res = validate_analysis(json.dumps(a), WORDS)
    assert res.analysis["star"]["action"]["quote"] is None and len(res.dropped) == 1


def test_gated_output_still_satisfies_the_strict_schemas():
    schemas = pytest.importorskip("brain.schemas")
    a = analysis(
        hedges=[{"quote": "I think maybe", "t": [2.5, 3.9]}, {"quote": "never said this", "t": [1.0, 2.0]}],
        contradictions=[{
            "quote": "we used caching and stuff", "t": [4.0, 6.4],
            "conflicts_with": {"answer_id": "A1", "quote": "unknown answer", "t": [1.0, 2.0]}, "why": "x",
        }],
    )
    a["star"]["action"]["quote"] = "we cached things"
    a["star"]["result"] = {"present": True, "quote": "it worked fine", "t": [9.5, 10.9]}
    res = validate_analysis(a, WORDS)
    assert len(res.dropped) == 4
    model = schemas.Analysis.model_validate(res.analysis)
    assert model.star.action.quote is None and model.star.result.present is False
    assert len(model.hedges) == 1 and model.contradictions == []

    res = validate_analysis(question("we cached lots of things"), WORDS)
    q = schemas.Question.model_validate(res.analysis)
    assert q.why.triggered_by is None
    res = validate_analysis(question(), WORDS)
    assert schemas.Question.model_validate(res.analysis).why.triggered_by.answer_id == "A3"


# --- report gate -------------------------------------------------------------------------

def test_report_filter_drops_unvalidated_top_fixes():
    validated = validate_analysis(analysis(), WORDS).validated
    report = {
        "top_fixes": [
            {"behaviour": "vague action", "answer_id": "A3", "quote": "We used caching and stuff.",
             "t": [4.0, 6.4], "rubric_line": "C3", "why_it_matters": "...", "stronger_version": "..."},
            {"behaviour": "invented", "answer_id": "A3", "quote": "we optimised the TTL carefully",
             "t": [4.0, 6.4]},
            {"behaviour": "wrong answer", "answer_id": "A1", "quote": "we used caching and stuff",
             "t": [4.0, 6.4]},
            {"behaviour": "no answer id", "quote": "we used caching and stuff", "t": [4.0, 6.4]},
        ],
        "overall_band": {"band": "borderline", "what_would_move_it": "quantify results"},
    }
    out, dropped = filter_report(report, validated)
    assert [b["behaviour"] for b in out["top_fixes"]] == ["vague action"]
    assert [(d.path, d.reason) for d in dropped] == [
        ("top_fixes[1]", "not_validated"), ("top_fixes[2]", "not_validated"), ("top_fixes[3]", "no_answer_id"),
    ]
    assert out["overall_band"] == report["overall_band"]
    assert len(report["top_fixes"]) == 4  # input untouched


def test_report_filter_keeps_per_question_entries_but_nulls_bad_quotes():
    validated = validate_analysis(analysis(), WORDS).validated
    report = {"per_question": [{
        "question_id": "Q3", "answer_id": "A3", "verdict": "vague",
        "star": {"action": {"present": True, "quote": "we used caching and stuff", "t": [4.0, 6.4]},
                 "result": {"present": False}},
        "key_quote": {"quote": "we used caching and stuff, mostly Redis", "t": [4.0, 6.4]},
        "bullets": [{"quote": "I think maybe", "t": [2.5, 3.9]}, {"quote": "never said this"}],
    }]}
    out, dropped = filter_report(report, validated)
    entry = out["per_question"][0]
    assert entry["verdict"] == "vague"
    assert entry["star"]["action"]["quote"] == "we used caching and stuff"
    assert entry["key_quote"] is None  # a bare quote object is nulled at its parent
    assert entry["bullets"] == [{"quote": "I think maybe", "t": [2.5, 3.9]}]
    assert {d.path for d in dropped} == {"per_question[0].key_quote", "per_question[0].bullets[1]"}


def test_report_filter_fills_missing_t_and_maps_question_ids():
    validated = validate_analysis(analysis(), WORDS).validated
    report = {
        "top_fixes": [{"answer_id": "A3", "quote": "we used caching and stuff"}],
        "per_question": [{"question_id": "Q3", "key_quote": {"quote": "I think maybe"}}],
    }
    out, dropped = filter_report(report, validated, answer_ids={"Q3": "A3"})
    assert dropped == []
    assert out["top_fixes"][0]["t"] == [4.0, 6.4]
    assert out["per_question"][0]["key_quote"]["t"] == [2.5, 3.9]


def test_report_filter_accepts_plain_pairs_and_optional_fuzzy_matching():
    report = {"top_fixes": [{"answer_id": "A3", "quote": "used caching and stuff"}]}
    out, dropped = filter_report(report, [("A3", "we used caching and stuff")])
    assert out["top_fixes"] == [] and dropped[0].reason == "not_validated"
    out, dropped = filter_report(report, [("A3", "we used caching and stuff")], min_ratio=85)
    assert len(out["top_fixes"]) == 1 and dropped == []


def test_filtered_report_entries_satisfy_the_strict_schemas():
    schemas = pytest.importorskip("brain.schemas")
    validated = validate_analysis(analysis(), WORDS).validated
    report = {
        "top_fixes": [
            {"behaviour": "vague action", "answer_id": "A3", "quote": "we used caching and stuff",
             "t": [4.0, 6.4], "rubric_line": "C3: measured latency", "why_it_matters": "w", "stronger_version": "s"},
            {"behaviour": "invented", "answer_id": "A3", "quote": "we tuned the TTL", "t": [4.0, 6.4],
             "rubric_line": "C3: measured latency", "why_it_matters": "w", "stronger_version": "s"},
        ],
        "per_question": [{
            "question_id": "Q3", "answer_id": "A3", "verdict": "vague",
            "star": {"situation": True, "task": False, "action": True, "result": False},
            "key_quote": {"quote": "we tuned the TTL", "t": [4.0, 6.4]},
        }],
    }
    out, dropped = filter_report(report, validated)
    assert [d.path for d in dropped] == ["top_fixes[1]", "per_question[0].key_quote"]
    assert [schemas.TopFix.model_validate(b).quote for b in out["top_fixes"]] == ["we used caching and stuff"]
    assert schemas.PerQuestion.model_validate(out["per_question"][0]).key_quote is None
