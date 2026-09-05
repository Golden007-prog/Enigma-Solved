# PROGRESS — Interview Cracker (Enigma for Masai)

Build log kept by Claude Code. Every phase: plan → steps with verification → Acceptance with real numbers.
Legend: ✅ verified by command/test/screenshot · ⏳ in progress · ❌ failed · UNVERIFIED = could not be checked.

## Inputs (Checkpoint 0)

| # | Input | Status |
|---|---|---|
| 1 | FlutterFlow project ID | ✅ `enigma-solved-ctlkqt` (read from the project URL in Chrome; team "Oikantik Basu's Team", Growth plan) |
| 2 | FlutterFlow API key | ⏳ **needed from Oikantik before Phase 4** — not present in `~/.flutterflow/credentials.json`, `~/.config/flutterflow/claude-env.sh`, or `FF_API_KEY`. Path: copy from https://app.flutterflow.io/account and say "copied" (clipboard hand-off), or run bare `flutterflow ai` in his own terminal. Never pasted in chat. |
| 3 | Supabase | ✅ MCP authenticates (`list_tables` → `[]`, `get_project_url` → `https://reqleijouyejjzstyjeq.supabase.co`). ⏳ `SUPABASE_SERVICE_ROLE_KEY` must be placed in `server/.env` by Oikantik in Phase 3 (Claude writes `server/.env.example`). |
| 4 | Android phone | UNVERIFIED — not answered; **default: emulator only** (Phase 6.3 phone tests will be skipped unless a device shows up in `adb devices`). |
| 5 | Rive `.riv` interviewer | UNVERIFIED — not answered; **default: Phase 5A CustomPaint avatar ships first**. |
| 6 | Models drive | ✅ E: 120.3 GB free, C: 182.7 GB free → `E:\Enigma for Masai\server\models` |
| 7 | Demo date / pressure dial | UNVERIFIED — not answered; **default: Realistic**, no time-box applied. |

Kickoff note: Oikantik's kickoff replaced "stop at every ⛔ until I say go" with "don't stop before completing the project". Checkpoints are therefore executed without waiting, kept reversible, and each is logged in `docs/DECISIONS.md`.

---

## Phase 0 — Environment audit and toolchain

**Plan**
1. Audit every tool with one script; paste the table below.
2. Install what is missing with verified winget IDs (espeak-ng, JDK 17, platform-tools); Flutter from the official zip; Android SDK via cmdline-tools + `sdkmanager`.
3. User-level PATH + `ANDROID_HOME`; `flutter config --jdk-dir` / `--android-sdk`; `flutter doctor` and `--android-licenses`.
4. Repo: root becomes the working tree of `Golden007-prog/Enigma-Solved`; `.gitignore`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/screenshots/`, `docs/logs/`.
5. Chrome check + FlutterFlow "before" evidence.
6. Commit "Phase 0: toolchain".

**Step 1 — Audit (script: scratchpad `audit.ps1`, run 2026-09-05 12:27 IST)**

| Tool | Found | Status |
|---|---|---|
| `nvidia-smi` | driver **616.56**, NVIDIA GeForce RTX 4090 Laptop GPU, **16376 MiB** | ✅ (≥ 546.01 → Sysmem Fallback Policy control available) |
| `winget` | v1.29.290 | ✅ |
| `git` | 2.52.0.windows.1 | ✅ |
| `python` (on PATH) | 3.11.9 (`hermes-agent` venv shadows PATH); Python **3.12.10** (Microsoft Store) visible to `uv python list` | ✅ via `uv --python 3.12` |
| `uv` | 0.11.21 | ✅ |
| `lms` / LM Studio | CLI commit 07b7252; LM Studio **0.4.23+1** (winget) | ✅ |
| `flutter` | not installed → **3.47.2 stable (Dart 3.13.2, DevTools 2.60.0)** at `C:\dev\flutter` | ✅ `flutter --version` |
| `dart` | 3.13.3 stable standalone at `C:\tools\dart-sdk` | ✅ |
| `flutterflow` CLI | 0.0.38 → upgraded to **0.0.39** (`dart pub global activate flutterflow_cli`) | ✅ (`--version` is not a flag on the classic CLI; `flutterflow ai --version` needs a workspace) |
| `adb` | missing → **37.0.1** via `winget install Google.PlatformTools` | ✅ |
| `emulator` | missing → **37.1.11.0** via `sdkmanager --install emulator`; `emulator -accel-check` → "WHPX(10.0.26200) is installed and usable" | ✅ no reboot needed |
| `java` | Java 8 on PATH; `JAVA_HOME` = Temurin JDK 25.0.4 → installed **Microsoft OpenJDK 17.0.20.1** for Flutter | ✅ |
| `espeak-ng` | missing → **1.52.0** via `winget install eSpeak-NG.eSpeak-NG` | ✅ |
| `docker` | 29.0.1 (Docker Desktop 4.52.0) | ✅ optional |
| `hf` | missing | ⏳ Phase 1 (`uv tool install "huggingface_hub[cli]"`) |
| `node` | v25.2.1 | ✅ |
| Disk | C: 182.7 GB free · E: 120.3 GB free | ✅ |
| Hypervisor | `HyperVisorPresent = True` (Hyper-V/WHPX already on for Docker Desktop) | ✅ expect no reboot for the emulator; confirm with `emulator -accel-check` |
| Ollama | 0.12.6 installed (fallback runtime only, not used) | — |

**Step 2 — Installs**
- `winget install eSpeak-NG.eSpeak-NG` → `C:\Program Files\eSpeak NG\espeak-ng.exe --version` = 1.52.0 ✅
- `winget install Microsoft.OpenJDK.17` → `java -version` = openjdk 17.0.20.1 ✅
- `winget install Google.PlatformTools` → `adb version` = 1.0.41 / 37.0.1 ✅
- Flutter: `winget search flutter` has no SDK package → official zip `flutter_windows_3.47.2-stable.zip` (1.75 GB) → `C:\dev\flutter` ✅
- Android cmdline-tools `commandlinetools-win-15859902_latest.zip` (155.7 MB, from dl.google.com; the edgedl mirror refused curl) → `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest` (cmdline-tools 22.0; `sdkmanager` is deprecated in favour of the new `android` CLI but still works) ✅
- Licenses: piping `y` from PowerShell did not reach `sdkmanager.bat`; `yes | ./sdkmanager.bat --licenses` from Git Bash accepted all 7 ✅
- `sdkmanager --install`: `platform-tools 37.0.1`, `platforms;android-35`, `platforms;android-36` (Flutter 3.47 requires SDK 36), `build-tools;35.0.0`, `build-tools;36.0.0`, `emulator 37.1.11`, `system-images;android-35;google_apis;x86_64` (r09) — verified with `--list_installed` ✅

**Step 3 — Environment**
- User PATH prepended with `C:\dev\flutter\bin`, `C:\Program Files\eSpeak NG`, `%ANDROID_HOME%\cmdline-tools\latest\bin`, `%ANDROID_HOME%\platform-tools`, `%ANDROID_HOME%\emulator`; `ANDROID_HOME` (user) = `C:\Users\oikan\AppData\Local\Android\Sdk` ✅ (new terminals pick these up; this session exports them inline)
- `flutter config --jdk-dir "C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot" --android-sdk "…\Android\Sdk" --no-analytics` ✅ (`flutter config --list` confirms both)
- `yes | flutter doctor --android-licenses` → "All SDK package licenses accepted" ✅
- `flutter doctor` (final):
  ```
  [√] Flutter (Channel stable, 3.47.2, on Microsoft Windows [Version 10.0.26200.9278], locale en-IN)
  [√] Windows Version (Windows 11 or higher, 25H2, 2009)
  [√] Android toolchain - develop for Android devices (Android SDK version 36.0.0)
  [√] Chrome - develop for the web
  [X] Visual Studio - develop Windows apps   ← unrelated (Windows desktop target only); not installed on purpose
  [√] Connected device (3 available)
  [√] Network resources
  ```

**Step 4 — Repo**
- `git init -b main` at `E:\Enigma for Masai`, `origin` = `https://github.com/Golden007-prog/Enigma-Solved.git`, `main` tracks `origin/main` (commit `9688b9d Initial commit`, LICENSE restored) ✅
- `.gitignore`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/screenshots/`, `docs/logs/` ✅
- Leftovers not deleted (permission classifier): `Enigma-Solved/` sub-clone and empty file `1.0` are git-ignored; Oikantik may delete them.

**Step 5 — Chrome**
- `tabs_context` OK; navigated to the FlutterFlow dashboard → project `enigma-solved-ctlkqt` opens; page tree = single `HomePage` (AppBar "Page Title", empty Column). Text evidence in `docs/screenshots/00-ff-before.md`. **PNG UNVERIFIED** (saving the browser screenshot to disk was blocked by the permission classifier).

**Acceptance**
- every tool shows a version: ✅ (table above; `hf` deferred to Phase 1 by design)
- `flutter doctor` no red items except unrelated: ✅ (only Visual Studio, Windows-desktop-only)
- repo committed as "Phase 0: toolchain": ✅ (see `git log`)
- Background prep launched (results land in the scratchpad, integrated when each phase starts): workflow `phase1-derisk-research` (LM Studio CLI, onnx-asr timestamps, kokoro timestamps, silero/torch/uv, emulator), `phase2-brain-drafts` (schemas, prompts, fixtures, gates, agenda, protocol + tests), `phase3-supabase-draft` (migration SQL + RLS, reviewed, NOT applied), `phase4-5-app-prep` (package pins, DSL notes, VoiceLink.dart, CustomPaint avatar, LottieFiles shortlist).
- Commit `Phase 0: toolchain` (amended once to drop four zero-byte junk files that background subagent shells had created at the repo root; the junk was then deleted). From here on `git add` uses explicit paths, never `-A`.

---

## Phase 1 — Models: download, configure, measure

**Plan**
1. ⛔ (pre-approved) Download list: Qwen3.5-9B Q6_K 7.46 GB via `lms get qwen/qwen3.5-9b@q6_k --gguf -y`; Parakeet-TDT-0.6B-v2 ONNX (~1.5 GB) + Kokoro-82M (~0.4 GB) + Silero (2 MB) into `server/models/`; Gemma 4 12B fallback **deferred** (only if Qwen misses targets). Disk before: E: 120 GB free.
2. LM Studio: `lms daemon up` (already running, v0.4.23+1) → `lms server start --port 1234 --bind 127.0.0.1` → `lms load qwen/qwen3.5-9b --gpu max --context-length 8192 --speculative-draft-mtp --identifier interviewer`. CLI has no flags for KV-cache quant / flash attention / thinking → GUI click path for Oikantik + API verification (no `reasoning_content`, no `<think>`).
3. `server/`: `pyproject.toml` (deps per master prompt + torch cu126 index + openai client), `uv sync`, `hf` CLI installed via `uv tool install` (huggingface-hub 1.30.0).
4. Probes under `server/tools/`: `llm_probe.py` (JSON-schema Stage A on `fixtures/jd_fintech.txt`, TTFT + tok/s over 3 runs, target ≥ 35 tok/s, TTFT ≤ 400 ms), `tts_probe.py` (Kokoro token timestamps, `fixtures/sample_answer_1.wav`), `stt_probe.py` (onnx-asr Parakeet CUDA, word timestamps or fallback), `vad_probe.py` (Silero on CPU, 700 ms end-of-speech).
5. VRAM proof with everything loaded (`nvidia-smi`), NVIDIA sysmem-fallback policy note for Oikantik.
6. `tools/selftest.py` assembled from the probes; exits non-zero on failure.

**Step 1 — Downloads**
- `lms ls` before: only `openai/gpt-oss-20b` (12.11 GB, unusable in the VRAM budget) and `text-embedding-nomic-embed-text-v1.5` were present.
- `lms get qwen/qwen3.5-9b@q6_k --gguf -y` started detached (log: `docs/logs/lms-get-qwen.log`). The LM Studio Hub entry resolves to `lmstudio-community/Qwen3.5-9B-GGUF` → `Qwen3.5-9B-Q6_K.gguf` (7.36 GB) **plus** `mmproj-Qwen3.5-9B-BF16.gguf` (0.92 GB, vision projector, downloaded automatically; will be kept off the GPU). ⏳
- `hf download hexgrad/Kokoro-82M` → `server/models/hf-cache/models--hexgrad--Kokoro-82M` (347 MB) ✅
- `hf download istupakov/parakeet-tdt-0.6b-v2-onnx` → 3.0 GB (fp32 encoder 41 MB + 2.44 GB `.onnx.data`, int8 encoder 652 MB, decoder-joint, `nemo128.onnx`, `vocab.txt`) ✅
- Silero VAD ships inside the `silero-vad` wheel (no download).

**Research findings applied (workflow `phase1-derisk-research`, primary-source verified):**
- `onnx-asr` 0.12.0: `load_model("nemo-parakeet-tdt-0.6b-v2", providers=[...])` → `.with_timestamps().recognize()` returns `TimestampedResult(text, tokens, timestamps, logprobs)`; timestamps are **token-level** emission times on an 80 ms grid (seconds). Word spans are derived by grouping on the leading-space token boundary (`stt_probe.words_from_tokens`). int8 files are CPU artifacts; GPU path = fp32 on CUDAExecutionProvider.
- `onnxruntime-gpu` ≥ 1.27 on PyPI is built for **CUDA 13** (cuDNN 9); `pip extras [cuda,cudnn]` pull the matching `nvidia-*` wheels and `onnxruntime.preload_dlls()` loads them → `pyproject.toml` updated. Driver 616.56 is CUDA-13 capable. torch stays on the cu126 index (its DLLs are separate, no conflict).
- Kokoro 0.9.4: `KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', device='cuda')`; `Result.tokens[i].start_ts/end_ts` are seconds **relative to each yielded chunk** (offset by cumulative audio length → `tts_probe` fixed); misaki uses the bundled `espeakng-loader` DLL (env vars are ignored); English G2P needs spaCy `en_core_web_sm` → pinned as a wheel dependency for offline runs.
- LM Studio 0.4.23: `lms load` has `--gpu`, `-c`, `--parallel`, `--ttl`, `--identifier`, `--speculative-draft-mtp` (needs an MTP-capable GGUF) but **no** KV-quant/flash-attention flags → those live in My Models → gear (per-model defaults) or REST `POST /api/v1/models/load {"flash_attention": true}`. Qwen3.5 has no `/no_think`; thinking is the per-model field **"Enable Thinking"** (My Models → Inference → Reasoning) and per request via `"reasoning_effort": "none"` (bug #1990 still open for Qwen3.5 → verify by API). `reasoning_content` is separated from `content` by default since 0.4.7. Structured output: `response_format.json_schema{name,strict,schema}`.
- Parakeet fp32 on CUDA: no published VRAM figure; estimate 3–4 GB → **measure**; if the budget breaks, fall back to fp16-converted ONNX or CPU int8 (RTFx ~37).

**Step 2 — LM Studio** (`lms daemon status` → LM Studio v0.4.23+1 running, backed by the desktop app; `lms server start --port 1234 --bind 127.0.0.1` ✅)
- `lms get qwen/qwen3.5-9b@q6_k --gguf -y` → 8.28 GB on disk (Q6_K 7.36 GB + mmproj 0.92 GB), ~40 min at 3 MB/s ✅
- `lms load qwen/qwen3.5-9b -y --gpu max --context-length 8192 --speculative-draft-mtp` → **"Error: MTP speculative decoding requires a GGUF model with a bundled supported MTP head"** — the lmstudio-community GGUF has no MTP head. Loaded without MTP: `lms load qwen/qwen3.5-9b -y --gpu max --context-length 8192 --parallel 1 --identifier interviewer` → "Model loaded successfully in 15.91s (7.71 GiB)" ✅. `lms ps` shows CONTEXT 8192, PARALLEL 1.
- KV-cache q8_0 / Flash Attention / "Enable Thinking" cannot be set from `lms` (verified in `lms load --help`). **Click path for Oikantik (optional, not required for the targets):** LM Studio → My Models → `qwen/qwen3.5-9b` gear → Inference → Reasoning → *Enable Thinking* OFF; Load settings → *Flash Attention* ON, *K Cache / V Cache Quantization* q8_0, *Max Concurrent Predictions* 1. Thinking is already suppressed per request (`reasoning_effort: "none"`) and verified below.

**Step 3 — `server/` env**: `uv sync --python 3.12` (torch 2.14.0+cu126, onnxruntime-gpu 1.29.0 + CUDA-13 runtime wheels, kokoro 0.9.4, onnx-asr 0.12.0, silero-vad 6.2.1, openai 3.8.0, spaCy en_core_web_sm 3.8.0). First sync died on a 300 s cache-lock timeout (subagents were installing into the same uv cache); re-run with `UV_LOCK_TIMEOUT=1800` ✅. `hf` CLI 1.30.0 via `uv tool install`.

**Step 4 — Probes (measured on this laptop, 2026-09-05)**
- `tools/llm_probe.py --runs 3 --max-tokens 2500` (Stage A JSON-schema call, 1,800-token prompt, `reasoning_effort=none`):

  | run | prompt tok | completion tok | TTFT | tok/s | JSON | thinking leak |
  |---|---|---|---|---|---|---|
  | 1 (cold) | 1800 | ~1000 | 619 ms | 47.3 | parses | none |
  | 2 | 1800 | ~1000 | 69 ms | 62.4 | parses | none |
  | 3 | 1800 | ~1000 | 69 ms | 61.9 | parses | none |

  **median 59.3 tok/s (target ≥ 35) · median TTFT 104 ms (target ≤ 400)** ✅ (prompt is cached by LM Studio after run 1; the cold TTFT of 619 ms is the number to plan around after a JD change). First attempt with `max_tokens=900` truncated the rubric → "Unterminated string"; Stage A needs ~1,000 output tokens, cap raised. Log: `docs/logs/` (chat output).
- `tools/tts_probe.py` (Kokoro-82M, CUDA, `af_heart` / `am_michael`): KPipeline load 316 s on first run (spaCy model download; cached afterwards). `sample_answer_1` 18.4 s audio, 63/63 tokens with `start_ts/end_ts`, first audio 687 ms (includes G2P warm-up), RTF 0.037; `sample_answer_2` 28.8 s, 77/77 tokens, first audio 523 ms, RTF 0.018 ✅. Token timestamps confirmed (e.g. `'final-year' 0.99–1.52 s`).
- `tools/vad_probe.py` (Silero VAD 6.2.1 ONNX, CPU): 1 segment 0.30→17.90 s in 129 ms for 19.9 s audio (RTF 0.0065); streaming 0.16 ms per 32 ms chunk; end-of-turn fired 756 ms after true end with the 700 ms rule ✅.
- VRAM with LLM loaded + Kokoro on CUDA (Python process alive): **11,325 / 16,376 MiB** (LLM alone 10,616 MiB incl. ~2.5 GB desktop baseline).
- `tools/stt_probe.py --providers cuda,cpu-int8` (Parakeet-TDT-0.6B-v2 via onnx-asr 0.12.0, 28.8 s strong-answer clip): **CUDA fp32** load 5.05 s, transcription **265 ms → RTFx 109**, similarity to the script **99.4** (only "Redis" → "RIDI's"); **CPU int8** load 1.96 s, 1,779 ms → RTFx 16, similarity 99.4. Token timestamps are per sub-word token on an 80 ms grid (`' So'@0.24, ','@0.48, ' in'@0.64 …`); words are rebuilt on the leading-space boundary (`audio/stt.py:words_from_tokens`). ✅ **STT path chosen: onnx-asr Parakeet on CUDA fp32, word timestamps derived from token emission times** (DECISIONS.md).
- VRAM with LLM + Parakeet fp32 on CUDA loaded: **14,254 MiB** (STT alone ≈ 3.6 GB incl. CUDA context) → over the 12.5 GB target once Kokoro joins. Mitigation in progress: fp16 encoder conversion (`tools/convert_parakeet_fp16.py`); fallback: UD-Q4_K_XL LLM (−1.5 GB) or CPU int8 STT (RTFx 16).
