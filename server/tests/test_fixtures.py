"""The fixture self-check must hold: expected/*.json agree with the JDs and scripts they describe."""
from __future__ import annotations

import importlib.util
import pathlib

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def _verify_module():
    spec = importlib.util.spec_from_file_location("verify_fixtures", FIXTURES / "verify_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_fixtures_are_self_consistent():
    failures = _verify_module().run(FIXTURES, verbose=False)
    assert failures == [], "\n".join(failures)


def test_gate_norm_folds_pasted_punctuation():
    vf = _verify_module()
    assert vf.gate_norm("0–2 years") == vf.gate_norm("0-2 years") == "0-2 years"
    assert vf.gate_norm("We’re on‑call") == "we're on-call"
    assert vf.gate_norm("“quoted”") == '"quoted"'
    assert vf.gate_norm("150 milliseconds") == "150 milliseconds"
    # The plain sketch does not fold any of these; that is the whole point of gate_norm.
    assert vf.plain_norm("0–2 years") != vf.plain_norm("0-2 years")


def test_spoken_word_count_rule():
    vf = _verify_module()
    assert vf.spoken_word_count("API") == 3
    assert vf.spoken_word_count("900 milliseconds") == 3  # nine hundred milliseconds
    assert vf.spoken_word_count("140") == 3  # one hundred forty
    assert vf.spoken_word_count("p95 latency") == 4  # p ninety five latency
    assert vf.spoken_word_count("30-second TTL") == 5  # thirty second T T L
    assert vf.spoken_word_count("I profiled the endpoint.") == 4
