"""Prompt templates, sampling parameters and dial tables for the interview brain.

Spec: docs/BLUEPRINT.md section 5 (5.1-5.6) and CLAUDE_CODE_MASTER_PROMPT.md Phase 2.

Conventions
-----------
* Every template in this module is a ``str.format`` template. Runtime values
  use single braces (``{jd_text}``); literal JSON braces are doubled. Use
  ``render(stage, **fields)`` - it formats both the system and the user text,
  raises KeyError on a missing field and ValueError on a blank JD / transcript.
* Target model is Qwen3.5-9B Q6_K, 8K context, thinking off. Each template is
  kept under ~380 words, and only the coverage matrix plus the last two turns go
  in as history (multi-turn drift is real for small models - BLUEPRINT s.5).
* The prompts *describe* the JSON shape; the shape is *enforced* by
  ``response_format: json_schema`` built from ``brain/schemas.py``. Every
  property the grammar requires is shown in the prompt shape (tests/test_prompts.py
  checks this), and every field the grammar excludes is absent from it. The gates
  (rubric substring gate, RapidFuzz quote gate) live in code, never here.

Where the shapes deviate from the s.5 JSON, and who fills the gap
-----------------------------------------------------------------
* Stage A ``jd_quotes[].start/end`` (s.5.1) are not asked of the model - a 9B
  model cannot count characters. ``rubric.validate_rubric`` computes them with
  ``rubric.find_quote_offsets`` after the substring match succeeds.
* Stage A ``difficulty_ladder`` is constant per s.5.1 (the same four rungs on
  every competency), so it is not asked either; ``rubric.validate_rubric`` stamps
  ``rubric.LADDER`` on every surviving competency. Both fields are ``LLM_EXCLUDE``
  in schemas.py.
* Stage A re-ask fields (``rejected_list`` / ``kept_list``) come from
  ``rubric.build_reask_fields(jd, raw_rubric)``; ``rubric.merge_reask`` keeps the
  first pass's proven competencies whatever the re-ask returns.
* Stage B: the Agenda Manager decides competency, evidence gap, rung, strategy
  and trigger in code; the model returns only ``{text, evidence_item}`` and
  agenda.py assembles the s.5.2 why-trace from its own inputs.
* Stage C ``answer_id`` is asked of the model (it is given in the prompt and the
  grammar makes a constant field free); ``analyzer.py`` overwrites it with the
  real id anyway. ``specificity.scale`` is *not* asked (``LLM_EXCLUDE``); the
  schema default stamps ``"0-3"``.
* Stage C ``t`` is requested as ``[start of first quoted word, start of last
  quoted word]`` so it always lies inside the matched span; ``analyzer.py``
  widens ``t[1]`` to the last matched word's ``end`` after validation.
* Stage C ``key_quote`` (not in s.5.3) is always requested so that a generic
  answer - no STAR parts, no hedges - still yields one verified quote for Stage D
  to cite. ``contradictions[].conflicts_with`` is a full ``{answer_id, quote, t}``
  so both halves pass the quote gate (s.2.5 evidence lock); ``prior_claims`` is
  rendered with ``CLAIM_FORMAT`` so both halves are copyable.
* Stage C ``jd_keywords``: s.5.1 has no keyword list, so they are derived in
  code by ``rubric.jd_keywords(competency)`` - content words of the grounded
  ``jd_quotes`` plus ``evidence_expected``, capped at 8 - keeping them
  provenance-linked like everything else.
* Stage D asks the model only for ``top_fixes`` / ``per_question`` /
  ``overall_band`` / ``band_mover``; ``report.py`` attaches ``coverage_matrix``
  (from the agenda state) and ``delivery`` (from prosody.py) to the report
  object so the ``/report/<id>`` JSON matches s.5.5. ``per_question[].key_quote``
  is nullable: with no verified quote the model must write null, never invent.
* Pressure dial: s.5.6's Tough row is additive ("+ unimpressed") while s.6.4
  says nods happen only in Warm-up / Realistic. s.6.4 wins: Tough does not nod,
  and ``avatar_states`` is the single truth of what a dial may emit.
"""

from __future__ import annotations

import string

# ---------------------------------------------------------------------------
# Shared vocabulary (schemas.py builds its Literal types from these)
# ---------------------------------------------------------------------------

STRATEGIES = (
    "open_probe",
    "evidence_probe",
    "dig_deeper_vague",
    "dig_deeper_generic",
    "quantify_result",
    "ownership_probe",
    "contradiction_probe",
    "escalate",
)
LADDER = ("recall", "applied example", "trade-off or failure", "design under constraint")
VERDICTS = ("vague", "generic", "adequate", "strong")
EVIDENCE_LEVELS = ("none", "weak", "strong")
MOODS = ("neutral", "interested", "thinking", "unimpressed")
MOOD_ID = {"neutral": 0, "interested": 1, "thinking": 2, "unimpressed": 3}  # Rive `mood` input, s.6.1
BANDS = ("not yet ready", "borderline", "ready with polish", "strong")
DIALS = ("warmup", "realistic", "tough")

# How analyzer.py serialises the word-timestamped transcript for Stage C.
# Start time only: end times double the token cost and the validator recomputes
# the span from the matched words anyway.
WORD_FORMAT = "{word}@{start:.1f}"
WORD_SEP = " "
# How agenda.py serialises a turn for Stage B's "last two turns".
TURN_FORMAT = "Q{n}: {question}\nA{n}: {answer}"
NO_TURNS = "(none - this is the first question)"
# How analyzer.py lists a validated prior claim for Stage C, one per line, so a
# contradiction's conflicts_with half can be copied verbatim (answer_id, quote, t).
CLAIM_FORMAT = '{answer_id} [{t0:.1f}, {t1:.1f}]: "{quote}"'
NO_CLAIMS = "(none)"
# The follow-up trigger line for Stages B and C; "" for a fresh probe.
TRIGGER_LINE_FORMAT = 'Triggered by the candidate saying: "{quote}" (at {t0:.1f}s)'
NO_TRIGGER = ""

# ---------------------------------------------------------------------------
# Stage A - JD -> rubric with provenance (s.5.1)
# ---------------------------------------------------------------------------

STAGE_A_SYSTEM = """\
You are the lead of a hiring panel. You turn a job description (JD) into a competency rubric that will drive an interview.

Rules:
1. Extract 5 to 8 competencies. Never invent a competency the JD text does not support.
2. For each competency copy 1 or 2 sentences or clauses from the JD, verbatim: same words, same spelling, same punctuation, same order. No paraphrase, no grammar fixes, no merging two sentences into one. A program checks each quote as an exact substring of the JD; a quote that fails deletes the whole competency.
3. Do not use the same JD sentence for two competencies; if two competencies share a sentence, merge them.
4. priority: must_have when the JD says required, must, essential, strong, or lists it under requirements; nice_to_have when it says good to have, plus, bonus, preferred, or familiarity.
5. type: technical (tools, languages, systems, methods) or behavioral (teamwork, communication, ownership, learning, handling pressure).
6. evidence_expected: 2 to 4 short phrases naming the proof a strong candidate would give in an interview - something they built, a decision they made, a number they measured.
7. seniority: fresher, junior, mid or senior, read from the JD. behavioral_technical_mix: two fractions that sum to 1.0.
8. Order competencies must_have first; ids C1, C2, ... in that order.
Return JSON only. No commentary.
"""

# The difficulty ladder is not in the shape: it is constant (rubric.LADDER) and
# rubric.validate_rubric stamps it.
_STAGE_A_SHAPE = """\
{{"role_title": "...",
 "seniority": "fresher|junior|mid|senior",
 "behavioral_technical_mix": {{"behavioral": 0.4, "technical": 0.6}},
 "competencies": [
  {{"id": "C1", "name": "...", "type": "technical|behavioral", "priority": "must_have|nice_to_have",
   "jd_quotes": [{{"text": "<verbatim JD sentence or clause>"}}],
   "evidence_expected": ["...", "..."]}}
 ]}}
"""

STAGE_A_USER = """\
JOB DESCRIPTION (quote only from this text):
<<<JD
{jd_text}
JD>>>

Return exactly this shape:
""" + _STAGE_A_SHAPE

# Used once, when validate_rubric() rejects more than two competencies. Each call
# is a fresh system+user pair (no previous assistant turn), so the shape block
# and the kept competencies' quotes are repeated here for copying.
# {rejected_list}: one '- <id> <name>: "<quote that failed>"' line per failed quote.
# {kept_list}: one '- <id> <name>: "<grounded quote>"' line per kept quote, or "(none)".
# Both come from rubric.build_reask_fields(jd, raw_rubric).
STAGE_A_REASK_USER = """\
JOB DESCRIPTION (quote only from this text):
<<<JD
{jd_text}
JD>>>

A program checked your previous rubric: every jd_quotes text must be an exact substring of the JD. These were not grounded — quote the JD literally or drop them:
{rejected_list}

These competencies passed the check; keep them and copy their quotes exactly as listed:
{kept_list}

Rebuild the full rubric (5 to 8 competencies) in this JSON shape. Every jd_quotes text must be copied character for character from the JD above. If no literal sentence supports a competency, drop it rather than paraphrase.
""" + _STAGE_A_SHAPE

# ---------------------------------------------------------------------------
# Stage B - Agenda Manager -> next question (s.5.2)
# The agenda decides competency / gap / rung / strategy in code; the model only
# words the question. The why-trace is assembled by agenda.py from its own
# inputs, so it is verifiable without trusting the model.
# ---------------------------------------------------------------------------

STRATEGY_HINTS = {
    "open_probe": "Fresh topic. Invite one concrete example from their own project, internship or coursework.",
    "evidence_probe": "They claimed a JD keyword without detail. Ask them to walk you through how they did it.",
    "dig_deeper_vague": "The last answer had no specific noun, number or name. Ask for one specific instance: what exactly, which tool, which number.",
    "dig_deeper_generic": "The last answer was textbook, not lived. Ask what they personally did in one real situation.",
    "quantify_result": "No result was given. Ask what changed because of it - any number, before and after.",
    "ownership_probe": "They said 'we' throughout. Ask what their own part was.",
    "contradiction_probe": "Two statements conflict. Mention both briefly and ask them to reconcile.",
    "escalate": "The last answer was strong. Move one rung up the ladder on the same competency.",
}

LADDER_HINTS = {
    "recall": "Ask what it is or how it works, in their own words.",
    "applied example": "Ask for a time they actually used it, and what came of it.",
    "trade-off or failure": "Ask what went wrong, or what they gave up and why.",
    "design under constraint": "Give one constraint (time, scale, budget, team size) and ask how they would design for it.",
}

STAGE_B_SYSTEM = """\
You are a calm, professional interviewer at an Indian company, talking to a fresher or early-career candidate. You speak plain Indian English as used in an office: simple words, short sentences, no slang, no idioms, no jokes, no praise.

The interview plan is decided for you: which competency, which evidence gap, which difficulty rung, which strategy. Your only job is to word the next question so it sounds natural and follows that plan.

Rules:
- Exactly one question, at most 35 words. No preamble such as "Great answer". Do not join two questions with "and".
- Talk about the JD topic naturally. Never read the JD sentence aloud and never say "competency", "rubric", "ladder", "strategy" or "evidence".
- For a follow-up, briefly reuse the candidate's own words from the trigger so it is clear you listened.
- Aim the question so that a strong candidate would naturally mention the chosen evidence item.
- Follow the tone instruction. Comment on the answer only, never on the person.

Return JSON only:
{{"text": "<the question>", "evidence_item": "<one item copied exactly from the evidence gap list>"}}
"""

# {trigger_line}: TRIGGER_LINE_FORMAT for follow-ups, or NO_TRIGGER ("") for a
# fresh probe. {evidence_gap}: comma-separated items whose coverage is still
# none/weak for the target competency.
STAGE_B_USER = """\
Pressure dial: {pressure_dial}. Tone: {tone}

Coverage so far (competency: evidence still missing):
{coverage_summary}

Target competency: {competency_name}
JD says: "{jd_quote}"
Evidence gap (choose one item): {evidence_gap}
Difficulty rung: {ladder_rung} - {ladder_hint}
Strategy: {strategy} - {strategy_hint}
{trigger_line}
Last two turns:
{last_two_turns}

Write question {question_id} now.
"""

# ---------------------------------------------------------------------------
# Stage C - answer analysis (s.5.3)
# ---------------------------------------------------------------------------

STAGE_C_SYSTEM = """\
You analyse one candidate answer from a mock interview and return strict JSON. A program checks every quote against the transcript and deletes any that is not a verbatim span or whose time does not match the words, so:
- Every quote is copied exactly from the transcript: same words, same order, 2 to 12 words, no "...", no corrections. Quotes contain the words only; never include the @ numbers. Example: transcript "we@8.2 used@8.5 caching@8.9" gives "quote": "we used caching", "t": [8.2, 8.9].
- Every t is [start of the first quoted word, start of the last quoted word], read from the @ timestamps.
- If something is absent, set present to false and write null for its quote, t and ownership. Never invent.

Judge:
- STAR: situation, task, action, result. A result needs a past-tense outcome or a number. action.ownership: "I" if the candidate says I/my/me for the work, "we" if only team language, else "unclear" (a program re-checks it from the pronouns).
- key_quote: the one phrase that best shows how the candidate answered. Always give it when the transcript is not empty, even for a generic answer.
- specificity score 0-3: 0 no concrete noun, number or name; 1 one concrete detail; 2 a named technology plus one detail; 3 named technology, a number or time frame, and a decision.
- jd_keyword_coverage: listed JD keywords the candidate actually used (hit) and not used (missed).
- hedges: phrases such as "I think maybe", "kind of", "or something", "I guess", "not sure".
- contradictions: only where the answer conflicts with a listed prior claim. Copy that claim's answer_id, quote and t exactly as listed into conflicts_with; otherwise [].
- verdict: vague (specificity 0-1) | generic (textbook, no own instance) | adequate | strong (specific, owned, with a result). Judge generic vs adequate by the difficulty rung: at recall a correct explanation is adequate; from applied example upward an answer with no own instance is generic.
- evidence_updates: one entry per listed evidence item: none | weak (mentioned) | strong (shown with detail).
- next_strategy: dig_deeper_vague | dig_deeper_generic | quantify_result (no result) | ownership_probe (only "we") | evidence_probe (keyword claimed, no detail) | contradiction_probe | escalate (only after strong) | open_probe. If the question was a follow-up and the answer still lacks what it asked for, keep the same next_strategy.
- reaction: interested (strong or adequate) | neutral (generic) | thinking (vague).
Return JSON only.
"""

# {transcript_words}: WORD_FORMAT tokens joined by WORD_SEP.
# {prior_claims}: CLAIM_FORMAT lines for verified action/result quotes from
# earlier answers, or NO_CLAIMS. {trigger_line}: as in Stage B.
# {jd_keywords}: rubric.jd_keywords(competency), comma-separated.
STAGE_C_USER = """\
Question {question_id} ({competency_name}): {question_text}
Why it was asked: strategy={strategy}; difficulty rung={ladder_rung}. {trigger_line}
Evidence items: {evidence_expected}
JD keywords: {jd_keywords}
Prior claims from earlier answers (answer_id [start, end]: "quote"):
{prior_claims}

Transcript (each word followed by @ and its start time in seconds):
{transcript_words}

Return exactly this shape (every t is [start of first word, start of last word]; absent parts are null):
{{"answer_id": "{answer_id}",
 "star": {{
   "situation": {{"present": true, "quote": "<words copied from the transcript>", "t": [0.4, 1.3], "ownership": null}},
   "task": {{"present": false, "quote": null, "t": null, "ownership": null}},
   "action": {{"present": true, "quote": "<words copied from the transcript>", "t": [8.2, 9.8], "ownership": "I|we|unclear"}},
   "result": {{"present": false, "quote": null, "t": null, "ownership": null}}}},
 "specificity": {{"score": 1, "missing": ["named technology", "number", "time frame"]}},
 "jd_keyword_coverage": {{"hit": ["..."], "missed": ["..."]}},
 "hedges": [{{"quote": "kind of", "t": [5.1, 5.6]}}],
 "contradictions": [{{"quote": "<this answer's words>", "t": [12.0, 13.4],
                     "conflicts_with": {{"answer_id": "A1", "quote": "<prior claim as listed>", "t": [30.2, 31.9]}}}}],
 "key_quote": {{"quote": "<the phrase that best shows how they answered>", "t": [8.2, 9.8]}},
 "verdict": "vague|generic|adequate|strong",
 "evidence_updates": [{{"competency_id": "{competency_id}", "evidence_item": "<item as listed>", "level": "none|weak|strong"}}],
 "next_strategy": "...",
 "reaction": "interested|neutral|thinking"}}
"""

# ---------------------------------------------------------------------------
# Stage D - report from validated JSON only (s.5.5)
# ---------------------------------------------------------------------------

STAGE_D_SYSTEM = """\
You write the final report of a mock interview for a fresher or early-career candidate. Your input is verified material only: per-answer judgements whose quotes and timestamps have already been checked against the transcript, a coverage matrix and delivery metrics. Do not add any quote, number or claim that is not in the input; a program deletes every report line whose answer_id and quote pair is not in the verified set.

Rules:
- top_fixes: the 3 most fixable behaviours (things the candidate can change by next week), not the 3 worst moments. Each names one behaviour, cites one verified quote with its answer_id and t, gives the rubric line it hurts ("<competency>: <evidence item>" from the coverage matrix), says why it matters for this role, and a stronger_version: 2 or 3 sentences the candidate could have said in their own situation, with placeholders like [number] or [tool] where they must supply the fact.
- per_question: for every answer, the STAR strip (S, T, A, R present or not), the verdict and one key quote, all copied from the input. If the input has no verified quote for an answer, set key_quote to null; never invent one.
- overall_band: one of "not yet ready", "borderline", "ready with polish", "strong". A band, never a score, mark or percentage. band_mover: the single change most likely to move the candidate up one band.
- Tone: direct, specific, respectful. Address the candidate as "you". Criticise the answer, never the person. No praise padding, no "great job".
- Do not restate the coverage matrix or metrics; the app renders them. Mention them only inside a fix's why_it_matters.
Return JSON only.
"""

STAGE_D_USER = """\
Role: {role_title}. Pressure dial: {pressure_dial}. Answers: {n_answers}.

Verified per-answer judgements (cite only these quotes, with their answer_id and t):
{validated_analyses}

Coverage matrix (* = must-have; cells are none|weak|strong):
{coverage_matrix}

Delivery metrics:
{delivery_metrics}

Return exactly this shape (key_quote is null for an answer with no verified quote):
{{"top_fixes": [
   {{"behaviour": "...", "answer_id": "A3", "quote": "<verified quote>", "t": [8.2, 11.9],
     "rubric_line": "<competency>: <evidence item>", "why_it_matters": "...", "stronger_version": "..."}}
 ],
 "per_question": [
   {{"answer_id": "A1", "star": {{"S": true, "T": false, "A": true, "R": false}},
     "verdict": "vague|generic|adequate|strong", "key_quote": {{"quote": "<verified quote>", "t": [0.4, 1.9]}}}}
 ],
 "overall_band": "not yet ready|borderline|ready with polish|strong",
 "band_mover": "..."}}
"""

# ---------------------------------------------------------------------------
# Canned interviewer lines (no LLM call; TTS'd directly)
# ---------------------------------------------------------------------------

OPENER_TEMPLATE = (
    "Hello, and welcome. I will ask you a few questions about the {role_title} role, one at a time. "
    "There is no going back, so take a second to think, then answer with specifics. Let us begin."
)
CLOSING_LINE = "Thank you, that is the end of this round. Your report is being prepared now."
RETRY_OPENER = "Let us try one question again. Same question; this time give me the specifics."

# Mood -> short spoken lead-in, prepended to the next question's TTS (server
# picks one at random). Keys are exactly MOODS. The mood itself is sent as
# {"type":"reaction","mood":...} per s.4.1.
REACTION_LINES = {
    "neutral": ["Okay.", "Alright.", "Noted."],
    "interested": ["Okay, good.", "Right, that helps.", "Okay, let us go further on that."],
    "thinking": ["Hmm, okay.", "Let me see.", "Okay, one moment."],
    "unimpressed": ["That is still not specific.", "I need one concrete instance.", "Let me push you on this."],
}

# Spoken after {"type":"interrupt"} in Tough mode (s.2.3, s.5.6): on time-out
# and on looping (repeated n-grams).
INTERRUPT_LINES = {
    "timeout": ["Let me stop you there.", "Okay, I will stop you there; time is up for this one."],
    "looping": ["Let me stop you there, you are repeating yourself.", "Okay, I have got that point. Let us move on."],
}

# Default mood from a Stage C verdict (the model's `reaction` field is advisory;
# agenda.py takes the verdict default unless the model's reaction is stricter,
# then clamps to the dial's avatar_states). `unimpressed` is never produced by
# the model - only by the dial rule "second vague answer to the same probe" in Tough.
REACTION_BY_VERDICT = {"strong": "interested", "adequate": "interested", "generic": "neutral", "vague": "thinking"}

# ---------------------------------------------------------------------------
# Pressure dial (s.5.6 table + s.2.4 + s.6.4). avatar_states is the single
# truth of what a dial may emit: "nod" appears only where the puppet nods.
# ---------------------------------------------------------------------------

PRESSURE_DIAL = {
    "warmup": {
        "label": "Warm-up",
        "n_questions": 6,
        "time_limit_s": {"behavioral": None, "technical": None},
        "countdown": "none",
        "followups_per_competency": 1,
        "contradiction_probes": False,
        "interrupt_on_timeout": False,
        "interrupt_on_looping": False,
        "looping_ngram": None,
        "avatar_states": ("listening", "thinking", "nod"),
        "unimpressed_after_second_vague": False,
        "tone": "Gentle and encouraging; simpler wording, no time pressure. Still exactly one question. Never interrupt.",
    },
    "realistic": {
        "label": "Realistic",
        "n_questions": 8,
        "time_limit_s": {"behavioral": 90, "technical": 60},
        "countdown": "hidden",
        "followups_per_competency": 2,
        "contradiction_probes": False,
        "interrupt_on_timeout": True,
        "interrupt_on_looping": False,
        "looping_ngram": None,
        "avatar_states": ("listening", "thinking", "nod", "interested", "neutral"),
        "unimpressed_after_second_vague": False,
        "tone": "Professional and neutral, like a campus placement panel. Brief, no small talk.",
    },
    "tough": {
        "label": "Tough",
        "n_questions": 10,
        "time_limit_s": {"behavioral": 90, "technical": 60},
        "countdown": "visible",
        "followups_per_competency": 2,
        "contradiction_probes": True,
        "interrupt_on_timeout": True,
        "interrupt_on_looping": True,
        "looping_ngram": {"n": 4, "min_repeats": 3},  # heuristic - tune on real transcripts
        # No "nod": s.6.4 (nods only in Warm-up / Realistic) wins over s.5.6's "+".
        "avatar_states": ("listening", "thinking", "interested", "neutral", "unimpressed"),
        "unimpressed_after_second_vague": True,
        "tone": "Brisk and demanding. Short questions, no reassurance. Press for specifics.",
    },
}

# ---------------------------------------------------------------------------
# Sampling per stage (BLUEPRINT s.5 + s.8.2). top_k, presence_penalty and
# repeat_penalty are listed as supported chat-completions payload parameters in
# LM Studio's reference (lmstudio.ai/docs/developer/openai-compat/chat-completions,
# read 2026-09-05); top_k is not in the OpenAI client's signature, so llm.py passes
# it via extra_body. presence_penalty 1.5 is Qwen's non-thinking recommendation
# for prose; it is 0 for the JSON stages so repeated keys are not penalised.
# max_tokens is a hard cap under grammar-constrained decoding: if it is hit the
# JSON is truncated and will not parse, so every cap has headroom over the
# largest output the prompt's own limits allow:
#   stage_a: 8 competencies x 2 quotes (~25 words) x 4 evidence items ~ 5 KB
#            ~ 1,400-1,650 tokens (chars/3.5-4 estimate, not the Qwen tokenizer).
#   stage_b: 35-word question + evidence_item + scaffolding ~ 70-90 tokens.
#   stage_c: full shape with nulls, one contradiction, key_quote ~ 400-450 tokens.
#   stage_d: 3 fixes (~500 chars each) + 10 per_question rows ~ 1,000 tokens.
# ---------------------------------------------------------------------------

SAMPLING = {
    "stage_a": {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "max_tokens": 2500},
    "stage_b": {"temperature": 0.65, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5, "max_tokens": 160},
    "stage_c": {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "max_tokens": 800},
    "stage_d": {"temperature": 0.3, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0, "max_tokens": 1600},
}

PROMPTS = {
    "stage_a": {"system": STAGE_A_SYSTEM, "user": STAGE_A_USER, "sampling": SAMPLING["stage_a"]},
    "stage_a_reask": {"system": STAGE_A_SYSTEM, "user": STAGE_A_REASK_USER, "sampling": SAMPLING["stage_a"]},
    "stage_b": {"system": STAGE_B_SYSTEM, "user": STAGE_B_USER, "sampling": SAMPLING["stage_b"]},
    "stage_c": {"system": STAGE_C_SYSTEM, "user": STAGE_C_USER, "sampling": SAMPLING["stage_c"]},
    "stage_d": {"system": STAGE_D_SYSTEM, "user": STAGE_D_USER, "sampling": SAMPLING["stage_d"]},
}
# Short aliases: STAGE_B["system"], STAGE_B["user"], STAGE_B["sampling"].
STAGE_A = PROMPTS["stage_a"]
STAGE_A_REASK = PROMPTS["stage_a_reask"]
STAGE_B = PROMPTS["stage_b"]
STAGE_C = PROMPTS["stage_c"]
STAGE_D = PROMPTS["stage_d"]

# Fields that carry the model's only evidence; a blank one would make it invent.
NONBLANK_FIELDS = frozenset({"jd_text", "transcript_words"})


def fields(stage: str) -> set[str]:
    """Placeholder names a stage's templates require (for tests and callers)."""
    names: set[str] = set()
    for key in ("system", "user"):
        for _, name, _, _ in string.Formatter().parse(PROMPTS[stage][key]):
            if name:
                names.add(name)
    return names


def render(stage: str, **values: object) -> tuple[str, str, dict]:
    """Return (system, user, sampling) for a stage with all placeholders filled.

    Raises KeyError on a missing field and ValueError when ``jd_text`` or
    ``transcript_words`` is blank, rather than sending a half-filled prompt.
    """
    spec = PROMPTS[stage]
    for name in NONBLANK_FIELDS:
        if name in values and not str(values[name]).strip():
            raise ValueError(f"{stage}: {name} is blank; refusing to prompt the model with no evidence")
    return spec["system"].format(**values), spec["user"].format(**values), dict(spec["sampling"])


__all__ = [
    "STRATEGIES", "LADDER", "VERDICTS", "EVIDENCE_LEVELS", "MOODS", "MOOD_ID", "BANDS", "DIALS",
    "WORD_FORMAT", "WORD_SEP", "TURN_FORMAT", "NO_TURNS", "CLAIM_FORMAT", "NO_CLAIMS",
    "TRIGGER_LINE_FORMAT", "NO_TRIGGER",
    "STAGE_A_SYSTEM", "STAGE_A_USER", "STAGE_A_REASK_USER",
    "STAGE_B_SYSTEM", "STAGE_B_USER", "STRATEGY_HINTS", "LADDER_HINTS",
    "STAGE_C_SYSTEM", "STAGE_C_USER",
    "STAGE_D_SYSTEM", "STAGE_D_USER",
    "OPENER_TEMPLATE", "CLOSING_LINE", "RETRY_OPENER", "REACTION_LINES", "INTERRUPT_LINES",
    "REACTION_BY_VERDICT",
    "PRESSURE_DIAL", "SAMPLING", "PROMPTS", "NONBLANK_FIELDS",
    "STAGE_A", "STAGE_A_REASK", "STAGE_B", "STAGE_C", "STAGE_D",
    "fields", "render",
]
