# "Speak It" — Research Report (5 Sep 2026)

**Method note.** Web search, page fetches (2025–2026 sources preferred), Hugging Face Hub queries, and the eWAVE CLDF dataset (pulled from GitHub) were used. Reddit was blocked from the research environment, so "what users complain about" comes from Play Store / App Store / Trustpilot review pages and 2025–26 reviewer write-ups instead. Anything not verifiable directly is flagged inline and collected in §5.

---

## 1. Competitor / landscape scan (2025–2026)

| App | Correction loop (what actually happens after you speak) | Pronunciation | Offline | Pricing (India where found) | What users complain about |
|---|---|---|---|---|---|
| **ELSA Speak** (US/VN) | Listen-and-repeat drills scored per phoneme against American English; "phoneme-level highlighting of where you went wrong, with audible delta against a native speaker" (AIpedia, May 2026). **Does not correct grammar** (Koto review, Apr 2026). | Best-in-class phoneme scoring; accents: American/British/Australian | **Partial** — offline access only in Pro tier ("download lessons"); unclear whether scoring runs offline — *not verified* | Pro ~$19.99/mo or $129.99/yr; Premium $16–20/mo or $159.99/yr (Koto). India: TalkDrill lists ₹599/mo; EngVarta lists "₹12–₹17/month" (almost certainly USD mislabeled — *flag*). Play Store IN: 4.5★, 9.73L reviews, 1Cr+ installs | "Study Sets stop progressing automatically"; "charged every year since 2023 for a subscription I no longer use… no clear way to see if you're still subscribed"; support hard to reach; "AI only — zero conversation", "repetitive drill-based exercises", no interview prep |
| **Stimuler** (Bengaluru; IIT-BHU founders, 2022) | Voice-first simulated phone calls; "Record a 60 seconds speech and get instant feedback… in less than 20 seconds" across 15+ metrics (pronunciation, fluency, vocabulary, tone, energy) → "speech report card" → recommended exercises. Own blog says its corrections center on "pace, fillers, and clarity". | Proprietary "in-house models trained at the phoneme level, accounting for regional accents from India, Latin America, and Southeast Asia" (YourStory, 7 Jul 2025) | No (users hit "Something went wrong" errors) | Freemium; premium "from $3/month (varies by region)", Play listing "less than $5/month". 4M users, 60k paid, 175 countries, **85% of paying users outside India**; $3.75M pre-Series A (Lightspeed). Play IN: 4.8★, 1.95L reviews, 1Cr+ | Annual subscriber "asked to resubscribe after three months"; persistent "Something went wrong" errors killing streaks; previously-free IELTS practice paywalled — users say they are **switching to ChatGPT** |
| **BoldVoice** (YC) | Video lesson from accent coach → word drills → sentence practice → AI phoneme-level score. Pronunciation only: "doesn't build vocabulary, improve fluency, reduce speaking anxiety, or develop conversational confidence" (Practice Me, Apr 2026) | Phoneme-level; American English only | Not stated | "Varies by platform and promotional offers" — no figure | "certain sounds are persistently being misinterpreted by the language model"; scripted, repetitive; no free conversation |
| **Praktika** (AI avatars) | Never interrupts; a correction button appears beside every line — "even when you haven't made a mistake, so you must tap it constantly or risk missing errors"; "no end-of-lesson feedback summary"; "won't reliably catch subtle grammar or word-order mistakes unless they significantly disrupt meaning" (LanguaTalk, Jun 2026) | Speech recognition "does a good job interpreting partial sentences" but overly forgiving | Not stated | No monthly plan ("minimum commitment is fairly high"); ~$2M/month iPhone revenue (Mar 2026). Trustpilot 3.7/5 (1,178), 18% one-star | Billing ("They scam you with charges…"); "voice recognition frequently misunderstands spoken words" (App Store: said "sechs", heard "vier"); ignores beginner level; repetitive; a qualified teacher rated it 6/10 for wrong definitions and interface grammar errors |
| **Speak** (OpenAI-backed) | Real-time grammar/phrasing feedback during conversation; "sometimes requesting users repeat the phrase"; Premium Plus adds "Target Your Frequent Mistakes" | "Pronunciation Coach"; scoring "simpler" than ELSA; "one accent in, one accent out" (American only) | Not stated | US: $17.99/mo or $83.99/yr; Plus $39.99/mo or $164.99/yr (SpeakShark, Aug 2026). No India price found | No permanent free tier; American-only; little for advanced users |
| **Duolingo Video Call (Lily)** | Free-form call; "actionable feedback after calls and captions"; push-to-talk added 2025. Correction mechanism not documented | Not described | No | Max ~$30/mo or $168/yr (US). India price *not verified* | "Speaking practice is minimal"; conversation depth limited; whitepaper gives **no effect sizes** (see §2) |
| **TalkPal** | Orange "!" beside a turn → tap to see suggestion; "corrections are reactive rather than proactive"; **no summary** after a lesson (LanguaTalk, Feb 2026) | Score /100 per sentence with off words highlighted but "lacks actionable guidance" | Not stated | Free 10 min/day; $9.99/mo; $4.99/mo annual ($59.88) | Generic feedback; inconsistent pronunciation accuracy; not for complete beginners |
| **Loora** | Post-utterance/session feedback on pronunciation, pace, fillers; "grammar correction outside pronunciation is lighter" (misses missing articles/prepositions) | Individual sounds + word stress | Not stated | $29.99/mo | Premium price; B1+ only; "occasional feedback misses genuine errors"; loops |
| **Cambly (+AI review)** | Human tutor; "AI for pre- and post-lesson review" | Human | No | ~₹1,000 per 30-min lesson; ₹1,199–₹8,499/mo (EngVarta, Jul 2026); Trustpilot 2.1/5 | USD pricing; scheduling; ₹7,000/mo for 2 sessions/wk "unsustainable" |
| **Hallo** | "Press a button and start speaking in 3 seconds"; feedback on fluency/grammar/vocab **after** each lesson | Not detailed | No | Freemium; Play 2.9★ (42.4K), 1M+ | Duplicate charges; free InstaMatch removed; points not tracked; 3–7 day support |
| **Ling** | Gamified courses for less-common languages; not a speaking-first English tool | Basic | Partial (lessons) | — | Low relevance to this decision |
| **Google Little Language Lessons / Gemini Live** | Tiny Lesson, Slang Hang, Word Cam (29 Apr 2025) — vocabulary/phrase generation; **no pronunciation feedback or error correction**; Gemini Live is a general voice assistant, not a tutor | None | No | Free | "complementing… not replacing traditional study" |
| **ChatGPT Voice** | Corrects only if asked; Meng (Mar 2026): prompt-customized voice mode gave "more balanced feedback and emotional support", but the "standard uncustomized model proved adequate". Classroom use (Dettinger, spring 2025): language-detection failures, "responses simply too long", free-tier minutes exhausted, hallucinations, "difficulty understanding students" | None dedicated | No | Free tier; Plus $20/mo | See left; but it is the substitute users defect to from paid apps |
| **Bhashini ecosystem** | Government BHASHINI app = translation. "Bhashini.ai Speak" is a *private* Bengaluru read-aloud/translate app (4.2★, 17 reviews, 1,000+) — not a tutor; a reviewer asks "The app should work offline". **VoicERA** (MeitY + EkStep + IIIT-B + AI4Bharat, 20 Feb 2026): open-source voice-AI stack for citizen services — no English-tutoring product | — | No | Free | — |
| **Indian apps** | TalkDrill (AI; "AI understands Indian English well"; "Requires internet"; $9.99/mo); EngVarta (human phone calls, "real-time corrections during the call, consolidated feedback towards the end", ₹2,700/25 sessions ≈ ₹108/session); Hello English (₹299/mo, "basic speaking features", ads); EnglishBhashi (Play link 404); Speakho (only CB Insights compare pages — *unverified*) | — | None offline | INR-priced | Tier-2/3 learners cite MTI not recognised by generic apps, fear of judgment by native speakers |
| **"Offline English speaking" Play Store apps** | Phrasebooks/grammar quizzes; no speech recognition or correction | None | Yes | Free/ads | Not a real speaking loop |

**The gap.** No product found does (a) the full **speak → hear → name the error → repeat** loop **offline**; (b) grammar **and** pronunciation **and** word-choice correction in one pass with a *forced* retry (Praktika/TalkPal make you tap to discover errors; ELSA/BoldVoice ignore grammar; Loora/Speak under-correct grammar); (c) Indian-L1-aware error targeting with Hindi-language explanations (only Stimuler claims accent-aware acoustics; nobody exposes a Hindi/Bengali/Tamil-specific taxonomy); (d) a beginner UI without typing and without a subscription auto-renew trap — the single most common complaint cluster across ELSA, Stimuler, Praktika, Hallo is **billing**, followed by **misrecognition of accented speech**, **over-forgiving/generic feedback with no summary**, **paywalls**, and **needing internet**.

---

## 2. What the evidence says

### 2.1 Corrective feedback (CF) on speaking — the meta-analyses
- **Li (2010), *Language Learning*, 33 studies**: CF overall **d = 0.61** immediate (random-effects 0.64), **0.57** short-delayed, **0.54** long-delayed — a medium, durable effect. **Explicit > implicit** on immediate (0.693 vs 0.542) and short-delayed (0.608 vs 0.444) posttests; **implicit > explicit** on long-delayed (0.544 vs 0.440). Metalinguistic feedback 0.581 vs recasts 0.506. **Computer-delivered feedback (d = 0.722) and face-to-face (0.675) "did not differ substantially."** Lab 1.091 vs classroom 0.472.
- **Lyster & Saito (2010), SSLA, 15 classroom studies, N = 827**: "CF had significant and durable effects"; "effects were larger for **prompts than recasts** and most apparent in measures that elicit free constructed responses"; younger learners benefited more; setting did not matter. *The exact d values (recollection: overall ≈0.74, prompts ≈0.83, recasts ≈0.53, explicit correction ≈0.65) are behind paywalls and could not be verified — treat as unconfirmed.*
- **Brown (2016), LTR** (observational meta-analysis): teachers default to **recasts (57% of all CF)** vs prompts (30%); **grammar gets 43%** of CF — i.e., the most common teacher move (recast) is the less effective one for uptake.
- **Timing.** Li, Zhu & Ellis (2016; 120 Chinese 8th-graders, English past passive): **immediate** recasts kept their advantage on a 2-week delayed grammaticality-judgement test; delayed CF's effect "diminished"; no group differences on elicited imitation (implicit knowledge). Li, Ou & Lee (2025, *Language Teaching*): during communicative tasks "immediate feedback… is more effective than delayed feedback" though mixed; no difference in drills; working memory predicts benefit from immediate CF; anxiety modulates response to delayed CF. Learners themselves strongly prefer **explicit** correction (M = 5.22) over clarification requests (M = 1.80) and want it **immediately after the error** (ERIC EJ1259669).
- **Theory hook:** Schmidt's noticing hypothesis and Gass's "noticing the gap" — learners must consciously register the mismatch between what they said and the target; showing *your utterance* next to *the corrected one* operationalizes this.

**Design implication:** explicit, metalinguistic, immediate-after-utterance correction **plus** an elicited retry (a "prompt") beats a passive recast, and it works just as well from a machine. Keep it short (1–2 errors per turn) — see anxiety below.

### 2.2 Fluency techniques
- **4/3/2 (Nation 1989).** Boers (2014; 10 adults): fluency improved with and without time pressure, but shrinking time "undermined potential gains in accuracy", with "a strikingly high amount of verbatim duplication". **Tran & Saito (2021; 36 university students)**: 4/3/2 **plus delayed metalinguistic correction between rounds** ("accuracy enhancement") "simultaneously impacted learners' overall fluency and accuracy across different topics" and gains transferred to new topics. Santos & Ramírez-Ávila (2022; n = 24 children, 5 weeks) report d = 2.65 within-group / 2.75 between — small sample, treat cautiously. *Two 2024–25 task-repetition meta-analyses exist (Wang 2024; System 2025) but abstracts were not retrievable.*
- **Shadowing.** Hsu (2025, *J. Computers in Education*; n = 42, 10 weeks shadowing + ASR): pronunciation accuracy and fluency improved significantly (t = 3.46, p = .001), "particularly benefiting lower-performing students". Foote & McDonough (2017) and Mori (2011) report gains in pronunciation accuracy and prosody; Hamada (2016) listening gains with 10–15 min, 3–4×/week for six weeks. Recommended procedure: scripted shadowing → audio-only chunks, 10–15 min sessions, record and compare to model. **Caution:** "Risk fossilising errors without prior phonics instruction; risk cognitive overload for beginners." *A 2025 systematic review on shadowing for pronunciation exists (Taylor & Francis) — 403, not read.*
- **Elicited imitation (listen-and-repeat).** Yan, Maeda, Lv & Ginther (2016; 24 effect sizes, 21 studies, 1,089 participants): EI "has a strong ability to discriminate between speakers across proficiency levels (**Hedges' g = 1.34**)" — a valid, typing-free proficiency probe.

### 2.3 Speaking anxiety / "freezing"
- Speaking is "regularly cited as the most anxiety provoking" skill; symptoms include "mental blocks", "freezing", avoidance and silence (Horwitz et al. 1986 FLCAS; communication apprehension + fear of negative evaluation). Suggested remedies include indirect correction, low-pressure environments and "AI platforms for lower-pressure practice".
- **Susoy (2025, *Frontiers in Psychology*; n = 48, crossover):** anxiety before AI-facilitated speaking exams M = 98.48 vs 102.94 with a human (t(47) = 2.67, p = .01, **d = 0.39**); crucially, anxiety predicted worse performance with humans (**r = −0.50**) but **not** with the AI (r = −0.04) — the AI *decoupled* anxiety from performance. Scores did not differ between conditions.
- **Ding & Yusof (2025, *Humanities & Social Sciences Communications*; n = 60 B1 IELTS learners, 6 weeks with Mondly):** significant speaking gains and reduced L2 speaking anxiety vs control (no effect sizes in abstract); interviewees credited the "non-judgmental, pressure-free environment".
- **EDEN (2024):** a spoken-English chatbot with an error-correction model plus adaptive emotional support "leads to higher perceived affective support", correlated with learner grit. Affective framing matters — but praise must not replace correction (see 2.4).

### 2.4 LLM / voice tutors 2024–2026 — what breaks
- **Over-validation is the failure mode that matters for "correct, don't praise".** Yasir et al. (NC State, May 2026; 7 LLMs incl. GPT-4.1, o3, Gemini-1.5-Pro, DeepSeek-R1, Qwen-3-32B, Llama-3.3-70B, Mistral-Large; 10,836 feedback pairs): near-ceiling on optimal answers (94–99% F1) but **over-validated 6–71% of incorrect solutions** and over-rejected 12–91% of valid-but-suboptimal ones. Kasneci & Kasneci (TUM, May 2026): GPT-5.2 and Claude 4.5 both show **~14% sycophancy** when pressured to validate misconceptions. "Feedback friction" (2025): LLMs also resist incorporating external feedback.
- **Speech LLMs for pronunciation:** zero-shot Qwen2-Audio-7B on speechocean762 agrees with humans within ±2 for good speech but "tends to overpredict low-quality speech scores and lacks precision in error detection" (Parikh et al., Jan 2026). Fine-tuned speech-LLM graders beat cascaded baselines for holistic L2 proficiency (Ma et al., Cambridge ALTA, 2025) — good for *scores*, not for *naming the mispronounced sound*.
- **GEC with open models:** Davis et al. (2024/2025; 7 open + 3 commercial LLMs, 4 benchmarks): "several open-source models outperform commercial ones on minimal-edit benchmarks"; commercial win on fluency rewrites; zero-shot ≈ few-shot. Minimal-edit correction (what a learner needs to repeat) is exactly the regime where a local model is competitive.
- **Product-level confirmation:** reviewers report Praktika "won't reliably catch subtle grammar or word-order mistakes", Loora "occasional feedback misses genuine errors", TalkPal "generic feedback", ChatGPT corrects only on request. Duolingo's Video Call report (Mar 2026) claims gains "on a standardized speaking test" for Japanese English learners practising ≥2×/day for a month — **no effect sizes published**.

### 2.5 Synthesis: best loop for adult beginners who freeze
1. **Lower the production load first**: start turns with elicited imitation / shadowing of a model sentence (EI is valid and typing-free), then open prompts.
2. **Immediately after each utterance**, give **one explicit, named correction** (tense / missing word / one sound) in the learner's language, show the corrected sentence, **play it**, and **require a retry** (a prompt, not a recast) — this is the Li 2010 explicit-immediate regime plus Lyster & Saito's prompt advantage.
3. Keep praise contingent and specific ("'ticket' — correct this time"), never generic; cap at 1–2 corrections per turn to hold anxiety down (Susoy, EDEN).
4. Build fluency with **task repetition under shrinking time only after an accuracy pass** (Tran & Saito 2021 4/3/2 + AE), and make repeated content the learner's own sentences.
5. Never rely on the LLM alone to decide "correct/incorrect" — add deterministic checks (ASR-match of the retry, rule detectors for the top Indian-English patterns, phoneme model for sounds) because LLM over-validation is 6–71%.

---

## 3. Indian-English / Hinglish specifics

### 3.1 Grammar & lexis taxonomy the app should target
Source: eWAVE 3.0 (Kortmann, Lunkenheimer & Ehret 2020; 77 varieties × 235 features), Indian English profile by Devyani Sharma — 61 features rated A (pervasive) or B. Examples are eWAVE's attested utterances; corrections are the report author's.

| # | Pattern (eWAVE feature) | Attested wrong → right |
|---|---|---|
| 1 | Progressive with stative verbs (F88, **A**) | "We are knowing each other." → "We know each other." (also "I am having two brothers" → "I have…") |
| 2 | Progressive for habitual (F89, A) | "Only dry-cleaning clothes are coming." → "…come." |
| 3 | Article omission — zero for *the* (F62, A) | "I'm not working in kitchen." → "…in the kitchen." |
| 4 | Article omission — zero for *a/an* (F63, A) | "We decided to rent apartment." → "…an apartment." |
| 5 | *the* where StE has zero (F64, A) | "sometimes they ask the questions" → "…ask questions" |
| 6 | *the* for *a* (F60, A) | "getting the driving license" → "a driving licence" |
| 7 | Present perfect for simple past (F100, A) | "I have come here about six months back." → "I came here six months ago." |
| 8 | Loose tense sequencing (F113, A) | "second time that such an object had been sighted" → "…has been sighted" |
| 9 | Invariant tag (F165, A) | "You are coming, isn't it?" → "…aren't you?" |
| 10 | Inverted indirect questions (F227, A) | "Do you know what does racial discrimination mean?" → "…what racial discrimination means?" |
| 11 | No inversion / no auxiliary in questions (F228/F229, A) | "Where you will get anything?" → "Where will you get…?"; "I can buy ticket on train itself?" → "Can I buy a ticket on the train?" |
| 12 | Subject/object/dummy pronoun drop (F42–44, A) | "Maybe too much cold over here." → "It's too cold here."; "we have two tailors who can make for us" → "…make them for us" |
| 13 | Resumptive pronoun (F45/F194, A) | "My old life I want to spend it in India." → "I want to spend my old life in India." |
| 14 | Plural regularization / mass nouns (F48/F55, A) | "womans", "childrens", "hardwares", "apparels" → women, children, hardware, clothing |
| 15 | Double determiners (F59, A) | "my this business" → "this business of mine" |
| 16 | *too / too much / very much* = "very" (F222, A) | "not too much common"; "very much difficult" → "not very common"; "very difficult" |
| 17 | *would* for plain future (F119, A); *was* for *were* (F147, A) | "would be building a hospital" → "will build…"; "if I was you" → "if I were you" |
| 18 | *who-all / where-all*, reduplicated *who-who* (F39/F40, A) | "Who-all came?" → "Who came?" |
| 19 | Indefinite *one* (F66, B) | "we arranged one gentleman" → "a gentleman" |
| 20 | Simple present for continuative perfect (F101, B) | "I am here since 2 o'clock." → "I have been here since 2 o'clock." |
| 21 | Politeness modal (F127, B) | "I would be visiting your place tomorrow." → "I'll visit…" |
| 22 | Copula/auxiliary deletion (F174/F46, B) | "Now they wearing…" → "they are wearing"; "Is very hard." → "It is very hard." |
| 23 | Existential possessive (F73, B); *there's* + plural (F172, B) | "Son is there." → "I have a son."; "there's a lot of buildings" → "there are…" |
| 24 | Double comparatives (F78–80, B) | "more easier", "the most big" → easier, the biggest |
| 25 | Quantifier + singular (F56, B) | "one and a half year old" → "…years old" |
| 26 | Lexis (Wikipedia, Indian English vocabulary) | prepone → bring forward; revert → reply; do the needful; out of station → away; pass out → graduate; updation/upgradation; kindly adjust; hotel → restaurant |

Items from the brief that could **not** be anchored in eWAVE/Wikipedia (still standard ELT lore, flag as such): "discuss about", "revert back", "cousin-brother", "timepass", emphatic "only"/"itself" (eWAVE does attest "on train itself", F229 example).

### 3.2 Pronunciation taxonomy by L1
- **Pan-Indian (Wikipedia, Indian English phonology):** /v/–/w/ merge to [ʋ] ("wet and vet are often homophones"); /θ/→[t̪ʰ] (north), /ð/→[d̪]; /t d/ often **retroflex** [ʈ ɖ], "especially in the north"; /p t k/ "always unaspirated" (pin ≈ bin to some listeners); variably rhotic, /r/ as tap [ɾ]; cot–caught merger; **spelling pronunciation** ("salmon" with /l/; "house" [haʊz] as a noun); **epenthesis** in initial clusters ("school" /isˈkuːl/); **syllable-timed rhythm** — "Indian native languages are actually syllable-timed languages, like French"; "stress accents at the wrong syllables". *Specific stress examples like "deVELop", "deTAIL" were not found in a fetched source — flag.*
- **Bengali L1 (Wikipedia, Bangladeshi English, citing Islam 2018):** tense–lax vowel merger (/iː ɪ/→/i/, /uː ʊ/→/u/: sheep = ship); /ɑː ʌ ɜː/→/a/; schwa→/æ/; /eɪ/→/e/, /əʊ/→/o/; **/v/→[b]/[β]** ("very" → "bhery"); **/z/→[dʒ]** ("zoo" as /dʒuː/); /θ ð/→[tʰ dʰ]; final /r/ trilled/flapped; syllable timing.
- **Tamil/Malayalam (Wikipedia, regional dialects):** monophthongal [oː eː] for /oʊ eɪ/; geminated doubles ("happy" [hæːppi], "summer" [sʌmmə]); **intervocalic/post-nasal voicing** ("simply" → [simbɭi]); retroflex [ʈ ɖ] ("water, door"); /θ ð/→[t̪ d̪]; Malayalam initial /t/→[ʈ]. *Telugu-specific features were not separately sourced — assume the Southern set; flag.* Assamese: /tʃ ʃ/→/s/, /dʒ ʒ/→/z/.
- **ASR reality check (Svarah, AI4Bharat, 2023; 9.6 h, 117 speakers, 65 districts):** Whisper-large WER **7.2% on Indian English vs 2.7% on LibriSpeech**; Azure 20.9–21.3%; Google 20.7–30.0%; wav2vec2/HuBERT ~24–25%. By L1: Tamil 5.3%, Maithili 4.5% (easiest); Nepali 9.8%, Assamese 10.1%, Bodo 11.6% (hardest). → **Whisper-large family is the right local STT and beats the cloud APIs most competitors use** — a genuine reason "local" can be *better*, not just offline.

### 3.3 Code-switching ("say it in Hindi if stuck, get the English")
- Scale: ~350M Hinglish speakers (Crystal 2004 estimate); 52% of sampled Indian YouTube comments in romanized Hindi vs 46% English; Hinglish "is now also used in university classrooms" (Wikipedia). India 2011 census: 129M English speakers, only 259,678 L1.
- Evidence base: the anxiety literature recommends indirect/low-pressure correction, Li 2010 shows *explicit metalinguistic* CF works best short-term — delivering that metalinguistic explanation **in Hindi** keeps it explicit *and* short for a beginner. **No RCT specifically on Hinglish-scaffolded English speaking practice** was found — flag as unproven but theoretically coherent (translanguaging).
- Feasible locally: Whisper is multilingual (transcribes Hindi/Hinglish), Gemma covers "over 140 languages", Kokoro-82M ships **2F/2M Hindi voices** (Apache-2.0). Hinglish text resources on HF: `findnitai/english-to-hinglish` (Hinglish-TOP + CMU DoG + HinGE + PHINC), `festvox/cmu_hinglish_dog`, `dianavdavidson/MUCS-Hinglish` (code-switched ASR), `agarwalayushi/hinglish` (Hindi/Hinglish/Indian-English audio from 14 public sets, CC-BY-4.0).

### 3.4 Corpora / datasets for seeding a corrector or building an eval set
- **No error-annotated *Indian-English learner* corpus (spoken or written) was found on Hugging Face** — flag. Best substitutes:
  - **eWAVE Indian English profile** (61 A/B features with attested examples; CLDF CSVs on GitHub) — use as the *specification* for a synthetic wrong→right eval set and rule detectors.
  - **L2-ARCTIC** (`KoelLabs/L2Arctic`, gated, CC-BY-NC-4.0): 24 speakers incl. **4 Hindi-L1**, ~1 h read speech each, ~150 utterances/speaker manually tagged for phone **substitutions/deletions/insertions** — a ready pronunciation-error test set for Hindi L1 (non-commercial licence).
  - **speechocean762** (`mispeech/speechocean762`, Apache-2.0, commercial OK): 5,000 utterances with sentence/word/phone-level accuracy, fluency, prosody, completeness scores and per-phone mispronunciation labels — L1 is Mandarin, so use only to calibrate a GOP scorer, not for Indian patterns.
  - **Svarah** (`ai4bharat/Svarah`, gated): 9.6 h Indian-accented English with L1 metadata — STT robustness eval.
  - **`skbose/indian-english-nptel-v0`** (100K–1M NPTEL lecture segments, Indian-English audio+text) — STT fine-tuning/adaptation data.
  - Text GEC (not Indian-specific): `bea2019st/wi_locness`, `jhu-clsp/jfleg`, `grammarly/coedit` (+ `grammarly/coedit-large`, CC-BY-NC); ErAConD (conversational GEC, 2021).
  - Phoneme recognizers: `mrrubino/wav2vec2-large-xlsr-53-l2-arctic-phoneme` (Apache-2.0, 48K downloads), `facebook/wav2vec2-lv-60-espeak-cv-ft` (Apache-2.0).

---

## 4. Unique, locally-feasible product angles — ranked

Ranking weighs (evidence strength) × (novelty vs. table in §1) × (feasibility on RTX 4090 Laptop 16 GB + FlutterFlow).

| Rank | Angle | Evidence | Novelty | Local feasibility |
|---|---|---|---|---|
| 1 | **Name-one-thing → show → play → must-retry loop** (explicit metalinguistic correction in Hindi + corrected sentence + TTS + retry gate) | Strongest: Li 2010 explicit/immediate; Lyster & Saito prompts > recasts; Li et al. 2016 immediate; learner preference for explicit | High — competitors surface corrections passively (tap buttons, post-session reports) and rarely force a retry | High. STT → LLM with constrained JSON `{error_type, wrong_span, correct_sentence, hindi_explanation}` → Kokoro. **Retry pass/fail by ASR word alignment, not by the LLM** (guards against 6–71% over-validation) |
| 2 | **A/B playback: your clip vs corrected TTS with word/sound highlighted** | Noticing-the-gap (Schmidt/Gass); self-recording in shadowing studies (Foote & McDonough) | High — ELSA has an "audible delta" for pronunciation only; nobody does it for grammar + sound together | High. Store clip; word timestamps from STT; phoneme mismatch from wav2vec2-phoneme vs canonical (espeak/CMUdict) |
| 3 | **L1-aware error targeting** (pick Hindi/Bengali/Tamil/Telugu at onboarding → prioritized checklist of eWAVE features + L1 phoneme pairs: v/w, th, z→j, sheep/ship) | eWAVE feature ratings; Bangladeshi/Southern IE phonology; Svarah shows accent robustness matters | High — Stimuler claims accent-aware acoustics but no product exposes an L1 taxonomy or Hindi explanations | High. Rule detectors + prompt priors for top ~15 patterns; minimal-pair drills; decide target = *intelligibility* (don't "correct" rhoticity or "prepone" unless the scenario is international) |
| 4 | **Freeze detector**: after N s of silence, offer a sentence starter; or accept a Hindi utterance → give the English → repeat it | Anxiety–performance decoupling with AI (Susoy d = 0.39); planning/scaffolding lore; no direct study of this mechanic (flag) | Very high — none of the apps coach the *silence* | High. Silero VAD; Whisper handles Hindi; LLM translates; store the "freeze moments" as data |
| 5 | **4/3/2 with accuracy pass between rounds** on the learner's own self-intro | Tran & Saito 2021 (fluency **and** accuracy, transfer); Boers 2014 caution | High — no app implements 4/3/2 | Very high. Timer + speech-rate (syllables/min) and pause metrics from timestamps |
| 6 | **Spaced repetition of the learner's own mistakes** (personal error bank → next-day listen-and-repeat) | Spacing/retrieval literature (general); Praktika criticized for "no spaced repetition"; Speak sells "Target Your Frequent Mistakes" only in Premium Plus | Medium | High. Local SQLite + FSRS/SM-2; items are EI-style so no typing |
| 7 | **Shadowing mode** (scripted → audio-only, 10–15 min) gated behind a pronunciation check | Hsu 2025; Foote & McDonough 2017; Hamada 2016 | Medium | High (Kokoro + STT). Respect the fossilization caution: only after the sound is drilled |
| 8 | **Indian scenario library** — placement HR round, "tell me about yourself", explaining a gap, first client call, asking a doubt | Task-based practice; competitors have interviews (Stimuler) but generic | Low–medium; differentiate by Indian specificity and Hindi coaching | High (prompted role-play; scripted branches for beginners) |
| 9 | **Hindi UI + Hindi explanations, English-only practice** | FLA: comprehension lowers pressure; Li 2010 metalinguistic | Medium (Hello English/EnglishBhashi are Hindi-medium but not speech-loop) | High (multilingual LLM; Kokoro Hindi voices) |
| 10 | **CEFR-ish placement via elicited imitation** (10 sentences of rising length) | Yan et al. 2016 g = 1.34 | Medium | Medium — needs a calibrated item bank; scoring = ASR match + pause/rate |
| 11 | **Single big mic button, no typing** | Hallo "3 seconds"; Duolingo added push-to-talk | Low–medium | High |
| 12 | **Offline-first as the architecture** (LAN/hotspot server + on-device fallback) | Market: no competitor is offline; Svarah: cloud STT is *worse* on Indian accents | Very high | Medium-high. LM Studio/Ollama expose OpenAI-compatible APIs on the LAN; FlutterFlow custom actions call `http://<laptop-ip>`. **Airplane-mode nuance:** iOS/Android let you re-enable Wi-Fi with airplane mode on (Apple: "you can still use Wi-Fi and Bluetooth in Airplane Mode") — script the demo to do exactly that, or run Windows Mobile Hotspot. For a true no-laptop fallback, `sherpa_onnx` (pub.dev 1.13.7, 1 Sep 2026, Apache-2.0) runs Whisper/Zipformer ASR, Kokoro/Piper TTS and VAD on Android/iOS fully offline; FlutterFlow accepts pub.dev/Git dependencies (test mode needs web support — sherpa-onnx has WASM) |

**Guardrails the evidence demands:** never let the LLM be the sole judge of correctness (rule detectors + ASR-match + phoneme model); cap corrections per turn; log every "praise without correction" for QA; keep responses short (ChatGPT's "too long" problem); avoid American-accent norming — pick an intelligibility target for Indian professional contexts.

---

## 5. Verification flags (could not confirm)
- Lyster & Saito (2010) exact effect sizes (paywalled; recollected values marked as unverified above).
- ELSA India INR pricing (sources conflict: ₹599/mo vs "₹12–17/month"); whether ELSA *scoring* works offline vs only lesson downloads.
- Stimuler INR price; Duolingo Max India price; Speak India price; Speakho existence/details.
- Reddit sentiment (site blocked); Play Store review sampling is what the listing page exposed.
- Word-stress examples ("deVELop", "deTAIL"), "discuss about", "revert back", Telugu-specific phonology — not found in fetched sources.
- Indic Parler-TTS Indian-English accent support (gated model card, not read); ai4bharat/Svarah and KoelLabs/L2Arctic contents (gated).
- Duolingo Video Call whitepaper (403) — no numbers available; task-repetition meta-analyses (2024/2025) and the 2025 shadowing systematic review — abstracts not retrievable.
- No study found that tests a Hinglish "say it in Hindi → get English" scaffold or a silence-coaching mechanic directly.

---

## 6. Sources (all URLs used)

**Competitors**
- https://learn.kotoenglish.com/blog/elsa-speak-review/
- https://play.google.com/store/apps/details?id=us.nobarriers.elsa&hl=en_IN
- https://yourstory.com/2025/07/startup-helping-esl-learners-find-voice-ai-iit-bhu
- https://play.google.com/store/apps/details?id=com.stimuler&hl=en_IN
- https://stimuler.tech/blog/best-english-fluency-app
- https://practiceme.app/vs/boldvoice
- https://oh-yeah-sarah.medium.com/unbiased-praktika-review-by-a-qualified-language-teacher-bf14a26e9813
- https://languatalk.com/blog/praktika-review/
- https://www.trustpilot.com/review/praktika.ai
- https://apps.apple.com/us/app/praktika-ai-language-tutor/id1624701477?see-all=reviews
- https://learn.kotoenglish.com/blog/speak-app-review/
- https://speakshark.com/blog/speak-app-review-2026
- https://blog.duolingo.com/video-call-research-report
- https://blog.duolingo.com/product-highlights/
- https://duolingo-papers.s3.amazonaws.com/reports/Duolingo_whitepaper_language_video_call_improves_speaking_2025.pdf (403)
- https://ilampadmanabhan.medium.com/honest-talkpal-review-is-talkpal-ai-worth-it-when-chatgpt-is-free-sep-2025-b805fabacfb8
- https://languatalk.com/blog/talkpal-review/
- https://oxfordenglishglobal.com/blog/loora-ai-review/
- https://en.ai-pedias.com/blog/ai-english-learning-2026
- https://engvarta.com/best-cambly-alternatives-india-2026/
- https://engvarta.com/top-5-english-speaking-apps-in-india-best-english-speaking-app-2025/
- https://www.talkdrill.com/blog/compare/best-english-speaking-apps/
- https://www.talkdrill.com/blog/compare/talkdrill-vs-cambly/
- https://play.google.com/store/apps/details?id=com.halloglobal.flutterapp.hallo&hl=en_US
- https://blog.google/products-and-platforms/products/education/little-language-lessons/
- https://tech.yahoo.com/ai/articles/google-duolingo-think-ai-change-211228897.html
- https://arxiv.org/abs/2603.14884 (Meng 2026, ChatGPT Voice customization)
- https://fltmag.com/chatgpt-voice/
- https://play.google.com/store/apps/details?id=ai.bhashini.speak
- https://www.dhyeyaias.com/current-affairs/daily-pre-pare/view/voicera-india-open-source-voice-ai-meity
- https://www.fluentu.com/blog/learn/learn-languages-offline/ (search listing only)

**Pedagogy**
- https://eric.ed.gov/?id=EJ883422 and https://www.academia.edu/2911659/Li_S_2010_The_effectiveness_of_corrective_feedback_in_SLA_A_meta_analysis_Language_Learning_60_309_365 (Li 2010)
- https://eric.ed.gov/?id=EJ892626 and https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/abs/oral-feedback-in-classroom-sla/4999EE1C8379B2BF026B148EAF373CA1 (Lyster & Saito 2010)
- https://journals.sagepub.com/doi/10.1177/1362168814563200 (Brown 2016)
- https://www.academia.edu/23677759/Li_S_Zhu_Y_and_Ellis_R_2016_The_effects_of_the_timing_of_corrective_feedback_on_the_acquisition_of_a_new_linguistic_structure_Modern_Language_Journal_100_276_295
- https://www.cambridge.org/core/journals/language-teaching/article/timing-of-corrective-feedback-in-second-language-learning/0E8856852D0183E9DD91EDB4C249E245 (Li, Ou & Lee 2025)
- https://files.eric.ed.gov/fulltext/EJ1259669.pdf (learner CF preferences)
- https://en.wikipedia.org/wiki/Noticing_hypothesis
- https://en.wikipedia.org/wiki/Foreign_language_anxiety
- https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1745942/full (Susoy 2025)
- https://www.nature.com/articles/s41599-025-05550-z (Ding & Yusof 2025)
- https://eric.ed.gov/?id=EJ1047012 (Boers 2014)
- https://discovery-pp.ucl.ac.uk/id/eprint/10128571 (Tran & Saito 2021)
- https://tesl-ej.org/wordpress/issues/volume26/ej102/ej102a1/ (Santos & Ramírez-Ávila 2022)
- https://link.springer.com/article/10.1007/s40692-025-00374-x (Hsu 2025 shadowing + ASR)
- https://gianfrancoconti.com/2025/07/26/shadowing-for-fluency-prosody-and-listening-comprehension-the-what-why-and-how-according-to-sla-research/
- https://eric.ed.gov/?id=EJ1114289 (Yan et al. 2016 elicited imitation)
- https://ouci.dntb.gov.ua/en/works/9j5kwbwl/ (Wang 2024 task-repetition meta-analysis, metadata only)
- https://arxiv.org/html/2605.16207 (Yasir et al. 2026, LLM tutors over-validate)
- https://arxiv.org/html/2605.14604v1 (Kasneci & Kasneci 2026, sycophancy)
- https://arxiv.org/abs/2601.16230 (Parikh et al. 2026, zero-shot speech LLM L2 evaluation)
- https://arxiv.org/abs/2505.21148 and https://arxiv.org/html/2505.21148 (Ma et al. 2025, speech LLM L2 grading)
- https://arxiv.org/abs/2407.09209 (pronunciation assessment with multimodal LLMs)
- https://arxiv.org/abs/2401.07702 (Davis et al., prompting LLMs for GEC)
- https://arxiv.org/abs/2406.17982 (EDEN) ; https://arxiv.org/abs/2406.03486 (BIPED)

**Indian English / data**
- https://ewave-atlas.org/ ; https://ewave-atlas.org/languages/52 ; CLDF data: https://raw.githubusercontent.com/cldf-datasets/ewave/master/cldf/values.csv , parameters.csv, examples.csv, languages.csv
- https://en.wikipedia.org/wiki/Indian_English
- https://en.wikipedia.org/wiki/Regional_differences_and_dialects_in_Indian_English
- https://en.wikipedia.org/wiki/Bangladeshi_English
- https://en.wikipedia.org/wiki/Hinglish
- https://arxiv.org/abs/2305.15760 and https://arxiv.org/pdf/2305.15760 (Svarah)
- https://psi.engr.tamu.edu/l2-arctic-corpus/
- https://hf.co/datasets/ai4bharat/Svarah ; https://hf.co/datasets/KoelLabs/L2Arctic ; https://hf.co/datasets/mispeech/speechocean762 ; https://hf.co/datasets/skbose/indian-english-nptel-v0 ; https://hf.co/datasets/ai4bharat/IndicVoices ; https://hf.co/datasets/findnitai/english-to-hinglish ; https://hf.co/datasets/festvox/cmu_hinglish_dog ; https://hf.co/datasets/dianavdavidson/MUCS-Hinglish ; https://hf.co/datasets/agarwalayushi/hinglish ; https://hf.co/datasets/bea2019st/wi_locness ; https://hf.co/datasets/jhu-clsp/jfleg ; https://hf.co/datasets/grammarly/coedit
- Models: https://hf.co/hexgrad/Kokoro-82M (VOICES.md) ; https://hf.co/ai4bharat/indic-parler-tts ; https://hf.co/Qwen/Qwen2.5-Omni-7B ; https://hf.co/nvidia/parakeet-tdt-0.6b-v2 ; https://hf.co/mrrubino/wav2vec2-large-xlsr-53-l2-arctic-phoneme ; https://hf.co/facebook/wav2vec2-lv-60-espeak-cv-ft ; https://hf.co/grammarly/coedit-large

**Local stack / platform**
- https://github.com/SYSTRAN/faster-whisper
- https://ollama.com/library/qwen2.5 ; https://ollama.com/library/gemma3
- https://pub.dev/packages/sherpa_onnx ; https://github.com/k2-fsa/sherpa-onnx
- https://docs.flutterflow.io/concepts/custom-code/
- https://support.apple.com/en-us/HT204234 ; https://en.wikipedia.org/wiki/Airplane_mode
