"""Wire protocol and session state machine for the Interview Cracker voice server.

Source of truth: docs/BLUEPRINT.md §4.1 (wire protocol) and §4.2 (session state
machine), the why-trace shape from §5.2, the pressure dial from §5.6 and the mood
inputs from §6.1/§6.4. Where the blueprint is silent the choice is documented on
the model that makes it.

One WebSocket per session at ``ws://<laptop-ip>:8765/ws``. Text frames carry JSON
control messages discriminated by ``"type"``; binary frames carry raw PCM16 mono
audio (20 ms / 640 bytes at 16 kHz inbound, 24 kHz outbound). Binary frames are
plain ``bytes`` and are not modelled here beyond the framing constants.

Client → server: ``hello``, ``ptt``, ``cancel``, ``ping``.
Server → client: ``ready``, ``vad``, ``stt``, ``question``, ``reaction``,
``tts_start``, ``viseme``, ``mouth``, ``tts_end``, ``interrupt``, ``report``,
``error``, ``pong``.

Python 3.12, pydantic v2, nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Iterable, Literal, Mapping, TypeAlias

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

__all__ = [
    # framing constants
    "FRAME_MS", "IN_SR", "OUT_SR", "SAMPLE_BYTES",
    "IN_FRAME_SAMPLES", "FRAME_BYTES", "OUT_FRAME_SAMPLES", "OUT_FRAME_BYTES",
    "MOUTH_MIN", "MOUTH_MAX",
    # enums / literals
    "Pressure", "Mood", "MOOD_INDEX", "Strategy", "STRATEGIES", "VadState", "ErrorCode",
    # client messages
    "AudioIn", "AudioOut", "HelloMessage", "PttMessage", "CancelMessage", "PingMessage",
    "ClientMessage",
    # server messages
    "TriggeredBy", "WhyTrace", "ReadyMessage", "VadMessage", "SttMessage",
    "QuestionMessage", "ReactionMessage", "TtsStartMessage", "VisemeMessage",
    "MouthMessage", "TtsEndMessage", "InterruptMessage", "ReportMessage",
    "ErrorMessage", "PongMessage", "ServerMessage",
    # codecs
    "ProtocolError", "parse_client_message", "parse_server_message",
    "encode_server_message", "encode_client_message", "encode_viseme_track",
    # ordering
    "OrderingError", "check_tts_ordering",
    # state machine
    "SessionState", "ROUND_STATES", "TRANSITIONS", "IllegalTransition",
    "can_transition", "transition", "SessionFSM",
]

# ---------------------------------------------------------------------------
# Framing constants (§4.1)
# ---------------------------------------------------------------------------

FRAME_MS = 20
IN_SR = 16_000
OUT_SR = 24_000
SAMPLE_BYTES = 2  # PCM16, little-endian (s16le on the phone side)

IN_FRAME_SAMPLES = IN_SR * FRAME_MS // 1000  # 320
FRAME_BYTES = IN_FRAME_SAMPLES * SAMPLE_BYTES  # 640 — the inbound frame the spec fixes
OUT_FRAME_SAMPLES = OUT_SR * FRAME_MS // 1000  # 480
OUT_FRAME_BYTES = OUT_FRAME_SAMPLES * SAMPLE_BYTES  # 960 — derived, the spec does not fix outbound chunking

assert FRAME_BYTES == 640, "BLUEPRINT §4.1 fixes 640-byte inbound frames"

MOUTH_MIN, MOUTH_MAX = 0, 9  # ten mouth shapes, §6.1


# ---------------------------------------------------------------------------
# Small vocabularies
# ---------------------------------------------------------------------------


class Pressure(StrEnum):
    """Pressure dial (§2.4, §5.6). Default is Realistic per the master prompt."""

    WARMUP = "warmup"
    REALISTIC = "realistic"
    TOUGH = "tough"


Mood: TypeAlias = Literal["neutral", "interested", "thinking", "unimpressed"]

# Rive ``mood`` number input (§6.1): 0 neutral / 1 interested / 2 thinking / 3 unimpressed.
MOOD_INDEX: dict[str, int] = {"neutral": 0, "interested": 1, "thinking": 2, "unimpressed": 3}

Strategy: TypeAlias = Literal[
    "open_probe",
    "evidence_probe",
    "dig_deeper_vague",
    "dig_deeper_generic",
    "quantify_result",
    "ownership_probe",
    "contradiction_probe",
    "escalate",
]
STRATEGIES: tuple[str, ...] = Strategy.__args__  # type: ignore[attr-defined]

VadState: TypeAlias = Literal["speech_start", "speech_end"]


class ErrorCode(StrEnum):
    """Codes for ``error`` messages. The spec names the message but not its body."""

    BAD_JSON = "bad_json"  # text frame is not valid JSON
    UNKNOWN_TYPE = "unknown_type"  # "type" missing or not a client message type
    BAD_MESSAGE = "bad_message"  # known type, invalid fields (e.g. empty token)
    BAD_TOKEN = "bad_token"  # hello.token does not match the session token from the QR
    BAD_STATE = "bad_state"  # message not allowed in the current session state
    INTERNAL = "internal"  # server-side failure (model, LLM, disk)


def _check_span(t: tuple[float, float]) -> tuple[float, float]:
    t0, t1 = t
    if t0 < 0 or t1 < t0:
        raise ValueError(f"time span must satisfy 0 <= t0 <= t1, got {t!r}")
    return t


# ``[t_start, t_end]`` in seconds into the candidate's answer (§5.2, §5.3).
Span = Annotated[tuple[float, float], AfterValidator(_check_span)]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# ---------------------------------------------------------------------------
# Model bases
# ---------------------------------------------------------------------------


class _ClientMessage(BaseModel):
    """Lenient on input: unknown keys from a newer app build are ignored, not fatal."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)


class _ServerMessage(BaseModel):
    """Strict on output: a typo in a field the server emits fails at construction."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)


# ---------------------------------------------------------------------------
# Client → server (§4.1)
# ---------------------------------------------------------------------------


class AudioIn(_ClientMessage):
    """What the client will stream. Anything that is not pcm16 / 16 kHz / mono is
    resampled server-side (the web test page sends float32 at the OS rate)."""

    fmt: Literal["pcm16", "f32"] = "pcm16"
    sr: int = Field(default=IN_SR, ge=8_000, le=192_000)
    ch: int = Field(default=1, ge=1, le=2)


class AudioOut(_ClientMessage):
    fmt: Literal["pcm16"] = "pcm16"
    sr: int = Field(default=OUT_SR, ge=8_000, le=192_000)


class HelloMessage(_ClientMessage):
    """First text frame on the socket. ``token`` comes from the pairing QR and is
    checked against the per-session token before anything else is accepted.

    ``jd``, ``pressure`` and ``voice`` are not in the §4.1 example. The blueprint
    has the phone collect them in LOBBY (§4.2) but names no message that carries
    them to the server, and Stage A cannot run without the JD; carrying them on
    ``hello`` is the smallest extension that keeps the four client message types.
    """

    type: Literal["hello"] = "hello"
    token: NonEmptyStr
    mode: Literal["interview"] = "interview"
    audio_in: AudioIn = Field(default_factory=AudioIn, alias="in")
    audio_out: AudioOut = Field(default_factory=AudioOut, alias="out")
    jd: str | None = None
    pressure: Pressure = Pressure.REALISTIC
    voice: str | None = None

    @property
    def needs_resample(self) -> bool:
        a = self.audio_in
        return a.fmt != "pcm16" or a.sr != IN_SR or a.ch != 1


class PttMessage(_ClientMessage):
    """Optional push-to-talk; VAD end-pointing is the default (§7.1 Room page)."""

    type: Literal["ptt"] = "ptt"
    state: Literal["down", "up"]


class CancelMessage(_ClientMessage):
    """Abort the current turn / round. The server decides what that means per state."""

    type: Literal["cancel"] = "cancel"


class PingMessage(_ClientMessage):
    """``t`` is the client's millisecond clock; ``pong`` echoes it so the phone can
    measure Wi-Fi RTT (master prompt §6.3)."""

    type: Literal["ping"] = "ping"
    t: int | None = None


ClientMessage = Annotated[
    HelloMessage | PttMessage | CancelMessage | PingMessage,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Server → client (§4.1, why-trace shape from §5.2)
# ---------------------------------------------------------------------------


class TriggeredBy(_ServerMessage):
    """The candidate quote that caused a follow-up (§5.2)."""

    answer_id: NonEmptyStr
    quote: NonEmptyStr
    t: Span


class WhyTrace(_ServerMessage):
    """Provenance for a question: the competency, the literal JD sentence that
    justifies it, the difficulty rung and the agenda strategy. Tapping the question
    card flips it to show this (§2.2)."""

    competency_id: NonEmptyStr
    jd_quote: NonEmptyStr
    ladder_rung: NonEmptyStr
    strategy: Strategy
    triggered_by: TriggeredBy | None = None


class ReadyMessage(_ServerMessage):
    type: Literal["ready"] = "ready"
    session: NonEmptyStr


class VadMessage(_ServerMessage):
    """Drives the avatar's ``listening`` bool (§6.4)."""

    type: Literal["vad"] = "vad"
    state: VadState


class SttMessage(_ServerMessage):
    type: Literal["stt"] = "stt"
    text: str
    final: bool = True


class QuestionMessage(_ServerMessage):
    """``time_limit_s`` is ``None`` in Warm-up, where §5.6 says "Timer: none"."""

    type: Literal["question"] = "question"
    id: NonEmptyStr
    text: NonEmptyStr
    why: WhyTrace
    time_limit_s: int | None = Field(default=None, gt=0)


class ReactionMessage(_ServerMessage):
    type: Literal["reaction"] = "reaction"
    mood: Mood
    nod: bool = False


class TtsStartMessage(_ServerMessage):
    type: Literal["tts_start"] = "tts_start"
    sr: int = Field(default=OUT_SR, gt=0)


class VisemeMessage(_ServerMessage):
    """Mouth shape at ``t_ms`` into the current TTS span. The phone schedules it
    against the audio playback clock, never wall time (§4.1)."""

    type: Literal["viseme"] = "viseme"
    t_ms: int = Field(ge=0)
    id: int = Field(ge=MOUTH_MIN, le=MOUTH_MAX)


class MouthMessage(_ServerMessage):
    """RMS fallback for a TTS engine without token timestamps (§6.3)."""

    type: Literal["mouth"] = "mouth"
    t_ms: int = Field(ge=0)
    open: float = Field(ge=0.0, le=1.0)


class TtsEndMessage(_ServerMessage):
    type: Literal["tts_end"] = "tts_end"


class InterruptMessage(_ServerMessage):
    """Barge-in: the phone calls ``SoLoud.stop()`` and flushes its buffer (§4.1)."""

    type: Literal["interrupt"] = "interrupt"


class RubricChip(_ServerMessage):
    id: NonEmptyStr
    name: NonEmptyStr
    priority: Literal["must_have", "nice_to_have"]
    type: Literal["technical", "behavioral"]


class RubricMessage(_ServerMessage):
    """Sent once after Stage A so the Prep page can show competency chips — names only,
    never the questions (BLUEPRINT §7.1: transparency without preview)."""

    type: Literal["rubric"] = "rubric"
    role_title: str
    competencies: list[RubricChip]
    n_questions: int


class ReportMessage(_ServerMessage):
    type: Literal["report"] = "report"
    url: NonEmptyStr
    session: str | None = None


class ErrorMessage(_ServerMessage):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    fatal: bool = False  # True → the server closes the socket after sending this


class PongMessage(_ServerMessage):
    type: Literal["pong"] = "pong"
    t: int | None = None


ServerMessage = Annotated[
    ReadyMessage
    | VadMessage
    | SttMessage
    | QuestionMessage
    | ReactionMessage
    | TtsStartMessage
    | VisemeMessage
    | MouthMessage
    | TtsEndMessage
    | InterruptMessage
    | RubricMessage
    | ReportMessage
    | ErrorMessage
    | PongMessage,
    Field(discriminator="type"),
]

_CLIENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(ClientMessage)
_SERVER_ADAPTER: TypeAdapter[Any] = TypeAdapter(ServerMessage)


# ---------------------------------------------------------------------------
# Codecs
# ---------------------------------------------------------------------------


class ProtocolError(ValueError):
    """A text frame that is not a valid message. ``code`` maps onto ``ErrorCode``
    so the server can answer with ``to_error()`` and decide whether to close."""

    def __init__(self, code: ErrorCode, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message

    def to_error(self, *, fatal: bool = False) -> ErrorMessage:
        return ErrorMessage(code=self.code, message=self.message, fatal=fatal)


def _classify(exc: ValidationError) -> ProtocolError:
    errors = exc.errors()
    first = errors[0] if errors else {"type": "unknown", "loc": (), "msg": str(exc)}
    kind = first.get("type", "")
    loc = ".".join(str(p) for p in first.get("loc", ()))
    detail = f"{loc}: {first.get('msg', '')}" if loc else str(first.get("msg", ""))
    if kind == "json_invalid":
        return ProtocolError(ErrorCode.BAD_JSON, detail)
    if kind in ("union_tag_invalid", "union_tag_not_found"):
        return ProtocolError(ErrorCode.UNKNOWN_TYPE, detail)
    return ProtocolError(ErrorCode.BAD_MESSAGE, detail)


def parse_client_message(text: str | bytes | bytearray) -> HelloMessage | PttMessage | CancelMessage | PingMessage:
    """Decode one client text frame. Raises ``ProtocolError`` (never pydantic's own
    exception) so the WebSocket handler has a single thing to catch."""
    if isinstance(text, (bytes, bytearray)):
        # Binary frames are PCM audio; the caller should have branched on frame kind.
        try:
            text = bytes(text).decode("utf-8")
        except UnicodeDecodeError as e:
            raise ProtocolError(ErrorCode.BAD_JSON, "text frame is not UTF-8") from e
    try:
        return _CLIENT_ADAPTER.validate_json(text)
    except ValidationError as e:
        raise _classify(e) from e


def parse_server_message(text: str | bytes | bytearray) -> Any:
    """Decode one server text frame (for the test client and the e2e harness)."""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8")
    try:
        return _SERVER_ADAPTER.validate_json(text)
    except ValidationError as e:
        raise _classify(e) from e


def encode_server_message(obj: BaseModel | dict[str, Any]) -> str:
    """Serialise a server message to the JSON text the phone expects. Accepts a
    model or a plain dict that carries ``"type"``; dicts are validated first so a
    malformed event never reaches the wire. For the bare ``{t_ms, id}`` /
    ``{t_ms, open}`` events that ``audio.visemes`` produces use
    ``encode_viseme_track``."""
    model = obj if isinstance(obj, BaseModel) else _SERVER_ADAPTER.validate_python(obj)
    return model.model_dump_json(by_alias=True)


def encode_viseme_track(events: Iterable[Mapping[str, Any]]) -> list[str]:
    """Wire frames for a mouth track from ``audio.visemes``: ``{t_ms, id}`` events
    become ``viseme`` messages, ``{t_ms, open}`` events become ``mouth`` messages.
    The server interleaves these with the PCM frames whose playback time they
    match (§4.1). Validation errors surface as pydantic ``ValidationError``."""
    frames: list[str] = []
    for ev in events:
        if "id" in ev:
            frames.append(VisemeMessage(t_ms=ev["t_ms"], id=ev["id"]).model_dump_json())
        elif "open" in ev:
            frames.append(MouthMessage(t_ms=ev["t_ms"], open=ev["open"]).model_dump_json())
        else:
            raise ValueError(f"mouth event needs 'id' or 'open': {dict(ev)!r}")
    return frames


def encode_client_message(obj: BaseModel | dict[str, Any]) -> str:
    """Serialise a client message (``in``/``out`` keys as on the wire)."""
    model = obj if isinstance(obj, BaseModel) else _CLIENT_ADAPTER.validate_python(obj)
    return model.model_dump_json(by_alias=True)


# ---------------------------------------------------------------------------
# Ordering constraint for a TTS span (§4.1: tts_start, PCM + visemes, tts_end)
# ---------------------------------------------------------------------------


class OrderingError(AssertionError):
    """A server event sequence violates the tts_start / viseme / tts_end contract."""


def _event_type(ev: Any) -> str | None:
    """'type' of a model or dict event; ``None`` for a binary audio frame."""
    if isinstance(ev, (bytes, bytearray, memoryview)):
        return None
    if isinstance(ev, BaseModel):
        return getattr(ev, "type", "")
    if isinstance(ev, dict):
        return str(ev.get("type", ""))
    raise TypeError(f"unsupported event {type(ev).__name__}")


def _event_t_ms(ev: Any) -> int:
    return int(ev.t_ms if isinstance(ev, BaseModel) else ev["t_ms"])


def check_tts_ordering(events: Iterable[Any]) -> int:
    """Assert the TTS contract over a sequence of server events.

    Rules: every ``viseme``/``mouth`` event and every binary PCM frame lies between
    a ``tts_start`` and its ``tts_end``; spans do not nest; viseme times inside a
    span never go backwards; an ``interrupt`` closes the span (the phone has
    flushed), after which a ``tts_end`` is tolerated but no more audio or visemes
    are. A span left open at the end of the sequence is an error.

    Accepts model instances, plain dicts with a ``"type"``, and ``bytes``.
    Returns the number of completed spans. Raises ``OrderingError``.
    """
    OUTSIDE, INSIDE, INTERRUPTED = "outside", "inside", "interrupted"
    state = OUTSIDE
    spans = 0
    last_t: int | None = None
    for i, ev in enumerate(events):
        kind = _event_type(ev)
        if kind == "tts_start":
            if state == INSIDE:
                raise OrderingError(f"event {i}: nested tts_start (previous span not ended)")
            state, last_t = INSIDE, None
        elif kind in ("viseme", "mouth") or kind is None:
            what = "audio frame" if kind is None else kind
            if state == OUTSIDE:
                raise OrderingError(f"event {i}: {what} before tts_start")
            if state == INTERRUPTED:
                raise OrderingError(f"event {i}: {what} after interrupt")
            if kind is not None:
                t = _event_t_ms(ev)
                if last_t is not None and t < last_t:
                    raise OrderingError(f"event {i}: {kind} t_ms {t} goes backwards (last {last_t})")
                last_t = t
        elif kind == "tts_end":
            if state == OUTSIDE:
                raise OrderingError(f"event {i}: tts_end without tts_start")
            state, last_t = OUTSIDE, None
            spans += 1
        elif kind == "interrupt":
            if state == INSIDE:
                state = INTERRUPTED
        # every other server message is allowed anywhere
    if state == INSIDE:
        raise OrderingError("sequence ended inside a tts span (no tts_end)")
    return spans


# ---------------------------------------------------------------------------
# Session state machine (§4.2)
# ---------------------------------------------------------------------------


class SessionState(StrEnum):
    """§4.2, flattened: the ROUND super-state is the set ``ROUND_STATES`` and its
    sub-states are first-class members, so a session carries one ``state`` field.

    ``ANALYSING ∥ PLANNING`` (Stage C for answer *n* concurrently with Stage B for
    question *n+1*, §5.3) is modelled as two states with a transition each way:
    the server sits in whichever finished last, and the guard lets either lead to
    ``ASKING``. ``INTERRUPT`` is the moment one party cuts the other off — the
    interviewer's "let me stop you there" on time-out or looping (from
    ``LISTENING``), or the candidate barging in on TTS (from ``ASKING``) — and is
    only reachable when the pressure dial is Tough (§4.2, master prompt Phase 2.2).
    Realistic's "interruption on time-out" (§5.6) is therefore the silent path
    ``LISTENING → ANALYSING`` when the timer expires, with no spoken cut-off.
    """

    LOBBY = "lobby"  # phone: paste JD, pressure dial, voice
    PAIR = "pair"  # phone: scan QR; socket: hello → ready
    PREP = "prep"  # server: Stage A, opener + Q1 audio pre-rendered
    ASKING = "asking"  # TTS of the question is playing
    LISTENING = "listening"  # candidate is answering (VAD/PTT)
    ANALYSING = "analysing"  # Stage C on the answer
    PLANNING = "planning"  # Stage B for the next question
    INTERRUPT = "interrupt"  # Tough only: cut-off / barge-in
    WRAP = "wrap"  # Stage D report generation
    REPORT = "report"  # phone: report screen; retry-the-weakest returns to ASKING


ROUND_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.ASKING,
        SessionState.LISTENING,
        SessionState.ANALYSING,
        SessionState.PLANNING,
        SessionState.INTERRUPT,
    }
)

_S = SessionState
TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    _S.LOBBY: frozenset({_S.PAIR}),
    _S.PAIR: frozenset({_S.PREP, _S.LOBBY}),  # → LOBBY: pairing failed / cancelled
    _S.PREP: frozenset({_S.ASKING, _S.LOBBY}),  # → LOBBY: Stage A failed / cancel
    _S.ASKING: frozenset({_S.LISTENING, _S.INTERRUPT, _S.WRAP}),  # → WRAP: cancel
    _S.LISTENING: frozenset({_S.ANALYSING, _S.PLANNING, _S.INTERRUPT, _S.WRAP}),
    _S.ANALYSING: frozenset({_S.PLANNING, _S.ASKING, _S.WRAP}),  # → WRAP: agenda done
    _S.PLANNING: frozenset({_S.ANALYSING, _S.ASKING, _S.WRAP}),
    _S.INTERRUPT: frozenset({_S.LISTENING, _S.ANALYSING, _S.PLANNING, _S.WRAP}),
    _S.WRAP: frozenset({_S.REPORT}),
    _S.REPORT: frozenset({_S.ASKING, _S.LOBBY}),  # → ASKING: retry weakest question
}
del _S

assert set(TRANSITIONS) == set(SessionState), "every state needs a transition row"


class IllegalTransition(ValueError):
    def __init__(self, current: SessionState, target: SessionState, pressure: Pressure):
        super().__init__(f"{current} -> {target} is not allowed (pressure={pressure})")
        self.current, self.target, self.pressure = current, target, pressure


def can_transition(
    current: SessionState,
    target: SessionState,
    *,
    pressure: Pressure = Pressure.REALISTIC,
) -> bool:
    """Guard: is ``current → target`` legal under this pressure dial?"""
    if target not in TRANSITIONS[current]:
        return False
    if target is SessionState.INTERRUPT and pressure is not Pressure.TOUGH:
        return False
    return True


def transition(
    current: SessionState,
    target: SessionState,
    *,
    pressure: Pressure = Pressure.REALISTIC,
) -> SessionState:
    """Return ``target`` if the move is legal, else raise ``IllegalTransition``."""
    if not can_transition(current, target, pressure=pressure):
        raise IllegalTransition(current, target, pressure)
    return target


@dataclass
class SessionFSM:
    """Minimal holder the server can embed in a session object: current state,
    the dial, and the path taken (useful in logs and in the e2e harness)."""

    pressure: Pressure = Pressure.REALISTIC
    state: SessionState = SessionState.LOBBY
    history: list[SessionState] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [self.state]

    @property
    def in_round(self) -> bool:
        return self.state in ROUND_STATES

    def can(self, target: SessionState) -> bool:
        return can_transition(self.state, target, pressure=self.pressure)

    def advance(self, target: SessionState) -> SessionState:
        self.state = transition(self.state, target, pressure=self.pressure)
        self.history.append(self.state)
        return self.state
