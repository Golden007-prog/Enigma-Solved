"""Stage D gate (BLUEPRINT §5.5): a report line may only cite a validated ``(answer_id, quote)``.

The report generator already sees only validated Stage C JSON, but a small model can
still invent or "improve" a quote on the way out. ``filter_report`` walks ``top_fixes``
and ``per_question`` and drops — in code — every bullet whose ``(answer_id, quote)`` pair
is not in the validated set produced by ``quotegate.validate_analysis``. Matching is on
normalised text (``quotegate.norm_text``), so case, punctuation and whitespace differences
pass while any change of wording does not.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

from rapidfuzz import fuzz

from .quotegate import DroppedQuote, ValidatedQuote, norm_text, walk_quotes

__all__ = ["filter_report", "validated_index"]

QuoteRef = ValidatedQuote | Mapping[str, Any] | tuple[str | None, str]

_MISSING = object()

# A boolean STAR strip arrives keyed by the full word (BLUEPRINT §5.3 shape); the Stage D
# report schema spells it S/T/A/R (``schemas.StarStrip``).
_STAR_INITIALS = {"situation": "S", "task": "T", "action": "A", "result": "R"}


def validated_index(
    validated: Iterable[QuoteRef],
) -> dict[tuple[str | None, str], tuple[float, float] | None]:
    """``{(answer_id, normalised quote): t}`` from ``ValidatedQuote``s, dicts with
    ``answer_id``/``quote``[/``t``], or bare ``(answer_id, quote)`` tuples."""
    index: dict[tuple[str | None, str], tuple[float, float] | None] = {}
    for v in validated:
        if isinstance(v, ValidatedQuote):
            key, t = v.key, v.t
        elif isinstance(v, Mapping):
            quote = v.get("quote")
            if not isinstance(quote, str):
                continue
            raw = v.get("t")
            key = (v.get("answer_id"), norm_text(quote))
            t = (float(raw[0]), float(raw[1])) if isinstance(raw, (list, tuple)) and len(raw) == 2 else None
        else:
            aid, quote = v
            key, t = (aid, norm_text(quote)), None
        index.setdefault(key, t)
    return index


def filter_report(
    report_json: Mapping[str, Any] | str,
    validated_quotes: Iterable[QuoteRef],
    *,
    drop_sections: Iterable[str] = ("top_fixes",),
    null_sections: Iterable[str] = ("per_question",),
    answer_ids: Mapping[str, str] | None = None,
    min_ratio: float | None = None,
) -> tuple[dict[str, Any], list[DroppedQuote]]:
    """Return ``(filtered_report, dropped)``; the input is deep-copied, not modified.

    In ``drop_sections`` (``top_fixes``) a bullet whose quote is not validated is removed
    from the list. In ``null_sections`` (``per_question``) the entry itself survives — it
    carries the STAR strip and verdict — and only the offending ``quote``/``t`` are nulled;
    lists nested inside an entry (e.g. ``bullets``) still have failing items removed. The
    ``answer_id`` for a quote is the nearest enclosing one; ``answer_ids`` maps a
    ``question_id`` to an ``answer_id`` for entries that only carry the former. A bullet
    with no resolvable ``answer_id`` is dropped as ``no_answer_id``. A validated pair's
    ``t`` is copied onto a bullet that has none, so every surviving line can be replayed.
    ``min_ratio`` (off by default) additionally accepts a bullet whose quote scores at
    least that ``fuzz.ratio`` against a validated quote of the same answer.
    """
    src = json.loads(report_json) if isinstance(report_json, str) else report_json
    report: dict[str, Any] = copy.deepcopy(dict(src))
    index = validated_index(validated_quotes)
    by_answer: dict[str | None, list[tuple[str, tuple[float, float] | None]]] = {}
    for (aid, quote_n), t in index.items():
        by_answer.setdefault(aid, []).append((quote_n, t))
    dropped: list[DroppedQuote] = []

    def check(node: dict[str, Any], path: str, aid: str | None) -> bool:
        quote: str = node["quote"]

        def drop(reason: str, score: float | None = None) -> bool:
            dropped.append(DroppedQuote(aid, path, quote, node.get("t"), reason, score))
            node["quote"] = None
            if "t" in node:
                node["t"] = None
            return False

        if aid is None:
            return drop("no_answer_id")
        quote_n = norm_text(quote)
        t: Any = index.get((aid, quote_n), _MISSING)
        score: float | None = None
        if t is _MISSING and min_ratio is not None and by_answer.get(aid):
            score, t_best = max(((fuzz.ratio(quote_n, q), tt) for q, tt in by_answer[aid]), key=lambda x: x[0])
            if score >= min_ratio:
                t = t_best
        if t is _MISSING:
            return drop("not_validated", score)
        if node.get("t") is None and t is not None:
            node["t"] = [t[0], t[1]]
        return True

    def resolve_answer_id(entry: dict[str, Any]) -> None:
        if answer_ids and not isinstance(entry.get("answer_id"), str):
            qid = entry.get("question_id")
            if isinstance(qid, str) and qid in answer_ids:
                entry["answer_id"] = answer_ids[qid]

    def canonicalise_per_question(entry: dict[str, Any]) -> None:
        """Shape a per-question row for ``schemas.PerQuestion`` (strict): ``question_id`` is
        not carried once ``answer_id`` is known, and a boolean STAR strip keyed
        situation/task/action/result becomes the S/T/A/R form. A STAR strip whose values are
        objects (quotes + timestamps) is left alone — those quotes are what the gate validates.
        """
        if isinstance(entry.get("answer_id"), str):
            entry.pop("question_id", None)
        star = entry.get("star")
        if isinstance(star, dict) and star and all(isinstance(v, bool) for v in star.values()):
            if set(star) <= set(_STAR_INITIALS):
                entry["star"] = {_STAR_INITIALS[k]: star[k] for k in _STAR_INITIALS if k in star}

    for name in drop_sections:
        section = report.get(name)
        if isinstance(section, list):
            for entry in section:
                if isinstance(entry, dict):
                    resolve_answer_id(entry)
            walk_quotes(section, check, path=name)
        elif isinstance(section, dict):
            resolve_answer_id(section)
            walk_quotes(section, check, path=name)

    for name in null_sections:
        section = report.get(name)
        entries = section if isinstance(section, list) else [section] if isinstance(section, dict) else []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            resolve_answer_id(entry)
            canonicalise_per_question(entry)
            # Walked as a dict, not as a list item, so the entry is never removed.
            walk_quotes(entry, check, path=f"{name}[{i}]" if isinstance(section, list) else name)

    return report, dropped
