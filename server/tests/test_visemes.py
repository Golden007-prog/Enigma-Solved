"""Tests for audio/visemes.py (§6.2 Kokoro token track, §6.3 RMS fallback) using
fake token objects that mimic Kokoro's MToken (.phonemes, .start_ts, .end_ts)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from audio import visemes as V


@dataclass
class Tok:
    text: str
    phonemes: str | None
    start_ts: float | None
    end_ts: float | None


def _ids(events):
    return [e["id"] for e in events]


def _times(events):
    return [e["t_ms"] for e in events]


def _assert_track_invariants(events, *, max_gap=V.MAX_GAP_MS):
    assert events, "track must not be empty"
    times = _times(events)
    assert times == sorted(times), "events must be time-ordered"
    assert len(set(times)) == len(times), "no two events at the same t_ms"
    assert all(0 <= e["id"] <= 9 for e in events)
    assert V.max_gap_ms(events) <= max_gap
    assert events[-1]["id"] == V.MOUTH_REST, "track must end on a closed mouth"


# ---------------------------------------------------------------------------
# phoneme → mouth map
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "phoneme,mouth",
    [
        ("m", 1), ("b", 1), ("p", 1),
        ("f", 2), ("v", 2),
        ("θ", 3), ("ð", 3),
        ("l", 4),
        ("t", 5), ("d", 5), ("n", 5), ("s", 5), ("z", 5), ("ʃ", 5), ("ʒ", 5), ("ʧ", 5), ("ʤ", 5),
        ("ɹ", 6), ("r", 6),
        ("ɑ", 7), ("a", 7), ("æ", 7), ("ʌ", 7),
        ("i", 8), ("ɪ", 8), ("e", 8), ("ɛ", 8),
        ("o", 9), ("ʊ", 9), ("u", 9), ("ɔ", 9),
    ],
)
def test_spec_groups_from_section_6_1(phoneme, mouth):
    assert V.mouths_for_phoneme(phoneme) == (mouth,)


@pytest.mark.parametrize("mark", ["ˈ", "ˌ", "ː", "ˑ", " ", ".", ","])
def test_stress_length_and_punctuation_produce_no_mouth(mark):
    assert V.mouths_for_phoneme(mark) == ()


def test_stress_marks_are_alpha_yet_dropped():
    """Regression for the §6.2 sketch: ˈ is category Lm, so isalpha() is True."""
    assert "ˈ".isalpha()
    assert V.mouths_for_phoneme("ˈ") == ()


def test_small_schwa_is_a_vowel_not_a_mark():
    assert V.mouths_for_phoneme("ᵊ") == (V.MOUTH_AH,)


def test_unknown_letters_fall_back_like_the_sketch():
    assert V.mouths_for_phoneme("x") == (V.MOUTH_TEETH,)  # unknown consonant → teeth
    assert V.mouths_for_phoneme("ɶ") == (V.MOUTH_TEETH,)  # unknown IPA vowel not in fallback set
    assert V.mouths_for_phoneme("a") == (V.MOUTH_AH,)


def test_diphthongs_expand_to_two_mouths():
    assert V.mouths_for_phoneme("I") == (V.MOUTH_AH, V.MOUTH_EE)  # aɪ
    assert V.mouths_for_phoneme("W") == (V.MOUTH_AH, V.MOUTH_OH)  # aʊ
    assert V.mouths_for_phoneme("O") == (V.MOUTH_OH,)


# ---------------------------------------------------------------------------
# visemes_from_tokens
# ---------------------------------------------------------------------------


def test_single_token_even_split_and_trailing_rest():
    # "map": m a p over 0.0–0.3 s → 3 phonemes at 0, 100, 200 ms, rest at 300 ms
    events = V.visemes_from_tokens([Tok("map", "mæp", 0.0, 0.3)])
    _assert_track_invariants(events)
    key = [(e["t_ms"], e["id"]) for e in events if e["t_ms"] in (0, 100, 200, 300)]
    assert key == [(0, 1), (100, 7), (200, 1), (300, 0)]
    assert events[-1] == {"t_ms": 300, "id": 0}


def test_rate_guarantee_inserts_holds_for_long_phonemes():
    # one 1-second token with two phonemes: without holds the gaps would be 500 ms
    events = V.visemes_from_tokens([Tok("oo", "uː", 0.0, 1.0)])
    _assert_track_invariants(events)
    assert V.max_gap_ms(events) <= 40
    # hold events repeat the previous mouth, they do not invent shapes
    held = [e["id"] for e in events if 0 < e["t_ms"] < 1000]
    assert set(held) == {V.MOUTH_OH}
    # 1 s of track needs at least 25 events
    assert len(events) >= 25


def test_events_per_second_at_least_25_over_a_sentence():
    toks = [
        Tok("Tell", "tˈɛl", 0.00, 0.30),
        Tok("me", "mi", 0.30, 0.45),
        Tok("about", "əbˈWt", 0.45, 0.90),
        Tok("yourself", "jɔɹsˈɛlf", 0.90, 1.60),
        Tok(".", None, None, None),
    ]
    events = V.visemes_from_tokens(toks)
    _assert_track_invariants(events)
    duration_s = (events[-1]["t_ms"] - events[0]["t_ms"]) / 1000
    assert len(events) / duration_s >= V.EVENTS_PER_SECOND_MIN


def test_untimed_and_empty_phoneme_tokens_are_skipped():
    events = V.visemes_from_tokens(
        [
            Tok(",", None, None, None),
            Tok("", "", 0.0, 0.1),
            Tok("hi", "hˈI", 0.0, 0.2),
            SimpleNamespace(text="?", phonemes=None, start_ts=0.2, end_ts=0.2),
        ]
    )
    _assert_track_invariants(events)
    assert events[0]["t_ms"] == 0 and events[-1] == {"t_ms": 200, "id": 0}


def test_no_timed_tokens_gives_empty_track():
    assert V.visemes_from_tokens([]) == []
    assert V.visemes_from_tokens([Tok(".", None, None, None)]) == []
    assert V.visemes_from_tokens([Tok("ˈ", "ˈ", 0.0, 0.1)]) == []  # only marks


def test_leading_silence_starts_closed_and_holds():
    events = V.visemes_from_tokens([Tok("so", "sˈO", 0.5, 0.7)])
    _assert_track_invariants(events)
    assert events[0] == {"t_ms": 0, "id": 0}
    assert all(e["id"] == 0 for e in events if e["t_ms"] < 500)
    assert any(e["t_ms"] == 500 and e["id"] == V.MOUTH_TEETH for e in events)


def test_adjacent_words_do_not_flicker_closed():
    # 10 ms between words: no rest inserted; the mouth holds the last shape
    events = V.visemes_from_tokens([Tok("a", "a", 0.0, 0.2), Tok("b", "b", 0.21, 0.4)])
    _assert_track_invariants(events)
    between = [e["id"] for e in events if 200 <= e["t_ms"] < 210]
    assert V.MOUTH_REST not in between


def test_real_pause_between_words_closes_the_mouth():
    events = V.visemes_from_tokens([Tok("a", "a", 0.0, 0.2), Tok("b", "b", 0.5, 0.7)])
    _assert_track_invariants(events)
    assert {"t_ms": 200, "id": 0} in events
    assert all(e["id"] == 0 for e in events if 200 <= e["t_ms"] < 500)


def test_coincident_rest_and_next_phoneme_keeps_the_phoneme():
    # token 1 ends exactly when token 2 starts, with rest_gap_ms=0 forcing a rest
    events = V.visemes_from_tokens([Tok("a", "a", 0.0, 0.2), Tok("s", "s", 0.2, 0.4)], rest_gap_ms=0)
    at_200 = [e for e in events if e["t_ms"] == 200]
    assert at_200 == [{"t_ms": 200, "id": V.MOUTH_TEETH}]


def test_offset_shifts_whole_track_for_chunked_synthesis():
    base = V.visemes_from_tokens([Tok("hi", "hˈI", 0.0, 0.2)])
    shifted = V.visemes_from_tokens([Tok("hi", "hˈI", 0.0, 0.2)], offset_ms=1500)
    assert _ids(base) == _ids(shifted)
    assert [t + 1500 for t in _times(base)] == _times(shifted)
    assert shifted[0]["t_ms"] == 1500


def test_total_ms_extends_rest_to_end_of_audio():
    events = V.visemes_from_tokens([Tok("hi", "hˈI", 0.0, 0.2)], total_ms=600)
    _assert_track_invariants(events)
    assert events[-1] == {"t_ms": 600, "id": 0}
    assert all(e["id"] == 0 for e in events if e["t_ms"] >= 200)


def test_diphthong_splits_its_slot():
    # "I" (aɪ) alone over 200 ms → Ah at 0, Ee at 100, rest at 200
    events = V.visemes_from_tokens([Tok("I", "I", 0.0, 0.2)])
    key = [(e["t_ms"], e["id"]) for e in events if e["t_ms"] in (0, 100, 200)]
    assert key == [(0, V.MOUTH_AH), (100, V.MOUTH_EE), (200, V.MOUTH_REST)]


def test_stress_marks_do_not_consume_time():
    with_stress = V.visemes_from_tokens([Tok("map", "mˈæp", 0.0, 0.3)])
    without = V.visemes_from_tokens([Tok("map", "mæp", 0.0, 0.3)])
    assert with_stress == without


def test_reversed_timestamps_are_clamped_not_crashed():
    events = V.visemes_from_tokens([Tok("a", "a", 0.3, 0.1)])
    _assert_track_invariants(events)
    assert events[-1]["t_ms"] == 300


def test_custom_max_gap():
    events = V.visemes_from_tokens([Tok("oo", "u", 0.0, 1.0)], max_gap_ms=20)
    assert V.max_gap_ms(events) <= 20
    with pytest.raises(ValueError):
        V.visemes_from_tokens([Tok("oo", "u", 0.0, 1.0)], max_gap_ms=0)


def test_events_are_wire_ready_dicts():
    for e in V.visemes_from_tokens([Tok("hi", "hˈI", 0.0, 0.2)]):
        assert set(e) == {"t_ms", "id"}
        assert isinstance(e["t_ms"], int) and isinstance(e["id"], int)


def test_max_gap_helper():
    assert V.max_gap_ms([]) == 0
    assert V.max_gap_ms([{"t_ms": 0, "id": 0}]) == 0
    assert V.max_gap_ms([{"t_ms": 0, "id": 0}, {"t_ms": 40, "id": 1}, {"t_ms": 130, "id": 0}]) == 90


# ---------------------------------------------------------------------------
# rms_mouth_events (§6.3)
# ---------------------------------------------------------------------------

np = pytest.importorskip("numpy")

SR = 24000


def _pcm(samples):
    return (np.clip(np.asarray(samples, dtype=np.float64), -1, 1) * 32767).astype("<i2").tobytes()


def _sine(seconds, amp=0.5, freq=220.0):
    t = np.arange(int(SR * seconds)) / SR
    return amp * np.sin(2 * math.pi * freq * t)


def test_rms_silence_is_closed():
    events = V.rms_mouth_events(_pcm(np.zeros(SR // 2)), SR)  # 0.5 s
    assert events and all(e["open"] == 0.0 for e in events)
    assert events[-1] == {"t_ms": 500, "open": 0.0}


def test_rms_window_count_and_spacing():
    events = V.rms_mouth_events(_pcm(_sine(1.0)), SR, window_ms=40)
    # 25 windows of 40 ms + final closing event at 1000 ms
    assert len(events) == 26
    assert _times(events) == [i * 40 for i in range(25)] + [1000]
    assert events[-1]["open"] == 0.0


def test_rms_partial_last_window_counted():
    n = SR // 10 + 7  # 100 ms and a bit
    events = V.rms_mouth_events(_pcm(_sine(n / SR)), SR, window_ms=40)
    assert len(events) == math.ceil(n / (SR * 40 // 1000)) + 1
    assert events[-1]["t_ms"] == math.ceil(n * 1000 / SR)


def test_rms_loud_then_quiet():
    loud = _sine(0.2, amp=0.8)
    quiet = _sine(0.2, amp=0.05)
    events = V.rms_mouth_events(_pcm(np.concatenate([loud, quiet])), SR)
    first, second = events[:5], events[5:10]
    assert all(e["open"] >= 0.9 for e in first)
    assert all(e["open"] < 0.15 for e in second)


def test_rms_values_in_unit_range_and_loudest_reaches_one():
    events = V.rms_mouth_events(_pcm(_sine(0.5, amp=0.3)), SR)
    assert all(0.0 <= e["open"] <= 1.0 for e in events)
    assert max(e["open"] for e in events) == 1.0


def test_rms_reference_scales_chunks_consistently():
    chunk = _pcm(_sine(0.2, amp=0.25))
    own = V.rms_mouth_events(chunk, SR)
    scaled = V.rms_mouth_events(chunk, SR, ref_rms=1.0)  # far louder reference
    assert max(e["open"] for e in own) == 1.0
    assert max(e["open"] for e in scaled) < 0.3


def test_rms_offset_and_rate():
    events = V.rms_mouth_events(_pcm(_sine(0.3)), SR, offset_ms=2000)
    assert events[0]["t_ms"] == 2000
    assert V.max_gap_ms(events) <= V.MAX_GAP_MS


def test_rms_rejects_bad_input():
    assert V.rms_mouth_events(b"", SR) == []
    with pytest.raises(ValueError):
        V.rms_mouth_events(b"\x00", SR)  # odd byte count
    with pytest.raises(ValueError):
        V.rms_mouth_events(b"\x00\x00", 0)
    with pytest.raises(ValueError):
        V.rms_mouth_events(b"\x00\x00", SR, window_ms=0)
    with pytest.raises(ValueError):
        V.rms_mouth_events(b"\x00\x00", SR, gate=1.0)


def test_mouth_id_from_open_thresholds():
    assert V.mouth_id_from_open(0.0) == V.MOUTH_REST
    assert V.mouth_id_from_open(0.1) == V.MOUTH_REST
    assert V.mouth_id_from_open(0.3) == V.MOUTH_EE
    assert V.mouth_id_from_open(0.9) == V.MOUTH_AH
    assert V.mouth_id_from_open(1.0) == V.MOUTH_AH


def test_mouth_events_to_visemes_keeps_rate_and_ends_closed():
    events = V.rms_mouth_events(_pcm(_sine(0.4)), SR)
    vis = V.mouth_events_to_visemes(events)
    _assert_track_invariants(vis)
    assert _times(vis) == _times(events)
