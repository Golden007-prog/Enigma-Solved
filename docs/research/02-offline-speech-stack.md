# Fully local speech stack for a 16 GB RTX 4090 Laptop (Windows) — research report

**Date of research:** 5 Sep 2026. All numbers are quoted from the cited sources; anything not verifiable is marked **[unverified]** or **[estimate]**.

## Headline findings

1. **There is now a public Indian-English benchmark inside the Open ASR Leaderboard.** Since 28 Aug 2026 the default English column set includes **"Voice Arena Monsoon en-IN"** — 2,102 conversational phone-recorded clips, 5.62 h, 1,444 speakers from 428 districts — so every model on the board has an Indian-accented-English WER. There is also a Hindi (hi-IN) Monsoon set. This replaces guesswork about accents.
2. On that Indian-English set the best open-weight models are all within ~0.5 WER of each other: ARK-ASR-0.6B 3.43, Cohere Transcribe 3.44, Qwen3-ASR-1.7B 3.50, distil-large-v3.5 3.60, Canary-Qwen-2.5B 3.60, Parakeet-TDT-0.6B-v2 3.89, Whisper large-v3 3.95. The best *streaming* model is nvidia/nemotron-speech-streaming-en-0.6b at 4.45. Whisper large-v3-turbo is 4.79. Voxtral-Mini-4B-Realtime is the worst of the modern models at 8.86.
3. For **Hindi/Hinglish**, AI4Bharat IndicConformer-600M is the best open model on Monsoon hi-IN (8.47 OIWER) but has **no English**; Qwen3-ASR-1.7B is the best single model that does both (en-IN 3.50, hi-IN 12.25), and Nemotron-3.5-ASR-streaming is the only *streaming* model with a Hindi locale (hi-IN 13.85, en-IN 7.31).
4. **Windows-native runtimes matured in 2026:** NVIDIA's own NeMo-Speech.cpp (GGUF, `install.ps1 -Backend cuda`) and LocalAI's parakeet.cpp (Windows CUDA zip, cache-aware streaming, per-word timestamps, MIT) mean Parakeet/Nemotron no longer require NeMo (which still says "Windows: No support yet"). llama.cpp now runs Qwen3-ASR, Voxtral-Mini, Qwen2.5/3-Omni and Gemma 4 with audio input on Windows.
5. **Speech-LLMs cannot yet be trusted to grade pronunciation zero-shot.** Fine-tuning Qwen2-Audio-7B on speechocean762 gives word-level PCC 0.62 (zero-shot: −0.03); phoneme level 0.38. A Jan-2026 zero-shot study found the model "tends to overestimate scores for lower-quality speech" and has "insufficient precision in identifying specific pronunciation errors". Use a phoneme recogniser + forced alignment for "which word was wrong", and the LLM only for feedback wording.
6. **TTS with an Indian-English voice, permissively licensed:** ai4bharat/indic-parler-tts (Apache-2.0, 21 named English speakers, "officially supports Indian English accents"), Chatterbox-Multilingual/Turbo (MIT, zero-shot clone from an Indian-English reference clip), Veena (Apache-2.0, Hindi/English/code-mixed, ~200 ms on RTX 4090 but 3B params). Kokoro-82M (Apache-2.0) is the lowest-latency/lowest-VRAM choice but has only US/UK English voices plus 4 Hindi voices.

---

## 1. Speech-to-text

### 1a. Open ASR Leaderboard snapshot (hf-audio, `english_short_latest.csv`, board updated Aug 2026)

Open-weight models only, sorted by **Indian-English (Voice Arena Monsoon) WER**. "avg" = leaderboard headline average over 8 English sets; RTFx measured on the leaderboard's H200/A100 harness (higher = faster).

| Model | en-IN WER | avg WER | RTFx | LS-clean / other | AMI | Params (B) | Streaming | Word timestamps | License |
|---|---|---|---|---|---|---|---|---|---|
| AutoArk-AI/ARK-ASR-0.6B (May 2026) | **3.43** | 4.56 | 663 | 1.48 / 3.44 | 8.61 | 1.15 | no | not documented | Apache-2.0 |
| CohereLabs/cohere-transcribe-03-2026 | 3.44 | 4.67 | 907 | 0.97 / 2.05 | 7.02 | 2 | no | **no** (no LID/timestamps/diarization) | Apache-2.0 |
| Qwen/Qwen3-ASR-1.7B-hf | 3.50 | **4.31** | 820 | 1.26 / 2.94 | 8.31 | 2.04 | vLLM only | via Qwen3-ForcedAligner (not in streaming) | Apache-2.0 |
| distil-whisper/distil-large-v3.5 | 3.60 | 5.40 | 879 | 1.94 / 4.52 | 12.09 | 0.8 | no | segment-level; word via faster-whisper/WhisperX | MIT |
| nvidia/canary-qwen-2.5b | 3.60 | 4.43 | 867 | 1.23 / 2.63 | 7.91 | 2.5 | no | no (open HF discussion) | CC-BY-4.0 |
| zai-org/GLM-ASR-Nano-2512 | 3.80 | 5.31 | 334 | 1.70 / 3.83 | 13.95 | 2 | no | ? | MIT |
| nvidia/canary-1b-flash | 3.81 | 4.88 | 2129 | 1.20 / 2.52 | 10.58 | 1 | no | yes (NeMo) | CC-BY-4.0 |
| OpenMOSS/MOSS-Transcribe-Diarize | 3.87 | 4.64 | 381 | 1.66 / 4.16 | 8.33 | 0.91 | no | yes + speaker labels | Apache-2.0 |
| **nvidia/parakeet-tdt-0.6b-v2** | 3.89 | 4.70 | **6025** | 1.28 / 2.73 | 9.09 | 0.6 | chunked only | **yes, native** (char/word/segment) | CC-BY-4.0 |
| openai/whisper-large-v3 | 3.95 | 5.78 | 470 | 1.56 / 3.52 | 13.63 | 1.55 | no | DTW/segment; word via WhisperX/faster-whisper | Apache-2.0 / MIT |
| bosonai/higgs-audio-v3-stt | 3.97 | 4.39 | 111 | 1.08 / 2.61 | 7.19 | 2.68 | no | ? | Apache-2.0 |
| nvidia/parakeet-tdt-0.6b-v3 | 4.14 | 4.86 | 6076 | 1.52 / 3.13 | 9.42 | 0.6 | chunked only | yes, native | CC-BY-4.0 |
| Qwen/Qwen3-ASR-0.6B-hf | 4.23 | 5.04 | 744 | 1.70 / 4.01 | 9.33 | 0.78 | vLLM only | via ForcedAligner | Apache-2.0 |
| **nvidia/nemotron-speech-streaming-en-0.6b** | **4.45** | 5.25 | 1060 | 1.89 / 4.35 | 8.84 | 0.62 | **yes, cache-aware 80–1120 ms** | yes (`word_time_offsets`) | NVIDIA Open Model License |
| microsoft/Phi-4-multimodal-instruct | 4.46 | 5.02 | 163 | 1.35 / 3.45 | 9.12 | 5.6 | no | no | MIT |
| nvidia/canary-180m-flash | 4.49 | 5.54 | 2489 | 1.52 / 3.42 | 12.09 | 0.18 | no | yes | CC-BY-4.0 |
| microsoft/VibeVoice-ASR-HF (7B) | 4.74 | 5.58 | 219 | 1.56 / 4.95 | 12.02 | 8 | separate Streaming model | ? | MIT |
| ibm-granite/granite-speech-5.0-470m-turboctc (Aug 25 2026) | 4.76 | 5.04 | **12,946** | 1.48 / 2.73 | 7.72 | 0.47 | "streaming-style" block attention; no API | CTC frames (not documented) | Apache-2.0 |
| openai/whisper-large-v3-turbo | 4.79 | 6.36 | 792 | 2.13 / 3.71 | 13.88 | 0.8 | no | as large-v3 | MIT |
| mistralai/Voxtral-Mini-3B-2507 | 4.90 | 5.54 | 181 | 1.48 / 3.63 | 13.57 | 4.7 | no | no | Apache-2.0 |
| nvidia/canary-1b-v2 | 4.97 | 5.71 | 1825 | 1.76 / 3.07 | 13.03 | 1 | no | yes | CC-BY-4.0 |
| kyutai/stt-2.6b-en | 6.13 | 5.57 | 133 | 1.38 / 3.99 | 10.52 | 2.6 | yes (2.5 s delay) | yes (text-stream offset) | CC-BY-4.0 |
| nvidia/nemotron-3.5-asr-streaming-0.6b | 7.31 | 7.88 | 1472 | 2.83 / 6.79 | 13.43 | 0.64 | yes, cache-aware; 40 locales incl. **hi-IN** | yes | OpenMDW-1.1 |
| mistralai/Voxtral-Mini-4B-Realtime-2602 | 8.86 | 6.46 | 103 | 1.62 / 4.94 | 13.34 | 4.4 | yes (80–2400 ms) | no | Apache-2.0 |
| moonshine-tiny / streaming-tiny | 13.06 / 15.61 | 11.78 / 12.36 | 3840 / 4445 | 4.08 / 11.07 | 18.8 | 0.03 | yes (streaming) | no | MIT |

Proprietary reference points on the same en-IN column (from the same CSV): AssemblyAI universal-3-5-pro 3.49, ElevenLabs scribe_v2 3.32, **Microsoft azure-speech-06-2026 4.40**, Zoom scribe_v2_pro 3.00 — i.e. a 0.6B local Parakeet beats Azure's cloud STT on Indian English.

Regional note from the leaderboard blog (28 Aug 2026): "Eight models clustered between 4.81–4.99 WER on the Indian English public set" but Voxtral-Mini-3B varied "1.68 points (4.38 in Central vs. 6.06 in East)" while whisper-large-v3-turbo varied only 0.46 points across zones — accent robustness differs per model even at equal averages.

### 1b. Hindi (Monsoon hi-IN, lattice-based OIWER; `multilingual_hi.csv`)

| Model | hi-IN WER | RTFx |
|---|---|---|
| **ai4bharat/indic-conformer-600m-multilingual** | **8.47** | 7.7 |
| ARTPARK-IISc/SraVaani-1.0 (0.43B) | 11.21 | 184 |
| Qwen/Qwen3-ASR-1.7B-hf | 12.25 | 79 |
| nvidia/nemotron-3.5-asr-streaming-0.6b | 13.85 | 517 |
| facebook/omniASR-LLM-7B-v2 | 14.53 | 27 |
| Qwen/Qwen3-ASR-0.6B-hf | 18.13 | 79 |
| mistralai/Voxtral-Mini-3B-2507 | 22.90 | 98 |
| Voxtral-Mini-4B-Realtime-2602 | 24.73 | 34 |
| openai/whisper-large-v3 | 28.17 | 90 |
| openai/whisper-large-v3-turbo | 40.79 | 252 |

**Hinglish code-switching:** no public leaderboard column exists. Community fine-tunes: `moorlee/qwen3-asr-0.6b-hinglish` (Apache-2.0; HiACC conversational WER 15.85 %, "−8.88 pp" vs base; outputs mixed Devanagari + Latin) and `shunyalabs/zero-stt-hinglish` (Whisper-medium fine-tune, OpenRAIL, no WER published). Older Indian-English reference (Svarah, 2023, 9.6 h/117 speakers): Whisper-large 7.2, Whisper-medium 8.3, NVIDIA Conformer 14.6, wav2vec2-large 24.9; Google-IN 20.7, Azure-IN 21.3 — i.e. the modern models above are ~2× better than 2023 Whisper on Indian English. AI4Bharat's own ASR models (IndicConformer, IndicWhisper, IndicVoices-trained) cover the 22 scheduled languages and **do not include English**; the Voice of India benchmark (May 2026) likewise covers 15 Indian languages only.

### 1c. Per-model notes (runtime, VRAM, Windows path)

| Model | Real-time | VRAM (as measured/estimated) | Windows install path | Notes |
|---|---|---|---|---|
| **Whisper large-v3 / turbo** | none (30 s windows) | faster-whisper large-v3 on RTX 3070 Ti: FP16 beam 5 = 4,525 MB; INT8 beam 5 = 2,926 MB; turbo ≈ half **[estimate]** | `pip install faster-whisper` (v1.2.1, Oct 31 2025; needs CUDA 12 + cuDNN 9, installable via `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` wheels); whisper.cpp ships Windows CUDA/Vulkan/OpenVINO builds; Purfview Faster-Whisper-XXL standalone exe | word timestamps via `word_timestamps=True` (cross-attention DTW) or WhisperX; Silero VAD built in; turbo is 6.36 avg vs 5.78 for v3 |
| **distil-large-v3.5** | none | ≈ turbo | `distil-whisper/distil-large-v3.5-ct2` in faster-whisper | English-only; short-form 7.10 vs 7.14 for large-v3 per card, but long-form 10.04 vs 8.82; "1.46×" faster |
| **Parakeet-TDT-0.6B v2/v3** | chunked script only (no cache-aware) | q8_0 GGUF 714 MB; NeMo card: "at least 2GB RAM"; ≈1.2–1.5 GB VRAM **[estimate]** | parakeet.cpp `cudart-parakeet-bin-win-cuda-x64.zip` (v0.5.0, 1 Aug 2026), NeMo-Speech.cpp `install.ps1 -Backend cuda`, sherpa-onnx (`sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`, offline only), HF Transformers `AutoModelForTDT`, `onnx-asr` | v3 = 25 European languages, **no Hindi**; native char/word/segment timestamps; RTFx 3,386 on A100 |
| **Nemotron speech streaming en 0.6B** (Mar 13 2026 ckpt) | cache-aware, chunks 80/160/320/560/1120 ms | q8_0 GGUF ≈ 0.74–0.98 GB; bf16 ≈ 1.3 GB weights, ≈1.5–2 GB runtime **[estimate]** | HF `transformers>=5.13` (`AutoModelForRNNT`, native streaming generator) — runs on native Windows PyTorch; parakeet.cpp; NeMo-Speech.cpp | WER vs chunk: 1.12 s → 6.93 avg; 0.56 s → 7.07; 0.16 s → 7.67; 0.08 s → 8.43 (leaderboard-style avg); emits `word_time_offsets` |
| **Nemotron 3.5 ASR streaming 0.6B** (Jun 4 2026) | same, + `target_lang=auto` language tag | as above | same three paths; in parakeet.cpp since v0.2.0 | 40 locales incl. hi-IN; NVIDIA says use the English model for English-only; OpenMDW-1.1 licence |
| **Canary-1B-v2 / Canary-Qwen-2.5B** | no | "Minimum 6GB RAM to load" (1B-v2) | NeMo (Linux/WSL2) | Canary-Qwen has no timestamps; 1B-v2 has word/segment timestamps |
| **Qwen3-ASR 0.6B/1.7B** (Jan 29 2026; native Transformers Jun 26 2026) | "streaming inference is only available with the vLLM backend… does not support batch inference or returning timestamps" | 1.7B bf16 ≈ 4.07 GB weights; Q8_0 GGUF 2.17 GB; third-party estimate "~5 GB" **[unverified]**; 0.6B ≈ 1.6 GB bf16 **[estimate]** | `pip install -U qwen-asr` (Transformers backend works on Windows); llama.cpp `llama-server -hf ggml-org/Qwen3-ASR-1.7B-GGUF:Q8_0`; vLLM = WSL2 | 52 languages/dialects incl. Hindi; Librispeech 1.63/3.38, Fleurs-en 3.35 (1.7B); streaming WER 1.95/4.51 |
| **Qwen3-ForcedAligner-0.6B** | n/a | 0.9B params | `qwen-asr` `model.align(audio, text, language=)` | AAS 42.9 ms vs WhisperX 133.2 ms / NFA 129.8 ms; 11 languages — **no Hindi**; ≤5 min audio; Apache-2.0 |
| **Moonshine v2** (Feb 2026) | yes ("ergodic streaming encoder") | tiny 33.6M / small 123M / medium 245M params | ONNX, HF `moonshine_streaming`, transcribe.cpp | paper avg WER 12.01 / 7.84 / 6.65; latency on M3 50/148/258 ms; English-only; MIT |
| **Kyutai STT** | yes: 1B en/fr 0.5 s delay + semantic VAD; 2.6B en 2.5 s | not published | `pip install moshi` (PyTorch) or `kyutai/stt-2.6b-en-trfs` in Transformers | en-IN 6.13 — weakest of the modern English models on Indian accent |
| **Voxtral Mini 4B Realtime 2602** (Feb 2026) | yes, 80–2400 ms | "a single GPU with >= 16GB memory" (bf16) → **does not fit** | vLLM (WSL2); Transformers ≥5.2 | FLEURS en 4.90 / hi 12.88 at 480 ms per card, but Monsoon en-IN 8.86 |
| **Voxtral Mini 3B 2507** | no | GGUF Q4 ≈ 2.5 GB **[estimate]** | llama.cpp `ggml-org/Voxtral-Mini-3B-2507-GGUF` (audio-in) | doubles as a speech-understanding LLM |
| **IndicConformer-600M** | not documented | 600M; ONNX | `AutoModel.from_pretrained(..., trust_remote_code)`; ONNX Runtime | Hybrid CTC+RNNT; 22 Indic languages, **no English**; MIT |
| **SenseVoice-Small** | pseudo-streaming (3rd-party) | small | sherpa-onnx (10 languages bindings), FunASR-ONNX; llama.cpp GGUF ~254 MB (Jun 2026) | zh/yue/en/ja/ko; emotion + audio-event tags; CTC timestamps; FunASR Model Licence (commercial "permitted when the model license is followed") |
| **VibeVoice-ASR-Streaming 7B/1.5B** (Sep 2 2026) | yes, speaker-attributed | card lists "9B" / "3B" params → too big | Transformers | MIT; 10 languages, no Hindi; WER not on card yet |
| **Granite Speech 5.0 470M TurboCTC** (Aug 25 2026) | block-attention CTC, no streaming API | 470M | `transformers>=5.16` `AutoModelForCTC` | RTFx 12,946 (fastest on the board); Apache-2.0; English only |

Also on the board but not detailed: Cohere Transcribe (2B, 14 languages, no timestamps), ARK-ASR-0.6B (19 languages, **no Hindi**), Higgs-audio-v3-stt, MOSS-Transcribe, omniASR v2 (Meta, 1,676 languages), GLM-ASR-Nano.

---

## 2. Forced alignment & "which word was wrong"

| Tool | Model / method | Accuracy | Windows | License | Verdict |
|---|---|---|---|---|---|
| **WhisperX** | Whisper + wav2vec2 CTC alignment (torchaudio bundles for en/fr/de/es/it, HF models for others) | AAS 133.2 ms (Qwen paper's measurement) | `pip install whisperx`, "install the CUDA toolkit 12.8"; "<8GB gpu memory for large-v2 with beam_size=5" | BSD-2 | Works, but alignment depends on torchaudio pipelines (see below) |
| **torchaudio `forced_align` + `MMS_FA`** | wav2vec2 MMS 300M (1,130 languages) | good; industry standard | torchaudio went into "maintenance phase" (issue #3902): I/O moved to TorchCodec, but `forced_align` "have been preserved" (Jan 2026 update) and `MMS_FA` is still listed in the 2.11 nightly pipelines docs. The 2.10 tutorial page nevertheless carries a removal warning → **pin and test your torchaudio version** | MMS weights are **CC-BY-NC** (see next row) | Fine for prototyping; licence risk for a product |
| **ctc-forced-aligner** (MahmoudAshraf97) | `MahmoudAshraf/mms-300m-1130-forced-aligner` (315M), `--romanize` via uroman for Hindi/Devanagari | ms-level | pip from git; GPU or CPU; needs ffmpeg | code BSD; default model **CC-BY-NC-4.0** ("make sure to use a different model for commercial usage") | Best Hinglish-capable aligner, but NC weights |
| **Montreal Forced Aligner 3.x** | HMM-GMM (Kaldi-style, `english_mfa`) | phone-level, classic | `conda create -n aligner -c conda-forge montreal-forced-aligner`; G2P needs OpenFst ("If you're on Mac or Linux…") | MIT | Accurate offline batch aligner, slow, heavy (conda), no Indian-English dictionary |
| **Qwen3-ForcedAligner-0.6B** | LLM timestamp predictor (needs text + audio) | AAS 42.9 ms (vs WhisperX 133.2, NFA 129.8); 32.4 ms on human-labelled data | `pip install qwen-asr` (PyTorch on Windows) | Apache-2.0 | Best accuracy + licence; **English yes, Hindi no** |
| **Native ASR timestamps** | Parakeet-TDT / Nemotron RNNT word offsets; parakeet.cpp prints "per-word timestamps + confidence: one line per word" byte-identical to NeMo | tens of ms **[estimate]** | parakeet.cpp Windows CUDA | CC-BY-4.0 / NVIDIA OML / MIT (runtime) | Zero extra VRAM — comes free with the STT |

**Pinpointing the wrong word — what actually works (evidence):**
- Word-level detection is a text-alignment problem: align the ASR hypothesis (with word timestamps) against the target sentence (Levenshtein), flag substitutions/deletions, and use the timestamps to play back the exact span.
- For "right word, wrong pronunciation" you need phonemes. `facebook/wav2vec2-lv-60-espeak-cv-ft` (Apache-2.0, IPA output, multilingual) or `wav2vec2-xlsr-53-espeak-cv-ft` (Apache-2.0) + `espeak-ng` G2P of the expected text + Needleman-Wunsch alignment is the standard open recipe (e.g. crazycloud/mispronunciation-detection-diagnosis-wav2vec2-and-llm). ZIPA (ACL 2025) is far more accurate as a phone recogniser (PFER 2.71 vs 11.88 for XLSR-53) but the authors warn it "tend[s] to smooth out phonetic variation" toward dictionary pronunciations — i.e. it may *hide* accent errors.
- Scoring research on speechocean762 (PCC): fine-tuned Qwen2-Audio-7B word-accuracy 0.62 / phoneme 0.38 / sentence 0.77 vs GOPT 0.61 / 0.29 / 0.74 and Azure 0.62 / — / 0.78; zero-shot word PCC −0.03. A Jun-2026 label-free method (HuBERT discrete-token surprisal + transcript-guided DTW) reaches 0.661/0.763/0.753 (accuracy/fluency/prosody) — no code released. Takeaway: **phoneme-level judgement is still ≈0.3–0.4 PCC for every method**; word-level ≈0.6 is achievable. Present word-level flags with confidence, not phoneme-level verdicts.

---

## 3. Text-to-speech

Arena data: the only current human-preference numbers found are third-party compilations (offlinetts.com, updated 1 Aug 2026) of the Artificial Analysis Speech Arena — treat as **[unverified]**: Fish S2 Pro 1128.7 Elo, Step-Audio-EditX 1104.9, Magpie-Multilingual-357M 1064.2, Kokoro v1.0 1056.2, Voxtral TTS 1055.9, Maya1 1050.6, Fish Speech 1.5 1011.9, Chatterbox 1006.4, VibeVoice-7B 959.7, XTTS-v2 885.9. Breeze-TTS-2's card claims "#1 among open-weight models on Artificial Analysis". Resemble's Podonos test: "65.3% of listeners preferred Chatterbox-Turbo… versus 24.5% for ElevenLabs".

| Model | Params | Naturalness | First audio / RTF | Streaming | VRAM | License (commercial?) | Indian-English voice | Windows |
|---|---|---|---|---|---|---|---|---|
| **Kokoro-82M v1.0** (Jan 27 2025) | 82M | Elo ≈1056 [unverified]; A-grade `af_heart` | 36× RT (T4) / 96× (A10G) / 81× (L4) PyTorch; CPU RTF 0.47–0.51; short sentence ≈1.8 s on 4 CPU cores | chunk-by-sentence | ≈0.4–0.6 GB **[estimate]** | Apache-2.0 ✔ | **No** (US 20 + GB 8 voices; 4 Hindi voices hf_alpha/hf_beta/hm_omega/hm_psi, grade C) | `pip install kokoro` + espeak-ng MSI; kokoro-onnx / sherpa-onnx (CUDA) |
| **Piper (piper1-gpl)** | VITS tiny | robotic-ish | real-time on CPU | sentence | <1 GB CPU | **GPL-3.0** (current fork) ✖ for closed-source | en_US / en_GB only; hi_IN voices exist, no en_IN | `pip install piper-tts`; sherpa-onnx |
| **Chatterbox-Turbo** (350M) / **Multilingual v3** (500M) / **Nano** (110M) | 110–500M | 65.3 % preferred vs ElevenLabs (Podonos) | Nano "3x faster than realtime on 8 CPU cores"; community streaming on 4090: "Latency to first chunk: 0.472s", RTF 0.499; Turbo on RTX 3060 "1.8x faster than realtime", "around 5GB" VRAM [third-party] | official: no; `chatterbox-streaming` fork: yes | ≈3–5 GB [unverified] | **MIT** ✔ (PerTh watermark embedded) | 23 languages incl. **Hindi**; zero-shot clone from ~10 s reference → Indian-accented English if you clone an Indian speaker (README: outputs "may inherit the accent of the reference clip") **[expected, untested]** | `pip install chatterbox-tts` (tested on Debian; community Windows installers exist) |
| **Orpheus-3B** | 3B Llama + SNAC | good, emotion tags | "~200ms streaming latency… ~100ms with input streaming" | yes | fp16 ≈8–12 GB; Q4 GGUF ≈2.5 GB **[estimate]** | Apache-2.0 ✔ | English (multilingual research preview) | vLLM (WSL2) or llama.cpp/LM Studio via Orpheus-FastAPI |
| **Dia 1.6B / Dia2** | 1.6B | dialogue-style | RTX 4090: bf16 ×2.1 RT with compile; VRAM ~4.4 GB bf16 / ~7.9 GB fp32 | no | 4.4 GB | Apache-2.0 ✔ | English only | CUDA 12.6 |
| **Kyutai TTS 1.6B** / **Pocket TTS (100M)** | 1.6B / 100M | good / "lightweight" | Pocket: "~200ms to get the first audio chunk", ~6× RT on M4 CPU | yes (text-in streaming) | Pocket = CPU | code MIT; **pocket-tts weights CC-BY-4.0 (gated)** ✔ | en/fr/de/pt/it/es — no Indian English | `pip install pocket-tts`; sherpa-onnx |
| **F5-TTS v1** | 336M | research-grade cloning | RTF 0.0394 (L20, TRT-LLM, 253 ms) / 0.1467 PyTorch | chunked | ≈4–8 GB [third-party] | code MIT, **weights CC-BY-NC** ✖ | no | pip |
| **Fish Audio S2-Pro** (Mar 2026) | 5B (4B+0.4B) | Elo 1128.7 (#1 open) [unverified] | RTF 0.195 (H200), ~100 ms TTFA | yes | too big | **Fish Audio Research License** ✖ commercial | 80+ languages incl. Hindi | — |
| OpenAudio S1-mini | 0.5B | good | — | — | ≈4–6 GB | CC-BY-NC-SA ✖ | 13 languages | — |
| **Fun-CosyVoice3-0.5B** (Dec 2025) | 0.5B | English WER 1.68 % (content) | "approximately 150ms first-packet" | bi-directional streaming | ≈4 GB **[estimate]** | Apache-2.0 ✔ | 9 languages, no Hindi | "Windows users should adapt Linux steps… WSL" |
| XTTS-v2 | ~0.5B | Elo ≈886 | — | chunked | ≈4–6 GB | **CPML non-commercial** ✖ | 17 languages incl. Hindi | pip (old deps) |
| Sesame CSM-1B | 1B + Mimi | context-dependent | not published | no | — | Apache-2.0 ✔ | English | Transformers ≥4.52 |
| VibeVoice-Realtime-0.5B / 1.5B | 0.5B / 1.5B | Elo 959.7 for 7B | "~300 milliseconds first audible latency" | yes | — | MIT, but "We do not recommend using VibeVoice in commercial or real-world applications" | en/zh (+ experimental) | Transformers |
| **Qwen3-TTS 0.6B / 1.7B** (Jan 22 2026) | 0.6B / 1.7B | English content WER 1.24 (1.7B-Base) | 97 ms first packet (A100 + FA2); community CUDA-graph build on RTX 4090: 0.6B TTFA 152 ms, RTF 5.56×; 1.7B TTFA 170 ms | "dual-track" streaming | ≈2–3 GB (0.6B) **[estimate]** | Apache-2.0 ✔ | 10 languages — **no Hindi/Indian English** | `pip install qwen-tts` (PyTorch) |
| **OmniVoice** (k2-fsa, Apr 2026) | 0.6B (Qwen3 diffusion-LM) | — | "RTF as low as 0.025 (40x faster than real-time)" | no | — | code Apache-2.0, **weights CC-BY-NC** ✖ | 600+ languages, accent attribute in voice design | `pip install omnivoice`; GGUF ports |
| **VoxCPM2** (Apr 2026) | 2B | competitive | RTX 4090 RTF ~0.30 (~0.13 Nano-vLLM); VRAM "~8 GB" | yes | 8 GB → too big | Apache-2.0 ✔ | 30 languages incl. **Hindi** | CUDA ≥12 |
| **Supertonic-3** (May 2026) | 99M ONNX | 2-step "robotic"; 5-step "clearly intelligible… slightly flat" | CPU RTF 0.165 (2-step)/0.313 (5-step), 0.73 s for 59 chars on 4 cores | — | CPU | OpenRAIL-M (commercial permitted with use restrictions) | 31 languages incl. **Hindi** and English (fixed preset styles) | `pip install supertonic`; sherpa-onnx |
| **Magpie TTS Multilingual 357M** (v2607, Jul 21 2026) | 364M | Elo 1064 [unverified]; English CER 0.37 %, SSIM 0.822 | not published | batched/long-form | small **[estimate]** | NVIDIA Open Model License ✔ (with terms) | 12 languages incl. **Hindi** + English; 5 voices | NeMo (Linux) or **NeMo-Speech.cpp GGUF** (Windows) |
| **Indic Parler-TTS** (AI4Bharat) | 0.9B | native-speaker score 64–99.8 % | slow (no streaming) | no | ≈2–3 GB fp16 **[estimate]** | Apache-2.0 ✔ | **Yes — "officially supports Indian English accents"; 21 English speakers (Mary, Thoma, Swapna, Dinesh, Meera…)** | `pip install git+…/parler-tts` |
| **Veena** (Maya Research) | 3B Llama + SNAC | MOS 4.2/5 (self-reported) | "~200ms" on RTX 4090, "<80ms" H100 | yes | ≈6–7 GB fp16; ~3.5 GB 4-bit **[estimate]** | Apache-2.0 ✔ | **Hindi, English and code-mixed**; 4 voices (kavya, agastya, maitri, vinaya) | Transformers + bitsandbytes |
| Higgs TTS 3 (4B) / Breeze-TTS-2 (3B) / Voxtral-4B-TTS | 3–4B | top-tier | Breeze "under 40 ms" TTFA on H100; 7.7 GiB VRAM | yes | 7.7–14 GB | all **non-commercial** ✖ | Higgs: Hindi + Indian English tier | — |

---

## 4. Speech-native / omni models (can they *hear* pronunciation?)

| Model | Size / VRAM at usable quant | Windows runtime | Audio-in in Ollama / LM Studio | Audio out | Pronunciation assessment |
|---|---|---|---|---|---|
| **Qwen3-Omni-30B-A3B** (Sep 2025) / **Qwen3.5-Omni** (Mar 30 2026, 30B MoE) | INT4 GGUF ≈15 GB; llama.cpp demo used Q8 across 5 GPUs | llama.cpp `ggml-org/Qwen3-Omni-30B-A3B-Instruct-GGUF` (audio + vision in); vLLM-omni (WSL2) | Ollama: no; LM Studio: not confirmed | talker/code2wav "converted, not yet integrated" in llama.cpp | too big to sit next to a 10 GB LLM — it would have to *be* the LLM |
| **Qwen2.5-Omni-3B / 7B** | 7B Q4 ≈5 GB + audio encoder **[estimate]** | llama.cpp `ggml-org/Qwen2.5-Omni-7B-GGUF` (audio in) | no / not confirmed | not in llama.cpp | zero-shot unreliable (see §2) |
| **Gemma 4 E2B / E4B / 12B** (2026; Apache-2.0) | 12B Q8_0 = 14 GB reported; E4B ≈4–5 GB Q8 **[estimate]** | llama.cpp audio works since PR #24118 (Jun 4 2026): `llama-server --mmproj mmproj-F16.gguf`, OpenAI `input_audio` field; "Up to 30 seconds at 16kHz mono" | **Ollama ≥0.20 has a Gemma 4 audio path** but an Apr 2026 Windows/RTX 3090 report shows "intermittent GGML assertion crash during audio inference" (issue #15333, open) and a tester found looping/hallucinated transcripts; v0.33.3 adds audio "on MLX engine" (Mac only) | no | FLEURS ASR 0.069 (12B) per card; no pronunciation eval |
| **Gemma 3n E2B/E4B** (Jun 2025) | small | Transformers (audio); llama.cpp text/vision only **[verify]** | no | no | — |
| **Phi-4-multimodal-instruct** (5.6B, MIT) | bf16 ≈12 GB; no GGUF audio | Transformers / vLLM (WSL2) | no | no | ASR en-IN 4.46 — good ears, no scoring evidence |
| **Ultravox** | v0.5 1B/8B GGUFs in llama.cpp; v0.7 (Dec 4 2025) = GLM-4.6 355B backbone → not local | llama.cpp | no / no | no | — |
| **Voxtral-Mini-3B-2507** | Q4 ≈2.5 GB **[estimate]** | llama.cpp GGUF (audio in) | Ollama issue #12440 open | no | en-IN 4.90 as ASR |
| **Kyutai Moshi / Unmute** | Moshi 7B ≈8 GB+; Unmute = STT-1B + LLM + TTS-1.6B via Docker | WSL2/Docker | n/a | yes (full duplex) | none |
| **Step-Audio 2 mini** (8B, Jul 2025) / **GLM-4-Voice** (9B) / **LLaMA-Omni2** (0.5–14B, "583ms" latency) | 8–9B bf16 ≈18 GB | Transformers/vLLM (WSL2) | no | yes | none |
| **MiniCPM-o 4.5** (9B, Jul 31 2026) | "BF16 ~19 GB; INT4 ~11 GB"; llama.cpp-omni full-duplex on "≥12 GB NVIDIA GPUs" | llama.cpp-omni (Linux-first) | no | yes (voice clone) | ASR WER 2.38; no pronunciation eval |
| **LFM2.5-Audio-1.5B** (Nov 28 2025) | GGUF, CPU-capable | llama.cpp GGUF, `pip install liquid-audio` | no | yes (interleaved) | English only; ASR avg 7.53 |
| **Nemotron-3-Nano-Omni-30B-A3B** | 24.5 GB in LM Studio | custom llama.cpp fork GGUFs (Aug 24 2026); LM Studio lists "speech transcription capabilities" | LM Studio: yes (per catalog page) | no | — |

**Bottom line for "hearing" accent problems:** every omni model that fits beside your LLM is ≤7B, and the only controlled study on such models (Qwen2-Audio-7B) shows zero-shot word-accuracy PCC of −0.03. They are fine as *conversational* interviewers that can be fed audio directly, but the verdict "you mispronounced *comfortable*" must come from the phoneme/alignment path in §2.

---

## 5. VAD, turn-taking, orchestration

| Component | Latest | Latency / accuracy | Windows offline | License |
|---|---|---|---|---|
| **Silero VAD v6.2** (Dec 10 2025) | ~260K params, ONNX opset 15/16, "6000+" languages | RTF 0.0127 (Xeon 6348, per TEN's comparison) | pip/ONNX Runtime, sherpa-onnx | MIT |
| **TEN VAD** | ONNX; in sherpa-onnx since Jul 2025 | RTF 0.0086; 306 KB lib; "rapid" speech→silence vs Silero "100s ms delay"; better PR curve than Silero/WebRTC (TEN's own eval) | Windows x64/x86 native lib + Python | "Apache 2.0 with additional conditions" |
| WebRTC VAD | legacy GMM | worst PR curve of the three | trivial | BSD |
| **Pipecat Smart Turn v3.1** (Dec 3 2025) | Whisper-tiny encoder + linear head, ~8M params, 8 MB int8 / 32 MB fp | English 94.7 % (8 MB) / 95.6 %; CPU 12–57 ms; 23 languages incl. **Hindi and Marathi** | bundled ONNX in Pipecat (`LocalSmartTurnAnalyzerV3`) | BSD-2 |
| **LiveKit turn detector** | audio `v1-mini` runs locally on CPU; 14 languages incl. Hindi; text detector 396 MB, "~50–160 ms" | full `v1` needs LiveKit Inference (cloud) | local for v1-mini | LiveKit Model License |
| **nvidia/parakeet_realtime_eou_120m-v1** | 120M ASR + `<EOU>` token | p50 160 ms, p90 280 ms; WER 9.30 avg | parakeet.cpp GGUF (129–267 MB) | NVIDIA OML |
| Kyutai semantic VAD | inside stt-1b-en_fr | 0.5 s delay | PyTorch | CC-BY-4.0 |

**Frameworks (100 % offline on Windows):**
- **Pipecat** — pure pip; local services: Whisper (faster-whisper: `LARGE_V3_TURBO`, `DISTIL_*`, int8/fp16), Moonshine, FunASR STT; Kokoro, Piper, Pocket TTS, XTTS-vLLM TTS; Ollama LLM; Silero VAD + `LocalSmartTurnAnalyzerV3`; `SmallWebRTC`/WebSocket transports (no cloud). Custom `STTService`/`TTSService` classes are small, so wrapping parakeet.cpp/Nemotron or Chatterbox is straightforward. **Easiest fully-offline Windows choice.**
- **NVIDIA reference agents** (`NeMo/examples/voice_agent`, `kwindla/nemotron-voice-agent`, `pipecat-ai/nemotron-january-2026`): Nemotron streaming ASR + Nemotron Nano LLM + Kokoro/Magpie/Pocket TTS + Smart Turn v3 — proven local designs, but Linux/Docker, 13–21 GB VRAM (9B/4B LLM) — copy the architecture, not the container.
- **LiveKit Agents** — needs a LiveKit server (self-hostable) and its best turn model is cloud-only; heavier than needed for single-user desktop.
- **RealtimeVoiceChat** (KoljaB) — Windows `install.bat`, faster-whisper + Kokoro/Coqui/Orpheus + Ollama, but "no longer being actively maintained".
- **Unmute** (Kyutai) — Docker/WSL2 only. **Vocode** — cloud-first. **Open WebUI** — voice via OpenAI-compatible local STT/TTS endpoints; fine for demos, not for a custom pronunciation UI.

---

## 6. RECOMMENDED end-to-end pipeline (RTX 4090 Laptop 16 GB, i9-13980HX, 32 GB RAM, airplane mode)

**Design rule:** the LLM (9–10 GB) stays resident; everything speech-related must fit in ≈5 GB, and CPU-capable pieces go to the CPU (24 cores available). Run all GPU speech models in **one** Python process — each extra CUDA process costs ~300–500 MB of context.

| Component | Choice (exact IDs) | Runtime on Windows | VRAM |
|---|---|---|---|
| Mic/VAD | `snakers4/silero-vad` v6.2 ONNX (or TEN VAD) | onnxruntime CPU | 0 |
| End-of-turn | `pipecat-ai/smart-turn` v3.1 (int8 ONNX) | CPU, ~40 ms | 0 |
| **Streaming STT (live captions, barge-in, word timestamps)** | `nvidia/nemotron-speech-streaming-en-0.6b` (en-IN 4.45); swap to `nvidia/nemotron-3.5-asr-streaming-0.6b` with `target_lang=auto` for Hinglish drills (en-IN 7.31 / hi 13.85) | `transformers>=5.13` `AutoModelForRNNT` (PyTorch CUDA, native Windows) **or** parakeet.cpp v0.5.0 `cudart-parakeet-bin-win-cuda-x64.zip` with `nemotron-*-q8_0.gguf` (0.74–0.98 GB) | ≈1.5–2.0 GB (bf16) / ≈1.2 GB (q8 GGUF) **[estimate]** |
| **Accurate re-score after end of turn** (Hinglish + timestamps) | `Qwen/Qwen3-ASR-0.6B-hf` (en-IN 4.23, hi 18.13) — or `Qwen3-ASR-1.7B` Q8_0 via llama.cpp if budget allows (en-IN 3.50, hi 12.25) | `pip install qwen-asr` / llama.cpp `llama-server` | ≈1.6–2.0 GB (0.6B bf16) / ≈2.7 GB (1.7B Q8) **[estimate]** |
| **Word/phoneme error localisation** | `facebook/wav2vec2-lv-60-espeak-cv-ft` (Apache-2.0) + `espeak-ng` G2P + Levenshtein/N-W alignment; timestamps from Nemotron `word_time_offsets`; optional `Qwen/Qwen3-ForcedAligner-0.6B` for 42.9 ms-accurate English alignment | Transformers (fp16) or CPU for ≤10 s clips | ≈0.9 GB fp16 or 0 (CPU) |
| **TTS (interviewer / coach)** | default `hexgrad/Kokoro-82M` (`af_heart`, Apache-2.0); "Indian voice" option: `ResembleAI/chatterbox-turbo` (MIT) cloned from a licensed Indian-English reference clip, or `ai4bharat/indic-parler-tts` (Apache-2.0, non-streaming) | `pip install kokoro` + espeak-ng MSI; `pip install chatterbox-tts` (+ `chatterbox-streaming` fork) | Kokoro ≈0.5 GB; Chatterbox-Turbo ≈3–5 GB **[unverified]** — load one at a time |
| Orchestration | Pipecat (`pipecat-ai[whisper]` skeleton, custom services) with `LocalAudioTransport`/SmallWebRTC, or plain FastAPI | pip | 0 |

**VRAM budget:** LLM 9–10 GB + Nemotron 1.8 + Qwen3-ASR-0.6B 1.8 + phoneme model 0.9 + Kokoro 0.5 ≈ **14.9 GB** (leaves ~1 GB for WDDM/contexts). If you want Chatterbox-Turbo, move the phoneme model to CPU and unload Qwen3-ASR while TTS runs, or drop to Qwen3-ASR Q8 GGUF (≈1 GB). Whisper alternative (faster-whisper `distil-large-v3.5-ct2` int8 ≈1.5 GB, en-IN 3.60) is accurate but not streaming and English-only.

**End-of-speech → first audio [estimate, not measured on this laptop]:**

| Stage | Time |
|---|---|
| VAD silence + Smart Turn decision | 250–350 ms (≈200–300 ms `min_silence` + ~40 ms) |
| Nemotron final flush (160 ms chunk config) | 100–150 ms |
| LLM first sentence (~20 tokens) on a 9–10 GB Q4 model: prefill 1–2k tokens 150–250 ms + 20 tok @ 30–40 tok/s | 650–900 ms |
| Kokoro first sentence (36–96× RT on GPU) | 80–150 ms |
| Output buffer | ~50 ms |
| **Total** | **≈1.1–1.6 s** (≈0.5–0.7 s when the reply is a pre-scripted drill prompt) |

The Qwen3-ASR re-score + phoneme diff (~300–500 ms) runs in parallel with the LLM and only gates the *feedback* overlay, not the spoken reply.

**Why not an omni model instead of STT+LLM:** none that fits beside a 10 GB LLM can be trusted to grade pronunciation (zero-shot PCC ≈0); and the ones that are good listeners (Qwen3-Omni 30B-A3B INT4 ≈15 GB, MiniCPM-o 4.5 INT4 ≈11 GB, Gemma 4 12B Q8 14 GB) would have to replace the LLM entirely. Voxtral-Mini-3B GGUF is the one cheap "hearing" model worth experimenting with for interview *semantics*.

**Things to verify on the target machine before committing:** Nemotron streaming through `transformers>=5.13` on Windows CUDA (documented, not tested here); actual VRAM of Qwen3-ASR-0.6B and Chatterbox-Turbo; whether an Indian-English reference clip really transfers accent in Chatterbox; sherpa-onnx CUDA-12 wheels for Windows (docs list GPU wheels "only Linux x64 and Windows x64" for the CUDA-11.8 variant); torchaudio `MMS_FA` availability in your pinned torchaudio version.

---

## Sources

STT roundups / leaderboard
- https://huggingface.co/spaces/hf-audio/open_asr_leaderboard
- https://huggingface.co/datasets/hf-audio/open-asr-leaderboard-results (english_short_latest.csv)
- https://huggingface.co/datasets/hf-audio/multilingual_evals (multilingual_hi.csv)
- https://huggingface.co/datasets/VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN
- https://huggingface.co/datasets/VoiceArena/MonsoonASR-Open-ASR-leaderboard-hi-IN
- https://huggingface.co/blog/open-asr-leaderboard-global-south
- https://huggingface.co/blog/open-asr-leaderboard
- https://arxiv.org/html/2510.06961v4
- https://www.marktechpost.com/2026/07/23/best-open-speech-recognition-asr-models-in-2026-wer-languages-latency-and-license-compared/
- https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks
- https://presenc.ai/research/best-open-weight-speech-to-text-models-2026
- https://www.speechdata.ai/blog/best-asr-models-2026
- https://snailtext.app/blog/parakeet-vs-whisper-turbo-vs-qwen3-asr/

STT models
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2
- https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b
- https://huggingface.co/nvidia/parakeet_realtime_eou_120m-v1
- https://huggingface.co/nvidia/canary-1b-v2
- https://huggingface.co/nvidia/canary-qwen-2.5b
- https://github.com/QwenLM/Qwen3-ASR
- https://huggingface.co/Qwen/Qwen3-ASR-1.7B
- https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B
- https://huggingface.co/ggml-org/Qwen3-ASR-1.7B-GGUF
- https://huggingface.co/microsoft/VibeVoice-ASR-Streaming-7B
- https://huggingface.co/microsoft/VibeVoice-ASR-Streaming-1.5B
- https://github.com/microsoft/VibeVoice
- https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602
- https://huggingface.co/mistralai/Voxtral-Mini-3B-2507
- https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
- https://github.com/AI4Bharat/IndicConformerASR
- https://ai4bharat.iitm.ac.in/areas/model/ASR/IndicWhisper
- https://huggingface.co/datasets/ai4bharat/Svarah
- https://arxiv.org/html/2305.15760v1
- https://arxiv.org/html/2604.19151v2
- https://huggingface.co/shunyalabs/zero-stt-hinglish
- https://huggingface.co/moorlee/qwen3-asr-0.6b-hinglish
- https://huggingface.co/kyutai/stt-2.6b-en
- https://huggingface.co/kyutai/stt-1b-en_fr
- https://github.com/kyutai-labs/delayed-streams-modeling
- https://arxiv.org/pdf/2602.12241
- https://huggingface.co/moonshine-ai/moonshine-streaming-medium
- https://github.com/FunAudioLLM/SenseVoice
- https://huggingface.co/distil-whisper/distil-large-v3.5
- https://pypi.org/project/faster-whisper/
- https://github.com/m-bain/whisperX
- https://github.com/ggml-org/whisper.cpp
- https://github.com/Purfview/whisper-standalone-win/releases
- https://huggingface.co/AutoArk-AI/ARK-ASR-0.6B
- https://huggingface.co/ibm-granite/granite-speech-5.0-470m-turboctc
- https://huggingface.co/CohereLabs/cohere-transcribe-03-2026

Runtimes
- https://github.com/NVIDIA/NeMo-Speech.cpp
- https://raw.githubusercontent.com/NVIDIA/NeMo-Speech.cpp/main/docs/install.md
- https://github.com/mudler/parakeet.cpp
- https://github.com/mudler/parakeet.cpp/releases
- https://huggingface.co/mudler/parakeet-cpp-gguf
- https://github.com/k2-fsa/sherpa-onnx
- https://k2-fsa.github.io/sherpa/onnx/index.html
- https://k2-fsa.github.io/sherpa/onnx/python/install.html
- https://github.com/k2-fsa/sherpa-onnx/issues/2918
- https://github.com/NVIDIA-NeMo/NeMo
- https://pypi.org/project/nemo-toolkit-asr/
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/multimodal.md

Alignment / pronunciation assessment
- https://github.com/MahmoudAshraf97/ctc-forced-aligner
- https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner
- https://github.com/pytorch/audio/issues/3902
- https://docs.pytorch.org/audio/stable/tutorials/ctc_forced_alignment_api_tutorial.html
- https://docs.pytorch.org/audio/stable/pipelines.html
- https://docs.pytorch.org/audio/stable/generated/torchaudio.functional.forced_align.html
- https://montreal-forced-aligner.readthedocs.io/en/latest/installation.html
- https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft
- https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft
- https://aclanthology.org/2025.acl-long.961.pdf
- https://github.com/crazycloud/mispronunciation-detection-diagnosis-wav2vec2-and-llm
- https://arxiv.org/abs/2601.16230
- https://arxiv.org/html/2509.15701
- https://arxiv.org/abs/2503.11229
- https://arxiv.org/html/2606.19910v1
- https://arxiv.org/html/2603.29087v1
- https://github.com/jimbozhang/speechocean762

TTS
- https://offlinetts.com/blog/tts-arena-leaderboard-2026/
- https://findskill.ai/blog/best-open-source-tts-2026/
- https://localaimaster.com/blog/best-local-tts-models
- https://github.com/resemble-ai/chatterbox
- https://huggingface.co/ResembleAI/chatterbox-turbo
- https://huggingface.co/ResembleAI/chatterbox-nano
- https://github.com/davidbrowne17/chatterbox-streaming
- https://growwstacks.com/blog/local-ai-voice-model-beats-paid-tts-chatterbox-turbo
- https://github.com/QwenLM/Qwen3-TTS
- https://qwenlm-qwen3-tts.mintlify.app/guides/streaming
- https://github.com/andimarafioti/faster-qwen3-tts/blob/main/BLOG.md
- https://huggingface.co/hexgrad/Kokoro-82M
- https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- https://gist.github.com/efemaer/23d9a3b949b751dde315192b4dcf0653
- https://heyneo.com/blog/kokoro-tts-vs-supertonic-3-tts
- https://github.com/OHF-Voice/piper1-gpl
- https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md
- https://huggingface.co/k2-fsa/OmniVoice
- https://huggingface.co/openbmb/VoxCPM2
- https://huggingface.co/BreezeBlue/Breeze-TTS-2
- https://huggingface.co/Supertone/supertonic-3
- https://huggingface.co/nvidia/magpie_tts_multilingual_357m
- https://huggingface.co/bosonai/higgs-tts-3-4b
- https://huggingface.co/ai4bharat/indic-parler-tts
- https://huggingface.co/maya-research/Veena
- https://huggingface.co/fishaudio/s2-pro
- https://github.com/nari-labs/dia
- https://github.com/canopyai/Orpheus-TTS
- https://github.com/SWivid/F5-TTS
- https://github.com/FunAudioLLM/CosyVoice
- https://huggingface.co/sesame/csm-1b
- https://github.com/kyutai-labs/pocket-tts
- https://huggingface.co/kyutai/pocket-tts
- https://huggingface.co/coqui/XTTS-v2
- https://huggingface.co/mistralai/Voxtral-4B-TTS-2603

Omni / speech-LLM
- https://www.spheron.network/blog/deploy-qwen3-5-omni-gpu-cloud/
- https://github.com/ggml-org/llama.cpp/discussions/18273
- https://discuss.huggingface.co/t/nemotron-3-omni-ggufs-with-working-audio-video-in-llama-cpp-9-tested-quants-one-pass-a-v/179220
- https://learnopencv.com/minicpm-o-4-5-a-9b-model-that-can-see-hear-and-speak-at-the-same-time/
- https://arxiv.org/html/2604.27393v1
- https://ai.google.dev/gemma/docs/core/model_card_4
- https://note.com/bhrtaym/n/n13e7d880d7c6?hl=en
- https://note.com/unco3/n/n871e994d27b2?hl=en
- https://github.com/ollama/ollama/issues/11798
- https://github.com/ollama/ollama/issues/12440
- https://github.com/ollama/ollama/issues/15333
- https://github.com/ollama/ollama/releases/tag/v0.20.0-rc1
- https://github.com/ollama/ollama/releases/tag/v0.33.3
- https://lmstudio.ai/models/nemotron-3-omni
- https://www.ultravox.ai/blog/introducing-ultravox-v0-7-the-world-s-smartest-speech-understanding-model
- https://huggingface.co/LiquidAI/LFM2.5-Audio-1.5B
- https://github.com/kyutai-labs/unmute
- https://arxiv.org/html/2507.16632v3
- https://arxiv.org/pdf/2505.02625

VAD / turn-taking / orchestration
- https://github.com/snakers4/silero-vad/wiki/Version-history-and-Available-Models
- https://huggingface.co/TEN-framework/ten-vad/blob/main/README.md
- https://www.daily.co/blog/improved-accuracy-in-smart-turn-v3-1/
- https://github.com/pipecat-ai/smart-turn
- https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview
- https://docs.pipecat.ai/server/services/stt/whisper
- https://docs.pipecat.ai/server/services/supported-services
- https://docs.livekit.io/agents/build/turns/turn-detector/
- https://github.com/NVIDIA-NeMo/NeMo/blob/main/examples/voice_agent/README.md
- https://github.com/kwindla/nemotron-voice-agent
- https://github.com/pipecat-ai/nemotron-january-2026/
- https://github.com/KoljaB/RealtimeVoiceChat
