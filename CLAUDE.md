# Enigma for Masai — Interview Cracker

Build lead rules for Claude Code in this repo. The design is `docs/BLUEPRINT.md`; the phase plan is `docs/CLAUDE_CODE_MASTER_PROMPT.md`; the evidence is `docs/research/01–05`. Progress and measurements go to `docs/PROGRESS.md`; every decision goes to `docs/DECISIONS.md` (one line: date · decision · why). Never edit `docs/BLUEPRINT.md` or `docs/research/` — append corrections to `docs/DECISIONS.md`.

## Non-negotiables

- **Local at runtime.** No cloud AI API (LLM, STT, TTS, embeddings) is called during an interview. Supabase is touched only by a background sync that tolerates being offline.
- **Evidence-locked.** Every rubric competency quotes a literal JD substring; every report claim fuzzy-matches the transcript with timestamps. Enforced in code (`server/brain/rubric.py`, `server/brain/analyzer.py`), not in prompts.
- **Secrets never enter the chat.** FlutterFlow API key, Supabase service-role key, tokens live in env files / the FlutterFlow credential cache. Never `cat` a secrets file, never put a key on a command line, never ask for a key to be pasted. Debug with presence checks only: `[ -n "$FF_API_KEY" ]`.
- **Verify, don't assume.** Every "done" is backed by a command output, a test, a screenshot in `docs/screenshots/`, or a measured number in `docs/PROGRESS.md`. Anything unverifiable is written as UNVERIFIED.
- **Ask before spending** (⛔): downloads > 1 GB, multi-GB installs, migrations to the cloud Supabase project, `flutterflow ai run` against the live project, admin-level Windows changes. (Oikantik pre-approved these for the 2026-09-05 run; each one is still logged in `docs/DECISIONS.md` and kept reversible.)
- **Windows reality.** Bash tool = Git Bash; use `powershell.exe -NoProfile -Command "..."` for winget, firewall, registry, services. Quote paths with spaces. Prefer `uv run` over activating venvs.

## Fixed choices (do not relitigate without asking)

| Layer | Choice | Fallback |
|---|---|---|
| LLM | `Qwen3.5-9B` Q6_K GGUF in LM Studio, thinking OFF, MTP speculative decoding, 8K ctx, JSON-schema output | `google/gemma-4-12B-it-qat-q4_0-gguf`; Ollama runtime |
| STT | `nvidia/parakeet-tdt-0.6b-v2` via `onnx-asr` (word timestamps) | `faster-whisper large-v3` int8 `word_timestamps=True`; `parakeet.cpp` |
| TTS | `hexgrad/Kokoro-82M` via `kokoro` + espeak-ng (per-token `start_ts/end_ts`) | `ResembleAI/chatterbox-turbo` + RMS mouth fallback |
| VAD / end-of-turn | Silero VAD v6 ONNX on CPU + 700 ms silence (v1); Smart Turn v3.1 (v2) | — |
| Server | Python 3.12, `uv`, FastAPI + `websockets`, SQLite, one process for all GPU speech models | — |
| App | FlutterFlow project **Enigma Solved** (`enigma-solved-ctlkqt`) via `flutterflow ai` DSL + custom code; export + `flutter build` | — |
| Avatar | Rive state machine (`mouth`, `mood`, `listening`, `nod`) | `CustomPaint` avatar (Phase 5A) — ships first |
| Data | Supabase cloud project **Enigma for Masai** (`reqleijouyejjzstyjeq`, ap-northeast-1) via Supabase MCP + `supabase-py` | Self-hosted Supabase in Docker (Phase 3B, optional) |
| Micro-animations | LottieFiles (Lottie Simple License only), FlutterFlow native Lottie widget, logged in `docs/ASSETS.md` | — |

## Repository layout

```
CLAUDE.md  .mcp.json  .gitignore  LICENSE  package.json (pre-existing, leave alone)
docs/        BLUEPRINT.md  CLAUDE_CODE_MASTER_PROMPT.md  PROGRESS.md  DECISIONS.md  ASSETS.md  TESTPLAN.md  DEMO.md  research/  screenshots/  logs/
server/      pyproject.toml  uv.lock  .env.example  README.md  server.py
             audio/  brain/  store/  tools/  static/  fixtures/  tests/  supabase/migrations/  models/ (git-ignored)
             run_demo.bat  firewall.ps1
app/         ff-workspace/ (flutterflow ai init)   export/ (flutterflow export-code)   assets/interviewer.riv (when it exists)
```

## Machine facts (audited 2026-09-05)

- GPU: RTX 4090 Laptop 16376 MiB, driver 616.56. RAM 31.6 GB. Windows 11 Pro 26200. Hypervisor present (Docker Desktop).
- LM Studio 0.4.23 at `%LOCALAPPDATA%\Programs\LM Studio`; `lms` at `~\.lmstudio\bin\lms.exe`.
- Flutter 3.47.2 stable (Dart 3.13.2) at `C:\dev\flutter`; standalone Dart 3.13.3 at `C:\tools\dart-sdk`; `flutterflow_cli` 0.0.39 in `%LOCALAPPDATA%\Pub\Cache\bin`.
- Android SDK at `%LOCALAPPDATA%\Android\Sdk` (`ANDROID_HOME`, cmdline-tools + platform-tools + emulator); adb 37.0.1 also via winget.
- JDK 17 at `C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot` (bound with `flutter config --jdk-dir`); `JAVA_HOME` stays on Temurin JDK 25.
- espeak-ng 1.52.0 at `C:\Program Files\eSpeak NG`. uv 0.11.21. Python 3.12.10 (store) available to uv. Docker 29.0.1.
- Models dir: `E:\Enigma for Masai\server\models` (E: had 120 GB free). Run with `HF_HUB_OFFLINE=1` after Phase 1.

## Command cheat-sheet

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

# FlutterFlow (Git Bash; source ~/.config/flutterflow/claude-env.sh first if present)
flutterflow ai status enigma-solved-ctlkqt ; flutterflow ai inspect enigma-solved-ctlkqt --outline ; flutterflow ai docs
flutterflow ai validate pages/room.dart && flutterflow ai run pages/room.dart --commit-message "Room page"
flutterflow export-code --project enigma-solved-ctlkqt --branch-name interview-cracker --dest ../export --include-assets

# Flutter / Android
flutter doctor ; emulator -avd pixel8 ; adb devices
cd "E:\Enigma for Masai\app\export" ; flutter pub get ; flutter run -d emulator-5554
adb reverse tcp:8765 tcp:8765 ; adb logcat -s flutter ; adb exec-out screencap -p > shot.png
```

## Ports, hosts, env

| Item | Value |
|---|---|
| LM Studio API | `http://127.0.0.1:1234/v1` (never bind beyond localhost) |
| Voice server | `0.0.0.0:8765` — WS `/ws`, HTTP `/pair`, `/health`, `/report/{id}`, `/clips/…`, `/static/test.html` |
| Emulator → laptop | `10.0.2.2:8765` |
| Phone via USB | `adb reverse tcp:8765 tcp:8765` → `127.0.0.1:8765` |
| Phone via hotspot | `192.168.137.1:8765` |
| Supabase (cloud) | `SUPABASE_URL`, `SUPABASE_ANON_KEY` (app), `SUPABASE_SERVICE_ROLE_KEY` (server only, `server/.env`) |
| Supabase (self-hosted, optional) | `http://<laptop-ip>:54321` |

## Working loop for every phase

(a) read the relevant blueprint sections; (b) write a 5–10 line plan into `docs/PROGRESS.md` under the phase heading; (c) execute step by step, running the verification command after each step; (d) fill the phase's Acceptance checklist with actual outputs/numbers; (e) summarise in chat in ≤ 10 lines.
