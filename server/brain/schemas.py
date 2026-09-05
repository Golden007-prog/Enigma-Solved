"""Interview Cracker brain — pydantic v2 models for BLUEPRINT §5 and the
LM Studio strict-JSON-schema exporter.

Two layers live here.

1. Canonical models (``Rubric``, ``Question``, ``Analysis``, ``Report`` and their
   parts).  Their dumped JSON is the §5.1–§5.5 shape, key for key.  This is what
   the server stores under ``data/sessions/<id>/`` and what the phone renders.

2. ``llm_schema(Model)`` derives, from a canonical model, the schema handed to LM
   Studio as ``response_format={"type": "json_schema", ...}``.  LM Studio turns
   that schema into a llama.cpp GBNF grammar, so it has to stay inside what the
   grammar converter supports and it has to be *strict*: every object closed
   (``additionalProperties: false``), every property required, optional values
   spelled as ``null`` unions rather than absent keys.  README-schemas.md lists
   every transform and why it exists.

Three small devices bridge the two layers:

* ``LLM_EXCLUDE`` (class attribute) — fields the server fills after the call and
  never asks the model for.  Example: ``JDQuote.start/end`` character offsets.
* ``LLM_OVERRIDES`` (class attribute) — fields whose LLM-facing type differs from
  the canonical one.  Example: ``Analysis.evidence_updates`` is a dict-of-dicts
  in §5.3, which cannot be expressed with ``additionalProperties: false``; the
  model emits a list of ``EvidenceUpdate`` triples and a validator folds them
  back into the dict.
* Draft models (``QuestionDraft``, ``ReportDraft``) — the LLM-authored subset of
  a stage whose canonical object is mostly assembled by server code (the Agenda
  Manager builds the why-trace; the metrics code builds coverage and delivery).

Python 3.12, pydantic v2, nothing else.  ``python brain/schemas.py`` prints every
LLM schema and runs the round-trip / strictness self-check.
"""

from __future__ import annotations

import copy
import enum
import json
import re
from typing import Any, ClassVar, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

__all__ = [
    # enums
    "Seniority", "CompetencyType", "Priority", "LadderRung", "Strategy", "EvidenceLevel",
    "Verdict", "Mood", "Ownership", "LLM_OWNERSHIP", "Band",
    "DEFAULT_LADDER", "FOLLOW_UP_STRATEGIES", "MOOD_INDEX",
    # shared
    "StrictBase", "Span", "Quote", "AnchoredQuote",
    # stage A
    "JDQuote", "Mix", "Competency", "Rubric",
    # stage B
    "Why", "Question", "QuestionDraft",
    # stage C
    "StarComponent", "Star", "Specificity", "KeywordCoverage", "Contradiction",
    "EvidenceUpdate", "Analysis",
    # stage D
    "TopFix", "StarStrip", "PerQuestion", "CoverageCell", "CoverageRow",
    "CoverageMatrix", "AnswerDelivery", "DeliveryMetrics", "ReportDraft", "Report",
    # exporter
    "llm_schema", "llm_response_format", "check_llm_schema", "STAGE_LLM_MODELS",
    "SPEC_EXAMPLES", "ANALYSIS_LLM_FORM",
]


# ---------------------------------------------------------------------------
# Enums (§5.1–§5.3, moods from §4.1)
# ---------------------------------------------------------------------------


class Seniority(enum.StrEnum):
    FRESHER = "fresher"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class CompetencyType(enum.StrEnum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"  # the §5.1 JSON spells it "behavioral"; the prose says "behavioural"


class Priority(enum.StrEnum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class LadderRung(enum.StrEnum):
    """§2.3 / §5.1 difficulty ladder, declared in escalation order."""

    RECALL = "recall"
    APPLIED_EXAMPLE = "applied example"
    TRADE_OFF_OR_FAILURE = "trade-off or failure"
    DESIGN_UNDER_CONSTRAINT = "design under constraint"


DEFAULT_LADDER: tuple[LadderRung, ...] = tuple(LadderRung)


class Strategy(enum.StrEnum):
    """§5.2 — the eight question strategies."""

    OPEN_PROBE = "open_probe"
    EVIDENCE_PROBE = "evidence_probe"
    DIG_DEEPER_VAGUE = "dig_deeper_vague"
    DIG_DEEPER_GENERIC = "dig_deeper_generic"
    QUANTIFY_RESULT = "quantify_result"
    OWNERSHIP_PROBE = "ownership_probe"
    CONTRADICTION_PROBE = "contradiction_probe"
    ESCALATE = "escalate"


# §5.2 policy step 1: a follow-up stays on the same competency and quotes the last
# answer. open_probe and escalate start a fresh question instead.
FOLLOW_UP_STRATEGIES: frozenset[Strategy] = frozenset(
    {
        Strategy.EVIDENCE_PROBE,
        Strategy.DIG_DEEPER_VAGUE,
        Strategy.DIG_DEEPER_GENERIC,
        Strategy.QUANTIFY_RESULT,
        Strategy.OWNERSHIP_PROBE,
        Strategy.CONTRADICTION_PROBE,
    }
)


class EvidenceLevel(enum.StrEnum):
    NONE = "none"
    WEAK = "weak"
    STRONG = "strong"


class Verdict(enum.StrEnum):
    VAGUE = "vague"
    GENERIC = "generic"
    ADEQUATE = "adequate"
    STRONG = "strong"


class Mood(enum.StrEnum):
    """§4.1 ``reaction`` moods. The Rive ``mood`` number input is ``MOOD_INDEX[m]`` (§6.1)."""

    NEUTRAL = "neutral"
    INTERESTED = "interested"
    THINKING = "thinking"
    UNIMPRESSED = "unimpressed"


MOOD_INDEX: dict[Mood, int] = {
    Mood.NEUTRAL: 0,
    Mood.INTERESTED: 1,
    Mood.THINKING: 2,
    Mood.UNIMPRESSED: 3,
}


class Ownership(enum.StrEnum):
    """Who did the work in a STAR component. The LLM is offered I / we / unclear
    (brain/prompts Stage C); the we-ratio cheap rule in quotegate.py may overwrite the
    action's ownership with "mixed". The LLM schema is narrowed to the first three
    (see ``StarComponent.LLM_OVERRIDES``); the canonical model accepts all four."""

    I = "I"
    WE = "we"
    UNCLEAR = "unclear"
    MIXED = "mixed"


LLM_OWNERSHIP = Literal["I", "we", "unclear"]


class Band(enum.StrEnum):
    """§5.5 overall band — deliberately not a score out of ten. Values are the phrases
    the Stage D prompt offers (brain/prompts ``BANDS``); they are shown verbatim in the app."""

    NOT_YET_READY = "not yet ready"
    BORDERLINE = "borderline"
    READY_WITH_POLISH = "ready with polish"
    STRONG = "strong"


# ---------------------------------------------------------------------------
# Base + shared pieces
# ---------------------------------------------------------------------------


class StrictBase(BaseModel):
    """Common config. Unknown keys are rejected: grammar-constrained output never has
    any, so an extra key means the schema and the model drifted apart."""

    model_config = ConfigDict(extra="forbid")

    # Directives read by llm_schema(); see the module docstring.
    LLM_EXCLUDE: ClassVar[frozenset[str]] = frozenset()
    LLM_OVERRIDES: ClassVar[dict[str, Any]] = {}


# [t_start, t_end] in seconds, taken from STT word timestamps.
Span = tuple[float, float]


class Quote(StrictBase):
    """A verbatim transcript span. Kept only if it survives the RapidFuzz gate (§5.3)."""

    quote: str
    t: Span


class AnchoredQuote(StrictBase):
    """A quote that also names the answer it came from (§5.2 ``triggered_by``)."""

    answer_id: str
    quote: str
    t: Span


# ---------------------------------------------------------------------------
# Stage A — JD → rubric with provenance (§5.1)
# ---------------------------------------------------------------------------


class JDQuote(StrictBase):
    """A verbatim JD sentence. ``start``/``end`` are character offsets into the pasted
    JD; the LLM is never asked for them (a 9B model cannot count characters) — the
    substring gate in rubric.py recomputes them after it has accepted ``text``."""

    text: str
    start: int | None = None
    end: int | None = None

    LLM_EXCLUDE: ClassVar[frozenset[str]] = frozenset({"start", "end"})


class Mix(StrictBase):
    """Behavioural/technical weighting. Renormalised to sum to 1 so the model may
    answer in percentages or rough weights without failing validation."""

    behavioral: float
    technical: float

    @model_validator(mode="after")
    def _normalise(self) -> Mix:
        b = max(float(self.behavioral), 0.0)
        t = max(float(self.technical), 0.0)
        total = b + t
        if total <= 0.0:
            b = t = 0.5
            total = 1.0
        self.behavioral = round(b / total, 3)
        self.technical = round(t / total, 3)
        return self


class Competency(StrictBase):
    id: str
    name: str
    type: CompetencyType
    priority: Priority
    jd_quotes: list[JDQuote] = Field(min_length=1)
    evidence_expected: list[str] = Field(min_length=1, max_length=4)
    difficulty_ladder: list[LadderRung] = Field(default_factory=lambda: list(DEFAULT_LADDER))


class Rubric(StrictBase):
    """Stage A output. The prompt asks for 5–8 competencies; the lower bound is not
    enforced here because the substring gate may legitimately remove some."""

    role_title: str
    seniority: Seniority
    behavioral_technical_mix: Mix
    competencies: list[Competency] = Field(min_length=1, max_length=8)

    def competency(self, competency_id: str) -> Competency | None:
        return next((c for c in self.competencies if c.id == competency_id), None)


# ---------------------------------------------------------------------------
# Stage B — Agenda Manager → next question with a why-trace (§5.2)
# ---------------------------------------------------------------------------


class Why(StrictBase):
    competency_id: str
    jd_quote: str
    ladder_rung: LadderRung
    strategy: Strategy
    triggered_by: AnchoredQuote | None = None


class Question(StrictBase):
    """The §5.2 object. ``time_limit_s`` is ``None`` on the Warm-up dial (§5.6: no
    timer). The wire frame in §4.1 renames ``question_id`` to ``id``; server.py does that."""

    question_id: str
    text: str
    why: Why
    time_limit_s: int | None = None
    reaction_before: Mood = Mood.NEUTRAL


class QuestionDraft(StrictBase):
    """What Stage B actually asks the LLM for (brain/prompts STAGE_B). The Agenda
    Manager has already chosen the competency, JD quote, strategy, ladder rung and
    trigger (that is the point of §2.3), so the model only words the question and
    names the evidence-gap item it aimed at; agenda.py checks ``evidence_item`` is one
    of the offered gap items before recording which cell the question probes."""

    text: str
    evidence_item: str


# ---------------------------------------------------------------------------
# Stage C — answer analysis (§5.3)
# ---------------------------------------------------------------------------


class StarComponent(StrictBase):
    present: bool
    quote: str | None = None
    t: Span | None = None
    ownership: Ownership | None = None

    # The model chooses among the three values the prompt names; "mixed" is reserved
    # for the server-side we-ratio rule.
    LLM_OVERRIDES: ClassVar[dict[str, Any]] = {"ownership": LLM_OWNERSHIP | None}


class Star(StrictBase):
    situation: StarComponent
    task: StarComponent
    action: StarComponent
    result: StarComponent


class Specificity(StrictBase):
    """``scale`` is a constant the §5.3 JSON carries for readers; the model is not asked
    to type it (the prompt's shape omits it), the default supplies it."""

    score: int = Field(ge=0, le=3)
    scale: Literal["0-3"] = "0-3"
    missing: list[str]

    LLM_EXCLUDE: ClassVar[frozenset[str]] = frozenset({"scale"})


class KeywordCoverage(StrictBase):
    hit: list[str]
    missed: list[str]


class Contradiction(StrictBase):
    """§5.3 lists ``contradictions[]`` without a shape; this is the one the Stage C
    prompt describes. ``quote``/``t`` come from the current answer and go through the
    quote gate; ``conflicts_with`` is the prior claim as it was listed in the prompt
    (analyzer.py passes prior claims as already-validated quote strings)."""

    quote: str
    t: Span
    conflicts_with: str


class EvidenceUpdate(StrictBase):
    """One cell of the coverage matrix, as the LLM emits it (LLM-facing form of
    ``Analysis.evidence_updates``)."""

    competency_id: str
    evidence_item: str
    level: EvidenceLevel


class Analysis(StrictBase):
    """Stage C output. Field order is generation order under the grammar, so the
    judgement fields (star, specificity, coverage) come before ``verdict``."""

    answer_id: str
    star: Star
    specificity: Specificity
    jd_keyword_coverage: KeywordCoverage
    hedges: list[Quote]
    contradictions: list[Contradiction]
    verdict: Verdict
    evidence_updates: dict[str, dict[str, EvidenceLevel]]
    next_strategy: Strategy
    reaction: Mood

    LLM_OVERRIDES: ClassVar[dict[str, Any]] = {"evidence_updates": list[EvidenceUpdate]}

    @field_validator("evidence_updates", mode="before")
    @classmethod
    def _fold_evidence_updates(cls, value: Any) -> Any:
        """Accept the LLM's list of triples as well as the canonical nested dict."""
        if not isinstance(value, list):
            return value
        folded: dict[str, dict[str, Any]] = {}
        for item in value:
            if isinstance(item, EvidenceUpdate):
                item = item.model_dump()
            if not isinstance(item, dict):
                raise ValueError("evidence_updates entries must be objects")
            try:
                cid, ev, level = item["competency_id"], item["evidence_item"], item["level"]
            except KeyError as e:
                raise ValueError(f"evidence_updates entry missing {e.args[0]}") from None
            folded.setdefault(str(cid), {})[str(ev)] = level
        return folded

    def evidence_update_list(self) -> list[EvidenceUpdate]:
        return [
            EvidenceUpdate(competency_id=cid, evidence_item=ev, level=level)
            for cid, cells in self.evidence_updates.items()
            for ev, level in cells.items()
        ]


# ---------------------------------------------------------------------------
# Stage D — report (§5.5, delivery from §5.4, coverage from §5.2)
# ---------------------------------------------------------------------------


class TopFix(StrictBase):
    behaviour: str
    answer_id: str
    quote: str
    t: Span
    rubric_line: str
    why_it_matters: str
    stronger_version: str


class StarStrip(StrictBase):
    """S/T/A/R present-or-not, keyed by initial as the Stage D prompt spells it."""

    S: bool
    T: bool
    A: bool
    R: bool


class PerQuestion(StrictBase):
    """One row of the per-answer strip. ``question_id`` is not carried: answers and
    questions pair 1:1 (``A3`` ↔ ``Q3``) and the server owns that mapping."""

    answer_id: str
    star: StarStrip
    verdict: Verdict
    key_quote: Quote | None = None


class CoverageCell(StrictBase):
    evidence_item: str
    level: EvidenceLevel


class CoverageRow(StrictBase):
    competency_id: str
    name: str
    priority: Priority
    cells: list[CoverageCell]

    @property
    def is_empty(self) -> bool:
        return all(c.level is EvidenceLevel.NONE for c in self.cells)


class CoverageMatrix(StrictBase):
    """Report view of the Agenda Manager state ``coverage[competency_id][evidence_item]``
    (§5.2), joined with the rubric so the phone can render names and priorities."""

    rows: list[CoverageRow]

    @classmethod
    def from_state(
        cls, rubric: Rubric, coverage: dict[str, dict[str, EvidenceLevel | str]]
    ) -> CoverageMatrix:
        rows: list[CoverageRow] = []
        for comp in rubric.competencies:
            cells = coverage.get(comp.id, {})
            rows.append(
                CoverageRow(
                    competency_id=comp.id,
                    name=comp.name,
                    priority=comp.priority,
                    cells=[
                        CoverageCell(evidence_item=ev, level=EvidenceLevel(cells.get(ev, EvidenceLevel.NONE)))
                        for ev in comp.evidence_expected
                    ],
                )
            )
        return cls(rows=rows)

    def empty_must_haves(self) -> list[CoverageRow]:
        """The rows the report uses to explain the band (§2.5)."""
        return [r for r in self.rows if r.priority is Priority.MUST_HAVE and r.is_empty]


class AnswerDelivery(StrictBase):
    answer_id: str
    duration_s: float
    time_limit_s: int | None = None
    wpm: float | None = None
    pause_count: int = 0
    longest_pause_s: float | None = None
    latency_to_first_word_s: float | None = None


class DeliveryMetrics(StrictBase):
    """§5.4, computed by code from timestamps and audio — never by the LLM. Anything
    that needs an optional pass (fillers → Whisper) or a baseline (monotone → Q1) is
    ``None`` when unavailable."""

    wpm: float | None = None
    wpm_band: tuple[int, int] = (130, 170)
    pause_count: int = 0  # pauses > 1.0 s
    longest_pause_s: float | None = None
    latency_to_first_word_s: float | None = None
    fillers_per_min: float | None = None
    hedge_count: int = 0
    time_used_ratio: float | None = None  # mean answer length / time_limit_s
    jd_keyword_coverage: KeywordCoverage = Field(default_factory=lambda: KeywordCoverage(hit=[], missed=[]))
    f0_sd_hz: float | None = None
    rms_variance: float | None = None
    monotone: bool | None = None
    per_answer: list[AnswerDelivery] = Field(default_factory=list)


class ReportDraft(StrictBase):
    """The LLM-authored part of Stage D. It sees only validated Stage C JSON, the
    metrics and the coverage matrix (§5.5); ``coverage_matrix`` and ``delivery`` are
    attached by code in ``Report.from_draft`` rather than re-typed by the model."""

    top_fixes: list[TopFix] = Field(min_length=1, max_length=3)
    per_question: list[PerQuestion]
    overall_band: Band
    band_mover: str  # §5.5: "a band plus the one thing that would move it"


class Report(StrictBase):
    """§5.5 output. ``top_fixes`` may end up shorter than the draft's because report.py
    drops any fix whose (answer_id, quote) pair is not in the validated set."""

    top_fixes: list[TopFix] = Field(max_length=3)
    per_question: list[PerQuestion]
    coverage_matrix: CoverageMatrix
    delivery: DeliveryMetrics
    overall_band: Band
    band_mover: str

    @classmethod
    def from_draft(
        cls, draft: ReportDraft, coverage_matrix: CoverageMatrix, delivery: DeliveryMetrics
    ) -> Report:
        return cls(
            top_fixes=list(draft.top_fixes),
            per_question=list(draft.per_question),
            coverage_matrix=coverage_matrix,
            delivery=delivery,
            overall_band=draft.overall_band,
            band_mover=draft.band_mover,
        )


# Which model each stage hands to LM Studio.
STAGE_LLM_MODELS: dict[str, type[StrictBase]] = {
    "A": Rubric,
    "B": QuestionDraft,
    "C": Analysis,
    "D": ReportDraft,
}


# ---------------------------------------------------------------------------
# LM Studio strict schema exporter
# ---------------------------------------------------------------------------

# Keys that carry no meaning for a grammar and only bloat the payload. ``description``
# goes too: LM Studio compiles the schema to GBNF and never shows it to the model, so
# field semantics belong in the stage prompt (brain/prompts/), not here.
_STRIP_KEYS = frozenset(
    {
        "title", "description", "default", "examples", "$schema", "$id", "$comment",
        "deprecated", "readOnly", "writeOnly",
    }
)
# Keys llama.cpp's json-schema-to-grammar does not implement (or implements
# partially, like ``pattern``). Enforced by pydantic on parse instead.
_UNSUPPORTED_KEYS = frozenset(
    {
        "format", "pattern", "patternProperties", "propertyNames", "multipleOf", "uniqueItems",
        "contains", "minContains", "maxContains", "dependentRequired", "dependentSchemas",
        "if", "then", "else", "not", "unevaluatedProperties", "unevaluatedItems",
        "minProperties", "maxProperties",
    }
)
# Numeric bounds are grammar-supported for integers only.
_NUMBER_BOUNDS = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
# Keys whose value is not a schema and must not be walked as one.
_VERBATIM_KEYS = frozenset({"enum", "const", "required", "type", "description"})


def llm_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for LM Studio's ``json_schema`` response format, strict mode.

    Guarantees (checked by ``check_llm_schema`` before returning):
    * no ``$ref``/``$defs`` — everything inlined, cycles rejected;
    * every object has ``additionalProperties: false`` and lists *all* its
      properties in ``required`` (optional fields are ``anyOf [..., null]``);
    * no free-form dicts, no ``format``/``pattern``/``patternProperties``, no
      numeric bounds on floats, tuples spelled as ``items`` + min/maxItems.
    """
    raw = model.model_json_schema()
    defs: dict[str, Any] = raw.pop("$defs", {})
    _apply_directives(model, raw, defs)
    schema = _inline_refs(raw, defs, ())
    schema = _strictify(schema)
    problems = check_llm_schema(schema)
    if problems:
        raise ValueError(f"{model.__name__}: schema is not strict:\n  " + "\n  ".join(problems))
    return schema


def llm_response_format(model: type[BaseModel], name: str | None = None) -> dict[str, Any]:
    """The ``response_format`` value for an OpenAI-compatible LM Studio call."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name or _snake(model.__name__),
            "strict": True,
            "schema": llm_schema(model),
        },
    }


def check_llm_schema(schema: dict[str, Any]) -> list[str]:
    """Return every way ``schema`` breaks the strict-mode contract (empty = fine)."""
    problems: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
            return
        if not isinstance(node, dict):
            return
        for key in node:
            if key in ("$ref", "$defs", "definitions"):
                problems.append(f"{path}: {key} is not allowed (inline it)")
            if key in _UNSUPPORTED_KEYS:
                problems.append(f"{path}: keyword {key!r} is not grammar-supported")
        kind = node.get("type")
        if kind == "object":
            props = node.get("properties")
            if not isinstance(props, dict):
                problems.append(f"{path}: free-form object (dict field?) has no properties")
            else:
                if node.get("additionalProperties") is not False:
                    problems.append(f"{path}: additionalProperties must be false")
                if node.get("required") != list(props):
                    problems.append(f"{path}: required must list every property in order")
                for name, sub in props.items():
                    walk(sub, f"{path}.{name}")
        elif kind == "number" and any(b in node for b in _NUMBER_BOUNDS):
            problems.append(f"{path}: numeric bounds on a float are not grammar-supported")
        elif kind == "array" and "items" not in node and "prefixItems" not in node:
            problems.append(f"{path}: array without items")
        for key, value in node.items():
            if key == "properties" or key in _VERBATIM_KEYS:
                continue
            walk(value, f"{path}.{key}")

    walk(schema, "$")
    return problems


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _reachable_models(tp: Any, seen: set[type[BaseModel]] | None = None) -> set[type[BaseModel]]:
    """Every BaseModel class reachable from ``tp`` through field annotations and
    LLM_OVERRIDES types."""
    seen = set() if seen is None else seen
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        if tp in seen:
            return seen
        seen.add(tp)
        for field in tp.model_fields.values():
            _reachable_models(field.annotation, seen)
        for override in getattr(tp, "LLM_OVERRIDES", {}).values():
            _reachable_models(override, seen)
        return seen
    for arg in get_args(tp):
        _reachable_models(arg, seen)
    return seen


def _apply_directives(root: type[BaseModel], raw: dict[str, Any], defs: dict[str, Any]) -> None:
    """Rewrite the pydantic schema in place per LLM_OVERRIDES then LLM_EXCLUDE.
    Overrides go first because they can add new ``$defs`` that excludes must see."""
    classes = sorted(_reachable_models(root), key=lambda c: c.__name__)

    def node_for(cls: type[BaseModel]) -> dict[str, Any]:
        node = raw if cls is root else defs.get(cls.__name__)
        if node is None:
            raise LookupError(f"{cls.__name__} carries LLM directives but has no $defs entry of that name")
        return node

    for cls in classes:
        for name, typ in getattr(cls, "LLM_OVERRIDES", {}).items():
            node = node_for(cls)
            props = node.setdefault("properties", {})
            if name not in props:
                raise KeyError(f"{cls.__name__}.LLM_OVERRIDES names unknown field {name!r}")
            sub = TypeAdapter(typ).json_schema()
            defs.update(sub.pop("$defs", {}))
            props[name] = sub

    for cls in classes:
        exclude = getattr(cls, "LLM_EXCLUDE", frozenset())
        if not exclude:
            continue
        node = node_for(cls)
        props = node.setdefault("properties", {})
        for name in exclude:
            if name not in props:
                raise KeyError(f"{cls.__name__}.LLM_EXCLUDE names unknown field {name!r}")
            del props[name]
        node["required"] = [r for r in node.get("required", []) if r not in exclude]


def _inline_refs(node: Any, defs: dict[str, Any], stack: tuple[str, ...]) -> Any:
    if isinstance(node, list):
        return [_inline_refs(item, defs, stack) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        if name in stack:
            raise ValueError(
                "recursive $ref " + " -> ".join(stack + (name,)) + "; grammar schemas must be trees"
            )
        if name not in defs:
            raise KeyError(f"unresolved $ref {node['$ref']!r}")
        # Sibling keys next to a $ref (pydantic puts a field description there) win.
        merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
        return _inline_refs(merged, defs, stack + (name,))
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {n: _inline_refs(s, defs, stack) for n, s in value.items()}
        else:
            out[key] = _inline_refs(value, defs, stack)
    return out


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIP_KEYS or key in _UNSUPPORTED_KEYS:
            continue
        if key == "properties":
            out[key] = {n: _strictify(s) for n, s in value.items()}
        elif key in _VERBATIM_KEYS:
            out[key] = value
        else:
            out[key] = _strictify(value)
    # Older pydantic wraps "$ref + description" as a one-element allOf; flatten it.
    if isinstance(out.get("allOf"), list) and len(out["allOf"]) == 1:
        inner = out.pop("allOf")[0]
        out = {**inner, **out}
    kind = out.get("type")
    if kind == "object":
        if "properties" not in out:
            raise ValueError(
                "free-form object (a dict-typed field) reached the LLM schema; "
                "give its model an LLM_OVERRIDES entry that spells it as a list"
            )
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    elif kind == "number":
        for bound in _NUMBER_BOUNDS:
            out.pop(bound, None)
    if "prefixItems" in out:
        items = out.pop("prefixItems")
        if any(item != items[0] for item in items):
            raise ValueError("heterogeneous tuple has no portable grammar form; use a model instead")
        out["items"] = items[0]
        out["minItems"] = len(items)
        out["maxItems"] = len(items)
    return out


# ---------------------------------------------------------------------------
# The §5 examples, verbatim, as fixtures for tests and the self-check
# ---------------------------------------------------------------------------

SPEC_EXAMPLES: dict[type[StrictBase], dict[str, Any]] = {
    Rubric: {
        "role_title": "Backend Developer (Node.js)",
        "seniority": "fresher",
        "behavioral_technical_mix": {"behavioral": 0.4, "technical": 0.6},
        "competencies": [
            {
                "id": "C1",
                "name": "REST API design in Node.js",
                "type": "technical",
                "priority": "must_have",
                "jd_quotes": [{"text": "Build and maintain RESTful services in Node.js", "start": 412, "end": 458}],
                "evidence_expected": ["designed endpoints", "handled auth or versioning", "measured latency"],
                "difficulty_ladder": ["recall", "applied example", "trade-off or failure", "design under constraint"],
            }
        ],
    },
    Question: {
        "question_id": "Q4",
        "text": "You mentioned caching. What exactly did you cache, and how did you decide the TTL?",
        "why": {
            "competency_id": "C3",
            "jd_quote": "optimise API latency",
            "ladder_rung": "trade-off or failure",
            "strategy": "dig_deeper_vague",
            "triggered_by": {"answer_id": "A3", "quote": "we used caching and stuff", "t": [8.2, 11.9]},
        },
        "time_limit_s": 90,
        "reaction_before": "interested",
    },
    QuestionDraft: {
        "text": "You mentioned caching. What exactly did you cache, and how did you decide the TTL?",
        "evidence_item": "measured latency",
    },
    Analysis: {
        "answer_id": "A3",
        "star": {
            "situation": {"present": True, "quote": "in my final-year project", "t": [0.4, 1.9]},
            "task": {"present": False},
            "action": {"present": True, "quote": "we used caching and stuff", "t": [8.2, 11.9], "ownership": "we"},
            "result": {"present": False},
        },
        "specificity": {"score": 1, "scale": "0-3", "missing": ["named technology", "number", "time frame"]},
        "jd_keyword_coverage": {"hit": ["caching"], "missed": ["latency", "TTL", "Redis"]},
        "hedges": [{"quote": "I think maybe", "t": [5.1, 5.8]}],
        "contradictions": [],
        "verdict": "vague",
        "evidence_updates": {"C3": {"measured latency": "none", "designed endpoints": "weak"}},
        "next_strategy": "dig_deeper_vague",
        "reaction": "neutral",
    },
    ReportDraft: {
        "top_fixes": [
            {
                "behaviour": "Result missing",
                "answer_id": "A2",
                "quote": "and it worked fine",
                "t": [41.0, 42.1],
                "rubric_line": "C3 · measured latency",
                "why_it_matters": "Without a number the interviewer cannot tell whether the cache helped.",
                "stronger_version": "…and p95 latency dropped from 800 ms to 120 ms after we cached the product list.",
            }
        ],
        "per_question": [
            {
                "answer_id": "A2",
                "star": {"S": True, "T": False, "A": True, "R": False},
                "verdict": "vague",
                "key_quote": {"quote": "and it worked fine", "t": [41.0, 42.1]},
            }
        ],
        "overall_band": "borderline",
        "band_mover": "State one measured result per answer.",
    },
}

# The exact bytes a grammar-constrained model would emit for the §5.3 example:
# every key present, absent values as null, no `scale`, evidence_updates as triples.
ANALYSIS_LLM_FORM: dict[str, Any] = {
    "answer_id": "A3",
    "star": {
        "situation": {"present": True, "quote": "in my final-year project", "t": [0.4, 1.9], "ownership": None},
        "task": {"present": False, "quote": None, "t": None, "ownership": None},
        "action": {"present": True, "quote": "we used caching and stuff", "t": [8.2, 11.9], "ownership": "we"},
        "result": {"present": False, "quote": None, "t": None, "ownership": None},
    },
    "specificity": {"score": 1, "missing": ["named technology", "number", "time frame"]},
    "jd_keyword_coverage": {"hit": ["caching"], "missed": ["latency", "TTL", "Redis"]},
    "hedges": [{"quote": "I think maybe", "t": [5.1, 5.8]}],
    "contradictions": [],
    "verdict": "vague",
    "evidence_updates": [
        {"competency_id": "C3", "evidence_item": "measured latency", "level": "none"},
        {"competency_id": "C3", "evidence_item": "designed endpoints", "level": "weak"},
    ],
    "next_strategy": "dig_deeper_vague",
    "reaction": "neutral",
}


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def _drop_keys(obj: Any, names: frozenset[str]) -> Any:
    if isinstance(obj, dict):
        return {k: _drop_keys(v, names) for k, v in obj.items() if k not in names}
    if isinstance(obj, list):
        return [_drop_keys(x, names) for x in obj]
    return obj


def _import_prompts() -> Any:
    """``brain.prompts`` when available — as a package sibling, or loaded by path from
    the directory next to this file when schemas.py is run as a script. ``None`` when
    the prompts module does not exist (yet)."""
    if __package__:
        try:
            from . import prompts  # type: ignore[import-not-found]
        except ImportError:
            return None
        return prompts
    import importlib.util
    from pathlib import Path

    init = Path(__file__).resolve().with_name("prompts") / "__init__.py"
    if not init.is_file():
        return None
    spec = importlib.util.spec_from_file_location("brain_prompts_for_self_check", init)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _self_check() -> None:
    # 1. Every §5 example parses and survives a JSON round trip.
    for model, example in SPEC_EXAMPLES.items():
        obj = model.model_validate(example)
        dumped = obj.model_dump(mode="json")
        assert model.model_validate(dumped) == obj, model.__name__
        assert model.model_validate_json(json.dumps(dumped)) == obj, model.__name__
        print(f"round-trip ok: {model.__name__}")

    # 2. The LLM-form Analysis folds into the canonical dict; the gate's "mixed" parses.
    canonical = Analysis.model_validate(SPEC_EXAMPLES[Analysis])
    from_llm = Analysis.model_validate(ANALYSIS_LLM_FORM)
    assert from_llm == canonical
    assert from_llm.model_dump(mode="json")["evidence_updates"] == SPEC_EXAMPLES[Analysis]["evidence_updates"]
    assert [u.model_dump() for u in from_llm.evidence_update_list()] == ANALYSIS_LLM_FORM["evidence_updates"]
    assert from_llm.model_dump(mode="json")["specificity"]["scale"] == "0-3"
    gated = copy.deepcopy(ANALYSIS_LLM_FORM)
    gated["star"]["action"]["ownership"] = "mixed"
    assert Analysis.model_validate(gated).star.action.ownership is Ownership.MIXED
    print("evidence_updates list<->dict ok; scale default ok; gate ownership ok")

    # 3. CoverageMatrix / Report assembly.
    rubric = Rubric.model_validate(SPEC_EXAMPLES[Rubric])
    matrix = CoverageMatrix.from_state(rubric, {"C1": {"designed endpoints": "weak"}})
    assert matrix.rows[0].cells[0].level is EvidenceLevel.WEAK
    assert matrix.rows[0].cells[2].level is EvidenceLevel.NONE
    assert not matrix.empty_must_haves()
    report = Report.from_draft(ReportDraft.model_validate(SPEC_EXAMPLES[ReportDraft]), matrix, DeliveryMetrics())
    assert list(report.model_dump()) == [
        "top_fixes", "per_question", "coverage_matrix", "delivery", "overall_band", "band_mover",
    ]
    print("report assembly ok")

    # 3b. Vocabulary drift guard against brain/prompts (the prompts *describe* what the
    #     grammar *enforces*; they must agree). Skipped when prompts is not importable.
    prompts = _import_prompts()
    if prompts is None:
        print("brain/prompts not importable here; vocabulary drift guard skipped")
    else:
        for const, enum_cls in (
            ("STRATEGIES", Strategy), ("LADDER", LadderRung), ("VERDICTS", Verdict),
            ("EVIDENCE_LEVELS", EvidenceLevel), ("MOODS", Mood), ("BANDS", Band),
        ):
            expected = tuple(getattr(prompts, const))
            actual = tuple(m.value for m in enum_cls)
            assert actual == expected, f"{enum_cls.__name__} {actual} != prompts.{const} {expected}"
        assert dict(prompts.MOOD_ID) == {m.value: i for m, i in MOOD_INDEX.items()}
        print("vocabulary matches brain/prompts (STRATEGIES, LADDER, VERDICTS, EVIDENCE_LEVELS, MOODS, BANDS, MOOD_ID)")

    # 4. Every LLM schema serialises and passes the strictness checker.
    payloads: dict[type[StrictBase], Any] = {
        Rubric: _drop_keys(rubric.model_dump(mode="json"), frozenset({"start", "end"})),
        QuestionDraft: SPEC_EXAMPLES[QuestionDraft],
        Analysis: ANALYSIS_LLM_FORM,
        ReportDraft: ReportDraft.model_validate(SPEC_EXAMPLES[ReportDraft]).model_dump(mode="json"),
        Question: Question.model_validate(SPEC_EXAMPLES[Question]).model_dump(mode="json"),
        Report: report.model_dump(mode="json"),
    }
    try:
        import jsonschema  # optional; not a server dependency
    except ImportError:  # pragma: no cover
        jsonschema = None
    ownership_llm = llm_schema(Analysis)["properties"]["star"]["properties"]["action"]["properties"]["ownership"]
    assert ownership_llm == {"anyOf": [{"enum": ["I", "we", "unclear"], "type": "string"}, {"type": "null"}]}
    assert "scale" not in llm_schema(Analysis)["properties"]["specificity"]["properties"]
    for model in (Rubric, QuestionDraft, Analysis, ReportDraft, Question, Report):
        schema = llm_schema(model)
        text = json.dumps(schema, indent=2)
        assert json.loads(text) == schema
        assert check_llm_schema(schema) == []
        stage = next((s for s, m in STAGE_LLM_MODELS.items() if m is model), None)
        label = f"Stage {stage} — {model.__name__}" if stage else f"{model.__name__} (server-side; strict export still works)"
        print(f"\n===== {label} =====\n{text}")
        if jsonschema is not None:
            jsonschema.Draft202012Validator(schema).validate(payloads[model])
            print(f"[jsonschema] example payload validates against llm_schema({model.__name__})")
    rf = llm_response_format(Analysis)
    assert rf["json_schema"]["name"] == "analysis" and rf["json_schema"]["strict"] is True
    print("\nself-check passed")


if __name__ == "__main__":
    _self_check()
