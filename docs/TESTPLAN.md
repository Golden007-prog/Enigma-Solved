# Judging-criteria regression list (master prompt Phase 6.5) — tick per run

Run date: ______  Build: ______  Tester: ______

## Automated (every phase)
- [ ] `cd server && uv run pytest` → 291 passed
- [ ] `uv run python tools/selftest.py` → READY, exit 0 (records tok/s, VRAM)
- [ ] `uv run python tools/e2e_client.py --questions 4 --pressure realistic` → OK, ordering check passes, report fetched, all fix quotes grounded
- [ ] `uv run python tools/swap_jd_demo.py` → 0 identical questions across JD-A / JD-B, every why-trace quote grounded

## C1 — questions clearly derived from the JD
- [ ] Paste JD-A → competency chips on Prep match JD-A's sentences (spot-check 3)
- [ ] Tap the question card → the JD sentence shown is a literal substring of the pasted JD
- [ ] Swap to JD-B (same title) → different chips, different Q1, different why-trace quote
- [ ] A follow-up's why-trace shows the candidate's own quote + timestamp

## C2 — a visible, audible interviewer
- [ ] Audio audible on the phone (24 kHz PCM via SoLoud); no clipping/stutter
- [ ] Mouth moves in sync at arm's length (ten shapes, playback-clock scheduling)
- [ ] `listening` state while the candidate speaks; `thinking` between answer end and next question; `interested` + nod after a strong answer
- [ ] Blink and idle motion present; no motion when idle except blink

## C3 — pressure
- [ ] Room has no AppBar back button; Android back does nothing while a round is live (FlutterFlow page setting "Disable Android Back Button" — set in the UI)
- [ ] No skip, no preview: Prep shows competencies only
- [ ] Countdown ring visible in Realistic/Tough; Warm-up shows none
- [ ] Tough: talking past the timer → "Let me stop you there." + interrupt; barge-in while the interviewer speaks cuts the audio
- [ ] Vague answer → dig_deeper follow-up; "we"-heavy answer → ownership probe; missing result → quantify_result

## C4 — a real result
- [ ] Report has ≥ 3 findings, every quote exists verbatim (fuzzy ≥ 90) in the transcript with a timestamp
- [ ] Tap a quote → the clip plays from that timestamp (`/clips/<session>/<idx>.wav`)
- [ ] Coverage matrix shows empty must-have rows when they were not covered
- [ ] Band + one mover (no score out of ten)

## Offline
- [ ] Laptop Wi-Fi disconnected (hotspot only), phone in airplane mode + Wi-Fi → full round completes
- [ ] `/health` shows `sync.mode = off` or `online = false`; no request leaves the laptop (check `netstat` if in doubt)

## Numbers to record
| Metric | Target | Measured |
|---|---|---|
| LLM tok/s (selftest) | ≥ 35 | |
| Answer end → tts_start p50 / p95 (e2e) | ≤ 1.8 s | |
| STT latency for a 20 s answer | ≤ 0.5 s | |
| Dedicated VRAM, all models loaded | ≤ 12.5 GB (+ desktop baseline) | |
| Shared GPU memory | ≈ 0 | |
