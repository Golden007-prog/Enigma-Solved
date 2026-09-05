"""Tests for protocol.py: message shapes (§4.1), the TTS ordering contract and the
session state machine (§4.2)."""

from __future__ import annotations

import json
from collections import deque

import pytest
from pydantic import ValidationError

import protocol as P

# The exact hello from BLUEPRINT §4.1.
SPEC_HELLO = (
    '{"type":"hello","token":"<from QR>","mode":"interview",'
    '"in":{"fmt":"pcm16","sr":16000,"ch":1},"out":{"fmt":"pcm16","sr":24000}}'
)

SPEC_WHY = {
    "competency_id": "C3",
    "jd_quote": "optimise API latency",
    "ladder_rung": "trade-off or failure",
    "strategy": "dig_deeper_vague",
    "triggered_by": {"answer_id": "A3", "quote": "we used caching and stuff", "t": [8.2, 11.9]},
}


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------


def test_framing_constants_match_spec():
    assert P.FRAME_MS == 20
    assert P.IN_SR == 16000
    assert P.OUT_SR == 24000
    assert P.FRAME_BYTES == 640
    assert P.FRAME_BYTES == P.IN_SR * P.FRAME_MS // 1000 * P.SAMPLE_BYTES
    assert P.OUT_FRAME_BYTES == P.OUT_SR * P.FRAME_MS // 1000 * P.SAMPLE_BYTES == 960


# ---------------------------------------------------------------------------
# hello → ready
# ---------------------------------------------------------------------------


def test_hello_parses_spec_example():
    msg = P.parse_client_message(SPEC_HELLO)
    assert isinstance(msg, P.HelloMessage)
    assert msg.type == "hello"
    assert msg.token == "<from QR>"
    assert msg.mode == "interview"
    assert (msg.audio_in.fmt, msg.audio_in.sr, msg.audio_in.ch) == ("pcm16", 16000, 1)
    assert (msg.audio_out.fmt, msg.audio_out.sr) == ("pcm16", 24000)
    assert msg.pressure is P.Pressure.REALISTIC  # default dial
    assert msg.jd is None and msg.voice is None
    assert msg.needs_resample is False


def test_hello_defaults_when_audio_blocks_omitted():
    msg = P.parse_client_message('{"type":"hello","token":"abc"}')
    assert isinstance(msg, P.HelloMessage)
    assert msg.audio_in.sr == P.IN_SR and msg.audio_out.sr == P.OUT_SR


def test_hello_web_build_needs_resample():
    msg = P.parse_client_message(
        '{"type":"hello","token":"abc","in":{"fmt":"f32","sr":48000,"ch":1}}'
    )
    assert msg.needs_resample is True


def test_hello_carries_session_config():
    msg = P.parse_client_message(
        '{"type":"hello","token":"abc","jd":"Build REST APIs in Node.js","pressure":"tough","voice":"bm_george"}'
    )
    assert msg.pressure is P.Pressure.TOUGH
    assert msg.jd.startswith("Build") and msg.voice == "bm_george"


def test_hello_rejects_unknown_pressure():
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message('{"type":"hello","token":"abc","pressure":"brutal"}')
    assert ei.value.code is P.ErrorCode.BAD_MESSAGE


def test_ready_shape():
    ready = P.ReadyMessage(session="s-42")
    wire = json.loads(P.encode_server_message(ready))
    assert wire == {"type": "ready", "session": "s-42"}
    back = P.parse_server_message(P.encode_server_message(ready))
    assert isinstance(back, P.ReadyMessage) and back.session == "s-42"


def test_hello_to_ready_handshake():
    """What server.py does on the first frame: parse hello, check the token, answer ready."""
    expected_token = "<from QR>"
    hello = P.parse_client_message(SPEC_HELLO)
    assert isinstance(hello, P.HelloMessage)
    assert hello.token == expected_token
    reply = P.encode_server_message(P.ReadyMessage(session="sess-1"))
    assert json.loads(reply)["type"] == "ready"
    assert set(json.loads(reply)) == {"type", "session"}


def test_ready_requires_session():
    with pytest.raises(ValidationError):
        P.ReadyMessage(session="")


# ---------------------------------------------------------------------------
# bad token / bad frames
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        '{"type":"hello","token":""}',
        '{"type":"hello","token":"   "}',
        '{"type":"hello"}',
        '{"type":"hello","token":null}',
        '{"type":"hello","token":123}',
    ],
)
def test_bad_token_rejected(payload):
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message(payload)
    assert ei.value.code is P.ErrorCode.BAD_MESSAGE
    err = ei.value.to_error(fatal=True)
    assert err.type == "error" and err.fatal is True
    assert "token" in err.message


def test_hello_model_requires_non_empty_token():
    with pytest.raises(ValidationError):
        P.HelloMessage(token="")
    with pytest.raises(ValidationError):
        P.HelloMessage(token="  \n")
    assert P.HelloMessage(token="  x  ").token == "x"


def test_unknown_type_rejected():
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message('{"type":"teleport"}')
    assert ei.value.code is P.ErrorCode.UNKNOWN_TYPE


def test_missing_type_rejected():
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message('{"token":"abc"}')
    assert ei.value.code is P.ErrorCode.UNKNOWN_TYPE


def test_server_message_types_are_not_client_messages():
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message('{"type":"ready","session":"x"}')
    assert ei.value.code is P.ErrorCode.UNKNOWN_TYPE


@pytest.mark.parametrize("payload", ["not json", "", "[1,2,3]", '"hello"'])
def test_non_object_or_invalid_json_rejected(payload):
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message(payload)
    assert ei.value.code in (P.ErrorCode.BAD_JSON, P.ErrorCode.UNKNOWN_TYPE, P.ErrorCode.BAD_MESSAGE)


def test_invalid_json_is_bad_json():
    with pytest.raises(P.ProtocolError) as ei:
        P.parse_client_message("{nope")
    assert ei.value.code is P.ErrorCode.BAD_JSON


def test_bytes_text_frame_accepted_when_utf8():
    msg = P.parse_client_message(b'{"type":"ping","t":5}')
    assert isinstance(msg, P.PingMessage) and msg.t == 5


def test_client_extra_keys_ignored():
    msg = P.parse_client_message('{"type":"cancel","reason":"user tapped stop"}')
    assert isinstance(msg, P.CancelMessage)


# ---------------------------------------------------------------------------
# other client messages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["down", "up"])
def test_ptt_states(state):
    msg = P.parse_client_message(json.dumps({"type": "ptt", "state": state}))
    assert isinstance(msg, P.PttMessage) and msg.state == state


def test_ptt_rejects_other_states():
    with pytest.raises(P.ProtocolError):
        P.parse_client_message('{"type":"ptt","state":"sideways"}')


def test_ping_pong_echo():
    ping = P.parse_client_message('{"type":"ping","t":123456}')
    pong = P.PongMessage(t=ping.t)
    assert json.loads(P.encode_server_message(pong)) == {"type": "pong", "t": 123456}


def test_hello_encodes_with_wire_aliases():
    wire = json.loads(P.encode_client_message(P.HelloMessage(token="abc")))
    assert "in" in wire and "out" in wire
    assert "audio_in" not in wire and "audio_out" not in wire
    assert wire["in"] == {"fmt": "pcm16", "sr": 16000, "ch": 1}
    # and it round-trips through the parser
    assert P.parse_client_message(json.dumps(wire)).token == "abc"


# ---------------------------------------------------------------------------
# server messages
# ---------------------------------------------------------------------------


def test_question_with_why_trace_round_trips():
    q = P.QuestionMessage(
        id="Q4",
        text="You mentioned caching. What exactly did you cache, and how did you decide the TTL?",
        why=SPEC_WHY,
        time_limit_s=90,
    )
    wire = json.loads(P.encode_server_message(q))
    assert wire["type"] == "question" and wire["id"] == "Q4" and wire["time_limit_s"] == 90
    assert wire["why"]["triggered_by"]["t"] == [8.2, 11.9]
    back = P.parse_server_message(json.dumps(wire))
    assert isinstance(back, P.QuestionMessage)
    assert back.why.strategy == "dig_deeper_vague"
    assert back.why.triggered_by.t == (8.2, 11.9)


def test_question_without_timer_is_warmup():
    q = P.QuestionMessage(id="Q1", text="Tell me about yourself.", why={**SPEC_WHY, "triggered_by": None})
    assert q.time_limit_s is None
    assert json.loads(P.encode_server_message(q))["time_limit_s"] is None


def test_why_trace_rejects_unknown_strategy():
    with pytest.raises(ValidationError):
        P.WhyTrace(**{**SPEC_WHY, "strategy": "made_up"})


@pytest.mark.parametrize("t", [[11.9, 8.2], [-1.0, 2.0]])
def test_time_span_validated(t):
    with pytest.raises(ValidationError):
        P.TriggeredBy(answer_id="A1", quote="x", t=t)


@pytest.mark.parametrize("mouth", [0, 9])
def test_viseme_id_bounds_ok(mouth):
    assert P.VisemeMessage(t_ms=0, id=mouth).id == mouth


@pytest.mark.parametrize("mouth", [-1, 10])
def test_viseme_id_out_of_range(mouth):
    with pytest.raises(ValidationError):
        P.VisemeMessage(t_ms=0, id=mouth)


def test_viseme_negative_time_rejected():
    with pytest.raises(ValidationError):
        P.VisemeMessage(t_ms=-1, id=0)


def test_mouth_open_bounds():
    assert P.MouthMessage(t_ms=0, open=1.0).open == 1.0
    with pytest.raises(ValidationError):
        P.MouthMessage(t_ms=0, open=1.5)


@pytest.mark.parametrize("mood", ["neutral", "interested", "thinking", "unimpressed"])
def test_reaction_moods(mood):
    r = P.ReactionMessage(mood=mood, nod=True)
    assert json.loads(P.encode_server_message(r)) == {"type": "reaction", "mood": mood, "nod": True}
    assert P.MOOD_INDEX[mood] in range(4)


def test_reaction_rejects_unknown_mood():
    with pytest.raises(ValidationError):
        P.ReactionMessage(mood="furious")


def test_vad_states():
    for s in ("speech_start", "speech_end"):
        assert P.VadMessage(state=s).state == s
    with pytest.raises(ValidationError):
        P.VadMessage(state="speech_maybe")


def test_server_messages_forbid_extra_fields():
    with pytest.raises(ValidationError):
        P.VisemeMessage(t_ms=0, id=0, foo=1)


def test_encode_accepts_plain_dict():
    assert json.loads(P.encode_server_message({"type": "viseme", "t_ms": 10, "id": 3})) == {
        "type": "viseme",
        "t_ms": 10,
        "id": 3,
    }
    with pytest.raises(ValidationError):
        P.encode_server_message({"type": "viseme", "t_ms": 10, "id": 30})


def test_encode_viseme_track_from_bare_events():
    """Events from audio.visemes carry no "type"; the track encoder adds it."""
    frames = P.encode_viseme_track([{"t_ms": 0, "id": 7}, {"t_ms": 40, "id": 0}])
    assert [json.loads(f) for f in frames] == [
        {"type": "viseme", "t_ms": 0, "id": 7},
        {"type": "viseme", "t_ms": 40, "id": 0},
    ]
    mouth = P.encode_viseme_track([{"t_ms": 0, "open": 0.5}])
    assert json.loads(mouth[0]) == {"type": "mouth", "t_ms": 0, "open": 0.5}
    # every frame is a valid server message and each track obeys the TTS contract
    # (one span per track: a server never mixes an id track and an open track)
    for track in (frames, mouth):
        parsed = [P.parse_server_message(f) for f in track]
        assert P.check_tts_ordering([P.TtsStartMessage(), *parsed, P.TtsEndMessage()]) == 1
    with pytest.raises(ValidationError):
        P.encode_viseme_track([{"t_ms": 0, "id": 12}])
    with pytest.raises(ValueError):
        P.encode_viseme_track([{"t_ms": 0}])


def test_encode_server_message_dict_needs_type():
    with pytest.raises(ValidationError):
        P.encode_server_message({"t_ms": 0, "id": 7})


def test_tts_start_default_sr_and_bare_messages():
    assert json.loads(P.encode_server_message(P.TtsStartMessage())) == {"type": "tts_start", "sr": 24000}
    assert json.loads(P.encode_server_message(P.TtsEndMessage())) == {"type": "tts_end"}
    assert json.loads(P.encode_server_message(P.InterruptMessage())) == {"type": "interrupt"}


def test_error_and_report_messages():
    err = P.ErrorMessage(code=P.ErrorCode.BAD_TOKEN, message="token mismatch", fatal=True)
    assert json.loads(P.encode_server_message(err)) == {
        "type": "error",
        "code": "bad_token",
        "message": "token mismatch",
        "fatal": True,
    }
    rep = P.ReportMessage(url="http://192.168.137.1:8765/report/s1.json")
    assert P.parse_server_message(P.encode_server_message(rep)).url.endswith("s1.json")


def test_messages_are_frozen():
    v = P.VisemeMessage(t_ms=1, id=1)
    with pytest.raises(ValidationError):
        v.id = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ordering: tts_start before any viseme, tts_end after them
# ---------------------------------------------------------------------------


def _viseme(t, mouth=7):
    return P.VisemeMessage(t_ms=t, id=mouth)


PCM = bytes(P.OUT_FRAME_BYTES)


def test_ordering_valid_span():
    events = [
        P.ReactionMessage(mood="interested"),
        P.QuestionMessage(id="Q1", text="Hi", why={**SPEC_WHY, "triggered_by": None}),
        P.TtsStartMessage(),
        PCM,
        _viseme(0, 0),
        _viseme(40),
        PCM,
        _viseme(80, 5),
        PCM,
        _viseme(120, 0),
        P.TtsEndMessage(),
        P.VadMessage(state="speech_start"),
    ]
    assert P.check_tts_ordering(events) == 1


def test_ordering_two_spans():
    span = [P.TtsStartMessage(), PCM, _viseme(0), _viseme(40, 0), P.TtsEndMessage()]
    assert P.check_tts_ordering(span + [P.SttMessage(text="ok")] + span) == 2


def test_ordering_accepts_dict_events():
    events = [
        {"type": "tts_start", "sr": 24000},
        {"type": "viseme", "t_ms": 0, "id": 7},
        {"type": "viseme", "t_ms": 40, "id": 0},
        {"type": "tts_end"},
    ]
    assert P.check_tts_ordering(events) == 1


def test_ordering_viseme_before_tts_start_fails():
    with pytest.raises(P.OrderingError, match="before tts_start"):
        P.check_tts_ordering([_viseme(0), P.TtsStartMessage(), P.TtsEndMessage()])


def test_ordering_viseme_after_tts_end_fails():
    with pytest.raises(P.OrderingError, match="before tts_start"):
        P.check_tts_ordering([P.TtsStartMessage(), _viseme(0), P.TtsEndMessage(), _viseme(40)])


def test_ordering_audio_outside_span_fails():
    with pytest.raises(P.OrderingError, match="audio frame before tts_start"):
        P.check_tts_ordering([PCM, P.TtsStartMessage(), P.TtsEndMessage()])


def test_ordering_missing_tts_end_fails():
    with pytest.raises(P.OrderingError, match="no tts_end"):
        P.check_tts_ordering([P.TtsStartMessage(), _viseme(0)])


def test_ordering_nested_tts_start_fails():
    with pytest.raises(P.OrderingError, match="nested"):
        P.check_tts_ordering([P.TtsStartMessage(), P.TtsStartMessage(), P.TtsEndMessage()])


def test_ordering_tts_end_without_start_fails():
    with pytest.raises(P.OrderingError, match="without tts_start"):
        P.check_tts_ordering([P.TtsEndMessage()])


def test_ordering_viseme_time_must_not_go_backwards():
    with pytest.raises(P.OrderingError, match="backwards"):
        P.check_tts_ordering([P.TtsStartMessage(), _viseme(80), _viseme(40), P.TtsEndMessage()])


def test_ordering_interrupt_closes_span():
    # after barge-in the phone has flushed: a trailing tts_end is fine, more visemes are not
    assert P.check_tts_ordering([P.TtsStartMessage(), _viseme(0), P.InterruptMessage(), P.TtsEndMessage()]) == 1
    assert P.check_tts_ordering([P.TtsStartMessage(), _viseme(0), P.InterruptMessage()]) == 0
    with pytest.raises(P.OrderingError, match="after interrupt"):
        P.check_tts_ordering([P.TtsStartMessage(), _viseme(0), P.InterruptMessage(), _viseme(40)])


def test_ordering_rejects_unknown_event_objects():
    with pytest.raises(TypeError):
        P.check_tts_ordering([42])


# ---------------------------------------------------------------------------
# session state machine (§4.2)
# ---------------------------------------------------------------------------

S = P.SessionState


def _walk(fsm: P.SessionFSM, *path: P.SessionState) -> None:
    for target in path:
        assert fsm.can(target), f"{fsm.state} -> {target} should be allowed ({fsm.pressure})"
        fsm.advance(target)
        assert fsm.state is target


def test_happy_path_realistic():
    fsm = P.SessionFSM(pressure=P.Pressure.REALISTIC)
    assert fsm.state is S.LOBBY and not fsm.in_round
    _walk(fsm, S.PAIR, S.PREP, S.ASKING)
    assert fsm.in_round
    # two turns: ANALYSING ∥ PLANNING may finish in either order
    _walk(fsm, S.LISTENING, S.ANALYSING, S.PLANNING, S.ASKING)
    _walk(fsm, S.LISTENING, S.PLANNING, S.ANALYSING, S.ASKING)
    _walk(fsm, S.LISTENING, S.ANALYSING, S.WRAP, S.REPORT)
    assert not fsm.in_round
    assert fsm.history[0] is S.LOBBY and fsm.history[-1] is S.REPORT


def test_round_states_membership():
    assert P.ROUND_STATES == {S.ASKING, S.LISTENING, S.ANALYSING, S.PLANNING, S.INTERRUPT}
    for s in (S.LOBBY, S.PAIR, S.PREP, S.WRAP, S.REPORT):
        assert s not in P.ROUND_STATES


def test_every_state_has_a_transition_row_with_valid_targets():
    assert set(P.TRANSITIONS) == set(S)
    for src, targets in P.TRANSITIONS.items():
        assert src not in targets, f"{src} must not self-loop"
        assert all(isinstance(t, S) for t in targets)


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.LOBBY, S.PREP),  # cannot skip pairing
        (S.LOBBY, S.ASKING),
        (S.PAIR, S.ASKING),  # cannot skip Stage A
        (S.PREP, S.LISTENING),
        (S.ASKING, S.ANALYSING),  # must listen before analysing
        (S.ASKING, S.REPORT),
        (S.LISTENING, S.ASKING),  # no question without analysis/planning
        (S.ANALYSING, S.LISTENING),
        (S.WRAP, S.ASKING),
        (S.WRAP, S.LOBBY),
        (S.REPORT, S.PREP),
        (S.LOBBY, S.LOBBY),
    ],
)
def test_illegal_transitions(src, dst):
    for pressure in P.Pressure:
        assert not P.can_transition(src, dst, pressure=pressure)
        with pytest.raises(P.IllegalTransition) as ei:
            P.transition(src, dst, pressure=pressure)
        assert ei.value.current is src and ei.value.target is dst


def test_interrupt_only_in_tough():
    for src in (S.LISTENING, S.ASKING):
        assert P.can_transition(src, S.INTERRUPT, pressure=P.Pressure.TOUGH)
        assert not P.can_transition(src, S.INTERRUPT, pressure=P.Pressure.REALISTIC)
        assert not P.can_transition(src, S.INTERRUPT, pressure=P.Pressure.WARMUP)
        assert not P.can_transition(src, S.INTERRUPT)  # default dial is Realistic
    with pytest.raises(P.IllegalTransition):
        P.transition(S.LISTENING, S.INTERRUPT, pressure=P.Pressure.REALISTIC)


def test_interrupt_unreachable_from_outside_the_round_even_in_tough():
    for src in (S.LOBBY, S.PAIR, S.PREP, S.ANALYSING, S.PLANNING, S.WRAP, S.REPORT):
        assert not P.can_transition(src, S.INTERRUPT, pressure=P.Pressure.TOUGH)


def test_tough_cut_off_and_barge_in_paths():
    fsm = P.SessionFSM(pressure=P.Pressure.TOUGH)
    _walk(fsm, S.PAIR, S.PREP, S.ASKING)
    # interviewer: "let me stop you there" on time-out, then analyse what was said
    _walk(fsm, S.LISTENING, S.INTERRUPT, S.ANALYSING, S.ASKING)
    # candidate barges in on the question's TTS: stop TTS, listen
    _walk(fsm, S.INTERRUPT, S.LISTENING, S.PLANNING, S.ASKING)


def test_retry_weakest_question_from_report():
    fsm = P.SessionFSM(pressure=P.Pressure.WARMUP)
    _walk(fsm, S.PAIR, S.PREP, S.ASKING, S.LISTENING, S.ANALYSING, S.WRAP, S.REPORT)
    _walk(fsm, S.ASKING, S.LISTENING, S.ANALYSING, S.WRAP, S.REPORT)
    _walk(fsm, S.LOBBY)  # start a new session


def test_cancel_paths_end_in_wrap_or_lobby():
    assert P.can_transition(S.PAIR, S.LOBBY)
    assert P.can_transition(S.PREP, S.LOBBY)
    for src in (S.ASKING, S.LISTENING, S.ANALYSING, S.PLANNING):
        assert P.can_transition(src, S.WRAP)
    assert P.can_transition(S.INTERRUPT, S.WRAP, pressure=P.Pressure.TOUGH)


def test_fsm_rejects_illegal_and_keeps_state():
    fsm = P.SessionFSM()
    with pytest.raises(P.IllegalTransition):
        fsm.advance(S.ASKING)
    assert fsm.state is S.LOBBY and fsm.history == [S.LOBBY]


def test_fsm_can_start_at_pair_for_server_side_sessions():
    fsm = P.SessionFSM(state=S.PAIR)
    assert fsm.history == [S.PAIR]
    fsm.advance(S.PREP)
    assert fsm.history == [S.PAIR, S.PREP]


def test_all_states_reachable_from_lobby_in_tough():
    seen, queue = {S.LOBBY}, deque([S.LOBBY])
    while queue:
        cur = queue.popleft()
        for nxt in S:
            if nxt not in seen and P.can_transition(cur, nxt, pressure=P.Pressure.TOUGH):
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(S)


def test_all_states_but_interrupt_reachable_in_realistic():
    seen, queue = {S.LOBBY}, deque([S.LOBBY])
    while queue:
        cur = queue.popleft()
        for nxt in S:
            if nxt not in seen and P.can_transition(cur, nxt, pressure=P.Pressure.REALISTIC):
                seen.add(nxt)
                queue.append(nxt)
    assert seen == set(S) - {S.INTERRUPT}
