# Interview Cracker — 4-minute demo script (BLUEPRINT §10)

**Before the day (with internet):** `cd server && uv sync`, `uv run python tools/selftest.py` → READY; export + install the APK (`app/export`, see PROGRESS Phase 4); run `firewall.ps1` as admin once; NVIDIA Control Panel → CUDA – Sysmem Fallback Policy → *Prefer No Sysmem Fallback* for `python.exe` and LM Studio; Settings → Mobile hotspot → Power saving OFF; disable sleep on AC. Rehearse the hotspot bootstrap three times: connect the laptop to any network → turn on Mobile Hotspot → disconnect the upstream → hotspot stays on 192.168.137.1. Pre-approve the phone's mic/camera prompts and Android's "no internet — stay connected" once.

**On the day (no internet anywhere):** laptop on AC; hotspot up via the bootstrap; double-click `server\run_demo.bat`; wait for `LLM 5x tok/s · VRAM 13.x GB · READY`; the pair page opens. Phone: airplane mode ON → Wi-Fi ON → join the laptop SSID → "Stay connected" → open Interview Cracker.

| t | Criterion | What to do | What the judges see |
|---|---|---|---|
| 0:00 | setup | Show the laptop's Wi-Fi says "no internet" and the phone is in airplane mode. `run_demo.bat` is already at READY. | The self-test line: tok/s + VRAM, nothing in the cloud. |
| 0:30 | **1 — JD-grounded** | Paste **JD-A** (`server/fixtures/jd_fintech.txt`, fintech backend). Pick *Realistic*. Start → Pair (scan QR) → Prep. | Prep shows the competency chips extracted from *this* JD (no questions). |
| 0:50 | 1 | First question arrives. **Tap the card** → it flips to the why-trace: the literal JD sentence highlighted, competency, rung, strategy. | Provenance is a string match, not a prompt promise. |
| 1:30 | **2 & 3 — visible interviewer, pressure** | Answer Q1 vaguely on purpose: *"we used caching and stuff to make it faster"*. | Avatar: listening → thinking → follow-up quotes your words: "You mentioned using caching…". Countdown ring runs; no back button, no skip. |
| 2:10 | 3 | Answer Q2 well (name Redis, a TTL, a number). | Avatar goes *interested* + nod; next question escalates a rung. In *Tough*, run past the timer once → "Let me stop you there." |
| 3:00 | **4 — real result** | Tap *End round early* after 3–4 answers. | Report: band + one mover; **Top fix #1 quotes your own words with a timestamp — tap ▶ to hear yourself say it**; STAR strip per answer; coverage matrix with empty must-have rows. |
| 3:30 | 1 again | On the laptop's browser test page (`/static/test.html`) paste **JD-B** (`jd_edtech.txt`, same title) → Start. | Different chips, different first question and a different JD sentence in the why-trace. `tools/swap_jd_demo.py` prints both side by side if the phone is busy. |
| 3:45 | close | *"This JD and this voice never left the laptop. It costs nothing per interview, and the speech model understands Indian English better than Azure does (Open ASR Leaderboard en-IN 3.89 vs 4.40)."* | |

## Fallback ladder (top to bottom)

1. Phone can't reach the laptop → **USB**: `adb reverse tcp:8765 tcp:8765` on the laptop, pair with `127.0.0.1:8765:<token>` (token is printed by the server and shown on `/pair`).
2. Hotspot refuses to start → make the **phone** the hotspot, join it from the laptop, restart `run_demo.bat` (it re-prints the new IP + QR).
3. Still nothing → the **browser test page** on the laptop (`http://localhost:8765/static/test.html`) runs the full loop with the laptop mic: the pipeline is the same, only the puppet is a mouth meter.
4. Travel router with no WAN (₹1,500) — the boring, reliable option.

Emulator instead of a phone: start `emulator -avd pixel8`, pair with `10.0.2.2:8765:<token>` (the server prints this line with `--emulator`), enable *Virtual microphone uses host audio input* in Extended Controls → Microphone.

## Numbers to say out loud (measured 2026-09-05 on this laptop)

LLM 59 tok/s, TTFT 104 ms (Qwen3.5-9B Q6_K) · STT 215–323 ms for a 20 s answer (Parakeet fp16 CUDA) · TTS first audio ~0.2 s (Kokoro) · everything resident in **≈ 11.3 GB VRAM** · 291 unit tests · every report quote fuzzy-matched to the transcript (≥ 90) or dropped by code.
