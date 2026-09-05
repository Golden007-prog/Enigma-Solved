"""Stage C quote gate (BLUEPRINT §5.3): the report may only cite words the candidate said.

Every ``{"quote": ..., "t": [t0, t1]}`` object in the analyzer's JSON — STAR components,
hedges, contradictions, and the ``why.triggered_by`` block of a follow-up question — must
(1) fuzzy-match a span of the STT transcript with RapidFuzz ``partial_ratio >= 90`` on
normalised text and (2) carry a ``t`` that falls inside that span's word timestamps
(±0.25 s). A quote that fails has its ``quote`` and ``t`` nulled — the enclosing object
(``star.action``, the analysis itself) survives — and the drop is recorded. Two shapes
are handled so the result still validates against ``schemas.py``: an object that is
nothing but a quote (``why.triggered_by``, ``per_question.key_quote``) is replaced by
``None`` in its parent, and items of a list that *are* a quote (hedges, contradictions)
are removed from the list, since a hedge with no quote is nothing.

Cheap rules layered on the LLM, when the object is an answer analysis (has ``star``):
a Result claim needs a past-tense outcome verb or a number in its quote; ownership is the
first-person-singular ratio over the answer (reported in ``GateResult.ownership`` — the
strict ``Analysis`` schema has no slot for it — and as the ``star.action.ownership``
label); a we-ratio above 0.7 flags team-hiding. The pronoun and verb lists are module
constants — heuristics, tune them.

Only stdlib + rapidfuzz. The input is deep-copied so the raw LLM JSON can be logged
unmodified for judges.
"""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from rapidfuzz import fuzz

__all__ = [
    "MIN_PARTIAL_RATIO", "T_TOLERANCE_S", "WE_RATIO_TEAM_HIDING",
    "Word", "Transcript", "Match", "ValidatedQuote", "DroppedQuote", "GateResult",
    "norm_text", "match_quote", "has_outcome_evidence", "ownership_stats",
    "validate_analysis", "walk_quotes",
]

MIN_PARTIAL_RATIO = 90.0
T_TOLERANCE_S = 0.25
WE_RATIO_TEAM_HIDING = 0.7

FIRST_PERSON_SINGULAR = frozenset({"i", "i'm", "i've", "i'd", "i'll", "me", "my", "mine", "myself"})
FIRST_PERSON_PLURAL = frozenset({"we", "we're", "we've", "we'd", "we'll", "us", "our", "ours", "ourselves"})

# Past-tense verbs that state a *change* — "it worked fine" (the blueprint's own demo of a
# missing Result) must not count, so generic past tense is deliberately excluded.
OUTCOME_VERBS = frozenset({
    "reduced", "cut", "saved", "improved", "increased", "decreased", "grew", "dropped", "fell",
    "rose", "raised", "lowered", "boosted", "doubled", "tripled", "halved", "shipped", "launched",
    "delivered", "deployed", "released", "achieved", "reached", "hit", "exceeded", "met", "won",
    "gained", "earned", "secured", "fixed", "resolved", "eliminated", "prevented", "recovered",
    "completed", "finished", "migrated", "scaled", "accelerated", "sped", "passed", "cleared",
    "converted", "onboarded", "automated", "replaced", "removed", "shortened", "unblocked",
    # A problem that *stopped* is an outcome too ("the timeout alerts stopped").
    "stopped", "ended", "ceased", "disappeared", "vanished", "stabilised", "stabilized",
})
NUMBER_WORDS = frozenset({
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "thousand", "lakh", "crore", "million", "billion",
    "percent", "half", "double", "triple", "twice", "thrice",
})
_OUTCOME_PATTERNS = re.compile(r"\b(went|go(?:es|ing)?|came|brought)\s+(up|down|from)\b")
_DIGIT = re.compile(r"\d")

# Curly quotes and the grave accent fold to a plain apostrophe before matching.
_APOS = str.maketrans({"’": "'", "‘": "'", "`": "'"})
_NONWORD = re.compile(r"[^\w']+")
_WS = re.compile(r"\s+")


def norm_text(s: str) -> str:
    """Lower-case, fold curly apostrophes, replace punctuation with spaces, collapse whitespace.

    Applied identically to quotes and transcript words, so "final-year project," and
    "final year project" compare equal.
    """
    s = _NONWORD.sub(" ", s.translate(_APOS).lower())
    return _WS.sub(" ", s).strip()


@dataclass(frozen=True)
class Word:
    text: str  # normalised
    start: float
    end: float


class Transcript:
    """Normalised transcript with a char-to-word index so a fuzzy span maps back to timestamps.

    Accepts the STT word list ``[{"word": str, "start": float, "end": float}, ...]``
    (``"text"`` is tolerated as an alias for ``"word"``). Tokens that normalise to nothing
    (a lone "," or "...") are skipped; they carry no evidence.
    """

    def __init__(self, words: Iterable[Mapping[str, Any]]):
        self.words: list[Word] = []
        self._spans: list[tuple[int, int]] = []
        parts: list[str] = []
        pos = 0
        for w in words:
            raw = w.get("word", w.get("text", ""))
            text = norm_text(str(raw))
            if not text:
                continue
            if parts:
                pos += 1  # the joining space
            self._spans.append((pos, pos + len(text)))
            self.words.append(Word(text, float(w["start"]), float(w["end"])))
            parts.append(text)
            pos += len(text)
        self.text = " ".join(parts)

    def __len__(self) -> int:
        return len(self.words)

    def words_in(self, c0: int, c1: int) -> tuple[int, int] | None:
        """Inclusive word-index range overlapping normalised char range ``[c0, c1)``."""
        first = next((k for k, (_, b) in enumerate(self._spans) if b > c0), None)
        last = next((k for k in range(len(self._spans) - 1, -1, -1) if self._spans[k][0] < c1), None)
        if first is None or last is None or last < first:
            return None
        return first, last

    def span_text(self, i: int, j: int) -> str:
        return " ".join(w.text for w in self.words[i : j + 1])

    def span_t(self, i: int, j: int) -> tuple[float, float]:
        return self.words[i].start, self.words[j].end


@dataclass(frozen=True)
class Match:
    score: float  # the partial_ratio that gates acceptance
    word_start: int  # inclusive
    word_end: int  # inclusive
    t_start: float
    t_end: float
    text: str  # normalised transcript span


def _as_transcript(words: Transcript | Iterable[Mapping[str, Any]]) -> Transcript:
    return words if isinstance(words, Transcript) else Transcript(words)


def _best_match(quote: str, tr: Transcript) -> Match | None:
    q = norm_text(quote)
    if not q or not tr.text:
        return None
    if len(q) > len(tr.text):
        # partial_ratio would align the *transcript* inside the quote and score a quote that
        # contains the whole answer plus invented words at 100; the only span a longer quote
        # can claim is the whole transcript, so compare against that directly.
        score = fuzz.ratio(q, tr.text)
        i, j = 0, len(tr) - 1
    else:
        al = fuzz.partial_ratio_alignment(q, tr.text)
        if al is None:
            return None
        score = al.score
        span = tr.words_in(al.dest_start, al.dest_end)
        if span is None:
            return None
        i, j = span
        # The character window can sit one or two characters off a word boundary; pick the
        # neighbouring whole-word span that reads closest to the quote.
        best = fuzz.ratio(q, tr.span_text(i, j))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii, jj = i + di, j + dj
                if (di, dj) == (0, 0) or ii < 0 or jj >= len(tr) or ii > jj:
                    continue
                r = fuzz.ratio(q, tr.span_text(ii, jj))
                if r > best:
                    best, (i, j) = r, (ii, jj)
    t0, t1 = tr.span_t(i, j)
    return Match(float(score), i, j, t0, t1, tr.span_text(i, j))


def match_quote(
    quote: str,
    words: Transcript | Iterable[Mapping[str, Any]],
    *,
    min_ratio: float | None = MIN_PARTIAL_RATIO,
) -> Match | None:
    """Locate ``quote`` in the transcript; ``None`` if nothing scores ``>= min_ratio``
    (pass ``min_ratio=None`` to always get the best candidate and its score)."""
    m = _best_match(quote, _as_transcript(words))
    if m is None or (min_ratio is not None and m.score < min_ratio):
        return None
    return m


@dataclass(frozen=True)
class ValidatedQuote:
    answer_id: str | None
    path: str  # e.g. "star.action", "hedges[1]", "why.triggered_by"
    quote: str  # as the LLM wrote it
    t: tuple[float, float]  # as the LLM wrote it (inside span_t +/- tolerance)
    word_start: int
    word_end: int
    span_t: tuple[float, float]  # the matched words' own timestamps — use these for replay
    score: float

    @property
    def key(self) -> tuple[str | None, str]:
        return self.answer_id, norm_text(self.quote)


@dataclass(frozen=True)
class DroppedQuote:
    answer_id: str | None
    path: str
    quote: str | None
    t: Any
    reason: str  # no_match | t_outside | missing_t | bad_t | unknown_answer | empty_transcript | result_no_outcome | not_validated | no_answer_id
    score: float | None = None


class GateResult(NamedTuple):
    analysis: dict[str, Any]
    validated: list[ValidatedQuote]
    dropped: list[DroppedQuote]
    ownership: dict[str, Any] | None  # ownership_stats() of the answer; None when cheap rules did not run


# A dict with only these keys is a bare quote object: nulling its fields would leave an
# object no schema accepts, so it is replaced by None in its parent instead.
_QUOTE_ONLY_KEYS = frozenset({"quote", "t", "answer_id"})


def _parse_t(t: Any) -> tuple[float, float] | None:
    if not isinstance(t, (list, tuple)) or len(t) != 2:
        return None
    a, b = t
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (a, b)):
        return None
    if a > b:
        return None
    return float(a), float(b)


def _null(node: dict[str, Any]) -> None:
    node["quote"] = None
    if "t" in node:
        node["t"] = None


Check = Callable[[dict[str, Any], str, str | None], bool]


def walk_quotes(
    node: Any,
    check: Check,
    *,
    path: str = "",
    answer_id: str | None = None,
    drop_on_nested_failure: bool = False,
) -> tuple[bool, bool]:
    """Visit every dict with a string ``quote`` and call ``check(obj, path, answer_id)``.

    ``check`` returns True to keep the quote and must null the object's ``quote``/``t``
    itself when returning False. ``answer_id`` is inherited from the nearest enclosing dict
    that carries one. A failed child that is a bare quote object (keys within
    ``quote``/``t``/``answer_id``) is replaced by ``None`` in its parent. A list item whose
    *own* quote failed is removed from the list; with ``drop_on_nested_failure`` an item is
    also removed when any quote nested inside it failed (a contradiction needs both of its
    sides). Returns ``(own_failed, any_failed)``.
    """
    if isinstance(node, dict):
        if isinstance(node.get("answer_id"), str):
            answer_id = node["answer_id"]
        own_failed = isinstance(node.get("quote"), str) and not check(node, path, answer_id)
        any_failed = own_failed
        for key, value in list(node.items()):
            if key in ("quote", "t") or not isinstance(value, (dict, list)):
                continue
            child_failed, nested_failed = walk_quotes(
                value, check, path=f"{path}.{key}" if path else key,
                answer_id=answer_id, drop_on_nested_failure=drop_on_nested_failure,
            )
            if child_failed and isinstance(value, dict) and set(value) <= _QUOTE_ONLY_KEYS:
                node[key] = None
            any_failed = any_failed or nested_failed
        return own_failed, any_failed
    if isinstance(node, list):
        kept: list[Any] = []
        any_failed = False
        for i, item in enumerate(node):
            own, nested = walk_quotes(
                item, check, path=f"{path}[{i}]", answer_id=answer_id,
                drop_on_nested_failure=drop_on_nested_failure,
            )
            any_failed = any_failed or nested
            if own or (drop_on_nested_failure and nested):
                continue
            kept.append(item)
        node[:] = kept
        return False, any_failed
    return False, False


def has_outcome_evidence(text: str) -> bool:
    """A Result needs a number or a past-tense outcome verb (§5.3 cheap rule)."""
    n = norm_text(text)
    if _DIGIT.search(n) or _OUTCOME_PATTERNS.search(n):
        return True
    tokens = set(n.split())
    return bool(tokens & OUTCOME_VERBS) or bool(tokens & NUMBER_WORDS)


def ownership_stats(text: str) -> dict[str, Any]:
    """First-person singular vs plural counts and ratios over ``text`` (normalised tokens)."""
    tokens = norm_text(text).split()
    i_count = sum(tok in FIRST_PERSON_SINGULAR for tok in tokens)
    we_count = sum(tok in FIRST_PERSON_PLURAL for tok in tokens)
    total = i_count + we_count
    i_ratio = i_count / total if total else None
    we_ratio = we_count / total if total else None
    return {
        "i_count": i_count,
        "we_count": we_count,
        "i_ratio": i_ratio,
        "we_ratio": we_ratio,
        "team_hiding": bool(we_ratio is not None and we_ratio > WE_RATIO_TEAM_HIDING),
    }


def _ownership_label(stats: Mapping[str, Any]) -> str | None:
    """``schemas.Ownership`` value ("I" / "we" / "mixed"), or None when no pronoun was used."""
    if stats["we_ratio"] is None:
        return None
    if stats["we_ratio"] > WE_RATIO_TEAM_HIDING:
        return "we"
    if stats["i_ratio"] > WE_RATIO_TEAM_HIDING:
        return "I"
    return "mixed"


def validate_analysis(
    analysis_json: Mapping[str, Any] | str,
    words: Transcript | Iterable[Mapping[str, Any]],
    *,
    answer_id: str | None = None,
    prior_words: Mapping[str, Transcript | Iterable[Mapping[str, Any]]] | None = None,
    min_ratio: float = MIN_PARTIAL_RATIO,
    tol_s: float = T_TOLERANCE_S,
    fill_missing_t: bool = False,
    cheap_rules: bool | None = None,
) -> GateResult:
    """Gate every quote in a Stage C analysis (or a Stage B question's ``why.triggered_by``).

    ``words`` is the STT word list for the answer named by ``answer_id`` (default: the
    object's own ``answer_id``). Quotes that name another answer — contradiction probes,
    ``triggered_by`` — are checked against ``prior_words[that_id]``; an id with no transcript
    is dropped as ``unknown_answer``. When the default transcript is unlabelled, quotes with
    an unknown id fall back to it, so ``validate_analysis(question, words_of_A3)`` works for
    a why-trace without naming A3 twice.

    ``t`` must lie inside the matched words' timestamps +/- ``tol_s``; a missing ``t`` drops
    the quote unless ``fill_missing_t`` copies the span's timestamps in. Cheap rules run when
    the object looks like an answer analysis (has ``star``) unless ``cheap_rules`` overrides.

    Returns ``GateResult(analysis, validated, dropped, ownership)``; ``analysis`` is a
    validated deep copy that still satisfies the strict ``schemas.Analysis`` (or
    ``schemas.Question``) model.
    """
    src = json.loads(analysis_json) if isinstance(analysis_json, str) else analysis_json
    analysis: dict[str, Any] = copy.deepcopy(dict(src))
    default_id = answer_id if answer_id is not None else analysis.get("answer_id")
    default_tr = _as_transcript(words)
    transcripts: dict[str, Transcript] = {k: _as_transcript(v) for k, v in (prior_words or {}).items()}
    if isinstance(default_id, str):
        transcripts[default_id] = default_tr

    validated: list[ValidatedQuote] = []
    dropped: list[DroppedQuote] = []

    def check(node: dict[str, Any], path: str, aid: str | None) -> bool:
        quote: str = node["quote"]
        tr = transcripts.get(aid) if aid is not None else default_tr
        if tr is None and default_id is None:
            tr = default_tr
        raw_t = node.get("t")

        def drop(reason: str, score: float | None = None) -> bool:
            dropped.append(DroppedQuote(aid, path, quote, raw_t, reason, score))
            _null(node)
            return False

        if tr is None:
            return drop("unknown_answer")
        if not tr.text:
            return drop("empty_transcript")
        m = match_quote(quote, tr, min_ratio=None)
        if m is None or m.score < min_ratio:
            return drop("no_match", m.score if m else None)
        t = _parse_t(raw_t)
        if t is None:
            if raw_t is None and fill_missing_t:
                t = (m.t_start, m.t_end)
                node["t"] = [t[0], t[1]]
            else:
                return drop("missing_t" if raw_t is None else "bad_t", m.score)
        if t[0] < m.t_start - tol_s or t[1] > m.t_end + tol_s:
            return drop("t_outside", m.score)
        validated.append(ValidatedQuote(aid, path, quote, t, m.word_start, m.word_end, (m.t_start, m.t_end), m.score))
        return True

    walk_quotes(analysis, check, answer_id=default_id, drop_on_nested_failure=True)

    ownership = None
    if cheap_rules or (cheap_rules is None and "star" in analysis):
        ownership = _apply_cheap_rules(analysis, default_tr, default_id, validated, dropped)
    return GateResult(analysis, validated, dropped, ownership)


def _apply_cheap_rules(
    analysis: dict[str, Any],
    tr: Transcript,
    answer_id: str | None,
    validated: list[ValidatedQuote],
    dropped: list[DroppedQuote],
) -> dict[str, Any]:
    star = analysis.get("star")
    star = star if isinstance(star, dict) else {}

    # Rule 1 — a Result claim must be backed by a number or an outcome verb in its quote.
    result = star.get("result")
    if isinstance(result, dict) and result.get("present") is True:
        quote = result.get("quote")
        if not isinstance(quote, str) or not has_outcome_evidence(quote):
            dropped.append(DroppedQuote(answer_id, "star.result", quote, result.get("t"), "result_no_outcome"))
            validated[:] = [v for v in validated if v.path != "star.result"]
            result["present"] = False
            _null(result)

    # Rule 2/3 — ownership is the first-person-singular ratio; we-ratio > 0.7 is team-hiding.
    stats = ownership_stats(tr.text)
    action = star.get("action")
    if isinstance(action, dict):
        # Label the action from its own pronouns when it has any, else from the whole answer.
        local = ownership_stats(action["quote"]) if isinstance(action.get("quote"), str) else stats
        action["ownership"] = _ownership_label(local if local["we_ratio"] is not None else stats)
    return stats
