"""Self-check for the Phase 2 fixtures: the JDs, the scripted answers and the two oracles.

`run(fixtures_dir)` returns the list of failed checks (empty when everything holds) and is
what tests/test_fixtures.py asserts on; the CLI prints PASS/FAIL per check and exits 1 on
any failure.

What it enforces
  JDs      350-500 words, shared title and seniority line; every jd_quote, alt_quote and
           other_grounded_sentence is a verbatim substring of its own JD under both the plain
           BLUEPRINT 5.1 norm and gate_norm, and absent from the other JD; jd_quote_offset
           slices the file to exactly the quote, which occurs once; every quote of an entry
           contains one of its match_keywords and no keyword of one entry occurs in another
           entry's quotes; fragment_examples_that_match match their entry under the oracle
           matching rule; paraphrases are not substrings; degenerate quotes are shorter than
           min_quote_words while at least three of them ARE plain substrings (so the check
           is not vacuous); domain terms are present here and absent there; the oracle's own
           behavioral mix satisfies expected_mix.
  Unicode  jd_fintech_unicode.txt is the ASCII JD plus the listed substitutions, each of
           which gate_norm folds back to its ASCII form; the ASCII quotes still ground under
           gate_norm and the must_fail ones do NOT ground under the plain norm.
  Answers  script exists, word_count / spoken_word_count_approx / approx_duration_s agree
           with the script, every quote substring is present exactly once, pronoun counts and
           we_ratio match the hint and team_hiding_flag == (we_ratio > 0.7), context resolves
           to exactly one rubric entry and uses the 5.2 / 5.3 enums, keyword hits occur as
           whole words in the script and misses do not, evidence expectations name real
           entries and levels.

Run by hand:   python fixtures/verify_fixtures.py [fixtures_dir]
Under uv:      uv run --python 3.12 python fixtures/verify_fixtures.py     (from phase2-drafts)
    phase2-drafts/pyproject.toml stops uv's project discovery there. From a directory that
    has a stray pyproject.toml somewhere above it, pass `uv run --no-project ...`, or uv
    adopts that project and tries to build it (the scratchpad root's onnx-asr / kokoro
    pyproject did exactly that and started pulling torch).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata

# Enums from BLUEPRINT 5.2 / 5.3 (kept local so the fixtures need no import from brain/).
LADDER = ("recall", "applied example", "trade-off or failure", "design under constraint")
STRATEGIES = (
    "open_probe", "evidence_probe", "dig_deeper_vague", "dig_deeper_generic",
    "quantify_result", "ownership_probe", "contradiction_probe", "escalate",
)
VERDICTS = ("vague", "generic", "adequate", "strong")
MOODS = ("neutral", "interested", "thinking", "unimpressed")
LEVELS = ("none", "weak", "strong")
WE_RATIO_TEAM_HIDING = 0.7
WPM = 155.0

_WS = re.compile(r"\s+")


def plain_norm(s: str) -> str:
    """The BLUEPRINT 5.1 sketch, verbatim: collapse whitespace, strip, lower."""
    return _WS.sub(" ", s).strip().lower()


# The punctuation a pasted JD carries that the model will write in ASCII. Mirrors
# expected_rubric_hints.json -> gate_norm.translate (verify checks the two agree).
PUNCT_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
    "…": "...",
})


def gate_norm(s: str) -> str:
    """What the rubric gate must apply to both quote and JD: NFKC, punctuation fold, plain_norm."""
    return plain_norm(unicodedata.normalize("NFKC", s).translate(PUNCT_FOLD))


_BULLET = re.compile(r"^(?:[-*•·]|\d+[.)])\s+")


def strip_for_match(q: str) -> str:
    """gate_norm plus: drop a leading bullet marker and trailing punctuation (oracle matching only)."""
    return _BULLET.sub("", gate_norm(q)).strip(" .;:,").strip()


def oracle_match(q: str, entry: dict, min_words: int) -> str | None:
    """The reference sentence of `entry` that `q` matches under the _notes rule, else None."""
    qn = strip_for_match(q)
    if len(qn.split()) < min_words:
        return None
    for ref in [entry["jd_quote"], *entry["alt_quotes"]]:
        rn = strip_for_match(ref)
        if qn in rn or rn in qn:
            return ref
    return None


def _number_words(n: int) -> int:
    """Words in the spoken English rendering of a non-negative integer (1400 -> 'one thousand four hundred' = 4)."""
    if n < 20:
        return 1
    if n < 100:
        return 1 if n % 10 == 0 else 2
    if n < 1000:
        return 2 + (_number_words(n % 100) if n % 100 else 0)
    return _number_words(n // 1000) + 1 + (_number_words(n % 1000) if n % 1000 else 0)


def spoken_word_count(text: str) -> int:
    """Estimate of the words a TTS engine speaks: digits become number words, all-caps
    abbreviations (API, TTL, ID) are spelled letter by letter, hyphen compounds are two words."""
    n = 0
    for raw in text.split():
        for part in raw.split("-"):
            core = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", part)
            if not core:
                continue
            m = re.fullmatch(r"([A-Za-z]*)(\d+)([A-Za-z]*)", core)
            if m:
                pre, num, post = m.groups()
                for affix in (pre, post):
                    if affix:
                        n += len(affix) if affix.isupper() else 1
                n += _number_words(int(num))
            elif core.isupper() and core.isalpha() and len(core) >= 2:
                n += len(core)
            else:
                n += 1
    return n


def _whole_word(term: str, text: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", text.lower()) is not None


def _entry_for_keyword(hints: dict, keyword: str) -> list[dict]:
    return [e for e in hints["competencies"] if keyword in e["match_keywords"]]


def run(fixtures_dir: str | pathlib.Path, *, verbose: bool = True) -> list[str]:
    D = pathlib.Path(fixtures_dir)
    failures: list[str] = []

    def check(cond: bool, msg: str) -> bool:
        if verbose:
            print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)
        return bool(cond)

    def read(name: str) -> str:
        data = (D / name).read_bytes()
        check(not data.startswith(b"\xef\xbb\xbf"), f"{name} has no BOM")
        check(b"\r" not in data, f"{name} uses LF line endings")
        return data.decode("utf-8")

    rub = json.loads((D / "expected/expected_rubric_hints.json").read_text(encoding="utf-8"))
    ana = json.loads((D / "expected/expected_analysis_hints.json").read_text(encoding="utf-8"))

    # The JSON's fold table and this module's must be the same table.
    check(
        {chr(k): v for k, v in PUNCT_FOLD.items()} == rub["gate_norm"]["translate"],
        "gate_norm.translate in the JSON equals verify_fixtures.PUNCT_FOLD",
    )
    min_quote_words = rub["min_quote_words"]
    min_match_words = rub["min_match_words"]
    check(1 <= min_quote_words <= min_match_words, "min_quote_words <= min_match_words")
    check(len(gate_norm("optimise API latency").split()) >= min_quote_words, "BLUEPRINT 5.2 example quote stays legal")

    # ------------------------------------------------------------------ JDs
    jds = {n: read(n) for n in rub["jds"]}
    check(len(jds) == 2, "exactly two contrasting JDs")
    for n, jd in jds.items():
        other = next(x for x in jds if x != n)
        h = rub["jds"][n]
        wc = len(jd.split())
        check(350 <= wc <= 500, f"{n} word count {wc} in 350-500")
        check(rub["shared_title"] in jd and "0-2 years" in jd, f"{n} carries shared title and 0-2 years")
        comps = h["competencies"]
        check(h["min_competencies"] <= len(comps) <= h["max_competencies"],
              f"{n} has {len(comps)} entries within [{h['min_competencies']}, {h['max_competencies']}]")
        check(rub["min_entries_matched"] <= len(comps), f"{n} min_entries_matched <= entries")
        n_beh = sum(c["type"] == "behavioral" for c in comps)
        mix = h["expected_mix"]
        check(n_beh >= mix["behavioral_count_min"] and n_beh / len(comps) >= mix["behavioral_min"],
              f"{n} oracle itself satisfies expected_mix ({n_beh}/{len(comps)} behavioral)")
        check(all(c["type"] in ("technical", "behavioral") and c["priority"] in ("must_have", "nice_to_have") for c in comps),
              f"{n} entry types/priorities are the 5.1 enums")
        check(any(c["priority"] == "nice_to_have" for c in comps), f"{n} has a nice_to_have entry")
        check(sum(c["priority"] == "must_have" for c in comps) >= 4, f"{n} has at least four must_have entries")
        for i, c in enumerate(comps):
            quotes = [c["jd_quote"], *c["alt_quotes"]]
            for q in quotes:
                check(plain_norm(q) in plain_norm(jd), f"{n} :: {c['name']} :: grounded (plain norm): {q[:48]}...")
                check(gate_norm(q) in gate_norm(jd), f"{n} :: {c['name']} :: grounded (gate norm): {q[:48]}...")
                check(gate_norm(q) not in gate_norm(jds[other]), f"{n} :: {c['name']} :: absent from {other}: {q[:48]}...")
                check(len(gate_norm(q).split()) >= min_match_words, f"{n} :: {c['name']} :: quote has >= {min_match_words} words: {q[:48]}...")
                check(any(k.lower() in gate_norm(q) for k in c["match_keywords"]),
                      f"{n} :: {c['name']} :: quote contains a match_keyword: {q[:48]}...")
            check(jd.count(c["jd_quote"]) == 1, f"{n} :: {c['name']} :: jd_quote occurs exactly once")
            off = c.get("jd_quote_offset")
            ok = isinstance(off, list) and len(off) == 2 and jd[off[0]:off[1]] == c["jd_quote"]
            check(ok, f"{n} :: {c['name']} :: jd_quote_offset {off} slices the file to the quote")
            for q in c.get("fragment_examples_that_match", []):
                check(gate_norm(strip_for_match(q)) in gate_norm(jd), f"{n} :: {c['name']} :: fragment grounded: {q[:48]}...")
                check(oracle_match(q, c, min_match_words) is not None, f"{n} :: {c['name']} :: fragment matches its entry: {q[:48]}...")
                check(all(oracle_match(q, o, min_match_words) is None for j, o in enumerate(comps) if j != i),
                      f"{n} :: {c['name']} :: fragment matches no other entry: {q[:48]}...")
            for j, o in enumerate(comps):
                if j == i:
                    continue
                leaked = [k for k in c["match_keywords"] for q in [o["jd_quote"], *o["alt_quotes"]] if k.lower() in gate_norm(q)]
                check(not leaked, f"{n} :: {c['name']} :: keywords {leaked} do not occur in {o['name']} quotes")
        for q in h["other_grounded_sentences"]:
            check(gate_norm(q) in gate_norm(jd), f"{n} :: other grounded: {q[:48]}...")
            check(gate_norm(q) not in gate_norm(jds[other]), f"{n} :: other grounded absent from {other}: {q[:48]}...")
            hit = [c["name"] for c in comps if oracle_match(q, c, min_match_words)]
            check(not hit, f"{n} :: other grounded sentence matches no entry ({hit}): {q[:48]}...")
        for p in h["paraphrase_that_must_be_rejected"]:
            check(plain_norm(p) not in plain_norm(jd) and gate_norm(p) not in gate_norm(jd),
                  f"{n} :: paraphrase not a substring: {p[:48]}...")
        degenerate = h["degenerate_quotes_must_be_rejected"]
        for p in degenerate:
            check(len(gate_norm(p).split()) < min_quote_words, f"{n} :: degenerate shorter than {min_quote_words} words: {p!r}")
        n_sub = sum(plain_norm(p) in plain_norm(jd) for p in degenerate)
        check(n_sub >= 3, f"{n} :: at least three degenerate quotes ARE plain substrings ({n_sub}) so the check bites")
        terms = h["domain_terms"]
        check(1 <= h["min_domain_terms_hit"] <= len(terms), f"{n} :: min_domain_terms_hit within domain_terms")
        for t in terms:
            check(t.lower() in gate_norm(jd), f"{n} :: domain term present: {t}")
            check(t.lower() not in gate_norm(jds[other]), f"{n} :: domain term absent from {other}: {t}")

    # ------------------------------------------------------------------ unicode variant
    for vname, v in rub["unicode_variants"].items():
        base_name = v["unicode_variant_of"]
        check(base_name in jds, f"{vname} :: variant of a known JD")
        base = jds[base_name]
        text = read(vname)
        check(sum(ord(ch) > 127 for ch in text) >= len(v["substitutions"]), f"{vname} :: carries non-ASCII punctuation")
        for s in v["substitutions"]:
            check(base.count(s["ascii"]) == 1, f"{vname} :: ascii form once in {base_name}: {s['what']}")
            check(text.count(s["unicode"]) == 1 and s["ascii"] not in text, f"{vname} :: unicode form replaces ascii form: {s['what']}")
            # Wrapping quotation marks are stripped before comparing, exactly as the whole-file check below does.
            check(gate_norm(s["ascii"]) in gate_norm(s["unicode"]).replace('"', ""), f"{vname} :: gate_norm folds substitution: {s['what']}")
        check(gate_norm(text).replace('"', "") == gate_norm(base), f"{vname} :: gate_norm(variant) minus quotation marks == gate_norm(base)")
        check(plain_norm(text) != plain_norm(base), f"{vname} :: plain norm does NOT fold the variant (the bug being fixed)")
        for q in v["ascii_quotes_must_still_ground"]:
            check(gate_norm(q) in gate_norm(text), f"{vname} :: ascii quote grounds under gate_norm: {q[:48]}...")
            check(plain_norm(q) in plain_norm(base), f"{vname} :: ascii quote grounds in the ASCII base: {q[:48]}...")
        for q in v["must_fail_under_plain_norm"]:
            check(q in v["ascii_quotes_must_still_ground"], f"{vname} :: must_fail entry is also a must_ground entry: {q[:48]}...")
            check(plain_norm(q) not in plain_norm(text), f"{vname} :: ascii quote does NOT ground under plain norm: {q[:48]}...")

    # ------------------------------------------------------------------ answers
    for k, a in ana["answers"].items():
        txt = read(a["script_file"])
        check(a["script_file"].startswith("sample_answer_") and a["wav_file"] == a["script_file"].replace(".txt", ".wav"),
              f"{k} :: script and wav share the sample_answer_ stem")
        wc = len(txt.split())
        check(wc == a["word_count"], f"{k} :: word_count {wc} == {a['word_count']}")
        spoken = spoken_word_count(txt)
        check(spoken == a["spoken_word_count_approx"], f"{k} :: spoken_word_count_approx {spoken} == {a['spoken_word_count_approx']}")
        est = spoken / WPM * 60
        check(abs(a["approx_duration_s"] - est) <= 1.0, f"{k} :: approx_duration_s {a['approx_duration_s']} ~ {est:.1f}s at {WPM:.0f} wpm")

        subs = list(a["quote_substrings"]) + list(a.get("hedges_quote_substrings", [])) + list(a.get("overlapping_quotes_both_valid", []))
        for part, v in a["star"].items():
            subs += v.get("quote_substrings", [])
            if v["present"]:
                check(bool(v.get("quote_substrings")), f"{k} :: star.{part} present => has quote_substrings")
        for q in subs:
            check(txt.count(q) == 1, f"{k} :: substring present exactly once: {q!r}")
            check(not re.search(r"\d", q), f"{k} :: substring has no digits: {q!r}")
        for bw in a.get("buzzwords", []):
            check(txt.count(bw) == 1, f"{k} :: buzzword present once: {bw}")
        for tech in a.get("named_technologies", []):
            check(_whole_word(tech, txt), f"{k} :: named technology in script: {tech}")
        if a.get("numbers_present"):
            check(re.search(r"\d", txt) is not None, f"{k} :: numbers present in script")
        if a.get("hedges_quote_substrings") == [] and "max_hedges" in a:
            for approximator in ("about", "around", "roughly", "maybe", "kind of", "sort of", "or something", "i think", "i guess"):
                check(not _whole_word(approximator, txt), f"{k} :: no approximator '{approximator}' in a no-hedge script")

        toks = re.findall(r"\b(i|my|we|our)\b", txt.lower())
        i_n = sum(t in ("i", "my") for t in toks)
        we_n = sum(t in ("we", "our") for t in toks)
        ratio = we_n / (i_n + we_n) if (i_n + we_n) else 0.0
        hint = a["ownership_ratio_hint"]
        check(hint["I"] == i_n and hint["we"] == we_n, f"{k} :: pronoun counts I={i_n} we={we_n} match hint")
        check(abs(hint["we_ratio"] - ratio) < 0.02, f"{k} :: we_ratio {ratio:.2f} matches hint {hint['we_ratio']}")
        check(isinstance(hint["team_hiding_flag"], bool) and hint["team_hiding_flag"] == (ratio > WE_RATIO_TEAM_HIDING),
              f"{k} :: team_hiding_flag is bool and equals we_ratio > {WE_RATIO_TEAM_HIDING}")

        ctx = a["context"]
        check(ctx["jd"] in jds, f"{k} :: context.jd is a fixture JD")
        entries = _entry_for_keyword(rub["jds"][ctx["jd"]], ctx["competency_match_keyword"]) if ctx["jd"] in jds else []
        check(len(entries) == 1, f"{k} :: competency_match_keyword resolves to exactly one entry")
        check(ctx["ladder_rung"] in LADDER and ctx["strategy"] in STRATEGIES, f"{k} :: context rung/strategy are 5.2 enums")
        check(bool(ctx["question"].strip()) and ctx["question"].rstrip().endswith("?"), f"{k} :: context has a question")
        check(bool(ctx["jd_keywords"]), f"{k} :: context.jd_keywords non-empty")
        for kw in ctx["jd_keywords"]:
            check(gate_norm(kw) in gate_norm(jds[ctx["jd"]]) if ctx["jd"] in jds else False, f"{k} :: jd_keyword is in the JD: {kw}")
        hits, misses = a["jd_keyword_hits_any_of"], a["jd_keyword_missed_any_of"]
        check(set(hits) <= set(ctx["jd_keywords"]) and set(misses) <= set(ctx["jd_keywords"]), f"{k} :: hits/misses are subsets of context.jd_keywords")
        check(not (set(hits) & set(misses)), f"{k} :: hits and misses disjoint")
        for kw in hits:
            check(_whole_word(kw, txt), f"{k} :: hit keyword occurs as a whole word in the script: {kw}")
        for kw in misses:
            check(not _whole_word(kw, txt), f"{k} :: missed keyword absent from the script: {kw}")
        if a.get("jd_keyword_hits_expected_empty"):
            check(hits == [] and all(not _whole_word(kw, txt) for kw in ctx["jd_keywords"]), f"{k} :: no jd_keyword occurs in the script")
        else:
            check(bool(hits) and bool(misses), f"{k} :: both hits_any_of and missed_any_of non-empty")
        for kw in a.get("evidence_keywords_any_of", []):
            check(_whole_word(kw, txt), f"{k} :: evidence keyword in script: {kw}")
        check(a.get("contradictions_expected_empty") is True, f"{k} :: contradictions_expected_empty is true")
        for eu in a["evidence_updates_expected"]:
            ents = _entry_for_keyword(rub["jds"][ctx["jd"]], eu["competency_match_keyword"]) if ctx["jd"] in jds else []
            check(len(ents) == 1, f"{k} :: evidence_updates_expected names one entry: {eu['competency_match_keyword']}")
            lv = eu.get("any_level", eu.get("max_level"))
            check(lv in LEVELS and ("any_level" in eu) != ("max_level" in eu), f"{k} :: evidence expectation has one valid level: {eu}")
        check(set(a["verdict_any_of"]) <= set(VERDICTS) and a["verdict_any_of"], f"{k} :: verdict_any_of within enum")
        check(set(a["next_strategy_any_of"]) <= set(STRATEGIES) and a["next_strategy_any_of"], f"{k} :: next_strategy_any_of within enum")
        check(set(a["reaction_any_of"]) <= set(MOODS) and a["reaction_any_of"], f"{k} :: reaction_any_of within enum")
        smin, smax = a.get("specificity_min", 0), a.get("specificity_max", 3)
        check(0 <= smin <= smax <= 3, f"{k} :: specificity bounds sane ({smin}..{smax})")
        if verbose:
            print(f"     {k}: {wc} script words, ~{spoken} spoken, est {est:.1f}s at {WPM:.0f} wpm, we_ratio {ratio:.2f}")

    flags = [a["ownership_ratio_hint"]["team_hiding_flag"] for a in ana["answers"].values()]
    check(any(flags) and not all(flags), "at least one answer trips team-hiding and at least one does not")
    check(any("overlapping_quotes_both_valid" in a for a in ana["answers"].values()), "an overlapping-quote case exists")
    return failures


def main(argv: list[str]) -> int:
    d = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).resolve().parent
    failures = run(d)
    print()
    print("ALL OK" if not failures else f"{len(failures)} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
