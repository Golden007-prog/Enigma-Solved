# brain/schemas.py — models and the LM Studio strict-schema exporter

`schemas.py` is the single source of shape for the interview brain. It holds the pydantic v2 models for BLUEPRINT §5.1–§5.5 and one function, `llm_schema(Model)`, that turns a model into a schema LM Studio can compile into a llama.cpp grammar. Run `python brain/schemas.py` to print every LLM schema and execute the built-in self-check: round trip of the §5 examples, list↔dict folding of `evidence_updates`, report assembly, a vocabulary drift guard against `brain/prompts`, the strictness audit of every exported schema, and — when `jsonschema` happens to be installed — validation of example payloads against each schema. It was exercised on Python 3.12.10 / pydantic 2.13.5 and 3.11.9 / pydantic 2.13.4.

## What each stage sends to LM Studio

| Stage | Canonical model (stored) | LLM-facing model (`STAGE_LLM_MODELS`) | Why they differ |
|---|---|---|---|
| A rubric | `Rubric` | `Rubric` | Same class. `JDQuote.start/end` are excluded from the LLM schema (`LLM_EXCLUDE`); rubric.py recomputes the offsets after the substring gate accepts `text`. |
| B question | `Question` (§5.2, full why-trace) | `QuestionDraft` = `{text, evidence_item}` | The Agenda Manager already chose competency, JD quote, strategy, rung and trigger (§2.3 — the why-trace must be provable code, not prose). The model only words the question and names the evidence-gap item it aimed at, exactly as `STAGE_B_SYSTEM` in `brain/prompts` asks. |
| C analysis | `Analysis` (§5.3, `evidence_updates` is a dict-of-dicts) | `Analysis` with `LLM_OVERRIDES`/`LLM_EXCLUDE` | A free-form dict cannot carry `additionalProperties: false`, so the model emits `evidence_updates` as a list of `{competency_id, evidence_item, level}` triples (`EvidenceUpdate`); a `mode="before"` validator folds the list back into the §5.3 dict, so `Analysis.model_validate_json(llm_text)` works directly and `model_dump()` is the spec shape (`evidence_update_list()` goes the other way). `specificity.scale` is a constant the model is not asked to type. `star.*.ownership` is narrowed to the prompt's `I / we / unclear`; the canonical enum also accepts `mixed`, which quotegate's we-ratio rule writes. |
| D report | `Report` (§5.5, five sections) | `ReportDraft` = `{top_fixes, per_question, overall_band, band_mover}` | `coverage_matrix` and `delivery` are computed by code (§5.2 state, §5.4 metrics) and attached with `Report.from_draft(...)`; asking a 9B model to re-type numbers it was given only invites drift. |

`llm_response_format(Model)` wraps the schema as `{"type": "json_schema", "json_schema": {"name", "strict": true, "schema"}}`, which is the `response_format` value for the OpenAI-compatible `/v1/chat/completions` call in `llm.py`.

## Strict-schema constraints applied by `llm_schema`

LM Studio hands the schema to llama.cpp's `json-schema-to-grammar`, which supports a subset of JSON Schema and silently ignores what it does not understand. The exporter therefore starts from `Model.model_json_schema()` and rewrites it so the result is (a) strict in the OpenAI-structured-outputs sense and (b) fully inside the grammar converter's vocabulary. `check_llm_schema(schema)` audits the result and `llm_schema` raises if anything slips through.

1. **No `$ref` / `$defs`.** Pydantic emits every nested model as a `$defs` entry. All references are inlined; a cycle raises `ValueError` because a grammar schema must be a tree. Sibling keys next to a `$ref` are merged in, and the older one-element `allOf` wrapper is flattened.
2. **Every object is closed and every property required.** `additionalProperties: false` on every object node and `required` = all properties in declaration order. Optional fields are still optional in Python (`x: T | None = None`) but appear in the schema as `anyOf: [T, {"type": "null"}]` and are required — the model writes `null` instead of omitting the key. Property order is generation order under the grammar, so the models are declared so the model reasons (STAR, specificity, coverage) before it commits to `verdict`.
3. **No free-form dicts.** Any `type: object` without `properties` (what a `dict[str, X]` field becomes) raises, pointing at `LLM_OVERRIDES` as the fix. That is why `evidence_updates` is spelled as triples.
4. **Tuples become `items` + `minItems`/`maxItems`.** `tuple[float, float]` (`Span`) produces `prefixItems` in pydantic; it is rewritten to `{"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}`, the most portable form (`prefixItems` is supported by recent llama.cpp but not by every converter). Heterogeneous tuples raise — use a model instead.
5. **Unsupported keywords are stripped**: `format`, `pattern`, `patternProperties`, `propertyNames`, `multipleOf`, `uniqueItems`, `contains`, `if/then/else`, `not`, `dependent*`, `unevaluated*`, `minProperties`/`maxProperties`. None of the models use them today; the strip makes that a guarantee rather than a habit, and the checker reports any that appear.
6. **Numeric bounds only on integers.** llama.cpp builds digit-by-digit rules for integer `minimum`/`maximum` (so `specificity.score` is grammar-limited to 0–3) but has no such rule for floats, so bounds on `number` are removed. Float fields therefore carry no bounds in pydantic either; `Mix` renormalises instead of rejecting, and timestamps are left to the quote gate.
7. **`minItems`/`maxItems` stay, and only simple ones exist**: `jd_quotes ≥ 1`, `evidence_expected 1–4`, `competencies 1–8`, `top_fixes 1–3` (draft) and the fixed length `2` for spans. The 5–8 competency count in the Stage A prompt is deliberately *not* a schema minimum: a short JD must not force invented competencies (§5.1 "Do not invent"), and the substring gate can legitimately shrink the list.
8. **Enums are plain `enum` arrays of strings**; `Literal["0-3"]` would become `const`, but that field is excluded from the LLM schema anyway.
9. **`title`, `default`, `examples`, `description` and other annotations are stripped.** LM Studio compiles the schema and never shows it to the model, so a class docstring in the payload is dead weight on every call. Field semantics live in the stage prompts. If the schema is ever pasted into a prompt as documentation, use `Model.model_json_schema()` directly.

Parsing the reply uses the canonical model (`Rubric.model_validate_json`, `Analysis.model_validate_json`, ...). `StrictBase` sets `extra="forbid"`, so an unexpected key means the schema and the model drifted; grammar-constrained output never produces one.

## Alignment with `brain/prompts/__init__.py`

The prompts *describe* the JSON shape and the grammar *enforces* it, so the two drafts were reconciled by reading the templates: strategies, ladder rungs, verdicts, evidence levels, moods, `MOOD_ID` and bands are identical (the self-check asserts this whenever `brain/prompts` is importable), Stage B's `{text, evidence_item}`, Stage C's `ownership: I|we|unclear`, string `conflicts_with` and omitted `scale`, and Stage D's `S/T/A/R` strip, bare-string `overall_band` and `band_mover` all match the templates verbatim.

Two things in the prompts still need a touch from whoever owns them, because the grammar cannot follow them:

- `STAGE_C_USER` shows `"evidence_updates": {"C3": {"<evidence item>": "none|weak|strong"}}` (the §5.3 dict). Under strict mode the model will be forced to emit `"evidence_updates": [{"competency_id": "C3", "evidence_item": "<evidence item>", "level": "none|weak|strong"}]`; the example line should say so, otherwise the model is told one shape and constrained to another.
- The Stage C example writes `"task": {"present": false}`; the grammar will require `"quote": null, "t": null, "ownership": null` as well. A short "absent fields are null" note in `STAGE_C_SYSTEM` keeps the instruction and the grammar in step.

## Decisions where the blueprint is silent

Each of these should get a line in `docs/DECISIONS.md` if the draft is adopted.

- `Ownership` is `I | we | unclear | mixed`. The LLM sees the first three (prompt vocabulary); `mixed` is what quotegate's we-ratio rule writes when both pronouns are used. §5.3 only shows `"we"`.
- `Band` is `not yet ready | borderline | ready with polish | strong` (the Stage D prompt's phrases, shown verbatim in the app), and `band_mover` carries "the one thing that would move it" as a sibling key of `overall_band`.
- `Contradiction` = `{quote, t, conflicts_with: str}` where `conflicts_with` is the prior claim exactly as listed in the prompt; only the current answer's half goes through the quote gate. A structured `{answer_id, quote, t}` half would let the report replay both sides — worth revisiting once analyzer.py decides how it lists prior claims.
- `StarStrip` is keyed `S/T/A/R`; `PerQuestion` carries `answer_id` only (answers and questions pair 1:1, the server owns the mapping).
- `time_limit_s` is `int | None`; `None` is the Warm-up dial (§5.6: no timer). `reaction_before` defaults to `neutral` so Q1 needs no prior analysis.
- `CoverageMatrix` is a list of rows (`competency_id`, `name`, `priority`, `cells[]`) built from the §5.2 dict state with `CoverageMatrix.from_state(rubric, coverage)`; `empty_must_haves()` returns the rows the report uses to explain the band.
- `DeliveryMetrics` mirrors §5.4 with `None` for anything that needs the optional Whisper pass (`fillers_per_min`) or a Q1 baseline (`monotone`, `f0_sd_hz`, `rms_variance`); `per_answer[]` keeps the per-answer numbers the report's STAR strip sits next to.
- `Report.top_fixes` allows 0–3 (the evidence gate may drop fixes); `ReportDraft.top_fixes` demands 1–3 from the model.
- `Mix` renormalises to sum 1 (accepts `40/60` as well as `0.4/0.6`) rather than failing the whole rubric on a rounding slip.
- `FOLLOW_UP_STRATEGIES` (evidence, dig-deeper ×2, quantify, ownership, contradiction) versus fresh-question strategies (`open_probe`, `escalate`) is spelled out for agenda.py's policy step 1. `MOOD_INDEX` maps §4.1 moods to the Rive `mood` number in §6.1.
- `JDQuote.start/end` are `int | None` in the canonical model and absent from the LLM schema; the gate fills them from `jd.find(...)` on the normalised text.
- No `Dial` enum lives here; the pressure dial (§5.6) is agenda.py's concern and `brain/prompts.DIALS` already names the three values.

## Things a reviewer may want to check

- The `evidence_updates` triple form was chosen over a generic `{key, value}` pair encoding because named keys read better to a 9B model; the cost is one explicit override on `Analysis`.
- LM Studio's exact `response_format` envelope (`json_schema.name`, `strict`) follows its OpenAI-compatibility docs as of the blueprint's sources; `llm_probe.py` in Phase 1 is the place that proves it against the running build.
- Integer bounds (`score` 0–3) are kept on the assumption that the bundled llama.cpp is post-mid-2024, which any LM Studio 0.4.x is. If a grammar compile error ever mentions `minimum`, add `"minimum"`/`"maximum"` to the integer-strip path and let pydantic enforce the range on parse.
- The sibling drafts (`agenda.py`, `rubric.py`, `quotegate.py`, `report_gate.py`) are dict-based and do not import `brain.schemas`; `agenda.py` keeps its own tolerant `Rubric`/`Competency` views. Nothing here breaks them, but once integration starts one of the two should become the source of truth for the rubric shape.
