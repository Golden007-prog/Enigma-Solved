"""Stage A substring gate (BLUEPRINT §5.1)."""
import copy
import re

import pytest

from brain.rubric import find_quote_offsets, needs_reask, norm, reask_hint, validate_rubric

JD = """Backend Developer (Node.js)

About the role:
We are looking for a fresher who will   Build and maintain RESTful services in Node.js,
optimise API latency for our payments product, and
work with   the   data team
on reporting pipelines.

Nice to have: exposure to Redis or Memcached."""


def comp(cid, *quotes, **extra):
    return {
        "id": cid, "name": f"competency {cid}", "type": "technical", "priority": "must_have",
        "jd_quotes": [{"text": q} for q in quotes],
        "evidence_expected": ["designed endpoints"], "difficulty_ladder": ["recall"], **extra,
    }


def rubric(*comps):
    return {
        "role_title": "Backend Developer (Node.js)", "seniority": "fresher",
        "behavioral_technical_mix": {"behavioral": 0.4, "technical": 0.6},
        "competencies": list(comps),
    }


def reference_validate_rubric(jd, rubric):
    """The blueprint's §5.1 sketch, verbatim, as the oracle for gate decisions."""
    norm_ = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    jd_n, rejected = norm_(jd), []
    for c in list(rubric["competencies"]):
        ok = [q for q in c["jd_quotes"] if norm_(q["text"]) in jd_n]
        if not ok:
            rejected.append(c["id"]); rubric["competencies"].remove(c)
        else:
            c["jd_quotes"] = ok
    return rubric, rejected


def test_literal_quote_accepted_with_exact_offsets():
    quote = "Build and maintain RESTful services in Node.js"
    out, rejected = validate_rubric(JD, rubric(comp("C1", quote)))
    assert rejected == []
    q = out["competencies"][0]["jd_quotes"][0]
    assert q["start"] == JD.index(quote)
    assert q["end"] == JD.index(quote) + len(quote)
    assert JD[q["start"]:q["end"]] == quote


def test_paraphrased_quote_rejected_and_competency_removed():
    out, rejected = validate_rubric(JD, rubric(comp("C1", "Maintain REST APIs using Node")))
    assert rejected == ["C1"]
    assert out["competencies"] == []


def test_whitespace_and_case_normalised_quote_accepted():
    quote = "build   and maintain\nrestful services in NODE.JS"
    out, rejected = validate_rubric(JD, rubric(comp("C1", quote)))
    assert rejected == []
    q = out["competencies"][0]["jd_quotes"][0]
    assert JD[q["start"]:q["end"]] == "Build and maintain RESTful services in Node.js"
    assert norm(JD[q["start"]:q["end"]]) == norm(quote)


def test_offsets_span_the_jd_own_whitespace_runs():
    out, _ = validate_rubric(JD, rubric(comp("C2", "work with the data team")))
    q = out["competencies"][0]["jd_quotes"][0]
    assert JD[q["start"]:q["end"]] == "work with   the   data team"


def test_offsets_across_a_line_break_in_the_jd():
    quote = "optimise API latency for our payments product, and work with"
    out, rejected = validate_rubric(JD, rubric(comp("C3", quote)))
    assert rejected == []
    q = out["competencies"][0]["jd_quotes"][0]
    assert "\n" in JD[q["start"]:q["end"]]
    assert norm(JD[q["start"]:q["end"]]) == norm(quote)


def test_mixed_quotes_keep_only_grounded_ones():
    out, rejected = validate_rubric(
        JD, rubric(comp("C1", "Redis-based caching experience", "exposure to Redis or Memcached"))
    )
    assert rejected == []
    quotes = out["competencies"][0]["jd_quotes"]
    assert [q["text"] for q in quotes] == ["exposure to Redis or Memcached"]
    assert JD[quotes[0]["start"]:quotes[0]["end"]] == "exposure to Redis or Memcached"


def test_empty_or_blank_quote_is_rejected():
    out, rejected = validate_rubric(JD, rubric(comp("C1", ""), comp("C2", "   \n ")))
    assert rejected == ["C1", "C2"]
    assert out["competencies"] == []


def test_rejected_ids_preserve_order_and_survivors_keep_position():
    out, rejected = validate_rubric(JD, rubric(
        comp("C1", "nonsense one"),
        comp("C2", "optimise API latency"),
        comp("C3", "nonsense three"),
        comp("C4", "on reporting pipelines"),
    ))
    assert rejected == ["C1", "C3"]
    assert [c["id"] for c in out["competencies"]] == ["C2", "C4"]


def test_rubric_is_mutated_in_place_and_returned():
    r = rubric(comp("C1", "optimise API latency"), comp("C2", "made up"))
    out, _ = validate_rubric(JD, r)
    assert out is r
    assert [c["id"] for c in r["competencies"]] == ["C1"]


def test_matches_blueprint_reference_decisions():
    r = rubric(
        comp("C1", "Build and maintain RESTful services in Node.js", "invented sentence"),
        comp("C2", "  OPTIMISE api   latency "),
        comp("C3", "handles Kafka streams"),
        comp("C4", "Nice to have: exposure to Redis or Memcached."),
    )
    ours, ours_rejected = validate_rubric(JD, copy.deepcopy(r))
    ref, ref_rejected = reference_validate_rubric(JD, copy.deepcopy(r))
    assert ours_rejected == ref_rejected
    assert [[q["text"] for q in c["jd_quotes"]] for c in ours["competencies"]] == \
        [[q["text"] for q in c["jd_quotes"]] for c in ref["competencies"]]


def test_find_quote_offsets_helper():
    assert find_quote_offsets(JD, "not in the jd") is None
    assert find_quote_offsets(JD, "") is None
    start, end = find_quote_offsets(JD, "backend developer (node.js)")
    assert (start, end) == (0, len("Backend Developer (Node.js)"))


def test_offsets_survive_lowercase_expansion():
    jd = "Team based in İstanbul office, hybrid."
    quote = "in İstanbul office"  # three words: clears MIN_QUOTE_WORDS, keeps the expanding 'İ'
    out, rejected = validate_rubric(jd, rubric(comp("C1", quote)))
    assert rejected == []
    q = out["competencies"][0]["jd_quotes"][0]
    assert jd[q["start"]:q["end"]] == quote
    # A quote that only matches after the dotted-I expands is not a literal substring.
    _, rejected = validate_rubric(jd, rubric(comp("C2", "istanbul office")))
    assert rejected == ["C2"]


@pytest.mark.parametrize("rejected, threshold, expected", [
    ([], 2, False),
    (["C1", "C2"], 2, False),
    (["C1", "C2", "C3"], 2, True),
    (3, 2, True),
    (["C1"], 0, True),
])
def test_needs_reask_threshold(rejected, threshold, expected):
    assert needs_reask(rejected, threshold) is expected


def test_needs_reask_default_threshold_is_more_than_two():
    assert needs_reask(["C1", "C2"]) is False
    assert needs_reask(["C1", "C2", "C3"]) is True


def test_reask_hint_lists_the_rejected_names():
    hint = reask_hint(["Kafka streaming", "Kubernetes ops"])
    assert "Kafka streaming, Kubernetes ops" in hint
    assert "quote the JD literally" in hint
