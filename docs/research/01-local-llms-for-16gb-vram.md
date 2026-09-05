# Local LLM selection for a real-time voice tutor / mock-interviewer on an RTX 4090 Laptop (16 GB) — as of 5 Sept 2026

> Research report produced with Hugging Face MCP (model cards, file listings, trending) + web sources. Numbers are quoted from the cited sources; anything marked *(est.)* or "unverified" was not measured on the target laptop.

## TL;DR

| | Pick | Quant / on-disk | Why |
|---|---|---|---|
| **#1** | **Qwen3.5-9B** (Alibaba, Mar 2 2026, Apache-2.0) | **Q6_K = 7.46 GB** (`unsloth/Qwen3.5-9B-GGUF`) or UD-Q4_K_XL = 5.97 GB | Best instruction-following/tool-calling in class (IFEval 91.5, TAU2 79.1, BFCL-V4 66.1), 201 languages incl. Hindi, hybrid Gated-DeltaNet arch → KV cache is only ~0.32 GB at 8K, native MTP head for speculative decoding, 262K context. Leaves ~4–5 GB free for STT+TTS. |
| **#2** | **Gemma 4 12B "Unified"** (Google, Jul 2026, Apache-2.0) | **QAT Q4_0 = 6.98 GB** (`google/gemma-4-12B-it-qat-q4_0-gguf`) or Q5_K_M = 8.41 GB | Humans prefer Gemma 4's conversational style in blind Arena tests; MMMLU 83.4 (multilingual); the only model here with native audio input (llama.cpp only). Slightly weaker tool-calling (Tau2 69.0). |
| Runtime | **LM Studio 0.4.23** (Aug 28 2026) | — | Stable MTP speculative decoding on CUDA (0.4.14+), per-model KV-quant/context/parallel control, grammar-constrained JSON schema, native tool-use templates, headless `llmster` daemon, text-only loading (saves ~0.9 GB vs Ollama's bundled vision projector). Ollama v0.33.3 is a fine fallback. |

Models newer than these exist on the HF trending list (Qwen3.8-27B, Qwen3.8-Flash-Next 180B, GLM-5.3-Flash 321B, DeepSeek-V4-Flash), but none fits 16 GB with 5 GB headroom; Qwen 3.6/3.7/3.8 have **no** sub-27B releases, so Qwen3.5-9B remains the newest small dense Qwen.

---

## 1. Hardware reality check

- RTX 4090 Laptop GPU: 16 GB GDDR6, 256-bit, **576 GB/s** ([everylocalai](https://everylocalai.com/hardware/nvidia-rtx-4090-laptop), updated 5 Sep 2026) vs. 1,008 GB/s on a desktop 4090. Single-stream decode is bandwidth-bound, so expect **~0.55–0.6× of desktop-4090 tok/s** for VRAM-resident models. Figures below marked *(est.)* are desktop measurements scaled by this ratio and were **not measured on your exact GPU**.
- Budget: 16 GB − ~0.5–1 GB Windows/driver reserve − 4–6 GB for STT+TTS ⇒ **LLM (weights + KV + CUDA buffers) must stay ≤ ~9.5–10.5 GB**. That excludes every ≥20B model at Q4 (details in §3).

---

## 2. Shortlist (8 candidates)

Sizes are exact file sizes from the HF repo listings (decimal GB, bytes/10⁹). "Ollama size" is what the Ollama library reports (includes the vision projector for VL models).

| # | Model (date, license) | Params (total / active) | Best quant for 16 GB w/ ~5 GB headroom | Exact on-disk | Ctx | Ollama tag | LM Studio ID | tok/s (source) | Tools / JSON | Hindi / Hinglish |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Qwen3.5-9B** (2 Mar 2026, Apache-2.0) | 9.65B dense (hybrid DeltaNet+attn, VL) | Q6_K (or UD-Q4_K_XL / Q8_0) | Q6_K **7.46 GB**; UD-Q4_K_XL 5.97; Q5_K_M 6.58; Q8_0 9.53; mmproj-F16 0.92 (optional) | 262,144 | `qwen3.5:9b` (6.6 GB, Q4_K_M + projector); `qwen3.5:9b-q8_0` (11 GB) | `qwen/qwen3.5-9b` (min 7 GB) | Desktop 4090: Q4_K_M ~92, Q6_K ~72, Q8_0 ~60 ([willitrunai](https://willitrunai.com/blog/qwen-3-5-quantization-speed-comparison), Jul 2026) → **~40–55 tok/s laptop (est.)** | Ollama badges: vision/tools/thinking; BFCL-V4 66.1, TAU2 79.1; IFEval 91.5 | 201 languages; MMMLU 81.2, INCLUDE 75.6, WMT24++ 72.6. Hinglish unmeasured |
| 2 | **Gemma 4 12B Unified** (Jul 2026, Apache-2.0) | 11.96B dense, encoder-free text+image+**audio** | QAT Q4_0 (Google-official) or Q5_K_M | QAT Q4_0 **6.98 GB** (+0.18 mmproj); Q4_K_M 7.12; UD-Q4_K_XL 7.37; Q5_K_M 8.41; Q6_K 9.79; Q8_0 12.67 | 256K | `gemma4:12b-it-qat` (7.2 GB); `gemma4:12b` (7.6 GB) | `google/gemma-4-12b` (min 7 GB) | "~21 tok/s on a mid-range GPU" ([orcarouter](https://www.orcarouter.ai/blog/qwen-3-8-27b-vs-gemma-4-12b), Aug 2026); MTP gives "1.5×–2.2×" ([Unsloth](https://unsloth.ai/docs/models/mtp)) → **~35–50 tok/s laptop at Q4 (est.)** | Native function calling + system role; Tau2 69.0 | 140+ languages; MMMLU 83.4. Audio ASR/translation "multiple languages" (30 s cap). Hinglish unmeasured |
| 3 | **Gemma 4 E4B** (Jul 2026, Apache-2.0) | 4.5B effective (8B w/ embeddings), audio-capable | QAT Q4_0 | **5.15 GB** (+0.99 mmproj) | 128K | `gemma4:e4b-it-qat` (6.1 GB) | `google/gemma-4-e4b` | "60–80 tok/s with MTP" claimed, unverified ([medium/ion](https://medium.com/@ion.stefanache0/multi-token-prediction-mtp-and-ollama-the-local-llm-server-6d8d8d61157e)) | Function calling; Tau2 42.2 (weak) | MMMLU 76.6 |
| 4 | **Qwen3.5-4B** (Mar 2026, Apache-2.0) | 4B dense | Q4_K_M | **2.74 GB** | 262,144 | `qwen3.5:4b` (3.4 GB) | `qwen/qwen3.5-4b` | not benchmarked; fastest option | TAU2 79.9, IFEval 89.8, BFCL 50.3 | MMMLU 76.1 |
| 5 | **Ministral 3 14B Instruct 2512** (Dec 2025, Apache-2.0) | 13.5B + 0.4B vision | Q4_K_M | **8.24 GB**; Q5_K_M 9.62; Q8_0 14.36 | 256K | `ministral-3:14b` (9.1 GB) | search `mistralai/Ministral-3-14B-Instruct-2512-GGUF` | no published 16 GB numbers; **~35–45 tok/s (est.)** | "native function calling and JSON outputting"; Arena-Hard 0.551. Ollama page shows no tools badge (flag) | Languages listed: en/fr/es/de/it/pt/nl/zh/ja/ko/ar — **Hindi not listed** |
| 6 | **gpt-oss-20b** (Aug 2025, Apache-2.0) | 21B / 3.6B MoE, MXFP4 | MXFP4 only | **12.11 GB** (`ggml-org`); unsloth Q4_K_M 11.62 | 128K | `gpt-oss:20b` (14 GB) | `openai/gpt-oss-20b` | RTX 4080 SUPER 186, 5070 Ti 189, 5060 Ti 111 tok/s; **~15.5 GB VRAM at 8K ctx** ([runaihome](https://runaihome.com/blog/gpt-oss-20b-local-ai-hardware-guide-2026/), Jun 2026) | Harmony tools/structured outputs; strong | MMMLU 69.7 — weak multilingual |
| 7 | **Gemma 4 26B-A4B** (Jul 2026, Apache-2.0) | 25.2B / 3.8B MoE | UD-Q3_K_XL (needs expert CPU-offload for headroom) | QAT Q4_0 14.44 GB; UD-IQ4_XS 13.60; UD-Q3_K_XL 12.91; UD-IQ3_XXS 11.42; UD-Q2_K_XL 10.55 | 256K | `gemma4:26b-a4b-it-qat` (16 GB) | `google/gemma-4-26b-a4b` (min 17 GB) | "~24 GB with drafter" ([pooyagolchian](https://pooyagolchian.com/blog/gemma-4-ollama-multi-token-prediction-local-2026/)); fast only if resident | MMLU-Pro 82.6, Tau2 68.2 | MMMLU 86.3 |
| 8 | **Qwen3.6-35B-A3B** (24 Apr 2026, Apache-2.0) | 36B / 3B MoE (256 experts, 8+1 active) | UD-IQ3_XXS or Q4 with `--n-cpu-moe` | UD-Q4_K_XL 22.36 GB; UD-Q3_K_XL 16.85; UD-IQ3_XXS 13.21; UD-Q2_K_XL 12.29; UD-IQ2_M 11.52; mmproj 0.90 | 262,144 | `qwen3.6:35b-a3b` (23 GB) | `qwen/qwen3.6-35b-a3b` | Desktop 4090: Q2_K ~85, Q4_K_M ~68 tok/s; "240 tok/s on RTX 6000 with MTP" | MMLU-Pro 85.2, GPQA 86.0, MCPMark 37.0, TAU3 67.2 | C-Eval 90.0; Hindi via Qwen3.5 base |

### Notes per model

**Qwen3.5-9B (#1).** Architecture: 32 layers, 8×(3×Gated DeltaNet + 1×Gated Attention), 4 KV heads × 256 dim on only 8 full-attention layers → KV cache 32 KB/token = **268 MB at 8K** plus ~50 MB of fixed recurrent state (from `config.json`). Card benchmarks (vs gpt-oss-20b): MMLU-Pro 82.5 vs 74.8; GPQA 81.7 vs 71.5; IFEval 91.5 vs 88.2; MultiChallenge 54.5 vs 40.1; MMMLU 81.2 vs 69.7; MAXIFE (multilingual instruction following) 83.4 vs 80.1. Thinking mode is **on by default** — turn it off for voice (see §7). MTP GGUFs (`unsloth/Qwen3.5-9B-MTP-GGUF`, Q6_K 7.68 GB) give "~1.5–2× faster generation" in llama.cpp ≥ May 16 2026 (`--spec-type draft-mtp`); caveat from Unsloth: `-np > 1` and `--mmproj` not yet supported with MTP. Recommended non-thinking sampling (Qwen card): temp 0.7, top_p 0.8, top_k 20, presence_penalty 1.5.

**Gemma 4 12B (#2).** 48 layers: 40 sliding-window (1024) + 8 global layers; global layers use one shared K=V head of dim 512, so KV at 8K is **~0.34 GB if the runtime windows the SWA cache, up to ~2.7 GB if it doesn't** (computed from `config.json`; llama.cpp windows by default — flag for Ollama). Google QAT Q4_0 claims "similar quality to bfloat16". Audio input (16 kHz mono, ≤30 s) works in llama.cpp `llama-server` since the 4 Jun 2026 converter fix; **Ollama does not support audio input** (crash issue #15333 unresolved as of Jun 2026); LM Studio audio support **not verified**. Arena AI: Gemma 4 31B 1452 vs Qwen3.5-27B 1404; 26B-A4B 1441 vs Qwen3.5-35B-A3B 1400 — "real users … consistently prefer Gemma 4" ([gemma4all](https://gemma4all.com/blog/gemma-4-vs-qwen-3-5-benchmarks), Jul 2026), while Qwen wins TAU2 by >10 points at every size. Default sampling: temp 1.0, top_p 0.95, top_k 64; lower temperature for correction tasks.

**Why the MoE 26B-A4B / 35B-A3B are "advanced" options only:** neither fits fully in VRAM with 5 GB headroom below ~Q3; LM Studio/llama.cpp can push expert weights to your 32 GB DDR5 (`--n-cpu-moe` / "offload expert weights to CPU"), which keeps quality but typically drops decode to the 10–25 tok/s range on laptop DDR5 — **no published number for this exact config; treat as unverified.**

## 3. Considered and excluded (with reasons)

- **gpt-oss-20b**: excellent tools/JSON, but 12.1 GB MXFP4 → ~15.3–15.5 GB total VRAM at 2–8K on Ollama ([runaihome](https://runaihome.com/blog/gpt-oss-20b-local-ai-hardware-guide-2026/)); no room for STT/TTS. Weak multilingual (MMMLU 69.7).
- **Qwen3.8-27B** (14 Aug 2026): Q4_K_M 16.46 GB; UD-Q3_K_XL 13.15 GB; UD-IQ3_XXS 10.93 GB; Q2_K_XL 9.83 GB. Only the Q2/IQ3 tiers leave headroom and "~48 t/s on a desktop 4090 (60–80 with MTP)" ([codersera](https://codersera.com/blog/how-to-run-qwen-3-8-locally-2026/)) → ~25–30 tok/s laptop (est.) at heavily degraded quant. Card: IFBench 79.5, GPQA 89.2 — superb, but not for this budget.
- **GLM-4.7-Flash** (30B-A3B, MIT): τ²-Bench 79.5 but UD-Q3_K_XL 13.78 GB, Q4_K_M 18.31 GB; languages en/zh only.
- **Sarvam-30B** (Mar 2026, Apache-2.0, 32B MoE / 2.4B active): best-in-class 22 Indian languages (MILU 76.8, MMLU-Pro 80.0), "can handle multilingual voice calls while performing tool calls" — but only Q4_K_M GGUF = **19.57 GB** (6 splits), not in the Ollama library (open issues #14319/#16242; community `predictivemanish/sarvam-30b`), needs CPU expert offload. Hinglish specialist if you accept that.
- **Nemotron 3.5 Lightning 30B-A3B** (Aug 2026): NVIDIA license, en/es/fr/de/it/ja, NVFP4 builds target Blackwell — not Ada.
- **Llama**: nothing new below Llama 4 Scout (109B) since 2025. **DeepSeek**: only V4 (huge); R1 distills are 2025 reasoning models (high TTFT). **Phi**: Phi-4-reasoning-vision-15B (Aug 2026) and Phi-4-mini-flash-reasoning are reasoning-first — poor voice TTFT. **Kimi K3 / MiniMax**: huge. **GLM-5.3-Flash**: 321B.

## 4. GEC-specific and English-teaching models (run alongside the LLM?)

| Model | Size | License | Notes |
|---|---|---|---|
| `grammarly/coedit-large` (Flan-T5) | 770M (~1.6 GB fp16); xl 3B; xxl 11B | **CC-BY-NC-4.0** (non-commercial) | Instruction-driven editing: "Fix grammatical errors in this sentence: …"; also paraphrase/formalize. ONNX ports exist (`rayliuca/coedit-large-onnx`). |
| `gotutiyan/gector-deberta-large-5k` (GECToR) | 410M | "Only non-commercial purposes" | Sequence-tagging GEC: millisecond latency, minimal edits, returns token-level edit tags (great for highlighting spans). Needs the `gector` repo code. |
| `vennify/t5-base-grammar-correction` | 220M | check card (older, JFLEG-trained) | Fluency-style rewrites; over-corrects informal speech. |
| `pszemraj/flan-t5-large-grammar-synthesis` | 780M | Apache-2.0 (per repo) | Typo/grammar synthesis; GGUF available. |
| `UniversalCEFR/ModernBERT-base-cefr-all-classifier` | 150M | Apache-2.0 | CEFR level classifier — useful for adaptive difficulty / progress tracking. |

**Verdict:** worth adding a tiny tagger (GECToR or CoEdIT-large, ~1–2 GB or CPU) as a *fast first pass and precision filter*, not as a replacement. Evidence: BEA 2026 study — minimal-edit prompting "acts as a precision filter"; zero-shot Claude Sonnet 4.5 reaches CoNLL-14 F0.5 67.05, Llama-4-Scout-17B 62.02 ([BEA 2026](https://aclanthology.org/2026.bea-1.17.pdf)); AIED 2026 study — fine-tuned GPT-4o gains +22.07 F0.5 over zero-shot and 73.76% of its "wrong" corrections were judged equally valid, i.e. LLM over-correction is real and reference metrics undercount it ([arXiv 2605.07635](https://arxiv.org/html/2605.07635)). Pipeline suggestion: STT → GEC tagger flags spans → LLM (Qwen/Gemma) explains, handles word choice/register/Indian-English idioms, and produces the JSON + spoken reply. Caveats: these GEC models are trained on written learner essays, so they will "correct" fillers/repetitions in speech transcripts — strip disfluencies first; CoEdIT and GECToR weights are non-commercial.

## 5. STT / TTS that fit the headroom (and Hinglish)

- **faster-whisper large-v3-turbo**: ~1.7 GB FP16 / **~0.9 GB INT8** ([gigagpu](https://gigagpu.com/whisper-vram-requirements/), Apr 2026). But whisper-large-v3 scores **29.74% WER** on conversational Hinglish (CoSHE-500) vs **13.67%** for `Trelis/whisper-hinglish-preview` (1.54B, Apache-2.0, Jun 2026; English FLEURS 6.93 vs 4.81) — from the Trelis card. Alternative: **Qwen3-ASR-1.7B** (Jul 2026, Apache-2.0) — Hindi + "English accents from multiple countries", streaming; `moorlee/qwen3-asr-0.6b-hinglish` fine-tune exists. Voxtral-Mini-4B-Realtime (Mistral, Feb 2026, 13 langs incl. hi, <500 ms) is a 4B model — likely too heavy for the headroom (VRAM not verified).
- **TTS**: Kokoro-82M ~0.5 GB, 40 ms first-audio, RTF 0.02; Chatterbox ~2–3 GB, 110 ms; XTTS-v2 4–6 GB ([gigagpu TTS](https://gigagpu.com/tts-latency-benchmarks/)). Kokoro is the budget pick.

## 6. Ollama vs LM Studio (Sept 2026)

| Feature | Ollama **v0.33.3** (2 Sep 2026) | LM Studio **0.4.23** (28 Aug 2026) |
|---|---|---|
| Structured output (JSON schema) | `format` = JSON schema; also `response_format` on `/v1`; docs advise temp 0 | `response_format: {type: "json_schema"}` — "llama.cpp's grammar-based sampling" for GGUF |
| Tool calling | `tools` on `/api/chat` and `/v1/chat/completions`; streaming + parallel calls; **`tool_choice` not supported** | Native for tool-trained templates ("hammer badge"), fallback prompt for others; streaming; `/v1/chat/completions` + `/v1/responses` |
| OpenAI-compatible API | chat/completions, completions, embeddings, models, `/v1/responses` (non-stateful) | OpenAI (incl. Responses) **and Anthropic `/v1/messages`**; API keys (0.4.21) |
| Multimodal incl. **audio input** | Text+image. **No audio** (Gemma 4 audio crashes, issue #15333, Jun 2026) | Image yes; audio **not verified** (no docs found; llama.cpp itself supports Gemma 4 audio since 4 Jun 2026) |
| Speculative decoding | MLX MTP first (Gemma 4 PR #15980); `-mtp-` tags exist for qwen3.6/3.8; **CUDA/Windows MTP unverified** | Draft-model SD (Power User mode); **MTP stable 0.4.14 (22 May 2026)**; DFlash/DSpark/MTP assistant drafters 0.4.22 (needs llama.cpp engine ≥2.29.1) |
| KV-cache quantization | `OLLAMA_KV_CACHE_TYPE=q8_0/q4_0` (global, needs `OLLAMA_FLASH_ATTENTION=1`) | Per-model K/V quant + Flash Attention in load settings/SDK (REST load API can't set it yet — issue #2024) |
| 2+ models concurrently | `OLLAMA_MAX_LOADED_MODELS` (default 3×GPUs), `OLLAMA_NUM_PARALLEL` (default 1) | Multiple models loaded simultaneously; parallel slots per model (default 4 — lower it, it multiplies KV) |
| Windows / CUDA | Native installer, bundled CUDA, runs as tray service | Native installer, auto-updating `llama.cpp-win-x86_64-nvidia-cuda12` runtime |
| Headless | `ollama serve` (open-source, MIT) | `llmster` daemon (`lms daemon up`), `lms server start` (closed-source; free-for-work status not re-verified) |
| New in 2026 | Claude Desktop/Code gateway (0.33), "prefill restore points" caching, metadata cache halves TTFT (0.32.15), GGUF default params (0.33.3) | 0.4 UI overhaul + llmster, parallel requests, Engine Protocol, MCP OAuth, LM Link/Locally mobile, tensor parallel, Anthropic API, MTP/DFlash |

**Recommendation for this project: LM Studio.** Reasons: (1) MTP speculative decoding on CUDA is stable and both picks ship MTP heads — the single biggest lever for tok/s and TTFT; (2) per-model context/KV-quant/parallel/GPU settings instead of global env vars; (3) you can load the text-only GGUF and skip the 0.9 GB vision projector; (4) grammar-constrained JSON + native tool templates + Responses API. Choose Ollama if you want MIT-licensed OSS and a simpler service; its API (`format`, `tools`, `think`) covers everything the app needs, but you lose verified MTP and ~0.9 GB to the bundled projector unless you pull an HF text-only GGUF.

## 7. VRAM budget — #1 pick, 8K context

Qwen3.5-9B Q6_K, text-only, LM Studio (llama.cpp CUDA), Flash Attention on, 1 parallel slot:

| Component | VRAM | Basis |
|---|---|---|
| LLM weights Q6_K | **7.46 GB** (7.36 GB lmstudio-community build) | HF file size |
| KV cache @ 8,192 tok, f16 | **0.27 GB** (+0.05 GB DeltaNet state) | 8 layers × 4 KV heads × 256 × 2 × 2 B; q8_0 KV halves it |
| llama.cpp compute buffers + CUDA context | ~0.8 GB | typical; not measured on this laptop |
| STT: faster-whisper large-v3-turbo INT8 (+CUDA ctx) | ~0.9 + 0.3 GB | gigagpu |
| TTS: Kokoro-82M fp16 (+CUDA ctx) | ~0.5 + 0.3 GB | gigagpu |
| Windows desktop/driver reserve | ~0.5–1.0 GB | rule of thumb |
| **Total** | **~11.1–11.6 GB → ~4.4–4.9 GB free** | |

Variants: Q8_0 (9.53 GB) → ~13.2–13.7 GB total (still fits, Kokoro only); swap Kokoro for Chatterbox (+2 GB) → use Q5_K_M/Q4_K_XL. Adding the MTP head (+~0.2 GB) and Unsloth's "~2 GB headroom" guidance for MTP is affordable at Q4_K_XL. In Ollama, `qwen3.5:9b` adds the 0.92 GB projector.

#2 (Gemma 4 12B QAT Q4_0 6.98 GB): KV 0.34 GB (windowed) — same envelope; budget 2.7 GB for KV if your runtime doesn't window SWA.

## 8. Install / run

**LM Studio (recommended)**
```powershell
winget install ElementLabs.LMStudio
lms get qwen/qwen3.5-9b            # choose Q6_K (check `lms get --help` for the @quant syntax)
lms get google/gemma-4-12b         # fallback (QAT Q4_0)
lms daemon up                      # headless llmster
lms server start --port 1234
lms load qwen/qwen3.5-9b --gpu max --context-length 8192 --identifier tutor
```
In the model's load settings: Flash Attention ON, K/V cache q8_0, Max Concurrent Predictions 1–2, **Enable Thinking OFF**, speculative decoding → MTP. Call `http://localhost:1234/v1/chat/completions` with `response_format: {type:"json_schema", …}` and `tools:[…]`.

**Ollama (fallback)**
```powershell
winget install Ollama.Ollama
setx OLLAMA_FLASH_ATTENTION 1
setx OLLAMA_KV_CACHE_TYPE q8_0
setx OLLAMA_CONTEXT_LENGTH 8192
setx OLLAMA_KEEP_ALIVE -1
ollama pull hf.co/unsloth/Qwen3.5-9B-GGUF:Q6_K   # text-only, 7.46 GB
ollama pull qwen3.5:9b                            # or: Q4_K_M + projector, 6.6 GB
ollama pull gemma4:12b-it-qat                     # fallback, 7.2 GB
```
API: `POST /api/chat` with `"think": false`, `"format": {…json schema…}`, `"tools": [...]`, `"options": {"temperature": 0.3}`.

**STT/TTS**: `pip install faster-whisper` (`WhisperModel("large-v3-turbo", compute_type="int8_float16")`), `pip install kokoro`; for Indian-English/Hinglish speakers evaluate `Trelis/whisper-hinglish-preview` or `Qwen/Qwen3-ASR-1.7B-hf`.

## 9. Could not verify / flags

- No tok/s measurement exists for these exact models on an RTX 4090 *Laptop*; laptop numbers are bandwidth-scaled estimates (576/1008 GB/s). Everylocalai's own 4090-laptop table (8B Q4_K_M ~40 tok/s) suggests Ollama overhead may pull real numbers toward the low end.
- Ollama MTP speculative decoding on CUDA/Windows; LM Studio audio-input support; whether Ollama windows Gemma 4's SWA KV cache; exact `lms get @quant` syntax; LM Studio commercial-use terms; Ministral 3 "tools" badge in Ollama; GLM-4.7-Flash 198K context (third-party figure).
- No Hinglish (romanized code-mixed) text benchmark exists for any general LLM here — run a 30-turn blind A/B (Qwen3.5-9B vs Gemma 4 12B) on your own tutor prompts before locking in.
- CoEdIT/GECToR licenses are non-commercial; `vennify/t5-base-grammar-correction` license not checked.

## Sources

Hugging Face (via HF MCP): [HF trending](https://huggingface.co/models?sort=trending) · [Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) · [unsloth/Qwen3.8-27B-GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) · [Qwen/Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) · [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF) · [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) · [unsloth/Qwen3.5-9B-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) · [unsloth/Qwen3.5-9B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-MTP-GGUF) · [lmstudio-community/Qwen3.5-9B-GGUF](https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF) · [unsloth/Qwen3.5-4B-GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF) · [google/gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) · [google/gemma-4-12B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) · [unsloth/gemma-4-12B-it-GGUF](https://huggingface.co/unsloth/gemma-4-12B-it-GGUF) · [lmstudio-community/gemma-4-12B-it-GGUF](https://huggingface.co/lmstudio-community/gemma-4-12B-it-GGUF) · [google/gemma-4-26B-A4B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf) · [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF) · [google/gemma-4-E4B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf) · [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) · [ggml-org/gpt-oss-20b-GGUF](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF) · [unsloth/gpt-oss-20b-GGUF](https://huggingface.co/unsloth/gpt-oss-20b-GGUF) · [mistralai/Ministral-3-14B-Instruct-2512](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512) · [Ministral-3-14B GGUF](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512-GGUF) · [zai-org/GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash) · [unsloth/GLM-4.7-Flash-GGUF](https://huggingface.co/unsloth/GLM-4.7-Flash-GGUF) · [zai-org/GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash) · [sarvamai/sarvam-30b](https://huggingface.co/sarvamai/sarvam-30b) · [sarvamai/sarvam-30b-gguf](https://huggingface.co/sarvamai/sarvam-30b-gguf) · [nvidia/Nemotron-3.5-Lightning-30B-A3B](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) · [microsoft/Phi-4-reasoning-vision-15B](https://huggingface.co/microsoft/Phi-4-reasoning-vision-15B) · [deepseek-ai/dflash_gemma4_12b_block7](https://huggingface.co/deepseek-ai/dflash_gemma4_12b_block7) · [grammarly/coedit-large](https://huggingface.co/grammarly/coedit-large) · [gotutiyan/gector-deberta-large-5k](https://huggingface.co/gotutiyan/gector-deberta-large-5k) · [UniversalCEFR ModernBERT CEFR](https://huggingface.co/UniversalCEFR/ModernBERT-base-cefr-all-classifier) · [vennify/t5-base-grammar-correction](https://huggingface.co/vennify/t5-base-grammar-correction) · [pszemraj/flan-t5-large-grammar-synthesis](https://huggingface.co/pszemraj/flan-t5-large-grammar-synthesis) · [Trelis/whisper-hinglish-preview](https://huggingface.co/Trelis/whisper-hinglish-preview) · [moorlee/qwen3-asr-0.6b-hinglish](https://huggingface.co/moorlee/qwen3-asr-0.6b-hinglish) · [Qwen/Qwen3-ASR-1.7B-hf](https://huggingface.co/Qwen/Qwen3-ASR-1.7B-hf) · [mistralai/Voxtral-Mini-4B-Realtime-2602](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)

Ollama: [qwen3.5](https://ollama.com/library/qwen3.5) · [qwen3.5 tags](https://ollama.com/library/qwen3.5/tags) · [qwen3.6 tags](https://ollama.com/library/qwen3.6/tags) · [gemma4](https://ollama.com/library/gemma4) · [gemma4 tags](https://ollama.com/library/gemma4/tags) · [gpt-oss tags](https://ollama.com/library/gpt-oss/tags) · [qwen3.8 tags](https://ollama.com/library/qwen3.8/tags) · [ministral-3 tags](https://ollama.com/library/ministral-3/tags) · [FAQ](https://docs.ollama.com/faq) · [structured outputs](https://docs.ollama.com/capabilities/structured-outputs) · [tool calling](https://docs.ollama.com/capabilities/tool-calling) · [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) · [releases](https://github.com/ollama/ollama/releases) · [Gemma4 MTP PR #15980](https://github.com/ollama/ollama/pull/15980) · [Sarvam request #14319](https://github.com/ollama/ollama/issues/14319) · [predictivemanish/sarvam-30b](https://ollama.com/predictivemanish/sarvam-30b)

LM Studio: [changelog index](https://lmstudio.ai/changelog/lmstudio) · [0.4.0](https://lmstudio.ai/changelog/lmstudio-v0.4.0) · [0.4.14](https://lmstudio.ai/changelog/lmstudio-v0.4.14) · [0.4.22](https://lmstudio.ai/changelog/lmstudio/lmstudio-v0.4.22) · [speculative decoding](https://lmstudio.ai/docs/app/advanced/speculative-decoding) · [SDK speculative decoding](https://lmstudio.ai/docs/typescript/llm-prediction/speculative-decoding) · [structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output) · [tool use](https://lmstudio.ai/docs/developer/openai-compat/tools) · [CLI](https://lmstudio.ai/docs/cli) · [trending models](https://lmstudio.ai/trending/models) · [google/gemma-4-12b](https://lmstudio.ai/models/google/gemma-4-12b) · [qwen/qwen3.5-9b](https://lmstudio.ai/models/qwen/qwen3.5-9b) · [bug #2024 KV quant](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2024)

Benchmarks/guides: [willitrunai Qwen3.5 quant speed (Jul 6 2026)](https://willitrunai.com/blog/qwen-3-5-quantization-speed-comparison) · [runaihome gpt-oss-20b (Jun 9 2026)](https://runaihome.com/blog/gpt-oss-20b-local-ai-hardware-guide-2026/) · [codersera Qwen3.8 (Aug 18 2026)](https://codersera.com/blog/how-to-run-qwen-3-8-locally-2026/) · [everylocalai RTX 4090 Laptop (Sep 5 2026)](https://everylocalai.com/hardware/nvidia-rtx-4090-laptop) · [orcarouter Qwen3.8 vs Gemma 4 12B (Aug 12 2026)](https://www.orcarouter.ai/blog/qwen-3-8-27b-vs-gemma-4-12b) · [gemma4all Gemma 4 vs Qwen 3.5 (Jul 14 2026)](https://gemma4all.com/blog/gemma-4-vs-qwen-3-5-benchmarks) · [gemma4all hardware (Jul 10 2026)](https://gemma4all.com/blog/gemma-4-hardware-requirements) · [techsy Gemma 4 12B (Jun 6 2026)](https://techsy.io/en/blog/gemma-4-12b) · [morphllm best Ollama models (Aug 21 2026)](https://www.morphllm.com/best-ollama-models) · [tech-insider LM Studio vs Ollama (Aug 30 2026)](https://tech-insider.org/lm-studio-vs-ollama-2026/) · [Unsloth MTP guide](https://unsloth.ai/docs/models/mtp) · [Unsloth Gemma 4 guide](https://unsloth.ai/docs/models/gemma-4) · [Gemma 4 12B audio in llama.cpp (Jun 5 2026)](https://note.com/unco3/n/n871e994d27b2?hl=en) · [avenchat LM Studio Gemma 4 (Jun 14 2026)](https://avenchat.com/blog/does-lm-studio-support-gemma-4) · [pooyagolchian Gemma 4 MTP Ollama (May 25 2026)](https://pooyagolchian.com/blog/gemma-4-ollama-multi-token-prediction-local-2026/) · [medium MTP + Ollama (May 15 2026)](https://medium.com/@ion.stefanache0/multi-token-prediction-mtp-and-ollama-the-local-llm-server-6d8d8d61157e) · [smeltcore Gemma 4 12B on RTX 4080 (Jul 4 2026)](https://smeltcore.com/recipes/gemma-4-12b-on-rtx-4080-local-private-assistant-via-llama-cpp-ollama-16gb/) · [gigagpu Whisper VRAM (Apr 13 2026)](https://gigagpu.com/whisper-vram-requirements/) · [gigagpu TTS latency](https://gigagpu.com/tts-latency-benchmarks/) · [AIED 2026 GEC evaluation (May 8 2026)](https://arxiv.org/html/2605.07635) · [BEA 2026 instruction-following LLMs for GEC (Jul 2026)](https://aclanthology.org/2026.bea-1.17.pdf)
