"""Agenda Manager - Stage B state and policy for the Interview Cracker brain.

Spec: docs/BLUEPRINT.md section 2.3, 5.2, 5.3 (critical-path trick), 5.6 (pressure dial);
docs/CLAUDE_CODE_MASTER_PROMPT.md Phase 2 step 3 and 5.

Pure Python: no LLM call, no I/O. The manager owns the coverage matrix and decides *what*
to ask next; Stage B's prompt turns the returned target into question wording and the
why-trace. Everything here is deterministic - given the same rubric, dial and sequence
of analyses, the same targets come out.

State (section 5.2):
    coverage[competency_id][evidence_item] in {"none", "weak", "strong"}
    asked_count[competency_id], ladder_pos[competency_id], mix_debt (behavioural vs technical)
    followups_asked[competency_id]  (max per competency comes from the dial, ceiling 2)

Policy, in order (section 5.2):
    (1) a pending follow-up from the last analysis's ``next_strategy`` (within budget);
    (2) else the must-have with the most "none" cells, respecting mix_debt (alternate
        behavioural / technical toward the JD mix);
    (3) escalate ladder_pos after a "strong" verdict (state rule: the next time that
        competency is picked it is asked one rung up, with strategy "escalate");
    (4) stop after N questions (6 Warm-up / 8 Realistic / 10 Tough) or when every
        must-have has at least one "strong" cell.

Decisions where the spec is silent (recorded here so docs/DECISIONS.md can pick them up):
    * The N cap and the all-must-haves-strong rule are hard guards checked *before* a
      pending follow-up, so a Realistic round can never run to 9 questions.
    * Coverage is monotonic: a later "none"/"weak" never downgrades an earlier "strong".
    * When every must-have has no "none" cell left but the round is not over, nice-to-haves
      with "none" cells are asked next, then "weak" cells are re-probed; when nothing is
      left the manager stops with reason "coverage_exhausted".
    * A "strong" verdict whose evidence_updates carry no "strong" cell still marks the
      targeted evidence_gap cell strong (a small-model inconsistency guard).
    * Contradiction probes exist only in Tough (section 5.6), do not consume the per-competency
      follow-up budget, and are capped at one per competency.
    * If Stage A marks nothing as must_have, every competency is treated as a must-have.

Per-turn flow (server side)::

    target = agenda.next_target()            # None -> stop, run Stage D
    question = stage_b(target, ...)          # LLM wording; why-trace built from target
    agenda.mark_asked(target, question_id)   # commits asked_count / mix / follow-up budget
    ... candidate answers, STT ...
    analysis = stage_c(transcript, ...)      # validated JSON (section 5.3)
    agenda.apply_analysis(analysis)          # coverage, ladder, pending follow-up

Critical-path trick (section 5.3): as soon as the transcript lands call
``provisional_target(transcript_text)`` and start Stage B on it while Stage C runs.
When Stage C returns: ``apply_analysis(analysis)``, ``final = next_target()``, and
``needs_swap(provisional, final)`` says whether the pre-planned question must be replaced
before TTS starts. If no swap is needed, copy ``final["triggered_by"]`` into the
pre-planned question's why-trace (the provisional one has no validated quote yet).
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "AgendaManager",
    "Dial",
    "DialConfig",
    "DIALS",
    "Rubric",
    "Competency",
    "AnalysisView",
    "STRATEGIES",
    "FOLLOWUP_STRATEGIES",
    "FOLLOWUP_HINTS",
    "DEFAULT_LADDER",
    "VAGUE_THRESHOLD",
    "WE_RATIO_THRESHOLD",
    "vague_score",
    "vagueness_features",
]

# --------------------------------------------------------------------------------------
# Vocabulary (section 5.2)
# --------------------------------------------------------------------------------------

LEVEL_RANK = {"none": 0, "weak": 1, "strong": 2}
DEFAULT_LADDER = ["recall", "applied example", "trade-off or failure", "design under constraint"]
DEFAULT_EVIDENCE = "one concrete example"

STRATEGIES = frozenset(
    {
        "open_probe",
        "evidence_probe",
        "dig_deeper_vague",
        "dig_deeper_generic",
        "quantify_result",
        "ownership_probe",
        "contradiction_probe",
        "escalate",
    }
)
# A Stage C ``next_strategy`` in this set means "stay on this competency and dig";
# ``open_probe`` / ``escalate`` / null mean "move on".
FOLLOWUP_STRATEGIES = frozenset(
    {
        "dig_deeper_vague",
        "dig_deeper_generic",
        "quantify_result",
        "ownership_probe",
        "contradiction_probe",
        "evidence_probe",
    }
)
VERDICTS = frozenset({"vague", "generic", "adequate", "strong"})

# Prompt-ready nudges from the section 5.2 trigger table; Stage B may quote them verbatim or reword.
FOLLOWUP_HINTS = {
    "open_probe": "Ask an open question that invites one specific, first-person example.",
    "evidence_probe": "Walk me through how you did {keyword}.",
    "dig_deeper_vague": "Give me one specific instance.",
    "dig_deeper_generic": "What was *your* part in that?",
    "ownership_probe": "What did you personally do, as opposed to the team?",
    "quantify_result": "What changed because of it - any number?",
    "contradiction_probe": "Earlier you said one thing and now another - which is it?",
    "escalate": "The last answer was strong: ask one rung harder on the same competency.",
}

VAGUE_THRESHOLD = 0.6  # vague_score() at or above this => follow-up (dig_deeper_vague)
WE_RATIO_THRESHOLD = 0.7  # section 5.3: we-ratio > 0.7 flags team-hiding (heuristic, tune it)

# --------------------------------------------------------------------------------------
# Pressure dial (section 5.6)
# --------------------------------------------------------------------------------------


class Dial(str, Enum):
    WARMUP = "warmup"
    REALISTIC = "realistic"
    TOUGH = "tough"


@dataclass(frozen=True)
class DialConfig:
    name: str
    max_questions: int
    max_followups_per_competency: int
    time_limit_s: dict  # {"behavioral": int|None, "technical": int|None}
    interrupt_on_timeout: bool
    interrupt_on_looping: bool
    contradiction_probes: bool
    unimpressed_after_vague: Optional[int]  # consecutive vague answers on one competency
    nods: bool


DIALS: dict[str, DialConfig] = {
    "warmup": DialConfig(
        name="warmup",
        max_questions=6,
        max_followups_per_competency=1,
        time_limit_s={"behavioral": None, "technical": None},
        interrupt_on_timeout=False,
        interrupt_on_looping=False,
        contradiction_probes=False,
        unimpressed_after_vague=None,
        nods=True,
    ),
    "realistic": DialConfig(
        name="realistic",
        max_questions=8,
        max_followups_per_competency=2,
        time_limit_s={"behavioral": 90, "technical": 60},
        interrupt_on_timeout=True,
        interrupt_on_looping=False,
        contradiction_probes=False,
        unimpressed_after_vague=None,
        nods=True,
    ),
    "tough": DialConfig(
        name="tough",
        max_questions=10,
        max_followups_per_competency=2,
        time_limit_s={"behavioral": 90, "technical": 60},
        interrupt_on_timeout=True,
        interrupt_on_looping=True,
        contradiction_probes=True,
        unimpressed_after_vague=2,
        nods=False,
    ),
}

_DIAL_ALIASES = {"warm-up": "warmup", "warm_up": "warmup", "warm": "warmup", "real": "realistic"}


def _parse_dial(dial: "str | Dial") -> str:
    if isinstance(dial, Dial):
        return dial.value
    key = str(dial).strip().lower()
    key = _DIAL_ALIASES.get(key, key)
    if key not in DIALS:
        raise ValueError(f"unknown pressure dial {dial!r}; expected one of {sorted(DIALS)}")
    return key


# --------------------------------------------------------------------------------------
# Minimal views of the Stage A rubric and Stage C analysis JSON (sections 5.1 / 5.3).
# Tolerant to extra keys so they stay compatible with brain/schemas.py.
# --------------------------------------------------------------------------------------


def _norm_type(value: Any) -> str:
    s = str(value or "").strip().lower().replace("-", "_")
    if s.startswith("behav"):
        return "behavioral"
    if s.startswith("tech"):
        return "technical"
    raise ValueError(f"competency type must be behavioural or technical, got {value!r}")


def _norm_priority(value: Any) -> str:
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in {"must_have", "must", "required", "core"}:
        return "must_have"
    if s in {"nice_to_have", "nice", "optional", "bonus"}:
        return "nice_to_have"
    raise ValueError(f"priority must be must_have or nice_to_have, got {value!r}")


def _norm_text(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().strip(".;:,").casefold()


class Competency(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    type: str = "technical"
    priority: str = "must_have"
    jd_quotes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_expected: list[str] = Field(default_factory=list)
    difficulty_ladder: list[str] = Field(default_factory=lambda: list(DEFAULT_LADDER))

    @field_validator("type", mode="before")
    @classmethod
    def _v_type(cls, v: Any) -> str:
        return _norm_type(v if v not in (None, "") else "technical")

    @field_validator("priority", mode="before")
    @classmethod
    def _v_priority(cls, v: Any) -> str:
        return _norm_priority(v if v not in (None, "") else "must_have")

    @field_validator("evidence_expected", mode="before")
    @classmethod
    def _v_evidence(cls, v: Any) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for raw in v or []:
            if isinstance(raw, dict):
                raw = raw.get("text") or raw.get("name") or raw.get("evidence") or ""
            text = re.sub(r"\s+", " ", str(raw)).strip()
            if not text or _norm_text(text) in seen:
                continue
            seen.add(_norm_text(text))
            items.append(text)
        return items or [DEFAULT_EVIDENCE]

    @field_validator("difficulty_ladder", mode="before")
    @classmethod
    def _v_ladder(cls, v: Any) -> list[str]:
        rungs = [re.sub(r"\s+", " ", str(r)).strip() for r in (v or []) if str(r).strip()]
        return rungs or list(DEFAULT_LADDER)

    @property
    def jd_quote(self) -> Optional[str]:
        for q in self.jd_quotes:
            text = q.get("text") if isinstance(q, dict) else None
            if text:
                return str(text)
        return None


class Rubric(BaseModel):
    model_config = ConfigDict(extra="allow")

    role_title: str = ""
    behavioral_technical_mix: dict[str, float] = Field(
        default_factory=lambda: {"behavioral": 0.5, "technical": 0.5}
    )
    competencies: list[Competency] = Field(min_length=1)

    @field_validator("behavioral_technical_mix", mode="before")
    @classmethod
    def _v_mix(cls, v: Any) -> dict[str, float]:
        mix = {"behavioral": 0.0, "technical": 0.0}
        for k, val in (v or {}).items():
            try:
                mix[_norm_type(k)] = max(0.0, float(val))
            except (ValueError, TypeError):
                continue
        total = mix["behavioral"] + mix["technical"]
        if total <= 0:
            return {"behavioral": 0.5, "technical": 0.5}
        return {k: val / total for k, val in mix.items()}

    @model_validator(mode="after")
    def _unique_ids(self) -> "Rubric":
        ids = [c.id for c in self.competencies]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate competency ids in rubric: {ids}")
        return self


class AnalysisView(BaseModel):
    """The subset of the Stage C JSON the agenda consumes (post quote-validation)."""

    model_config = ConfigDict(extra="allow")

    answer_id: Optional[str] = None
    competency_id: Optional[str] = None  # optional override; defaults to the last asked competency
    verdict: Optional[str] = None
    evidence_updates: dict[str, dict[str, Any]] = Field(default_factory=dict)
    next_strategy: Optional[str] = None
    star: dict[str, Any] = Field(default_factory=dict)
    contradictions: list[Any] = Field(default_factory=list)
    jd_keyword_coverage: dict[str, Any] = Field(default_factory=dict)
    reaction: Optional[str] = None
    triggered_by: Optional[dict[str, Any]] = None  # explicit trigger, if Stage C provides one

    @field_validator("verdict", mode="before")
    @classmethod
    def _v_verdict(cls, v: Any) -> Optional[str]:
        s = str(v or "").strip().lower()
        return s if s in VERDICTS else None

    @field_validator("next_strategy", mode="before")
    @classmethod
    def _v_strategy(cls, v: Any) -> Optional[str]:
        s = str(v or "").strip().lower()
        return s if s in STRATEGIES else None

    @field_validator("evidence_updates", mode="before")
    @classmethod
    def _v_updates(cls, v: Any) -> dict[str, dict[str, Any]]:
        return {str(k): dict(val) for k, val in (v or {}).items() if isinstance(val, dict)}


# --------------------------------------------------------------------------------------
# Vagueness heuristic (section 5.3 critical-path trick; section 5.2 follow-up triggers)
# --------------------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'+#.\-]*")
_NUMBER_WORDS = frozenset(
    "two three four five six seven eight nine ten eleven twelve fifteen twenty thirty forty "
    "fifty sixty seventy eighty ninety hundred thousand million billion half double twice "
    "triple dozen percent".split()
)
_UNIT_WORDS = frozenset(
    "ms millisecond milliseconds second seconds minute minutes hour hours day days week weeks "
    "month months year years users requests qps rps kb mb gb tb x".split()
)
# Named technologies that make an answer concrete even when STT lower-cases everything.
# Concepts ("caching", "api", "database") are deliberately absent - claiming a concept is
# exactly the "JD keyword claimed without detail" trigger.
_TECH_LEXICON = frozenset(
    """
    redis memcached postgres postgresql mysql mariadb mongodb mongo dynamodb sqlite cassandra
    elasticsearch kafka rabbitmq sqs sns celery docker kubernetes k8s helm terraform ansible
    aws gcp azure lambda s3 ec2 ecs eks rds cloudfront firebase supabase vercel netlify heroku
    python java javascript typescript kotlin swift golang rust scala ruby php dart flutter
    node nodejs express nestjs react angular vue svelte nextjs django flask fastapi spring
    springboot rails laravel graphql grpc websocket websockets jwt oauth oauth2 nginx apache
    linux ubuntu windows git github gitlab jenkins circleci jira figma postman swagger openapi
    pandas numpy pytorch tensorflow sklearn scikit-learn spark hadoop airflow tableau powerbi
    junit pytest jest selenium cypress
    """.split()
)
# Uppercase tokens that are generic, not names.
_GENERIC_CAPS = frozenset(
    "api apis ui ux db it hr qa ci cd ai ml ok jd cv sdk ide os url http https rest crud".split()
)
_VAGUE_PHRASES = [
    r"\bstuff\b", r"\bthings?\b", r"\band so on\b", r"\betc\.?\b", r"\betcetera\b",
    r"\bkind of\b", r"\bsort of\b", r"\bbasically\b", r"\bsomething like that\b",
    r"\bor whatever\b", r"\bvarious\b", r"\ba lot\b", r"\blots of\b", r"\bsomehow\b",
    r"\bsomewhere\b", r"\bgenerally\b", r"\busually\b", r"\bmostly\b", r"\bpretty much\b",
    r"\byou know\b", r"\blike that\b", r"\bworked fine\b", r"\bwent well\b", r"\bwent fine\b",
    r"\bit worked\b", r"\bwas good\b", r"\bpretty good\b", r"\bsome\b",
]
_HEDGE_PHRASES = [
    r"\bi think\b", r"\bmaybe\b", r"\bprobably\b", r"\bi guess\b", r"\bnot sure\b",
    r"\bperhaps\b", r"\bi believe\b", r"\bpossibly\b", r"\bi suppose\b",
]
_VAGUE_RE = re.compile("|".join(_VAGUE_PHRASES), re.IGNORECASE)
_HEDGE_RE = re.compile("|".join(_HEDGE_PHRASES), re.IGNORECASE)
_WE_WORDS = frozenset({"we", "we're", "we've", "we'd", "we'll", "our", "ours", "us", "ourselves"})
_I_WORDS = frozenset({"i", "i'm", "i've", "i'd", "i'll", "my", "me", "mine", "myself"})


def _is_name_token(tok: str, sentence_initial: bool) -> bool:
    low = tok.lower()
    if low in _TECH_LEXICON:
        return True
    if low in _GENERIC_CAPS or tok == "I" or low in _I_WORDS:
        return False
    has_alpha = any(ch.isalpha() for ch in tok)
    has_digit = any(ch.isdigit() for ch in tok)
    if has_alpha and has_digit:  # p95, k8s, s3, http2
        return True
    if has_alpha and any(ch in tok[1:-1] for ch in ".+#"):  # Node.js, C++, C#
        return True
    if len(tok) > 1 and tok[0].isupper() and not sentence_initial:
        return True
    if len(tok) > 1 and tok.isupper() and has_alpha:  # TTL, JWT even at sentence start
        return True
    return False


def vagueness_features(transcript_text: str) -> dict[str, Any]:
    """Cheap, LLM-free features behind ``vague_score``. Returned for the why-trace/logs."""
    text = transcript_text or ""
    tokens: list[str] = []
    has_name = False
    has_number = False
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0).rstrip(".,'")
        if not tok:
            continue
        tokens.append(tok)
        before = text[: m.start()].rstrip()
        sentence_initial = not before or before[-1] in ".!?;"
        low = tok.lower()
        if any(ch.isdigit() for ch in tok) or low in _NUMBER_WORDS or "%" in m.group(0):
            has_number = True
        elif low in _UNIT_WORDS and len(tokens) > 1 and any(ch.isdigit() for ch in tokens[-2]):
            has_number = True
        if _is_name_token(tok, sentence_initial):
            has_name = True
    n_words = len(tokens)
    lows = [t.lower() for t in tokens]
    we_count = sum(1 for t in lows if t in _WE_WORDS)
    i_count = sum(1 for t in lows if t in _I_WORDS)
    we_ratio = we_count / (we_count + i_count) if (we_count + i_count) else 0.0
    vague_markers = len(_VAGUE_RE.findall(text))
    hedges = len(_HEDGE_RE.findall(text))

    if n_words == 0:
        score = 1.0
    else:
        specificity = (0.5 if has_number else 0.0) + (0.5 if has_name else 0.0)
        vague_density = min(1.0, vague_markers / max(1.0, n_words / 20.0))
        hedge_density = min(1.0, hedges / max(1.0, n_words / 25.0))
        brevity = 1.0 if n_words < 12 else (0.5 if n_words < 25 else 0.0)
        we_penalty = max(0.0, (we_ratio - 0.5) * 2.0)
        score = (
            0.45 * (1.0 - specificity)
            + 0.25 * vague_density
            + 0.10 * hedge_density
            + 0.10 * brevity
            + 0.10 * we_penalty
        )
    return {
        "n_words": n_words,
        "has_number": has_number,
        "has_name": has_name,
        "vague_markers": vague_markers,
        "hedges": hedges,
        "we_count": we_count,
        "i_count": i_count,
        "we_ratio": round(we_ratio, 3),
        "score": round(min(1.0, max(0.0, score)), 3),
    }


def vague_score(transcript_text: str) -> float:
    """0.0 (concrete) .. 1.0 (vague). No concrete noun / number / name, filler phrases,
    hedges, brevity and a high "we" ratio all push it up. Threshold: ``VAGUE_THRESHOLD``."""
    return vagueness_features(transcript_text)["score"]


# --------------------------------------------------------------------------------------
# Agenda Manager
# --------------------------------------------------------------------------------------

_QID_RE = re.compile(r"^[Qq](\d+)$")


def _as_view(value: Any, view: type[BaseModel]) -> BaseModel:
    """Coerce a dict, one of our view models, or any other pydantic model (e.g. the full
    brain/schemas.py Rubric / Analysis) into ``view``; enums dump to their string values."""
    if isinstance(value, view):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return view.model_validate(value)


class AgendaManager:
    """Coverage-driven question planner (section 5.2). Pure Python, deterministic."""

    def __init__(
        self,
        rubric: "Rubric | BaseModel | dict[str, Any]",
        dial: "str | Dial" = "realistic",
        *,
        max_questions: Optional[int] = None,
        max_followups: Optional[int] = None,
        vague_threshold: float = VAGUE_THRESHOLD,
    ) -> None:
        self.rubric: Rubric = _as_view(rubric, Rubric)  # type: ignore[assignment]
        self.dial: DialConfig = DIALS[_parse_dial(dial)]
        self.max_questions: int = int(max_questions or self.dial.max_questions)
        self.max_followups: int = (
            int(max_followups) if max_followups is not None else self.dial.max_followups_per_competency
        )
        self.vague_threshold = float(vague_threshold)

        self._comps: dict[str, Competency] = {c.id: c for c in self.rubric.competencies}
        self._order: dict[str, int] = {c.id: i for i, c in enumerate(self.rubric.competencies)}
        must = [c.id for c in self.rubric.competencies if c.priority == "must_have"]
        self._must_have_ids: list[str] = must or list(self._comps)

        ids = list(self._comps)
        self.coverage: dict[str, dict[str, str]] = {
            cid: {item: "none" for item in self._comps[cid].evidence_expected} for cid in ids
        }
        self.asked_count: dict[str, int] = {cid: 0 for cid in ids}
        self.ladder_pos: dict[str, int] = {cid: 0 for cid in ids}
        self.followups_asked: dict[str, int] = {cid: 0 for cid in ids}
        self.contradiction_probes_asked: dict[str, int] = {cid: 0 for cid in ids}
        self.vague_streak: dict[str, int] = {cid: 0 for cid in ids}
        self.escalation_pending: dict[str, bool] = {cid: False for cid in ids}
        self.asked_by_type: dict[str, int] = {"behavioral": 0, "technical": 0}
        self.total_asked: int = 0
        self.pending_followup: Optional[dict[str, Any]] = None
        self.last_asked: Optional[dict[str, Any]] = None
        self.last_analysis: Optional[dict[str, Any]] = None
        self.history: list[dict[str, Any]] = []
        self.dropped_followups: list[dict[str, Any]] = []
        self.notes: list[str] = []

    # ---- derived state ---------------------------------------------------------------

    @property
    def competency_ids(self) -> list[str]:
        return list(self._comps)

    @property
    def must_have_ids(self) -> list[str]:
        return list(self._must_have_ids)

    def is_must_have(self, cid: str) -> bool:
        return cid in self._must_have_ids

    def counts(self, cid: str) -> dict[str, int]:
        cells = self.coverage[cid].values()
        return {level: sum(1 for v in cells if v == level) for level in LEVEL_RANK}

    def has_strong(self, cid: str) -> bool:
        return any(v == "strong" for v in self.coverage[cid].values())

    @property
    def mix_debt(self) -> dict[str, float]:
        """How many questions each type is *owed* if the next question is included.
        Positive = under-asked relative to the JD mix. Computed, never stored."""
        n = self.total_asked + 1
        mix = self.rubric.behavioral_technical_mix
        return {
            t: round(mix.get(t, 0.0) * n - self.asked_by_type[t], 6) for t in ("behavioral", "technical")
        }

    def _owed_type(self) -> Optional[str]:
        debt = self.mix_debt
        if abs(debt["behavioral"] - debt["technical"]) < 1e-9:
            return None
        return max(("behavioral", "technical"), key=lambda t: debt[t])

    def _all_must_haves_strong(self) -> bool:
        return all(self.has_strong(cid) for cid in self._must_have_ids)

    def _hard_stop_reason(self) -> Optional[str]:
        if self.total_asked >= self.max_questions:
            return "max_questions"
        if self._all_must_haves_strong():
            return "must_haves_strong"
        return None

    def should_stop(self) -> tuple[bool, Optional[str]]:
        """(stop?, reason). Reasons: max_questions | must_haves_strong | coverage_exhausted."""
        reason = self._hard_stop_reason()
        if reason:
            return True, reason
        if self.pending_followup is None and self._pick_fresh_competency() is None:
            return True, "coverage_exhausted"
        return False, None

    def suggested_reaction(self, analysis_reaction: Optional[str] = None) -> str:
        """Dial-aware reaction: Tough goes "unimpressed" after the Nth vague answer in a row
        on the same competency (section 5.6); otherwise Stage C's reaction (default neutral)."""
        cid = self.last_asked["competency_id"] if self.last_asked else None
        limit = self.dial.unimpressed_after_vague
        if cid and limit and self.vague_streak.get(cid, 0) >= limit:
            return "unimpressed"
        if analysis_reaction == "unimpressed" and not limit:
            return "neutral"
        return analysis_reaction or "neutral"

    # ---- policy -----------------------------------------------------------------------

    def next_target(self) -> Optional[dict[str, Any]]:
        """The next thing to ask, or None when the round should stop. Pure: no state change.

        Keys Stage B consumes: competency_id, evidence_gap, ladder_rung, strategy, is_followup,
        triggered_by. Extras for the prompt / why-trace: competency_name, competency_type,
        priority, jd_quote, time_limit_s, hint, provisional.
        """
        if self._hard_stop_reason():
            return None
        if self.pending_followup is not None:  # (1) already budget-checked in apply_analysis
            return deepcopy(self.pending_followup)
        cid = self._pick_fresh_competency()  # (2) + (3)
        if cid is None:
            return None  # (4) nothing left to ask
        return self._build_fresh_target(cid)

    def provisional_target(self, transcript_text: str) -> Optional[dict[str, Any]]:
        """Pre-plan question n+1 before Stage C has judged answer n (section 5.3).

        Uses the committed coverage (as of answer n-1) plus ``vague_score`` on the raw
        transcript. A vague / "we"-heavy answer yields a provisional follow-up on the
        competency just asked; otherwise the normal policy runs, preferring a different
        competency from the one just asked (any non-empty answer will move that one).
        """
        if self._hard_stop_reason():
            return None
        if self.last_asked is None:
            return self.next_target()
        cid = self.last_asked["competency_id"]
        feats = vagueness_features(transcript_text)
        strategy: Optional[str] = None
        if feats["score"] >= self.vague_threshold:
            strategy = "dig_deeper_vague"
        elif feats["we_ratio"] > WE_RATIO_THRESHOLD and feats["n_words"] >= 12:
            strategy = "dig_deeper_generic"
        if strategy and self.followups_asked[cid] < self.max_followups:
            target = self._build_followup(cid, strategy, None)
            target["provisional"] = True
            target["triggered_by"] = {
                "answer_id": self._expected_answer_id(),
                "quote": None,
                "t": None,
                "heuristic": feats,
            }
            return target
        fresh = self._pick_fresh_competency(avoid=cid)
        if fresh is None:
            return None
        target = self._build_fresh_target(fresh)
        target["provisional"] = True
        return target

    @staticmethod
    def needs_swap(
        provisional: Optional[dict[str, Any]],
        final: Optional[dict[str, Any]],
        *,
        strict: bool = False,
    ) -> bool:
        """True when the pre-planned question must be replaced before TTS.

        Default (section 5.3): swap only when Stage C demands a follow-up the provisional plan did
        not already anticipate. ``strict=True`` also swaps on any material difference in
        (competency_id, strategy, is_followup).
        """
        if final is None:
            return provisional is not None  # round is over; do not ask the pre-planned question
        if provisional is None:
            return True

        def key(t: dict[str, Any]) -> tuple:
            return (t.get("competency_id"), t.get("strategy"), bool(t.get("is_followup")))

        if strict:
            return key(provisional) != key(final)
        return bool(final.get("is_followup")) and key(provisional) != key(final)

    def mark_asked(self, target: dict[str, Any], question_id: Optional[str] = None) -> dict[str, Any]:
        """Commit a target as asked: counters, mix, follow-up budget. Returns the record."""
        cid = target["competency_id"]
        if cid not in self._comps:
            raise KeyError(f"unknown competency_id {cid!r}")
        self.total_asked += 1
        qid = question_id or f"Q{self.total_asked}"
        self.asked_count[cid] += 1
        self.asked_by_type[self._comps[cid].type] += 1
        strategy = target.get("strategy")
        if target.get("is_followup"):
            if strategy == "contradiction_probe":
                self.contradiction_probes_asked[cid] += 1
            else:
                self.followups_asked[cid] += 1
        if strategy == "escalate":
            self.escalation_pending[cid] = False
        self.pending_followup = None
        record = deepcopy(target)
        record["question_id"] = qid
        record["provisional"] = False
        record["asked_index"] = self.total_asked
        self.last_asked = record
        self.history.append(record)
        return deepcopy(record)

    def apply_analysis(self, analysis: "dict[str, Any] | BaseModel | AnalysisView") -> Optional[dict[str, Any]]:
        """Fold a validated Stage C result into the state. Returns the pending follow-up
        target (or None) so the server can decide whether to swap the pre-planned question."""
        a: AnalysisView = _as_view(analysis, AnalysisView)  # type: ignore[assignment]
        cid = a.competency_id if a.competency_id in self._comps else None
        if cid is None and self.last_asked is not None:
            cid = self.last_asked["competency_id"]

        # 1. coverage matrix, monotonic per cell
        upgraded_strong_for: set[str] = set()
        for ucid, cells in a.evidence_updates.items():
            if ucid not in self.coverage:
                self.notes.append(f"evidence_updates: unknown competency {ucid!r} ignored")
                continue
            for item, level in cells.items():
                lvl = str(level or "").strip().lower()
                if lvl not in LEVEL_RANK:
                    self.notes.append(f"evidence_updates[{ucid}][{item!r}]: unknown level {level!r} ignored")
                    continue
                key = self._match_evidence(ucid, str(item))
                if key is None:
                    self.notes.append(f"evidence_updates[{ucid}]: unknown evidence item {item!r} ignored")
                    continue
                if LEVEL_RANK[lvl] > LEVEL_RANK[self.coverage[ucid][key]]:
                    self.coverage[ucid][key] = lvl
                    if lvl == "strong":
                        upgraded_strong_for.add(ucid)

        # 2. verdict-driven state for the competency that was asked
        if cid is not None:
            if a.verdict == "strong":
                if cid not in upgraded_strong_for and not self.has_strong(cid):
                    last = self.last_asked or {}
                    gap = last.get("evidence_gap") if last.get("competency_id") == cid else None
                    key = (self._match_evidence(cid, gap) if gap else None) or self._evidence_gap(cid)
                    self.coverage[cid][key] = "strong"
                    self.notes.append(f"strong verdict on {cid} without a strong cell: marked {key!r} strong")
                ladder_len = len(self._comps[cid].difficulty_ladder)
                if self.ladder_pos[cid] < ladder_len - 1:
                    self.ladder_pos[cid] += 1
                    self.escalation_pending[cid] = True
                self.vague_streak[cid] = 0
            elif a.verdict in ("vague", "generic"):
                self.vague_streak[cid] += 1
            elif a.verdict == "adequate":
                self.vague_streak[cid] = 0

        # 3. pending follow-up (policy step 1), budget-checked here so next_target stays pure
        self.pending_followup = None
        strategy = a.next_strategy
        if cid is not None and strategy in FOLLOWUP_STRATEGIES:
            if strategy == "contradiction_probe":
                allowed = self.dial.contradiction_probes and self.contradiction_probes_asked[cid] < 1
                why = "contradiction probes are Tough-only and capped at one per competency"
            else:
                allowed = self.followups_asked[cid] < self.max_followups
                why = f"follow-up budget for {cid} exhausted ({self.max_followups} per competency)"
            if allowed:
                self.pending_followup = self._build_followup(cid, strategy, a)
            else:
                self.dropped_followups.append(
                    {"competency_id": cid, "strategy": strategy, "why": why, "answer_id": a.answer_id}
                )

        self.last_analysis = a.model_dump()
        return deepcopy(self.pending_followup)

    def target_for(self, cid: str) -> dict[str, Any]:
        """A fresh target for a specific competency (used by "retry the weakest question")."""
        if cid not in self._comps:
            raise KeyError(f"unknown competency_id {cid!r}")
        return self._build_fresh_target(cid)

    # ---- selection internals -----------------------------------------------------------

    def _rank_key(self, cid: str) -> tuple:
        """Deterministic ordering for policy (2): must-have first, most "none" cells, fewest
        "strong" cells, least asked, pending escalation first, then rubric order."""
        c = self.counts(cid)
        return (
            0 if self.is_must_have(cid) else 1,
            -c["none"],
            c["strong"],
            self.asked_count[cid],
            0 if self.escalation_pending[cid] else 1,
            self._order[cid],
            cid,
        )

    def _pick_fresh_competency(self, avoid: Optional[str] = None) -> Optional[str]:
        ids = list(self._comps)
        tiers = [
            [cid for cid in ids if self.is_must_have(cid) and self.counts(cid)["none"] > 0],
            [cid for cid in ids if not self.is_must_have(cid) and self.counts(cid)["none"] > 0],
            [cid for cid in ids if self.counts(cid)["weak"] > 0],
        ]
        for tier in tiers:
            cands = tier
            if not cands:
                continue
            if avoid is not None and len(cands) > 1:
                cands = [cid for cid in cands if cid != avoid] or cands
            owed = self._owed_type()
            if owed is not None:
                of_type = [cid for cid in cands if self._comps[cid].type == owed]
                if of_type:
                    cands = of_type
            return min(cands, key=self._rank_key)
        return None

    def _evidence_gap(self, cid: str, strategy: Optional[str] = None) -> str:
        items = self._comps[cid].evidence_expected
        cells = self.coverage[cid]
        not_strong = [i for i in items if cells[i] != "strong"]
        if strategy == "quantify_result":
            for i in not_strong:
                if re.search(r"measur|result|impact|number|metric|latency|improv|reduc|outcome|saved|increas", i, re.I):
                    return i
        for level in ("none", "weak"):
            for i in items:
                if cells[i] == level:
                    return i
        return items[0]

    def _match_evidence(self, cid: str, item: Optional[str]) -> Optional[str]:
        if not item:
            return None
        cells = self.coverage[cid]
        norm = _norm_text(item)
        for key in cells:
            if _norm_text(key) == norm:
                return key
        best, best_ratio = None, 0.0
        for key in cells:
            ratio = SequenceMatcher(None, _norm_text(key), norm).ratio()
            if ratio > best_ratio:
                best, best_ratio = key, ratio
        return best if best_ratio >= 0.8 else None

    def _rung(self, cid: str) -> str:
        ladder = self._comps[cid].difficulty_ladder
        return ladder[min(self.ladder_pos[cid], len(ladder) - 1)]

    def _expected_answer_id(self) -> Optional[str]:
        if self.last_asked is None:
            return None
        m = _QID_RE.match(str(self.last_asked.get("question_id", "")))
        return f"A{m.group(1)}" if m else f"A{self.last_asked.get('asked_index', self.total_asked)}"

    def _base_target(self, cid: str) -> dict[str, Any]:
        comp = self._comps[cid]
        return {
            "competency_id": cid,
            "competency_name": comp.name,
            "competency_type": comp.type,
            "priority": comp.priority,
            "jd_quote": comp.jd_quote,
            "time_limit_s": self.dial.time_limit_s.get(comp.type),
            "provisional": False,
        }

    def _build_fresh_target(self, cid: str) -> dict[str, Any]:
        if self.asked_count[cid] == 0:
            strategy = "open_probe"
        elif self.escalation_pending[cid]:
            strategy = "escalate"
        else:
            strategy = "evidence_probe"
        gap = self._evidence_gap(cid)
        target = self._base_target(cid)
        target.update(
            {
                "evidence_gap": gap,
                "ladder_rung": self._rung(cid),
                "strategy": strategy,
                "is_followup": False,
                "triggered_by": None,
                "hint": FOLLOWUP_HINTS[strategy].format(keyword=gap),
            }
        )
        return target

    def _build_followup(self, cid: str, strategy: str, a: Optional[AnalysisView]) -> dict[str, Any]:
        same = self.last_asked is not None and self.last_asked.get("competency_id") == cid
        rung = self.last_asked["ladder_rung"] if same else self._rung(cid)
        gap = self._evidence_gap(cid, strategy)
        keyword = gap
        if a is not None:
            hits = a.jd_keyword_coverage.get("hit") or []
            if isinstance(hits, list) and hits:
                keyword = str(hits[0])
        target = self._base_target(cid)
        target.update(
            {
                "evidence_gap": gap,
                "ladder_rung": rung,
                "strategy": strategy,
                "is_followup": True,
                "triggered_by": self._trigger_from_analysis(a, strategy),
                "hint": FOLLOWUP_HINTS[strategy].format(keyword=keyword),
            }
        )
        return target

    def _trigger_from_analysis(self, a: Optional[AnalysisView], strategy: str) -> dict[str, Any]:
        answer_id = (a.answer_id if a is not None else None) or self._expected_answer_id()
        trig: dict[str, Any] = {"answer_id": answer_id, "quote": None, "t": None}
        if a is None:
            return trig
        if isinstance(a.triggered_by, dict) and a.triggered_by.get("quote"):
            trig["quote"] = str(a.triggered_by["quote"])
            trig["t"] = a.triggered_by.get("t")
            return trig
        candidates: list[dict[str, Any]] = []
        if strategy == "contradiction_probe":
            for c in a.contradictions:
                if isinstance(c, dict):
                    candidates.append(c)
                    for sub in ("conflicts_with", "earlier", "later", "first", "second"):
                        if isinstance(c.get(sub), dict):
                            candidates.append(c[sub])
        star = a.star if isinstance(a.star, dict) else {}
        for part in ("action", "result", "task", "situation"):
            comp = star.get(part)
            if isinstance(comp, dict) and comp.get("present", True):
                candidates.append(comp)
        for c in candidates:
            quote = c.get("quote")
            if quote:
                trig["quote"] = str(quote)
                trig["t"] = c.get("t")
                break
        return trig

    # ---- persistence -------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """JSON-serialisable state (for turns.jsonl / SQLite). Restore with ``restore``."""
        return deepcopy(
            {
                "dial": self.dial.name,
                "max_questions": self.max_questions,
                "max_followups": self.max_followups,
                "vague_threshold": self.vague_threshold,
                "coverage": self.coverage,
                "asked_count": self.asked_count,
                "ladder_pos": self.ladder_pos,
                "followups_asked": self.followups_asked,
                "contradiction_probes_asked": self.contradiction_probes_asked,
                "vague_streak": self.vague_streak,
                "escalation_pending": self.escalation_pending,
                "asked_by_type": self.asked_by_type,
                "total_asked": self.total_asked,
                "pending_followup": self.pending_followup,
                "last_asked": self.last_asked,
                "last_analysis": self.last_analysis,
                "history": self.history,
                "dropped_followups": self.dropped_followups,
                "notes": self.notes,
            }
        )

    @classmethod
    def restore(cls, rubric: "Rubric | BaseModel | dict[str, Any]", snapshot: dict[str, Any]) -> "AgendaManager":
        mgr = cls(
            rubric,
            snapshot.get("dial", "realistic"),
            max_questions=snapshot.get("max_questions"),
            max_followups=snapshot.get("max_followups"),
            vague_threshold=snapshot.get("vague_threshold", VAGUE_THRESHOLD),
        )
        snap = deepcopy(snapshot)
        for cid, cells in snap.get("coverage", {}).items():
            if cid in mgr.coverage:
                for item, level in cells.items():
                    if item in mgr.coverage[cid] and level in LEVEL_RANK:
                        mgr.coverage[cid][item] = level
        for name in (
            "asked_count",
            "ladder_pos",
            "followups_asked",
            "contradiction_probes_asked",
            "vague_streak",
            "escalation_pending",
        ):
            store = getattr(mgr, name)
            for cid, val in snap.get(name, {}).items():
                if cid in store:
                    store[cid] = val
        mgr.asked_by_type.update(
            {k: int(v) for k, v in snap.get("asked_by_type", {}).items() if k in mgr.asked_by_type}
        )
        mgr.total_asked = int(snap.get("total_asked", 0))
        mgr.pending_followup = snap.get("pending_followup")
        mgr.last_asked = snap.get("last_asked")
        mgr.last_analysis = snap.get("last_analysis")
        mgr.history = list(snap.get("history", []))
        mgr.dropped_followups = list(snap.get("dropped_followups", []))
        mgr.notes = list(snap.get("notes", []))
        return mgr

    def coverage_report(self) -> dict[str, Any]:
        """Per-competency view for Stage D (section 5.5 coverage matrix) and the Prep screen."""
        rows = []
        for cid, comp in self._comps.items():
            c = self.counts(cid)
            rows.append(
                {
                    "competency_id": cid,
                    "name": comp.name,
                    "type": comp.type,
                    "priority": comp.priority,
                    "cells": dict(self.coverage[cid]),
                    "none": c["none"],
                    "weak": c["weak"],
                    "strong": c["strong"],
                    "asked_count": self.asked_count[cid],
                    "followups_asked": self.followups_asked[cid],
                    "ladder_pos": self.ladder_pos[cid],
                    "ladder_rung": self._rung(cid),
                    "has_strong": self.has_strong(cid),
                }
            )
        stop, reason = self.should_stop()
        return {
            "dial": asdict(self.dial),
            "total_asked": self.total_asked,
            "max_questions": self.max_questions,
            "mix_debt": self.mix_debt,
            "stopped": stop,
            "stop_reason": reason,
            "competencies": rows,
        }
