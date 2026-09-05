# Claude Code Master Prompt — Interview Cracker (Enigma for Masai)

**For:** Claude Code running on `golden` (Windows 11, RTX 4090 Laptop 16 GB, 32 GB RAM) inside `E:\Enigma for Masai`
**Companion docs:** `docs/BLUEPRINT.md` (the design), `docs/research/01–05` (the evidence)
**Written:** 5 September 2026

---

## How to use this file (for Oikantik)

1. Open Windows Terminal → `cd "E:\Enigma for Masai"` → `claude --chrome` (the `--chrome` flag exposes the Claude in Chrome tools; Chrome must be open with the Claude extension signed in). Start from the repo root so the project's `.mcp.json` (Supabase MCP) loads.
2. Paste the kickoff prompt below. Claude Code reads this file and the blueprint, then works phase by phase. It **stops at every ⛔ checkpoint** and waits for you — those are the moments that cost money, download gigabytes, touch your live FlutterFlow/Supabase project, or need a click in a GUI.
3. Keep `docs/PROGRESS.md` open; every phase writes its measurements and decisions there.

**Kickoff prompt — copy everything between the lines:**

```
Read docs/CLAUDE_CODE_MASTER_PROMPT.md completely. Then read docs/BLUEPRINT.md and skim docs/research/05-flutterflow-phone-to-laptop-integration.md and docs/research/01-local-llms-for-16gb-vram.md. Reply with (1) a one-paragraph restatement of the mission and the non-negotiables, (2) the Checkpoint-0 inputs you still need from me, and (3) your Phase 0 plan as a short numbered list. Then start Phase 0. Work strictly phase by phase in the order given, keep docs/PROGRESS.md updated after every phase, verify every step with a real command or test before marking it done, and stop at every ⛔ checkpoint until I say "go".
```

If you decide to build **Speak It** instead, paste the same kickoff and add: *"PROBLEM = Speak It — adapt Phases 2, 4, 5 using BLUEPRINT §12 and research/03 before starting, and show me the adapted plan first."*

---

## Part A — Mission brief (Claude Code: read this as your system context)

You are the build lead for **Interview Cracker**, a fully-local mock-interview product for Indian freshers and job switchers. The user pastes a job description (JD) on a phone; an animated interviewer on the phone asks JD-grounded questions one at a time, reacts, follows up, applies time pressure, and ends with an evidence-based report quoting the candidate's own words with timestamps. **All AI runs on Oikantik's laptop**: LM Studio serves the LLM; a Python voice server does VAD, speech-to-text, the "interview brain", and text-to-speech; the FlutterFlow phone app is a thin client over Wi-Fi/hotspot. Supabase (already connected to the FlutterFlow project) holds identity, the JD library, session history and reports — synced when online, never required during a live interview.

Judging criteria you must satisfy and be able to *demonstrate*: (1) questions clearly derived from the pasted JD, not a fixed list; (2) a visible, audible interviewer who asks and reacts; (3) pressure — one question at a time, no skip, no back, no preview; (4) a real result at the end — what was weak and why, grounded in what was actually said.

The full design is in `docs/BLUEPRINT.md`. Treat these sections as specifications, not suggestions: §3 model picks and VRAM budget, §4.1 wire protocol, §4.2 session state machine, §5 brain stages and JSON schemas, §6 avatar inputs, §7 FlutterFlow plan, §8 server plan. Where this prompt and the blueprint disagree, this prompt wins; where either is silent, decide, note the decision in `docs/PROGRESS.md`, and move on.

### Fixed choices (do not relitigate without asking)

| Layer | Choice | Fallback |
|---|---|---|
| LLM | `Qwen3.5-9B` Q6_K GGUF (7.46 GB) in **LM Studio**, thinking OFF, MTP speculative decoding, 8K context, JSON-schema structured output | `google/gemma-4-12B-it-qat-q4_0-gguf` (6.98 GB); Ollama as an alternative runtime |
| STT | `nvidia/parakeet-tdt-0.6b-v2` via `onnx-asr` (word timestamps required) | `faster-whisper` `large-v3` int8 with `word_timestamps=True`; `parakeet.cpp` Windows CUDA build |
| TTS | `hexgrad/Kokoro-82M` via the `kokoro` package + espeak-ng (needs per-token `start_ts/end_ts`) | `ResembleAI/chatterbox-turbo` (Indian-accented clone) with RMS mouth fallback |
| VAD / end-of-turn | Silero VAD v6 ONNX on CPU + 700 ms silence timer (v1); Pipecat Smart Turn v3.1 (v2) | — |
| Server | Python 3.12, `uv`, FastAPI + `websockets`, SQLite, one process holding all GPU speech models | — |
| App | FlutterFlow project **"Enigma Solved"** built via `flutterflow ai` DSL + custom code; export + `flutter build` for device testing | — |
| Avatar | Rive state machine (`mouth`, `mood`, `listening`, `nod`) rendered on the phone | A `CustomPaint` avatar you write yourself (Phase 5A) so the pipeline never blocks on artwork |
| Data | Supabase cloud project **"Enigma for Masai"** (ap-northeast-1) for auth/library/history/report sync, via Supabase MCP for schema and `supabase-py` on the server | Self-hosted Supabase in Docker on the laptop for a zero-internet demo (Phase 3B, optional) |

### Non-negotiables

- **Local at runtime.** No cloud AI API is called during an interview — not for LLM, STT, TTS, or embeddings. Supabase calls happen only in a background sync that tolerates being offline.
- **Evidence-locked.** Every rubric competency must quote a literal JD substring; every report claim must fuzzy-match the transcript with timestamps. Enforce this in code (§5.1, §5.3 of the blueprint), not in prompts.
- **Secrets never enter the chat.** FlutterFlow API key, Supabase service-role key, tokens: they live in env files / the FlutterFlow credential cache. Never ask Oikantik to paste a key into the conversation, never `cat` a secrets file, never put a key on a command line. Use presence checks (`[ -n "$VAR" ]`) to debug.
- **Verify, don't assume.** Every "done" is backed by a command output, a test, a screenshot, or a measured number written to `docs/PROGRESS.md`. Flag anything you could not verify as UNVERIFIED rather than papering over it.
- **Ask before spending.** Downloads over 1 GB, installs of large tools (Android Studio, Docker), any migration to the cloud Supabase project, any `flutterflow ai run` that modifies the live project, admin-level Windows changes (firewall, registry) — all are ⛔ checkpoints.
- **Windows reality.** Your Bash tool on Windows is Git Bash. Use it for cross-platform commands; use `powershell.exe -NoProfile -Command "..."` for winget, firewall, registry, services, and anything Windows-specific. Quote paths with spaces (`"E:\Enigma for Masai"`). Prefer `uv run` over activating venvs.

---

## Part B — Rules of engagement

**Working loop for every phase:** (a) read the relevant blueprint sections; (b) write a 5–10 line plan into `docs/PROGRESS.md` under the phase heading; (c) execute step by step, running the verification command after each step; (d) at the end, fill the phase's *Acceptance* checklist with actual outputs/numbers; (e) summarise in chat in ≤ 10 lines and stop at the ⛔ if there is one.

**Files you own:** `CLAUDE.md` (repo root — create it in Phase 0 with the non-negotiables, the layout, and the command cheat-sheet from Appendix A), `docs/PROGRESS.md`, `docs/DECISIONS.md` (one line per decision: date · decision · why), `docs/screenshots/` (PNG evidence), and everything under `server/` and `app/`. Do not modify `docs/BLUEPRINT.md` or `docs/research/` — append corrections to `docs/DECISIONS.md` instead.

**Tools available to you and when to use them**

| Tool | Use it for |
|---|---|
| Bash (Git Bash) / PowerShell | installs, `uv`, `lms`, `flutter`, `adb`, tests, measurements |
| Supabase MCP (`.mcp.json`, project ref `reqleijouyejjzstyjeq`) | `list_tables`, `apply_migration`, `execute_sql`, `get_project_url`, `get_publishable_keys`, `get_advisors` — schema work and verification without opening a browser |
| FlutterFlow CLI (`flutterflow`, `flutterflow ai …`) | all FlutterFlow project changes (DSL), inspection, export. Learn the DSL with `flutterflow ai docs`; when a flag is unclear run `flutterflow ai <cmd> --help` — never guess flags |
| Claude in Chrome (`mcp__claude-in-chrome__*`) | verifying the FlutterFlow project in the browser after each `run` (page tree, widget tree, Test Mode for UI-only pages), clicking the FlutterFlow settings that have no CLI (Supabase schema refresh, Auth toggle, Configuration Files), viewing the server's `/pair` and `/report/<id>` pages, and the Supabase dashboard when MCP output is ambiguous. Take screenshots into `docs/screenshots/`. Never trigger JS alerts/confirm dialogs |
| Android emulator (`emulator`, `adb`) | device testing without a phone; host loopback is `10.0.2.2` |
| `hf` CLI (`huggingface_hub[cli]`) | pre-downloading model weights into `server/models/` |

**Things only Oikantik can do — ask, don't work around:** clicking inside LM Studio's GUI (settings that `lms` cannot set), granting Android/iOS permission prompts on a real phone, authoring the Rive file, entering API keys, approving Windows admin prompts, plugging in the laptop, turning on the hotspot.

---

## Part C — Checkpoint 0: inputs to collect (⛔ before any phase)

Ask for these in one message, as a checklist; accept "later" for anything not needed until a later phase.

1. **FlutterFlow project ID** for "Enigma Solved" (from the URL `https://app.flutterflow.io/project/<id>`), or run `flutterflow ai projects --json` after the key is set and offer the match.
2. **FlutterFlow API key** — *not pasted in chat.* Path: Oikantik runs `flutterflow ai` bare in his own terminal once (onboarding wizard, key entered with echo off, cached in `~/.flutterflow/credentials.json`), **or** creates `%USERPROFILE%\.config\flutterflow\claude-env.sh` containing `export FF_API_KEY=…` and `export FLUTTERFLOW_API_TOKEN=…`. Verify only with `[ -n "$FF_API_KEY" ]` after sourcing.
3. **Supabase**: confirm the MCP in `.mcp.json` authenticates (run `list_tables`), and that Oikantik will put `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` into `server/.env` himself (you create `server/.env.example`). `get_project_url` and `get_publishable_keys` give you the first two; the service-role key must be copied from the dashboard by him.
4. **Devices**: is an Android phone available for testing (USB debugging on)? Emulator only otherwise.
5. **Rive**: does a `.riv` interviewer exist? If not, Phase 5A's CustomPaint avatar ships first.
6. **Disk**: which drive holds models (need ~25 GB free)? Default `E:\Enigma for Masai\server\models`.
7. **Demo date** (so the phase plan can be time-boxed) and pressure-dial default (Realistic unless told otherwise).

Record answers in `docs/PROGRESS.md` → "Inputs".

---

## Part D — Repository layout to create

```
E:\Enigma for Masai\
  CLAUDE.md                     # rules + cheat-sheet (Phase 0)
  .mcp.json                     # existing: Supabase MCP (keep); add the FlutterFlow MCP entry if init generates one
  .gitignore                    # server/models/, server/.env, server/data/, app/export/build/, **/.venv/, *.wav
  docs/                         # BLUEPRINT.md, research/, PROGRESS.md, DECISIONS.md, screenshots/, this file
  server/
    pyproject.toml  uv.lock  .env.example  README.md
    server.py                   # FastAPI app, WebSocket /ws, /pair, /health, /report/{id}, /clips/{session}/{idx}.wav
    audio/   vad.py stt.py tts.py visemes.py prosody.py resample.py
    brain/   schemas.py prompts/ rubric.py agenda.py analyzer.py report.py llm.py
    store/   db.py (SQLite) sync.py (Supabase outbox)
    tools/   selftest.py llm_probe.py stt_probe.py tts_probe.py e2e_client.py swap_jd_demo.py bench_latency.py
    static/  test.html pair.html
    fixtures/ jd_fintech.txt jd_edtech.txt sample_answer_*.wav
    tests/   test_rubric_gate.py test_quote_gate.py test_agenda.py test_protocol.py
    models/  (downloaded weights; git-ignored)
    run_demo.bat  firewall.ps1
  app/
    ff-workspace/               # `flutterflow ai init` output (DSL files, .flutterflow/)
    export/                     # `flutterflow export-code` output; built with the Flutter SDK
    assets/interviewer.riv      # when it exists
```

---

## Phase 0 — Environment audit and toolchain

**Goal:** know exactly what is installed, install what is missing, initialise the repo.

1. Audit with one script and paste the table into `docs/PROGRESS.md`: `nvidia-smi` (driver version — need ≥ 546.01 for the "CUDA – Sysmem Fallback Policy" control; note VRAM total), `winget --version`, `git --version`, `python --version` (want 3.12.x), `uv --version`, `lms --version`, `flutter --version`, `dart --version`, `flutterflow --version`, `adb version`, `emulator -list-avds`, `java -version` (17), `espeak-ng --version`, `docker --version` (optional), free space on E: and C:.
2. Install what is missing. Verify each winget ID with `winget search <name>` before installing; if no ID exists, use the official installer and say so. Expected IDs: `ElementLabs.LMStudio`, `astral-sh.uv`, `Python.Python.3.12`, `Git.Git`, `Google.AndroidStudio`, `Microsoft.OpenJDK.17`. Flutter: follow https://docs.flutter.dev/get-started/install/windows (stable channel), then `flutter doctor --android-licenses`. espeak-ng: the `.msi` from https://github.com/espeak-ng/espeak-ng/releases, then add its folder to PATH. FlutterFlow CLI: `dart pub global activate flutterflow_cli` and make sure `%LOCALAPPDATA%\Pub\Cache\bin` is on PATH. ⛔ before Android Studio or Docker (multi-GB).
3. Android SDK: from Android Studio's SDK Manager (or `sdkmanager`) install platform-tools, `platforms;android-35`, `system-images;android-35;google_apis;x86_64`, emulator; enable the Windows Hypervisor Platform feature (or install the Android Emulator Hypervisor Driver) — this needs a reboot/admin prompt, so ⛔.
4. Repo: `git init` (if not already), `.gitignore`, `CLAUDE.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/screenshots/`. Leave the existing `.mcp.json`, `.claude/`, `package.json` alone.
5. Chrome check: call the Claude in Chrome tabs-context tool once; open `https://app.flutterflow.io/project/<id>` and screenshot the current page tree into `docs/screenshots/00-ff-before.png`.

**Acceptance:** every tool in the audit table shows a version; `flutter doctor` has no red items except unrelated ones (note them); repo committed as "Phase 0: toolchain".

---

## Phase 1 — Models: download, configure, measure

**Goal:** every model loaded, running, and measured on this GPU; the VRAM budget proven.

⛔ Before downloading: report free disk space and the download list (Qwen3.5-9B Q6_K 7.46 GB; Gemma 4 12B QAT 6.98 GB fallback — ask whether to download now or later; Parakeet ≈ 1.5 GB; Kokoro ≈ 0.4 GB; Silero ≈ 2 MB).

1. **LM Studio.** `lms get qwen/qwen3.5-9b` and pick the **Q6_K** quant when prompted (if the catalog entry does not offer Q6_K, download `unsloth/Qwen3.5-9B-GGUF` and select `Qwen3.5-9B-Q6_K.gguf`). Then `lms daemon up`, `lms server start --port 1234 --bind 127.0.0.1`, `lms load <model-key> --gpu max --context-length 8192 --identifier interviewer` (run `lms load --help` first and use whatever flags exist for KV-cache quantisation, flash attention, and speculative decoding). For settings the CLI cannot set (thinking OFF, KV cache q8_0, Flash Attention ON, MTP speculative decoding, "limit offload to dedicated GPU memory"), write the exact click path for Oikantik, ask him to do it, and **verify by API**: a `/v1/chat/completions` response must contain no `reasoning_content` and no `<think>` text.
2. **`server/tools/llm_probe.py`** (`uv run`): calls `http://127.0.0.1:1234/v1/chat/completions` with `response_format: {type: "json_schema", …}` using the Stage-A rubric schema from the blueprint on `fixtures/jd_fintech.txt`; asserts the JSON parses; measures TTFT and tok/s with a ~2K-token prompt over 3 runs. Target: ≥ 35 tok/s, TTFT ≤ 400 ms. If below, try UD-Q4_K_XL (5.97 GB) and record both.
3. **Speech stack.** `cd server && uv init --python 3.12` (if not done), then `uv add fastapi "uvicorn[standard]" websockets numpy soundfile rapidfuzz praat-parselmouth qrcode pillow httpx pydantic python-dotenv onnx-asr onnxruntime-gpu nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" kokoro silero-vad supabase pytest` and `uv add torch --index pytorch-cu126=https://download.pytorch.org/whl/cu126` (check `uv add --help` for the current `--index` syntax; `UV_TORCH_BACKEND=auto` is the alternative). `uv tool install "huggingface_hub[cli]"`. Pre-download into `server/models/` with `hf download …`; from then on run everything with `HF_HUB_OFFLINE=1`.
4. **`tts_probe.py`**: Kokoro `KPipeline(lang_code='a')`, voice `af_heart` and one male voice; write `fixtures/sample_answer_1.wav` (a 20-second scripted "candidate answer" so you have test audio); **assert `result.tokens[i].start_ts` is populated**; time to first audio.
5. **`stt_probe.py`**: `onnx-asr` with `nemo-parakeet-tdt-0.6b-v2` on CUDA; transcribe the sample WAV; **check whether word-level timestamps are exposed** (read the onnx-asr README/API). If not: try `parakeet.cpp`'s Windows CUDA release as a subprocess, or fall back to `faster-whisper` `large-v3` int8 with `word_timestamps=True`. Record WER-ish sanity (does it match the script?), latency for the 20 s clip, and which path you chose in `docs/DECISIONS.md`.
6. **`vad_probe.py`**: Silero VAD ONNX on CPU over the sample WAV → speech segments; end-of-speech detection latency with a 700 ms silence rule.
7. **VRAM proof**: with LM Studio loaded and the speech process holding Parakeet + Kokoro, run `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` and Task Manager's "Shared GPU memory" (ask Oikantik to read it, or use `nvidia-smi -q -d MEMORY`). Target: dedicated ≤ 12.5 GB, shared ≈ 0. Ask Oikantik to set NVIDIA Control Panel → Manage 3D Settings → *CUDA – Sysmem Fallback Policy* → **Prefer No Sysmem Fallback** for `python.exe` and LM Studio.
8. **Optional fallbacks now or later**: `lms get google/gemma-4-12b` (QAT Q4_0); `uv add faster-whisper` for the verbatim filler pass; `chatterbox-tts` only if Oikantik wants an Indian-accented voice in v1.

**Acceptance (write the numbers):** LLM tok/s and TTFT; JSON-schema call passes; STT path chosen with word timestamps confirmed; Kokoro token timestamps confirmed; VAD works; dedicated VRAM total; `uv run python tools/selftest.py` (assemble it from the probes: one STT, one TTS, one LLM call, prints tok/s + VRAM, exits non-zero on failure).

---

## Phase 2 — Voice server + interview brain

**Goal:** a browser can hold a full mock interview against the server; two JDs produce visibly different, provenance-linked questions; the report is quote-locked.

1. **Protocol and transport.** Implement `server.py` exactly per BLUEPRINT §4.1: `GET /health`, `GET /pair` (HTML with a QR of `interviewcracker://pair?h=<ip>&p=8765&t=<token>&v=1` plus the plain text), `WS /ws` (JSON control + binary PCM16 frames, 640-byte/20 ms framing at 16 kHz in, 24 kHz out), `GET /report/{session}` (JSON + a minimal HTML view), `GET /clips/{session}/{idx}.wav`. Add `--emulator` (also prints `ws://10.0.2.2:8765` pairing) and `--host/--port` flags. Per-session token check on `hello`. Resample anything that is not 16 kHz mono PCM16 (the web build sends float32 at the OS rate).
2. **Audio pipeline.** Silero VAD → end-of-turn (700 ms silence; hook for Smart Turn later) → STT with word timestamps → prosody features → brain → Kokoro → stream PCM + viseme events (`visemes.py` from Kokoro tokens; RMS fallback for any TTS without timestamps) → `tts_end`. Barge-in: if VAD fires ≥ 350 ms of speech while TTS is playing (Tough mode only), send `interrupt`. Ignore VAD triggers for 600 ms after `tts_end` (echo gate).
3. **Brain** (`brain/`): Stage A rubric + `validate_rubric` substring gate (re-ask once with rejected IDs listed); Stage B Agenda Manager with the coverage matrix and why-trace; Stage C analyzer with RapidFuzz quote gate (`partial_ratio ≥ 90`) and timestamp containment; Stage D report generator that only sees validated JSON; pressure dial table from §5.6. All LLM calls through `llm.py` (OpenAI-compatible client pointed at LM Studio, `response_format` JSON schema, temperature 0.2–0.3 for analysis / 0.6–0.7 for question wording, `max_tokens` capped). Run Stage C for answer *n* concurrently with Stage B for question *n+1*; swap in a follow-up if Stage C demands one.
4. **Store.** SQLite (`store/db.py`): sessions, turns (question JSON, transcript, words, analysis, clip path), reports, `sync_outbox`. Save every answer's PCM as WAV under `server/data/sessions/<id>/`.
5. **Tests.** `tests/test_rubric_gate.py` (paraphrased quote rejected, literal accepted, whitespace/case-normalised match accepted); `tests/test_quote_gate.py`; `tests/test_agenda.py` (least-covered must-have chosen; follow-up after vague; ladder escalates after strong; stops at N); `tests/test_protocol.py` (hello→ready, bad token rejected, ordering of `tts_start`/viseme/`tts_end`). `tools/e2e_client.py`: a fake candidate that connects, streams `fixtures/sample_answer_*.wav` as 20 ms frames on each `question`, and asserts the event sequence for a 4-question Warm-up round; prints per-turn latency (end of audio → `tts_start`). `tools/swap_jd_demo.py`: runs Stage A + first 3 questions for `jd_fintech.txt` and `jd_edtech.txt` and prints a side-by-side of questions and their `jd_quote`s.
6. **Manual client.** `static/test.html`: mic capture (AudioWorklet → PCM16 16 kHz), WebSocket, playback, a mouth-open meter driven by viseme events, and a transcript pane — enough to test barge-in and latency from the laptop's own browser (Claude in Chrome can open it and screenshot it; Oikantik clicks the mic permission).

**Acceptance:** `uv run pytest` green; `e2e_client.py` completes a 4-question round with median latency reported (target ≤ 1.8 s to `tts_start`); `swap_jd_demo.py` output pasted into PROGRESS.md; a manual round in `test.html` with barge-in working; `/report/<id>` shows quotes + timestamps that all exist in the transcript.

---

## Phase 3 — Supabase: schema, security, sync

**Goal:** identity, JD library, sessions and reports persist to Supabase when online; the live loop never depends on it.

1. **Inspect** with the Supabase MCP: `list_tables`, `get_project_url`, `get_publishable_keys`. Write `server/.env.example` (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SESSION_TOKEN_SECRET`, `LMSTUDIO_URL=http://127.0.0.1:1234/v1`, `MODELS_DIR`, `SUPABASE_MODE=cloud|selfhosted|off`).
2. **Schema** (one migration file you also save under `server/supabase/migrations/`): `profiles` (id uuid pk → auth.users, display_name, l1_language, created_at); `jds` (id, user_id, title, raw_text, rubric jsonb, created_at); `sessions` (id, user_id, jd_id, pressure text, status text, started_at, ended_at, device_info jsonb, server_version text); `turns` (id, session_id, idx int, question jsonb, transcript text, words jsonb, analysis jsonb, clip_path text, started_at, ended_at); `reports` (id, session_id unique, report jsonb, created_at). Indexes on `(user_id, created_at)` and `(session_id, idx)`. **RLS on every table: owner-only** (`auth.uid() = user_id`, via join for turns/reports). Storage bucket `clips` (private) with paths `<user_id>/<session_id>/<idx>.wav` and an owner-only policy. Support **guest sessions**: `user_id` nullable + `device_id text` so an offline demo session can be claimed later. ⛔ Show the SQL; apply with `apply_migration` only after "go"; then run `get_advisors` (security) and fix what it flags.
3. **Server sync** (`store/sync.py`): `supabase-py` with the service-role key; an outbox worker that flushes sessions/turns/reports and uploads clips when `httpx.head(SUPABASE_URL)` succeeds; exponential backoff; never on the request path. `SUPABASE_MODE=off` disables it entirely (used in airplane-mode rehearsals).
4. **FlutterFlow side** (Chrome extension or Oikantik): Settings → Integrations → Supabase → refresh/fetch schema so the tables appear as FlutterFlow Supabase tables; Authentication → enable Supabase auth (email/password, plus **"Continue as guest"** as the default path so the app works with no internet). Screenshot both into `docs/screenshots/`.
5. **Phase 3B (optional, only if Oikantik wants Supabase itself to work with zero internet):** `scoop install supabase` (or the Windows installer), `supabase init && supabase start` in `server/supabase/` (Docker Desktop required), expose port 54321 on the LAN, apply the same migration, and switch the FlutterFlow project to **"Connect to Self-Hosted Supabase"** with `http://<laptop-ip>:54321` + the local anon key for the demo build. Keep a note of how to switch back to cloud.

**Acceptance:** tables and policies visible via `list_tables`/`execute_sql`; `get_advisors` clean; a completed local session appears in Supabase within a minute of the laptop going online (prove with `execute_sql`); FlutterFlow shows the tables; guest mode confirmed.

---

## Phase 4 — FlutterFlow app via `flutterflow ai`

**Goal:** the phone app exists in the live FlutterFlow project, exports, builds, and talks to the server.

1. **Preflight** (key rules in Part A apply): `flutterflow --version`; source the env file if present; `[ -n "$FF_API_KEY" ] && echo key: ok`. If no key, ask Oikantik to run the `flutterflow ai` onboarding wizard in his own terminal (echo-off prompt) — never in chat. Then `cd app && flutterflow ai init ff-workspace --project <id>` and `cd ff-workspace`. Run `flutterflow ai upgrade --check`, `flutterflow ai doctor`, `flutterflow ai context-check` (refresh if STALE).
2. **Orient**: `flutterflow ai status <id>`, `flutterflow ai resources <id>`, `flutterflow ai inspect <id> --outline`; `flutterflow ai docs` for the DSL (pages, app state, custom actions/widgets/code files, dependencies, API endpoints). Save intent with `flutterflow ai plan save --content "<what you will build>"`.
3. **Author → validate → run**, one DSL file per concern, always `validate` first and show the output, then `run --commit-message "…"`. ⛔ before the **first** `run` (confirm the target project and branch; create a branch `interview-cracker` with `flutterflow ai branch create … --checkout` so `main` stays clean). Build, in this order:
   - **App State**: `serverHost`, `serverPort`, `sessionToken`, `connectionState`, `pressureDial`, `voiceId`, `jdText`, `currentQuestion` (JSON), `lastReaction`, `mood`, `isListening`, `countdownSeconds`, `reportJson`, `isGuest`.
   - **Dependencies** (pin per the exported `pubspec.yaml`'s Dart SDK — check it before choosing): `record` `^6.2.1` (or `^7.1.1` only if Dart ≥ 3.12), `web_socket_channel` `^3.0.3`, `flutter_soloud` `^5.0.0` (fall back to `^4.x` on problems), `audio_session` `^0.2.4`, `mobile_scanner` `^7.4.0`, `rive` `^0.14.11` (only when the `.riv` exists — see Phase 5), `rapidfuzz`-style matching is server-side so nothing needed here.
   - **Code file** `VoiceLink` (singleton: WebSocket, `AudioRecorder` stream → 640-byte frames, `SoLoud` buffer stream at 24 kHz, broadcast `Stream<VoiceEvent>`, viseme scheduler against the playback clock, reconnect with backoff).
   - **Custom actions**: `connectVoice(host, port, token, mode)`, `disconnectVoice()`, `startTurn()`, `stopTurn()`, `fetchReport(sessionId)`; each updates App State at low frequency only.
   - **Custom widgets**: `InterviewerAvatar(width, height)` (Phase 5A CustomPaint first), `PairScanner(width, height, onPaired)`, `TranscriptTicker(width, height)`, `CountdownRing(width, height)`.
   - **Pages** per BLUEPRINT §7.1: `PasteJD`, `Pair`, `Prep`, `Room` (no AppBar back button; Android back disabled while a round is live), `Report`, `History` (Supabase-backed list, hidden in guest mode). Add the "why I asked this" flip on the question card.
   - **Configuration files** (FlutterFlow UI → Settings → Configuration Files; do it via Chrome or ask Oikantik): `AndroidManifest.xml` → `android:usesCleartextTraffic="true"`, permissions `RECORD_AUDIO`, `INTERNET`, `CAMERA`; `Info.plist` → microphone, camera, `NSLocalNetworkUsageDescription`, `NSAppTransportSecurity/NSAllowsLocalNetworking`; `build.gradle` → `minSdkVersion 24`. Also set the Supabase URL/anon key (already connected) and confirm the project's Flutter version in General Settings.
4. **Verify in Chrome after each `run`**: open the project, confirm the page/component appears in the tree, open **Test Mode** for the UI-only pages (`PasteJD`, `Prep`, `Report` with a mock `reportJson`) — audio and native plugins do not work in Test Mode, so do not test them there. Screenshot to `docs/screenshots/04-*.png`.
5. **Export and build**: source the env file (`FLUTTERFLOW_API_TOKEN` is read by the classic CLI — never pass `--token` on the command line), then `flutterflow export-code --project <id> --branch-name interview-cracker --dest app/export --include-assets`. `cd app/export && flutter pub get && flutter analyze && flutter build apk --debug`. Fix dependency conflicts by adjusting the DSL dependency versions and re-exporting (keep a `.flutterflowignore` for local-only files). ⛔ if you need a paid-plan feature (code export/Local Run) that the account does not have — report it rather than trying workarounds.

**Acceptance:** `flutterflow ai history` shows your runs; page tree screenshot; `flutter build apk --debug` succeeds; the APK installs on the emulator (Phase 6) and reaches the `Pair` page.

---

## Phase 5 — The interviewer on screen

**Goal:** a visible, lip-synced, reacting interviewer, without ever blocking on artwork.

**5A — CustomPaint avatar (do this first, ~half a day).** Implement `InterviewerAvatar` as a Flutter `CustomPainter`: head, hair block, eyes with a blink timer, brows (mood-driven angle), and a mouth drawn from **ten path shapes** matching BLUEPRINT §6.1 (0 rest, 1 M/B/P, 2 F/V, 3 TH, 4 L, 5 teeth, 6 R, 7 Ah, 8 Ee, 9 Oh/Oo). Inputs mirror the Rive contract exactly (`mouth` 0–9, `mood` 0–3, `listening`, `nod`) so swapping to Rive later is a one-file change. Drive `mouth` from `VoiceLink` viseme events at ≥ 25 Hz using the playback clock; drive `mood`/`nod`/`listening` from `reaction` and `vad` events. Style it stylised, warm, shoulders-up.

**5B — Rive (when the `.riv` exists).** Ask Oikantik to author or adapt the marketplace "Custom Talking Avatar: Real-Time Lip Sync" file with the four inputs named exactly `mouth`, `mood`, `listening`, `nod`. Add `rive ^0.14.11` via DSL, `await RiveNative.init()` once, load the artboard, set inputs through `controller.stateMachine.number('mouth').value = …`. Check the exported `pubspec.yaml` for a FlutterFlow-pinned `rive` version conflict and, if present, remove any built-in Rive widgets from the project or match the pinned version's API. Keep 5A as the fallback when the asset fails to load.

**Acceptance:** side-by-side video/GIF (emulator screen recording via `adb shell screenrecord`) of the avatar speaking a Kokoro sentence with the mouth in sync at arm's length; `thinking` mood visible between end-of-answer and `tts_start`.

---

## Phase 6 — Testing: automated, emulator, phone, Chrome

**6.1 Automated (every phase, not just now).** `uv run pytest`; `uv run python tools/e2e_client.py --questions 4 --pressure realistic` prints per-turn latency and asserts the event sequence; `tools/bench_latency.py` runs 10 turns and writes p50/p95 to PROGRESS.md.

**6.2 Android emulator.**
- Create the AVD once: `avdmanager create avd -n pixel8 -k "system-images;android-35;google_apis;x86_64" -d pixel_8`; start with `emulator -avd pixel8 -no-snapshot-load`; wait for `adb wait-for-device`.
- **Microphone:** in the emulator's Extended Controls (⋯) → Microphone, enable **"Virtual microphone uses host audio input"** (GUI — ask Oikantik if you cannot toggle it). Speaker output goes to the laptop speakers, so use the laptop's headset to avoid echo during barge-in tests.
- **Networking:** the emulator reaches the laptop at **`10.0.2.2`**. Start the server with `--emulator`; in the app use manual pairing `10.0.2.2:8765:<token>` (QR scanning inside an emulator is unreliable). Cleartext must be allowed (Phase 4 manifest change).
- Run: `cd app/export && flutter run -d emulator-5554` (or `flutter install` the APK). Walk the full flow: PasteJD (use `fixtures/jd_fintech.txt`) → Pair → Prep → Room (speak 4 answers into the laptop mic; include one deliberately vague answer to trigger a follow-up) → Report (tap a quote → clip plays). Capture `adb logcat -s flutter` to `docs/logs/`, screenshots with `adb exec-out screencap -p > docs/screenshots/06-room.png`, and a 30 s `adb shell screenrecord` of the avatar.
- Check `flutter run` console for dropped frames while the avatar animates (target: no jank at 60 fps on x86_64 emulator with GPU acceleration).

**6.3 Physical Android phone (if available).** Enable USB debugging; `adb reverse tcp:8765 tcp:8765` → pair with `127.0.0.1:8765:<token>`; then repeat over the laptop hotspot with the QR (`/pair`). Verify Android's "no internet — stay connected" prompt is accepted and the app still reaches the server with mobile data off. Measure Wi-Fi RTT with the server's `ping` frame.

**6.4 Claude in Chrome.** Use the browser tools to: (a) open `http://localhost:8765/pair` and `http://localhost:8765/health` and screenshot; (b) open `http://localhost:8765/static/test.html`, ask Oikantik to click "Allow" on the mic prompt, then drive one round (you read the transcript pane and viseme meter via the page text/DOM); (c) open the FlutterFlow project and Test Mode to check every UI-only page renders with mock data and the `Room` page has no back button; (d) open `http://localhost:8765/report/<session>` and verify each quote's timestamp exists in the transcript JSON; (e) optionally build the web target — `flutter run -d chrome --web-port 7357` — and drive the UI in Chrome (mic works in Chrome; `flutter_soloud` web setup may need its extra step; treat failures here as non-blocking since the phone is the target).

**6.5 Judging-criteria regression list** (keep in `docs/TESTPLAN.md`, tick per run): C1 swap-the-JD produces different question sets with valid why-traces; C2 avatar speaks/reacts, audio audible, mouth in sync; C3 no back/skip/preview, countdown enforced, Tough-mode interruption fires on time-out; C4 report has ≥ 3 quote-anchored findings, all quotes verifiable, tap-to-replay works, coverage matrix shows empty must-have rows when appropriate; **offline**: run a complete round with the laptop's Wi-Fi disconnected and the phone in airplane mode + Wi-Fi.

---

## Phase 7 — Demo hardening

1. `server/run_demo.bat` per BLUEPRINT §8.3 (`HF_HUB_OFFLINE=1`, `lms daemon up`, `lms server start`, `lms load`, `selftest.py` gate, `server.py --host 0.0.0.0`) and `server/firewall.ps1` (`New-NetFirewallRule … -LocalPort 8765 -Program <venv python> -Profile Private,Public`). ⛔ admin rights for the firewall rule; ask Oikantik to run it.
2. Ask Oikantik to: set the NVIDIA sysmem fallback policy; disable hotspot Power saving (or registry `PeerlessTimeoutEnabled=0`); disable sleep on AC; rehearse the hotspot bootstrap three times (connect laptop to any network → start Mobile Hotspot → disconnect upstream → hotspot stays at 192.168.137.1).
3. Prepare two contrasting JDs and the 4-minute demo script (BLUEPRINT §10) as `docs/DEMO.md` with the fallback ladder printed at the bottom (`adb reverse` → phone-as-hotspot → travel router).
4. Run the full offline rehearsal end-to-end and record: cold start time, tok/s, p50 latency, VRAM, any warning in the logs. Tag the repo `demo-rc1`.

---

## Definition of done

All Acceptance blocks filled with real numbers in `docs/PROGRESS.md`; `pytest` and `e2e_client.py` green; an APK that pairs and completes a Realistic round on the emulator **and** (if available) a phone over the hotspot; the Supabase project shows synced sessions; `run_demo.bat` boots from cold to READY without manual steps other than the hotspot; `docs/DEMO.md` written; every UNVERIFIED item listed in the final report with what would verify it.

**Final report format (chat):** ten lines max — what works, measured numbers (tok/s, TTFT, p50/p95 latency, VRAM), what is UNVERIFIED, top 3 risks for demo day, and the exact command Oikantik runs to start everything.

---

## Add-on A — Lottie micro-animations (paste any time after Phase 4 starts)

```
Add-on — Lottie micro-animations. Use LottieFiles for icons and state cues in the FlutterFlow app; keep Rive/CustomPaint for the interviewer avatar only. Source animations through the LottieFiles MCP if it's configured (searchPublicAnimations → pick → publicAnimation for the file URL and license), otherwise browse lottiefiles.com with the Chrome tools. Only free assets under the Lottie Simple License; log URL, author and license for each in docs/ASSETS.md. Needed set (one consistent flat style, recoloured to the app palette, ≤100 KB each, prefer .lottie): mic idle pulse, listening waveform, thinking dots, speaking indicator, countdown warning, QR-scan/pairing, connected check, offline/no-network, empty history, report success. Add them as assets and use FlutterFlow's native Lottie widget (asset source, loop/play/pause bound to App State: connectionState, isListening, mood). Rules: no decorative motion in the Room page beyond the current state cue, respect the OS reduced-motion setting, never let an animation block or delay the voice pipeline. Verify each placement in FlutterFlow Test Mode via Chrome and screenshot to docs/screenshots/lottie-*.png. Validate the DSL before running it, as always.
```

## Appendix A — Command cheat-sheet (also goes into `CLAUDE.md`)

```powershell
# LM Studio
lms daemon up ; lms server start --port 1234 --bind 127.0.0.1
lms ls ; lms ps ; lms load <model-key> --gpu max --context-length 8192 --identifier interviewer ; lms unload --all
curl http://127.0.0.1:1234/v1/models

# Server
cd "E:\Enigma for Masai\server" ; uv sync
$env:HF_HUB_OFFLINE=1 ; uv run python tools/selftest.py
uv run python server.py --host 0.0.0.0 --port 8765 --emulator
uv run pytest ; uv run python tools/e2e_client.py --questions 4
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# FlutterFlow (Git Bash)
flutterflow ai status <id> ; flutterflow ai inspect <id> --outline ; flutterflow ai docs
flutterflow ai validate pages/room.dart && flutterflow ai run pages/room.dart --commit-message "Room page"
flutterflow export-code --project <id> --branch-name interview-cracker --dest ../export --include-assets

# Flutter / Android
flutter doctor ; emulator -avd pixel8 ; adb devices
cd "E:\Enigma for Masai\app\export" ; flutter pub get ; flutter run -d emulator-5554
adb reverse tcp:8765 tcp:8765 ; adb logcat -s flutter ; adb exec-out screencap -p > shot.png
```

## Appendix B — Ports, hosts, env

| Item | Value |
|---|---|
| LM Studio API | `http://127.0.0.1:1234/v1` (never bind beyond localhost) |
| Voice server | `0.0.0.0:8765` — WS `/ws`, HTTP `/pair`, `/health`, `/report/{id}`, `/clips/…`, `/static/test.html` |
| Emulator → laptop | `10.0.2.2:8765` |
| Phone via USB | `adb reverse tcp:8765 tcp:8765` → `127.0.0.1:8765` |
| Phone via hotspot | `192.168.137.1:8765` (Windows Mobile Hotspot default) |
| Supabase (cloud) | `SUPABASE_URL`, `SUPABASE_ANON_KEY` (app), `SUPABASE_SERVICE_ROLE_KEY` (server only, `.env`) |
| Supabase (self-hosted, optional) | `http://<laptop-ip>:54321` |
| Model dir | `E:\Enigma for Masai\server\models` with `HF_HUB_OFFLINE=1` at run time |

## Appendix C — Where the details live

Wire protocol → BLUEPRINT §4.1 · state machine → §4.2 · rubric/question/analysis/report schemas and gates → §5 · avatar inputs and viseme map → §6 · pages, packages, config files → §7 · server layout, install, `run_demo.bat`, hotspot → §8 · build order → §9 · demo script → §10 · risks → §11 · FlutterFlow custom-code limits, Android/iOS networking, GPU sharing → `research/05` · model sizes and LM Studio/Ollama comparison → `research/01` · STT/TTS tables → `research/02` · interview-brain research and competitor gap → `research/04`.
