"""Stage A gate (BLUEPRINT §5.1): a competency survives only if at least one of its
JD quotes is a literal substring of the pasted JD.

The check is exactly the blueprint's ``norm(q) in norm(jd)`` where ``norm`` collapses
whitespace, strips and lower-cases. On top of that, every surviving quote gets
``start``/``end`` character offsets into the *original* JD text (end exclusive), found
with a normalisation-aware search so the app can highlight the sentence even when the
LLM changed case or line breaks. Enforced in code, not in the prompt.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

__all__ = ["norm", "find_quote_offsets", "validate_rubric", "needs_reask", "reask_hint", "PUNCT_FOLD", "MIN_QUOTE_WORDS"]

_WS = re.compile(r"\s+")

# The blueprint re-asks Stage A once when *more than* this many competencies were rejected.
REASK_THRESHOLD = 2

# A quote shorter than this (after normalisation) is not provenance: the §5.1 sketch's
# ``norm(q) in jd_n`` would accept "", "you" or "Node.js". Three keeps the blueprint's own
# 3-word why-trace example ("optimise API latency") legal.
MIN_QUOTE_WORDS = 3

# Pasted JDs (LinkedIn/Notion/Word) carry curly quotes, en/em dashes, non-breaking
# hyphens and spaces; a 9B model quotes them back in ASCII. Folding both sides is what
# keeps criterion 1 provable on real input. Applied after NFKC (which already turns U+00A0
# into a space and U+2011 into U+2010). Deviation from the plain §5.1 sketch is logged in
# docs/DECISIONS.md and pinned by fixtures/jd_fintech_unicode.txt.
PUNCT_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
    "…": "...",
})


def _fold(ch: str) -> str:
    """NFKC + punctuation fold for one source character (may expand to several)."""
    return unicodedata.normalize("NFKC", ch).translate(PUNCT_FOLD)


def norm(s: str) -> str:
    """The gate normaliser: NFKC + punctuation fold, collapse whitespace, strip, lower-case.

    Built through ``_norm_with_map`` so that the string compared and the string whose
    offsets are mapped back are always the same one.
    """
    return _norm_with_map(s)[0]


def _norm_with_map(s: str) -> tuple[str, list[int]]:
    """``norm(s)`` plus, per output character, the index of the source character it came from.

    Built character by character so a match in the normalised string can be mapped back
    to original offsets: a whitespace run collapses onto its first character, leading and
    trailing whitespace vanish, and a character whose lower-case form expands to several
    code points (e.g. 'İ') maps every output character to the same source index.
    ``str.isspace`` and the regex whitespace class agree on every code point, so the string is the
    same one ``norm`` produces except for context-sensitive lower-casing (Greek final
    sigma), which the caller tolerates by treating a failed lookup as "no offsets".
    """
    out: list[str] = []
    idx: list[int] = []
    run_start: int | None = None  # first index of the whitespace run being collapsed
    for i, ch in enumerate(s):
        folded = _fold(ch)
        if not folded or folded.isspace():
            if run_start is None:
                run_start = i
            continue
        if run_start is not None:
            if out:  # interior run -> one space; a leading run is stripped
                out.append(" ")
                idx.append(run_start)
            run_start = None
        for low in folded.lower():
            out.append(low)
            idx.append(i)
    return "".join(out), idx


def _locate(jd_m: str, idx: list[int], quote_n: str) -> tuple[int, int] | None:
    pos = jd_m.find(quote_n)
    if pos < 0:
        return None
    return idx[pos], idx[pos + len(quote_n) - 1] + 1


def find_quote_offsets(jd: str, quote: str) -> tuple[int, int] | None:
    """Offsets ``(start, end)`` of the first occurrence of ``quote`` in the original ``jd``
    under §5.1 normalisation, end exclusive, spanning the JD's own whitespace and case.
    ``None`` when the normalised quote is empty or not a substring of the normalised JD.
    """
    quote_n = norm(quote)
    if not quote_n:
        return None
    jd_m, idx = _norm_with_map(jd)
    return _locate(jd_m, idx, quote_n)


def validate_rubric(jd: str, rubric: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Drop every competency with no literal JD quote; keep only the grounded quotes of the rest.

    Mirrors the blueprint's reference implementation: ``rubric`` is modified in place and
    returned together with the ids of the removed competencies (the list to re-ask for).
    Each surviving quote dict gets ``start``/``end`` offsets into ``jd``. An empty or
    whitespace-only quote is rejected — the reference sketch's ``"" in jd_n`` would have
    let it through, and an empty quote is not provenance.
    """
    jd_n = norm(jd)
    jd_m, idx = _norm_with_map(jd)
    rejected: list[str] = []
    kept: list[dict[str, Any]] = []
    for c in list(rubric.get("competencies") or []):
        ok: list[dict[str, Any]] = []
        for q in c.get("jd_quotes") or []:
            text = q.get("text") if isinstance(q, dict) else None
            if not isinstance(text, str):
                continue
            quote_n = norm(text)
            if not quote_n or len(quote_n.split()) < MIN_QUOTE_WORDS or quote_n not in jd_n:
                continue
            span = _locate(jd_m, idx, quote_n)
            q["start"], q["end"] = span if span else (None, None)
            ok.append(q)
        if ok:
            c["jd_quotes"] = ok
            kept.append(c)
        else:
            rejected.append(c.get("id"))
    rubric["competencies"] = kept
    return rubric, rejected


def needs_reask(rejected: Sequence[str] | int, threshold: int = REASK_THRESHOLD) -> bool:
    """True when more than ``threshold`` competencies were rejected (§5.1: re-run Stage A once)."""
    count = rejected if isinstance(rejected, int) else len(rejected)
    return count > threshold


def reask_hint(rejected: Sequence[str]) -> str:
    """The sentence to append to the Stage A prompt on the single re-ask (§5.1 wording)."""
    listed = ", ".join(str(r) for r in rejected)
    return f"These were not grounded — quote the JD literally or drop them: {listed}."
