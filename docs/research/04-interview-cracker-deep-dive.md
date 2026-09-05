# Interview Cracker — Research Report (as of 5 Sep 2026)

Scope: competitor scan, on-screen interviewer options for a FlutterFlow phone + RTX 4090 Laptop (16 GB) local server, the all-local "interview brain", and how to prove JD-grounding and evidence-based feedback to judges. Figures are quoted from the sources listed at the end; anything not confirmable is marked **(unverified)**. Note: the research agent's web-search budget ran out mid-task, so a few items (Unstop details, Interviewer.AI, Rive community lip-sync files, some Indian tools) are flagged rather than confirmed.

---

## 1. Competitor scan (2025–2026)

| Product | Visible interviewer? | Adaptive follow-ups? | JD-grounded? | Feedback format | Offline? | Pricing (India pricing: none found for any) | Common complaints |
|---|---|---|---|---|---|---|---|
| **Final Round AI** | Not documented anywhere found (voice "back-and-forth" with "CoPilot") | Yes, "realistic back-and-forth" (own page) | Yes: "uses your Goal, including the target role, company, job description, resume" | "tracks your structure and clarity", "automatic debrief"; STAR suggested answers "calibrated to the job description" | No | Own blog (26 Aug 2026): $148/mo monthly, $300/yr ($25/mo). LoopCV (10 Jul 2026): "$149/month", ~$96/mo quarterly, ~$81/mo semi-annual, "~$500/year" — **conflicting, verify** | Billing: "rebilling after cancellation", refunds denied for "substantial usage" despite 3-day guarantee; Trustpilot 3.9 with "~17% one-star", ~18% of reviews use "scam"/"fraud"; live copilot "lagging, failing mid-interview, or producing... hallucinated answers" |
| **Yoodli** | No avatar documented (voice/text roleplay; "customize your conversation partner") | Yes: "Yoodli will ask you AI-powered follow-up questions" | Yes: "paste a job description, and the platform generates targeted interview questions" | Filler words, pacing (WPM), eye contact (webcam), vocabulary diversity, talk-to-listen ratio, conciseness, sentence starters | No | Free: 5 lifetime sessions; Pro $8/mo (annual, 10 sessions/week); Advanced $20/mo (annual, unlimited) | "doesn't write your answers or coach you on content", "doesn't know anything about the specific company"; eye-contact scoring "requires optimal conditions"; free tier "too limited" |
| **Google Interview Warmup** | No | No ("five independent prompts with no connection") | No (6 fixed tracks) | Word-frequency insights: "job-related terms, most-used words, and talking points"; "no scoring", "no STAR evaluation" | No | Free | **Reported retired April 2026** by two competitor blogs (AceRound, Final Round AI); the grow.google archive page did not confirm this when fetched — **treat as likely but unverified** |
| **Huru** | Not documented | Not documented | Yes: paste JD or Chrome-extension import from LinkedIn/Indeed; "Our AI reads the required skills and responsibilities to generate highly relevant, tailored questions" | Body language, filler words, grammar, "vocal tone, pitch, and energy", answer accuracy/relevance, confidence; model answers | No | Starter $24.99/mo; Growth $99/yr ($8.25/mo). Web + iOS + Chrome ext (a review lists Android; homepage doesn't — **unverified**) | "failing to ask any questions at all", extension bugs; Trustpilot 3.4/5 (6 reviews), Chrome store 3.7/5 (15 ratings) |
| **LockedIn AI** | Not documented (primarily a *live-interview stealth copilot*) | n/a | n/a | Mock mode: "post-interview feedback and habit highlights" | No | Third-party estimates $30–60/mo; "Unlimited"/"Credits" tiers, pricing not transparent | "4-5 second response lag", outputs that "sound like a LinkedIn post", refund friction, extension "visible to interviewers"; Trustpilot 3.7/5 (76 reviews, Mar 2026) |
| **Big Interview** | Yes, but **pre-recorded human video** asking canned questions | Not documented | No evidence | AI feedback on "word choice, filler words, eye contact from the camera, and pacing"; STAR "Answer Builder" | No | $39/mo BootCamp; $99/3 months; $299 lifetime | UI "feeling dated"; no live assistance |
| **Aced (ex-Exponent) Practice / Pramp** | Not documented ("Introducing our AI Interviewer") | Not documented | Role-filtered question banks, not JD | "realistic rubrics"; peer notes + AI | No | Free to start; paid tiers not shown | Peer no-shows (general Pramp complaint, not re-verified) |
| **micro1 (Zara)** | **Yes**: "Zara's avatar on the left, your coding environment on the right" | **Yes**: "Adaptive Branching... If you say you used Kafka, she will immediately ask how you handled partition rebalancing" | Role-specific (it is a hiring screen, not practice) | Pass/fail-style; "Integrity Score" ≥70% anti-cheat | No | n/a (vendor pays) | "Hard. Proctored. One Shot" |
| **HireVue-style async video** | No (text/video prompts) | No | Employer-set questions | Employer-side AI scoring | No | n/a | "3–8 pre-recorded questions", ~30 s prep, 1–3 min fixed response, limited retakes; candidates ask "does a person actually watch my interview"; abandonment over lack of human contact |
| **Interviewer.AI** | Employer async-video tool | No | Employer-set | Employer-side | No | Not fetched (pricing page exists) | **(unverified — not fetched)** |
| **Unstop AI Mock Interview (India)** | Product page exists (unstop.com/practice/ai-mock-interview) but blocked by cookie wall; promoted on LinkedIn/Instagram | **unverified** | **unverified** | **unverified** | No | **unverified** | — |
| **Scaler AI Mock Interview (India)** | **Yes: persona avatars**, e.g. "Ayesha Khan, System Design Expert in a company like Google" | Not documented | No JD upload; fixed tracks (DSA, System Design, EDA, NLP, MERN, Java, React) | "Instant scores & feedback", "Personalised improvement plans" | No | "Free 25-min interviews" (lead-gen for courses) | — |
| **PrepInsta (India)** | Placement-prep content; no AI-interviewer product details found | — | — | — | No | not found | **(unverified)** |
| **Interview Kickstart** | Human mentors only ("10-21 human mentor sessions"), no AI mock tool | n/a | n/a | Human feedback | No | "$5,000–$12,000 USD"; prices not listed publicly | Pricing opacity, "persistent emails, calls, and even text messages", inconsistent coaching |
| **Masai** | No AI mock-interview tool found | — | — | — | — | — | **(unverified)** |
| **Skillora.ai** | AI-driven; no visible avatar mentioned | "real-time guidance" | Resume/role-based | Instant feedback + example answers | No | free trial; pricing not disclosed | — |

**The gap.** Across the whole set, nobody combines all four judging criteria: (1) Yoodli, Huru and Final Round AI are JD-aware but faceless; (2) Big Interview and Scaler put a face on screen but with canned video or fixed tracks; (3) only micro1's Zara does avatar + adaptive branching, and it is a proctored hiring gate, not a practice tool; (4) feedback everywhere is scores/metrics or word clouds rather than "here is what you said, here is the rubric line it failed". And **none run offline** — every one is a cloud subscription with recurring billing complaints (Final Round AI, LockedIn) and Indian users pay USD prices. A fully-local, avatar-based, JD-grounded, pressure-mode interviewer with quote-level feedback is an empty square.

---

## 2. The on-screen interviewer — ranked

### VRAM reality check first (why this ranking looks the way it does)
- LLM: ~7–9 GB for a 9–14B model at Q4–Q6 (see research report 01) + KV cache.
- STT: faster-whisper large-v2 uses 4,525 MB (fp16) or 2,926 MB (int8) on GPU; `word_timestamps=True` and Silero `vad_filter` built in. NVIDIA `parakeet-tdt-0.6b-v2` (CC-BY-4.0, English, "Accurate word-level timestamp predictions", "RTFx of 3380... batch size of 128") is a lighter alternative (~1.2–2 GB **unverified**).
- TTS: Kokoro-82M (Apache-2.0) is tiny.
- That leaves roughly 2–4 GB for a face. Anything Wan/DiT-based (SoulX-FlashHead, LiveTalk, EchoMimic v3, OmniAvatar) does not fit beside a 9 GB LLM on 16 GB.

### Rank 1 — 2D animated interviewer rendered on the phone, driven by viseme timings from the laptop (RECOMMENDED)
**Feasibility: high. VRAM: ~0. Wow: high if the character has reactions, not just a mouth.**

- **FlutterFlow Rive support — confirmed, with a catch.** FlutterFlow has a native RiveAnimation widget (docs updated 25 Jul 2024): asset/URL `.riv`, artboard + animation selection, "Once"/"Continuous", "Auto Animate", and a "Rive Animation Action" on tap/double-tap/long-press. **It does not expose state-machine inputs** (community, Sep 2023: "the Rive widget only supports Rive animation and not Rive State Machines"). The workaround is a FlutterFlow **Custom Widget** using the `rive` pub package — v0.14.11 (published ~3 Aug 2026; 0.14 moved to the C++ `rive_native` runtime, Rive Renderer, Data Binding, and `getNumberInput()/getBoolInput()/getTriggerInput()`), MIT-licensed, Android/iOS/Web/Windows/macOS/Linux. Custom dependencies are added under Settings → Project Dependencies → "Add Pub Dependency"; FlutterFlow warns a package "must support Web to run your app in our Run/Test Mode" (rive 0.14 does). Rive editor: Free tier $0 (3 files, 1 project), Cadet $9/seat/mo — runtime use is free.
- **Viseme source #1 (best): Kokoro token timestamps.** Confirmed in `kokoro/pipeline.py`: `Result.tokens` is a `List[en.MToken]` with `start_ts`/`end_ts`, filled by `join_timestamps()` using `MAGIC_DIVISOR = 80` (pred_dur frames → seconds at 24 kHz), **only when `lang_code` is 'a' or 'b' (English via misaki G2P) and the model returns `pred_dur`**. These are token/word-level, not phoneme-level; phoneme timing needs summing per-phoneme durations (HF discussion, Feb 2025). Kokoro also has Hindi ('h') but without timestamps.
- **Viseme source #2 (ready-made): HeadTTS** (met4citizen, MIT, "doesn't use eSpeak or any other GPL-licensed module"). Wraps Kokoro and returns `words, wtimes, wdurations, visemes, vtimes, vdurations, phonemes` using the **Oculus 15-viseme set** (`aa E I O U PP SS TH CH FF kk nn RR DD sil`). Runs in-browser (WebGPU/WASM) or as a **Node.js WebSocket/REST server** (WebGPU or CPU) — run it as a sidecar on the laptop. RTF: 0.27 (Chrome WebGPU fp32), 1.45 (WASM q4), 0.12 (WebSocket WebGPU 2-thread). English only.
- **Viseme source #3 (offline, from any audio): Rhubarb Lip Sync** 1.14.0 (3 Apr 2024), MIT, Windows/macOS/Linux CLI. Mouth shapes A–F + optional G, H, X; TSV/XML/JSON output; PocketSphinx recognizer (English) or language-independent "phonetic" recognizer; `-d dialog.txt` improves accuracy. Use it as the fallback for non-English TTS audio (Hindi) — batch, not streaming.
- **Viseme source #4: espeak-ng phoneme events** — Kokoro uses espeak-ng as fallback G2P; using its phoneme timing directly was **not verified**.
- **Viseme sets to map to:** Oculus 15 (sil/PP/FF/TH/DD/kk/CH/SS/nn/RR/aa/E/I/O/U with phonemes p,b,m / f,v / th / t,d / k,g / tS,dZ,S / s,z / n,l / r / A: / e / ih / oh / ou); Azure's 22 IDs (0 Silence … 21 p,b,m; also "55 facial positions" at 60 FPS blend shapes, cloud-only so not usable here). The Rive lip-sync guide (Feb 2025) recommends **one Number input**, "8–10 grouped visemes instead of full phoneme mapping", instant transitions, and syncing to the audio playback position rather than timers.
- **Assets:** GraphicMama free Character Animator mouth sets — 14 standard + 12 expressive shapes in frontal and 3/4 view, AI/PNG (license terms not stated on the page — **check before shipping**). Adobe Character Animator's 14-viseme scheme (Neutral, Ah, D, Ee, F, L, M, Oh, R, S, Uh, W-Oo, Smile, Surprised) is the de-facto 2D standard — **(scheme cited from general knowledge; page not fetched)**. Rive Marketplace lip-sync files: **could not search (budget)**; report 05 found "Custom Talking Avatar: Real-Time Lip Sync for Your App" (stvfunm, Jun 2025, CC BY, free). Live2D route (as used by Open-LLM-VTuber, MIT, local LLM+ASR+TTS, "Voice interruption without headphones") has no Flutter runtime — WebView only, and Cubism SDK has its own license.
- **Lottie:** FlutterFlow supports Lottie natively, but Lottie has no state machine/inputs; you would scrub segments — workable for idle loops, poor for visemes. Prefer Rive.

**Effort: ~1–2 weeks** for a rigged character (idle/listen/nod/think/unimpressed + 10 mouth shapes), a Flutter custom widget, and a WebSocket that streams `{t, viseme}` + `{reaction}` events alongside the audio.

### Rank 2 — Pre-generated interviewer video clips + on-device stitching (good for a photoreal "wow", brittle for follow-ups)
This is how the cloud players do it. HeyGen's custom LiveAvatar training footage is literally "15 seconds listening, 90 seconds talking, 15 seconds listening"; D-ID describes "viseme-to-frame transformers", CTC alignment "within 30 milliseconds", "sub-200 millisecond latency" generating at "100 frames per second" over WebRTC — on Azure GPU clusters. HeyGen bills "1 credit = 30 seconds" (Full) / "1 minute" (Lite), overage "$0.10–$0.09/credit", enterprise "$40,000+ USD annually".
Local analog: record/generate idle, listening, nodding, thinking loops once; while the user reads the intro (~20–40 s), generate the opener + first 2–3 planned questions with **SadTalker** (Apache 2.0, "removed the non-commercial restriction", Windows `start.bat`, single image + audio) or **Ditto**; play with `video_player` + crossfades. **Problem:** follow-ups are generated live, so you still need a live path (Rank 1 or Rank 3) — which is why this is a layer, not a strategy.

### Rank 3 — Real-time neural talking head on the laptop, streamed to the phone (only if you free VRAM)
| Model | Real-time claim | VRAM | License | Windows | Notes |
|---|---|---|---|---|---|
| **Ditto** (Ant, ACM MM 2025) | RTF 0.635 offline / 0.895 online on **1× A100**; first-frame delay 385 ms; audio 23 ms + motion DiT 62 ms + render 15 ms | not stated | Apache-2.0 | tested CentOS; TensorRT 8.6.1 "Ampere_Plus" engines; PyTorch model (11 Jul 2025) — Windows **unverified** | Single image + audio; `stream_pipeline_online.py`. Best photoreal option for a 4090 if VRAM is freed |
| **MuseTalk 1.5** (28 Mar 2025) | "30fps+ on an NVIDIA Tesla V100" (own claim); Ditto's table measured RTF 2.248 | not stated; LiveTalking says "RTX 3080Ti 及以上" for real time | MIT (code); weights license not stated | `.bat` scripts present | 256×256 face region; needs a driving video; "center point of the face region... SIGNIFICANTLY affects generation results" |
| **LivePortrait** | 12.8 ms/frame on RTX 4090 (~78 FPS) | small | — | yes (community) | **Video-driven**, not audio-driven; audio via forks (JoyVASA etc.) |
| **LiteAvatar** (HumanAIGC) | "30fps on only CPU devices" | 0 GPU | MIT | `download_model.bat` | Needs their preprocessed avatar data (sample + ModelScope gallery); custom-avatar tooling not released; ASR front-end is `zh-cn` — English lip-sync quality **unverified** |
| **Ultralight-Digital-Human** | mobile real-time, 20 fps (WeNet) / 25 fps (HuBERT) | tiny; needs per-person training from 3–5 min video | Apache 2.0 | — | "combined audio + UNet model size under ~1M"; audio-quality sensitive |
| **Duix-Mobile** | "response latency under 120ms on Snapdragon 8 Gen 2" — **renders on the phone** | 0 laptop VRAM | **DUIX Community License**: "Powered by Duix.com" attribution; license required above "1 thousand" MAU | Android/iOS SDKs; Flutter **not documented** | 4 public avatars (Leo, Oliver, Sofia, Lily); custom avatar via support@duix.com from "15-second to 2-minute video" |
| **SoulX-FlashHead 1.3B** (12 Feb 2026) | Lite: "96 FPS... on single RTX4090"; Pro: 10.8 FPS on single 4090, real time on "two RTX5090" | not stated (Wan-based DiT; likely >8 GB **unverified**) | Apache-2.0 | needs flash_attn 2.8 — Windows **unverified** | Best quality-per-FPS in 2026, but not beside a 9 GB LLM |
| **GAIR LiveTalk 1.3B** (Dec 2025) | 24.82 FPS, 0.33 s first frame | "~20GB", needs ≥24 GB GPU | Apache 2.0 | — | too big |
| **Alibaba LiveAvatar 14B** (ECCV 2026) | 45 FPS on 5 GPUs; single ≥80 GB or 48 GB FP8 | — | Apache 2.0 | — | no |
| **EchoMimic v3 1.3B** (AAAI 2026) | not real-time (no FPS given) | "24G (RTX4090D)", "12G" quantized, 16G ComfyUI | Apache 2.0 | one-click package | up to 768×768; Flash-Pro 8-step (22 Jan 2026) |
| **Hallo / Hallo2** | RTF 53–57 (Ditto's table) | — | — | — | Hallo-Live (26 Apr 2026): 20.38 FPS, 0.94 s latency on **two H200** |
| **LatentSync 1.5 / 1.6** | not real-time | 8 GB (1.5) / 18 GB (1.6, 512×512) | Apache-2.0 | — | needs video input |
| **OmniAvatar** (Jun/Jul 2025) | 16.0 s/it single GPU — not real-time | 14B: 36G / 21G / 8G configs | Apache-2.0 | — | 480p only |
| **Wav2Lip** | fast, low-res | small | **"research/academic/personal purposes only... any form of commercial use is strictly prohibited"** | — | avoid for a product |
| **Sonic** | not real-time; "want at least an A10 / RTX 4090" (Pixazo) | — | — | — | offline only |

Ready-made streaming frameworks: **lipku/LiveTalking** v2.0.4 (20 Jun 2026, Apache-2.0) — ernerf/musetalk/wav2lip/Ultralight renderers, "WebRTC、RTMP、虚拟摄像头输出", pluggable LLM/TTS, Windows badge; **Linly-Talker-Stream** (Feb 2026, Apache-2.0) — Wav2Lip/MuseTalk/ER-NeRF/TalkingGaussian over WebRTC. Phone side: `flutter_webrtc` against an `aiortc` (Python) peer on the laptop; **MJPEG over HTTP** is the zero-dependency fallback on a hotspot; HLS adds seconds of latency — don't.

**CPU / <2 GB options that exist:** LiteAvatar (CPU), Ultralight-Digital-Human (mobile, per-person training), Duix-Mobile (on-phone, restrictive license), and of course Rank 1.

### Rank 4 — 3D avatar in Flutter
- `flutter_3d_controller` 2.3.0 (MIT) wraps Google's `<model-viewer>` web component: named animation playback and camera only — **no morph-target/blendshape weight API**, Windows "coming soon". Not usable for visemes without a JS bridge.
- `thermion_flutter` 0.5.0 (~Aug 2026, Apache-2.0, Filament 1.69.1, Android arm64/iOS/macOS/Windows/Web) lists "skinning + morph animations" — blendshape lip-sync is feasible but you own the whole pipeline.
- **Ready Player Me is gone**: Netflix acquisition announced 19 Dec 2025; "January 31, 2026... the avatar creator, PlayerZero and the developer APIs stopped being available". Exported GLBs still load. Alternatives: MetaPerson/Avatar SDK, Avaturn ("free for non-commercial use"), VRoid Studio, Blender MPFB.
- Fast path if you want 3D anyway: **met4citizen TalkingHead** (MIT, three.js) in a Flutter WebView — Oculus viseme blendshapes (`viseme_sil, viseme_PP, ...`), `speakAudio(audio, {words, wtimes, wdurations})` accepts exactly HeadTTS's output, idle `avatarIdleEyeContact` / head-move parameters. WebView-on-phone performance **unverified**.
- Verdict: more effort than Rank 1, higher uncanny-valley risk, no VRAM benefit.

### Recommendation and concrete pipeline
**Ship Rank 1 as the core; add Rank 2 clips for the intro/outro if time allows; keep Rank 3 (Ditto) as a demo-day toggle only if you drop to an 8B LLM.**

Pipeline (all on the laptop unless noted):
1. `interview_server` (FastAPI, Python): WebSocket to the phone; orchestrates LLM (LM Studio/Ollama, OpenAI-compatible), STT (faster-whisper int8 or Parakeet), TTS (Kokoro via HeadTTS sidecar or `KPipeline` directly).
2. For each interviewer utterance: LLM → `{text, reaction_tag}` → Kokoro → `audio.wav` + tokens `start_ts/end_ts` → phoneme→viseme map (Oculus 15 → your 10 Rive mouths) → send `{audio_url, visemes:[{t,v}], reaction}`.
3. Phone (FlutterFlow custom widget): `rive` 0.14 state machine with Number input `mouth` (0–9), Number `mood` (neutral/interested/unimpressed/thinking), Trigger `nod`, Bool `listening`; a `Ticker` reads `audioPlayer.position` and sets `mouth` from the viseme track; between questions `listening=true` + occasional `nod` triggered by VAD events from the server (user speaking energy).
4. Assets: one stylized interviewer (front-facing, shoulders-up) with 10 mouth shapes (map: sil→X, PP→A, FF/TH→G-ish, DD/kk/SS/nn/RR/CH→B/C variants, aa→D, E/I→C, O/U→E/F), eye blink, brow raise, head tilt, "note-taking" hand loop. Build in Rive (free tier) or import GraphicMama/Character-Animator style PNG mouths.
5. Fallback for Hindi/Hinglish TTS: Rhubarb phonetic recognizer on the WAV → A–H shapes.

---

## 3. The "interview brain" (all local)

### 3.1 Stack
- LLM via **LM Studio** (`/v1/chat/completions` with `response_format` JSON schema — grammar-based sampling for GGUF via llama.cpp; "Not all models are capable of structured output, particularly LLMs below 7B") or **Ollama** (`format` = JSON schema, 6 Dec 2024; advises temperature 0 and "return as JSON" in the prompt).
- STT with word timestamps: faster-whisper (`word_timestamps=True`, `vad_filter=True`) or Parakeet-TDT-0.6B-v2 (CC-BY-4.0). For *verbatim* fillers ("um/uh") and disfluency timing, **CrisperWhisper** (INTERSPEECH 2024) is the state of the art but the HF weights are **cc-by-nc-4.0** — fine for a hackathon demo, not for a paid product.
- Design precedent worth citing: **SparkMe** (SALT-NLP, 24 Feb 2026) — four agents: Interviewer, **Agenda Manager** ("subtopic coverage evaluation, emergent insight detection"), **Exploration Planner** ("question prioritization, rollout strategies, utility function weights"), optional User Agent; topic guide as JSON `{topic, subtopics[]}`; +4.7% guide coverage over baselines with fewer turns; interviewer prompt already includes "STAR framework usage". Also **LLM-as-an-Interviewer** (Dec 2024: problem modification → feedback → follow-ups → "interview report" of strengths/weaknesses), **MockLLM** (KDD 2025: interviewer/candidate agents with "reflection memory generation and dynamic strategy modification"), **EZInterviewer** (WSDM 2023: mock interviews from resume + JD).

### 3.2 Stage A — JD → competency rubric (with provenance)
Prompt pattern: *"You are a hiring-panel lead. Read the JD. Extract competencies. For every competency, copy the exact JD sentence(s) that justify it (verbatim, no paraphrase) and their character offsets. Do not invent competencies not in the text. Return JSON only."* Then **verify programmatically** that every `jd_quote` is a substring of the JD (reject/redo otherwise) — this is your anti-hallucination gate and your judge-facing trace.

```json
{
  "role_title": "string",
  "seniority": "fresher|junior|mid|senior",
  "domain": "string",
  "behavioral_technical_mix": {"behavioral": 0.4, "technical": 0.6},
  "competencies": [
    {
      "id": "C1",
      "name": "REST API design in Node.js",
      "type": "technical|behavioral|domain",
      "priority": "must_have|nice_to_have",
      "jd_quotes": [{"text": "Build and maintain RESTful services in Node.js", "start": 412, "end": 458}],
      "evidence_expected": ["designed endpoints", "handled auth/versioning", "measured latency"],
      "difficulty_ladder": ["recall", "applied example", "trade-off/failure", "design under constraint"]
    }
  ]
}
```

### 3.3 Stage B — Question planning ("Agenda Manager")
- Maintain a **coverage matrix**: competency × evidence_expected × {none, weak, strong}.
- Next-question policy: pick the must-have with the least evidence; alternate behavioral/technical per the mix; escalate one rung on the ladder after a strong answer; never repeat a competency more than 2 probes unless contradiction.
- Each question carries a **why-trace**: `{competency_id, jd_quote, ladder_rung, strategy}` where `strategy ∈ {open_probe, evidence_probe, dig_deeper_vague, dig_deeper_generic, quantify_result, ownership_probe, contradiction_probe, escalate}`.
- Follow-up triggers (from the answer analyzer, below): vague (no concrete noun/number/name) → "Give me one specific instance"; generic/"we" language → "What was *your* part?"; missing Result → "What changed because of it — any number?"; JD keyword claimed without detail → "Walk me through how you did X".
- Optional SparkMe-style rollout: sample 3 candidate follow-ups, have the LLM simulate a 1-sentence likely answer for each, pick the one that most increases expected coverage. Cheap on a 9–14B if you cap tokens.

```json
{
  "question_id": "Q4",
  "text": "You mentioned caching. What did you cache, and how did you decide the TTL?",
  "why": {"competency_id": "C3", "jd_quote": "optimise API latency", "ladder_rung": "trade-off/failure",
          "strategy": "dig_deeper_vague", "triggered_by": {"answer_id": "A3", "span": [8.2, 11.9], "quote": "we used caching and stuff"}},
  "time_limit_s": 90,
  "reaction_before": "interested"
}
```

### 3.4 Stage C — Answer analysis (transcript + timestamps in, JSON out)
Feed the LLM the verbatim transcript **with word timestamps** and the target competency. Require every judgment to cite `quote` + `[t_start, t_end]`; post-validate quotes against the transcript (fuzzy match ≥0.9 on normalized text; drop anything that doesn't match).

```json
{
  "answer_id": "A3",
  "star": {
    "situation": {"present": true, "quote": "in my final-year project", "t": [0.4, 1.9]},
    "task": {"present": false},
    "action": {"present": true, "quote": "we used caching and stuff", "t": [8.2, 11.9], "ownership": "we"},
    "result": {"present": false}
  },
  "specificity": {"score": 1, "scale": "0-3", "missing": ["named technology", "number", "time frame"]},
  "jd_keyword_coverage": {"hit": ["caching"], "missed": ["latency", "TTL", "Redis"]},
  "hedges": [{"quote": "I think maybe", "t": [5.1, 5.8]}],
  "contradictions": [],
  "verdict": "vague",
  "next_strategy": "dig_deeper_vague"
}
```

STAR/CAR detection tips: classify at the clause level (LLM), then apply cheap rules — a "Result" needs a past-tense outcome verb or a number; "Action" needs first-person singular for ownership; flag `we`-ratio > 0.7 as a team-hiding signal (a heuristic — not from literature).

### 3.5 Delivery analytics (Yoodli-class metrics, computed locally)
From STT word timestamps + audio:
- **WPM** = words / (speaking time excluding pauses > 0.5 s); report vs. a 130–170 conversational band **(band is common guidance, not verified)**.
- **Fillers** per minute and % of words (list: um, uh, like, you know, so, basically, actually, right) — use CrisperWhisper or a verbatim prompt; plain Whisper often drops fillers.
- **Pauses**: count and longest gap > 1.0 s; **latency to first word** after the question ends.
- **Hedging** phrases (I think, maybe, kind of, sort of, probably) with timestamps.
- **Answer length** (s and words) vs. question's `time_limit_s`; **talk ratio**.
- **JD keyword coverage** (from Stage A vocabulary).
- **Prosody**: pitch (F0) standard deviation and range via `librosa.pyin`/Parselmouth; RMS energy variance → "monotone" flag when F0 SD is low relative to the user's own baseline **(thresholds must be calibrated on your test users; not from literature)**.
- Yoodli's public dimension list for parity: filler words, pacing (WPM), eye contact, vocabulary diversity, talk-to-listen ratio, conciseness, sentence starters. Skip eye contact on v1 (Yoodli's own complaint: "requires optimal conditions").

### 3.6 Hallucination-safe feedback
- Feedback generator only sees the **validated** Stage C JSON, never free-form; each bullet must reference an `answer_id` + quote + `t` that passed validation. Unreferenced claims are dropped by code, not by prompt.
- Give the judge a reference: "No Free Labels" (Mar 2025) finds LLM judges improve with reference answers — supply the rubric's `evidence_expected` and a one-line ideal-answer sketch per question.
- Keep turns short and re-summarize state each turn: "LLMs Get Lost in Multi-Turn Conversation" (May 2025) reports "significantly poorer" multi-turn performance from "premature assumptions" — so pass the coverage matrix + last 2 turns, not the full chat.
- Context-grounded hallucination detection is itself hard for LLMs ("Fine-Grained Detection of Context-Grounded Hallucinations", Sep 2025) — which is why string-matching quotes against the transcript is the safer gate than asking the model to self-check.

### 3.7 Pressure features and the ethics of not humiliating beginners
- Pressure mechanics: one question on screen; no back/skip/preview; visible countdown (e.g., 90 s behavioral, 60 s technical recall); server-side VAD end-pointing; **interviewer barge-in** ("Let me stop you there —") when time expires or the answer loops (repeated n-grams); reaction states driven by Stage C verdict (`interested` on specific answers, `neutral_waiting` on vague, `unimpressed` only after a second vague answer to the same probe).
- Evidence that this kind of practice works and that anxiety matters: meta-analysis (Powell, Stanley & Brown, 2018, *Canadian J. Behavioural Science*) — interview anxiety vs. performance **r = −.19**, moderated by mock vs. actual interview; MACH (MIT, UbiComp 2013): "a weeklong trial with 90 MIT undergraduates... Students who interacted with MACH were rated by human experts to have improved in overall interview performance, while the ratings of students in control groups did not improve" — MACH nodded, mirrored and gave post-hoc visual feedback; VR-JIT RCT (n=26): VR-trained group showed "greater improvement during live standardized job interview role-play performances... (p = 0.046)", self-confidence "p = 0.060".
- Design rules that follow: (1) a **pressure dial** set by the user (Warm-up / Realistic / Tough) — the "unimpressed" state only exists in Tough; (2) reactions target the *answer*, never the person ("That didn't tell me what you did" not "You're not prepared"); (3) the report leads with 1–3 fixable behaviors and a "what a strong answer would have included" for the weakest question; (4) allow a retry of the single weakest question after the report (learning) but not during (pressure); (5) show the user their own quote so the critique is falsifiable.

---

## 4. Evaluation — proving it to judges

1. **"Why I asked this" trace, live.** A tap on any question flips the card to show: competency name, the verbatim JD sentence highlighted in the pasted JD, ladder rung, strategy, and (for follow-ups) the candidate quote + timestamp that triggered it. Because Stage A's quotes are substring-validated, this never shows a paraphrase.
2. **Swap-the-JD demo.** Paste two JDs with the same title (e.g., "Software Engineer" at a fintech vs. an ed-tech), run 3 questions each, show a side-by-side diff of questions and their JD anchors. This directly refutes "fixed list with the title swapped."
3. **Coverage matrix** on the results screen: competencies (rows) × evidence found (cells with quotes). Empty must-have rows explain why certain questions were asked and why the score is what it is.
4. **Evidence-based report**: every weakness = `quote` + `[mm:ss–mm:ss]` (tap to replay the user's own audio) + rubric line (`competency`, `evidence_expected` item) + "stronger version" sketch. Include a per-answer STAR presence strip.
5. **Determinism check for skeptics**: re-run Stage C on the same transcript twice at temperature 0 and show identical verdicts; log the JSON so a judge can inspect it.
6. **Offline proof**: toggle the laptop's Wi-Fi to hotspot-only and run the whole interview.

---

## 5. Risks

- **VRAM contention**: 9 GB LLM + 3–4.5 GB STT + KV cache leaves no room for any DiT-based head; Ditto/MuseTalk only if you drop to an 8B LLM or int8 STT. Rank 1 avoids this entirely.
- **Timestamps English-only**: Kokoro `start_ts/end_ts` exist only for lang_code 'a'/'b'; Hindi/Hinglish needs Rhubarb (batch) or amplitude-based mouth fallback.
- **Indian-English STT accuracy**: documented WER disparities on Indian English lectures (NPTEL study, 2023) — test faster-whisper vs. Parakeet on your own users; fillers are often dropped by Whisper.
- **FlutterFlow + Rive 0.14**: state-machine control requires a Custom Widget and the `rive_native` C++ runtime; Test Mode is web-only; expect debugging time.
- **Licenses**: Wav2Lip non-commercial; CrisperWhisper weights cc-by-nc-4.0; Duix "Community License" (attribution + license above 1,000 MAU); GraphicMama asset terms unstated.
- **Neural-head Windows support**: Ditto (TensorRT, CentOS-tested), SoulX-FlashHead (flash_attn) are Linux-first.
- **Hallucinated critique** if you skip quote validation; **over-pressure** harming anxious freshers (r = −.19) if the dial is not user-controlled.
- **Hotspot reliability**: audio upload + event streams on a phone hotspot — keep payloads small (opus/16 kHz), reconnect logic, and pre-buffer the next question's audio.
- **Unverified items**: Interview Warmup shutdown date, Unstop/PrepInsta/Masai tooling, Huru Android, Final Round AI avatar and exact pricing, SoulX-FlashHead VRAM, Parakeet VRAM, espeak-ng timing route, Rive community lip-sync assets.

---

## Sources

Competitors
- https://blog.loopcv.pro/final-round-ai-review/
- https://www.finalroundai.com/blog/is-final-round-ai-worth-it
- https://www.finalroundai.com/ai-mock-interview
- https://www.articuler.ai/resources/compare/yoodli-ai-interview-coach/
- https://www.finalroundai.com/blog/yoodli-review-pros-cons
- https://yoodli.ai/
- https://grow.google/interview-warmup-archived
- https://www.aceround.app/blog/google-interview-warmup-review/
- https://www.finalroundai.com/blog/google-interview-warmup-discontinued-alternatives
- https://interviewsidekick.com/blog/huru-review
- https://huru.ai/
- https://interviewsidekick.com/blog/lockedin-ai-review
- https://lastroundai.com/compare/big-interview
- https://www.tryexponent.com/practice
- https://aitrainer.work/guides/micro1-review/
- https://www.willo.video/blog/hirevue-candidate-experience-review
- https://interviewer.ai/pricing/ (not fetched)
- https://unstop.com/practice/ai-mock-interview (cookie-walled)
- https://www.scaler.com/ai-mock-interview
- https://skillora.ai/blog/prepinsta-alternatives
- https://igotanoffer.com/en/advice/interview-kickstart-alternatives
- https://tech.yahoo.com/apps/articles/10-ai-tools-interview-prep-193536699.html

Phone-side avatar (Rive / FlutterFlow / visemes / assets)
- https://docs.flutterflow.io/concepts/animations/rive-animation/
- https://docs.flutterflow.io/widgets-and-components/widgets/base-elements/riveanimation
- https://community.flutterflow.io/discussions/post/rive-limitations-or-out-of-date-nnHrKJIw0UbrAmK
- https://community.flutterflow.io/ask-the-community/post/rive-animations-with-state-machine-lZy3FPG2mnyusKI
- https://docs.flutterflow.io/concepts/custom-code/
- https://docs.flutterflow.io/customizing-your-app/custom-functions/custom-widgets
- https://pub.dev/packages/rive/changelog
- https://github.com/rive-app/rive-flutter/blob/master/LICENSE
- https://rive.app/pricing
- https://dev.to/uianimation/how-to-build-real-time-ai-lip-sync-using-rive-state-machine-viseme-data-26o7
- https://github.com/hexgrad/kokoro
- https://raw.githubusercontent.com/hexgrad/kokoro/main/kokoro/pipeline.py
- https://huggingface.co/hexgrad/Kokoro-82M
- https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX-timestamped/discussions/2
- https://github.com/met4citizen/HeadTTS
- https://github.com/met4citizen/TalkingHead/blob/main/README.md
- https://github.com/DanielSWolf/rhubarb-lip-sync/blob/master/README.adoc
- https://github.com/DanielSWolf/rhubarb-lip-sync/releases
- https://developers.meta.com/horizon/documentation/unity/audio-ovrlipsync-viseme-reference/
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-speech-synthesis-viseme
- https://graphicmama.com/blog/free-mouth-shapes-character-animator-puppet/
- https://github.com/Open-LLM-VTuber/Open-LLM-VTuber

3D in Flutter
- https://github.com/m-r-davari/flutter_3d_controller
- https://pub.dev/packages/thermion_flutter
- https://docs.readyplayer.me/ready-player-me/api-reference/avatars/morph-targets
- https://avatarsdk.com/blog/2026/01/15/switch-from-ready-player-me-to-avatar-sdk-fast-familiar-production-ready/

Neural talking heads and streaming
- https://github.com/TMElyralab/MuseTalk
- https://github.com/TMElyralab/MuseTalk/blob/main/LICENSE
- https://github.com/antgroup/ditto-talkinghead
- https://arxiv.org/pdf/2411.19509v3
- https://arxiv.org/html/2407.03168v1
- https://github.com/antgroup/echomimic_v3
- https://github.com/bytedance/LatentSync
- https://github.com/OpenTalker/SadTalker
- https://github.com/Rudrabha/Wav2Lip
- https://github.com/Omni-Avatar/OmniAvatar
- https://github.com/duixcom/Duix-Mobile
- https://github.com/duixcom/Duix-Mobile/blob/main/LICENSE
- https://github.com/duixcom/Duix-Avatar
- https://github.com/HumanAIGC/lite-avatar
- https://github.com/anliyuan/Ultralight-Digital-Human
- https://github.com/Soul-AILab/SoulX-FlashHead
- https://huggingface.co/Soul-AILab/SoulX-FlashHead-1_3B
- https://github.com/Soul-AILab/SoulX-FlashTalk
- https://github.com/GAIR-NLP/LiveTalk
- https://huggingface.co/GAIR/LiveTalk-1.3B-V0.1
- https://github.com/Alibaba-Quark/LiveAvatar
- https://arxiv.org/html/2604.23632
- https://github.com/lipku/livetalking
- https://github.com/Kedreamix/Linly-Talker-Stream
- https://github.com/yepicaiaaron/awesome-realtime-video-generation
- https://www.pixazo.ai/blog/best-open-source-ai-lip-sync-models
- https://lipsync.com/blog/open-source-lip-sync
- https://help.heygen.com/en/articles/12758866-liveavatar-faq
- https://www.computerweekly.com/blog/CW-Developer-Network/Inside-D-IDs-real-time-AI-avatar-technology
- https://docs.d-id.com/docs/realtime-overview
- https://docs.d-id.com/reference/talks-streams-overview
- https://www.videosdk.live/blog/flutter-webrtc
- https://dev.to/whitphx/python-webrtc-basics-with-aiortc-48id

Interview brain / local stack / research
- https://ollama.com/blog/structured-outputs
- https://lmstudio.ai/docs/app/api/structured-output
- https://huggingface.co/Qwen/Qwen3-14B-GGUF
- https://huggingface.co/unsloth/gemma-3-12b-it-GGUF
- https://github.com/SYSTRAN/faster-whisper
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- https://arxiv.org/abs/2408.16589
- https://huggingface.co/nyralabs/CrisperWhisper
- https://arxiv.org/abs/2602.21136
- https://github.com/SALT-NLP/SparkMe
- https://arxiv.org/abs/2412.10424
- https://arxiv.org/abs/2405.18113
- https://arxiv.org/abs/2301.00972
- https://arxiv.org/abs/2205.10977
- https://arxiv.org/abs/2505.06120
- https://arxiv.org/abs/2503.05061
- https://arxiv.org/abs/2509.22582
- https://arxiv.org/abs/2307.10587
- https://api.semanticscholar.org/graph/v1/paper/DOI:10.1037/cbs0000108 (Powell, Stanley & Brown 2018)
- https://link.springer.com/article/10.1007/s10803-014-2113-y
- https://www.media.mit.edu/publications/mach-my-automated-conversation-coach/
- https://www.media.mit.edu/projects/mach-my-automated-conversation-coach/overview/
