"""Mouth-shape tracks for the on-phone interviewer puppet.

Two sources, per docs/BLUEPRINT.md §6.2 and §6.3:

* ``visemes_from_tokens`` — Kokoro ``KPipeline`` tokens (``.phonemes`` in misaki
  IPA, ``.start_ts`` / ``.end_ts`` in seconds) → ``{"t_ms", "id"}`` events on the
  ten-mouth scale of §6.1.
* ``rms_mouth_events`` — for any TTS without token timestamps: RMS energy per
  40 ms window of the PCM16 about to be sent → ``{"t_ms", "open"}`` events in
  0..1, plus ``mouth_id_from_open`` to collapse that onto mouths 0/7/8.

Both guarantee at least one event every ``MAX_GAP_MS`` (40 ms → ≥ 25 events/s)
by inserting hold events, and both end on a closed mouth, so the phone's
scheduler — which runs against the audio playback clock — never starves and the
mouth never sticks open after the audio stops.

Tokens are duck-typed (anything with ``phonemes``, ``start_ts``, ``end_ts``), so
tests can use ``SimpleNamespace`` and the server can pass Kokoro's ``MToken``.
Only numpy is required, and only for the RMS path.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Any, Iterable, Protocol, TypedDict, runtime_checkable

__all__ = [
    "MAX_GAP_MS", "EVENTS_PER_SECOND_MIN",
    "MOUTH_REST", "MOUTH_MBP", "MOUTH_FV", "MOUTH_TH", "MOUTH_L", "MOUTH_TEETH",
    "MOUTH_R", "MOUTH_AH", "MOUTH_EE", "MOUTH_OH",
    "PHONEME_MOUTHS", "IGNORED_MARKS", "VisemeEvent", "MouthEvent", "TokenLike",
    "mouths_for_phoneme", "visemes_from_tokens", "max_gap_ms",
    "rms_mouth_events", "mouth_id_from_open", "mouth_events_to_visemes",
]

# ≥ 25 events/s (§6.2) ⇔ no two consecutive events further apart than 40 ms.
MAX_GAP_MS = 40
EVENTS_PER_SECOND_MIN = 1000 // MAX_GAP_MS  # 25

# Ten mouth shapes, Character-Animator grouping (§6.1).
MOUTH_REST = 0  # rest / closed
MOUTH_MBP = 1  # M B P
MOUTH_FV = 2  # F V
MOUTH_TH = 3  # TH
MOUTH_L = 4  # L
MOUTH_TEETH = 5  # D T N S Z (teeth)
MOUTH_R = 6  # R
MOUTH_AH = 7  # Ah (open)
MOUTH_EE = 8  # Ee (wide)
MOUTH_OH = 9  # Oh / Oo (round)


def _all(chars: str, *mouths: int) -> dict[str, tuple[int, ...]]:
    return {c: tuple(mouths) for c in chars}


# misaki IPA (Kokoro, lang_code 'a'/'b') → one or more mouths. A diphthong gets two
# mouths and splits its time slot between them. Velars/glottal (k ɡ ŋ h) have no
# shape of their own in a ten-mouth set and ride on "teeth", as the §6.2 sketch's
# default does. Tune by ear against the Rive shapes; the tests pin only the spec'd
# groups. The single-letter diphthongs (A I W Y O Q) follow the misaki README as
# of Kokoro 0.9.x — *verify* against ``misaki`` on the installed version.
PHONEME_MOUTHS: dict[str, tuple[int, ...]] = {
    **_all("mbp", MOUTH_MBP),
    **_all("fv", MOUTH_FV),
    **_all("θð", MOUTH_TH),
    **_all("l", MOUTH_L),
    **_all("tdnszʃʒʧʤɾŋkɡgh", MOUTH_TEETH),
    **_all("ɹr", MOUTH_R),
    "ɚ": (MOUTH_R,),  # r-coloured schwa reads as an R shape
    **_all("ɑaæʌɐɒəᵊɜ", MOUTH_AH),
    **_all("iɪeɛᵻj", MOUTH_EE),  # 'j' is the yod ("yes"), not a consonant closure
    **_all("oʊuɔw", MOUTH_OH),
    "A": (MOUTH_EE,),  # eɪ
    "I": (MOUTH_AH, MOUTH_EE),  # aɪ
    "W": (MOUTH_AH, MOUTH_OH),  # aʊ
    "Y": (MOUTH_OH, MOUTH_EE),  # ɔɪ
    "O": (MOUTH_OH,),  # oʊ (American)
    "Q": (MOUTH_AH, MOUTH_OH),  # əʊ (British)
}

# Stress and length marks are Unicode category Lm, so ``str.isalpha()`` is True for
# them — the §6.2 sketch's ``p.isalpha()`` filter would turn every stress mark into
# a "teeth" viseme. They are dropped here by name, and any other modifier letter
# or non-letter (ties, syllabic marks, punctuation, spaces) is dropped by category.
IGNORED_MARKS = frozenset("ˈˌːˑ.‿͡")
_FALLBACK_VOWELS = frozenset("aeiou")


class VisemeEvent(TypedDict):
    t_ms: int
    id: int


class MouthEvent(TypedDict):
    t_ms: int
    open: float


@runtime_checkable
class TokenLike(Protocol):
    phonemes: str | None
    start_ts: float | None
    end_ts: float | None


def mouths_for_phoneme(p: str) -> tuple[int, ...]:
    """Mouth id(s) for one misaki phoneme character; ``()`` for marks to skip."""
    if p in PHONEME_MOUTHS:
        return PHONEME_MOUTHS[p]
    if p in IGNORED_MARKS:
        return ()
    cat = unicodedata.category(p)
    if cat not in ("Ll", "Lu", "Lo"):  # Lm modifiers, Mn combining, punctuation, space
        return ()
    return (MOUTH_AH,) if p in _FALLBACK_VOWELS else (MOUTH_TEETH,)


def _fill_holds(events: list[tuple[int, int]], max_gap_ms: int) -> list[tuple[int, int]]:
    """Repeat the previous id every ``max_gap_ms`` until the next event is within reach."""
    if not events:
        return events
    out = [events[0]]
    for t, mouth in events[1:]:
        while t - out[-1][0] > max_gap_ms:
            out.append((out[-1][0] + max_gap_ms, out[-1][1]))
        out.append((t, mouth))
    return out


def visemes_from_tokens(
    tokens: Iterable[Any],
    *,
    offset_ms: int = 0,
    total_ms: int | None = None,
    max_gap_ms: int = MAX_GAP_MS,
    rest_gap_ms: int = 50,
) -> list[VisemeEvent]:
    """Viseme track from Kokoro token timestamps (§6.2).

    Each token's duration is split evenly across its mouth shapes (a diphthong
    counts twice). A rest (id 0) is placed at each token's ``end_ts`` — but only
    when the next timed token starts at least ``rest_gap_ms`` later, because a
    rest shorter than a scheduler frame is invisible at best and a between-words
    flicker at worst. The track always begins with a rest at ``offset_ms`` if the
    first token starts later, always ends with a rest (at the last token's end,
    or at ``offset_ms + total_ms`` when the audio length is known), and never has
    two consecutive events more than ``max_gap_ms`` apart.

    ``offset_ms`` lets the server concatenate the per-chunk results Kokoro yields
    for long text, whose timestamps restart at 0 for every chunk.
    Tokens with ``start_ts``/``end_ts`` of ``None`` or empty phonemes (punctuation)
    are skipped, as in the spec.
    """
    if max_gap_ms <= 0:
        raise ValueError("max_gap_ms must be positive")

    # (start_ms, end_ms, mouths) per timed token, in order.
    timed: list[tuple[int, int, list[int]]] = []
    for tk in tokens:
        start = getattr(tk, "start_ts", None)
        end = getattr(tk, "end_ts", None)
        ph = getattr(tk, "phonemes", None)
        if start is None or end is None or not ph:
            continue
        mouths = [m for p in ph for m in mouths_for_phoneme(p)]
        if not mouths:
            continue
        t0 = offset_ms + int(round(float(start) * 1000))
        t1 = max(t0, offset_ms + int(round(float(end) * 1000)))
        timed.append((t0, t1, mouths))

    raw: list[tuple[int, int]] = []
    for i, (t0, t1, mouths) in enumerate(timed):
        step = (t1 - t0) / len(mouths)
        for k, mouth in enumerate(mouths):
            raw.append((int(round(t0 + k * step)), mouth))
        is_last = i == len(timed) - 1
        next_start = None if is_last else timed[i + 1][0]
        if is_last or next_start - t1 >= rest_gap_ms:
            raw.append((t1, MOUTH_REST))

    if not raw:
        return []

    raw.sort(key=lambda e: e[0])  # stable: same-time events keep emission order
    # Same timestamp → the later emission wins (a token's phoneme beats the previous
    # token's rest when they coincide).
    deduped: list[tuple[int, int]] = []
    for t, mouth in raw:
        if deduped and deduped[-1][0] == t:
            deduped[-1] = (t, mouth)
        else:
            deduped.append((t, mouth))

    if deduped[0][0] > offset_ms:
        deduped.insert(0, (offset_ms, MOUTH_REST))
    if deduped[-1][1] != MOUTH_REST:
        deduped.append((deduped[-1][0], MOUTH_REST))
    if total_ms is not None and offset_ms + total_ms > deduped[-1][0]:
        deduped.append((offset_ms + total_ms, MOUTH_REST))

    return [{"t_ms": t, "id": mouth} for t, mouth in _fill_holds(deduped, max_gap_ms)]


def max_gap_ms(events: Iterable[dict[str, Any]]) -> int:
    """Largest gap between consecutive events (0 for fewer than two events)."""
    gap, prev = 0, None
    for ev in events:
        t = int(ev["t_ms"])
        if prev is not None:
            gap = max(gap, t - prev)
        prev = t
    return gap


# ---------------------------------------------------------------------------
# §6.3 fallback: RMS mouth-open for a TTS without timestamps
# ---------------------------------------------------------------------------


def rms_mouth_events(
    pcm16_bytes: bytes | bytearray | memoryview,
    sr: int,
    window_ms: int = 40,
    *,
    offset_ms: int = 0,
    ref_rms: float | None = None,
    gate: float = 0.08,
) -> list[MouthEvent]:
    """RMS energy per ``window_ms`` of little-endian PCM16 mono → ``open`` in 0..1.

    ``open`` is the window RMS relative to ``ref_rms`` (default: this buffer's
    loudest window, so a whole utterance always reaches 1.0), with anything below
    ``gate`` of the reference clamped to 0 so breath and synthesis noise keep the
    mouth shut. Pass ``ref_rms`` when synthesising in chunks so every chunk is
    scaled the same way. A final ``open=0`` is appended at the end of the audio.
    """
    import numpy as np  # local import: the token path must not need numpy

    if sr <= 0:
        raise ValueError("sr must be positive")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")
    if not 0.0 <= gate < 1.0:
        raise ValueError("gate must be in [0, 1)")
    buf = bytes(pcm16_bytes)
    if len(buf) % 2:
        raise ValueError("PCM16 buffer must have an even number of bytes")
    if not buf:
        return []

    x = np.frombuffer(buf, dtype="<i2").astype(np.float32) / 32768.0
    n = x.shape[0]
    win = max(1, sr * window_ms // 1000)
    n_win = math.ceil(n / win)
    x = np.pad(x, (0, n_win * win - n))
    rms = np.sqrt(np.mean(x.reshape(n_win, win) ** 2, axis=1))

    ref = float(rms.max()) if ref_rms is None else float(ref_rms)
    if ref <= 0.0:
        opens = np.zeros(n_win, dtype=np.float32)
    else:
        opens = np.clip((rms / ref - gate) / (1.0 - gate), 0.0, 1.0)

    events: list[MouthEvent] = [
        {"t_ms": offset_ms + i * window_ms, "open": round(float(o), 3)} for i, o in enumerate(opens)
    ]
    events.append({"t_ms": offset_ms + math.ceil(n * 1000 / sr), "open": 0.0})
    return events


def mouth_id_from_open(open_: float) -> int:
    """Collapse an RMS ``open`` value onto mouths 0 / 8 / 7 (closed / wide / open),
    the three shapes §6.3 says to blend."""
    if open_ < 0.15:
        return MOUTH_REST
    if open_ < 0.6:
        return MOUTH_EE
    return MOUTH_AH


def mouth_events_to_visemes(events: Iterable[MouthEvent]) -> list[VisemeEvent]:
    """Turn ``{t_ms, open}`` events into ``{t_ms, id}`` viseme events for a client
    that only understands the ``viseme`` message."""
    return [{"t_ms": int(ev["t_ms"]), "id": mouth_id_from_open(float(ev["open"]))} for ev in events]
