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
