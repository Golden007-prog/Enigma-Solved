# Assets - Lottie micro-animations (master prompt Add-on A)

Sourced 2026-09-05 through the LottieFiles public GraphQL API (`graphql.lottiefiles.com/2022-08`, the surface the LottieFiles MCP wraps; the MCP endpoint itself returned 404 in this session). Only free public animations under the **Lottie Simple License** (https://lottiefiles.com/page/license), each <= 100 KB, recoloured to the app palette by `app/tools/lottie_fetch.py` (fills/strokes -> theme colour, motion untouched). Files live in `app/assets/lottie/`; they are embedded in the FlutterFlow custom widget `StateCue` so the app never fetches a network URL at runtime (offline demo).

| Cue | File (palette role) | Used on | Source | Author | Size | License |
|---|---|---|---|---|---|---|
| `mic_idle` | `app/assets/lottie/mic_idle.json` (primary) | Room - idle (not listening, not speaking) | [mic_on](https://lottiefiles.com/animations/mic-on-vX5uqF4NOg) | jzyquumjhp | 20.7 KB | Lottie Simple License |
| `listening_wave` | `app/assets/lottie/listening_wave.json` (primary) | Room - isListening | [voice](https://lottiefiles.com/animations/voice-XqGAJYnkFm) | 8f5ufqi7fl1enskt | 12.4 KB | Lottie Simple License |
| `thinking_dots` | `app/assets/lottie/thinking_dots.json` (secondary) | Room - thinking (answer end -> tts_start) | [loading dots](https://lottiefiles.com/animations/loading-dots-zjFgEqTaJW) | wdcwjqsa5c19xf06 | 7.5 KB | Lottie Simple License |
| `speaking` | `app/assets/lottie/speaking.json` (tertiary) | Room - isSpeaking | [speaker](https://lottiefiles.com/animations/speaker-F0BShEsQyS) | fkper7rap6fois3u | 26.1 KB | Lottie Simple License |
| `countdown_warning` | `app/assets/lottie/countdown_warning.json` (warning) | Room - countdownSeconds <= 10 | [warning](https://lottiefiles.com/animations/warning-6Hz20v0HcO) | o2o6mzg5m2f2xmqz | 6.4 KB | Lottie Simple License |
| `qr_scan` | `app/assets/lottie/qr_scan.json` (secondary) | Pair - while scanning | [QR Scan](https://lottiefiles.com/animations/qr-scan-sWvkVj0N5q) | zdwne3dx2v94m1qu | 39.8 KB | Lottie Simple License |
| `connected_check` | `app/assets/lottie/connected_check.json` (success) | Pair - connectionState == connected | [Success](https://lottiefiles.com/animations/success-5ZYxkCGG6h) | nwuiosky9p | 4.8 KB | Lottie Simple License |
| `offline` | `app/assets/lottie/offline.json` (error) | Pair/Room - connectionState == disconnected/error | [no internet](https://lottiefiles.com/animations/no-internet-jzg0A6Bb2h) | tkxrwmpbja | 28.8 KB | Lottie Simple License |
| `empty_history` | `app/assets/lottie/empty_history.json` (secondary) | History - no sessions | [empty](https://lottiefiles.com/animations/empty-6eKau18esg) | otq1xzry2d | 57.2 KB | Lottie Simple License |
| `report_success` | `app/assets/lottie/report_success.json` (success) | Report - when the report arrives | [Confetti](https://lottiefiles.com/animations/confetti-VZJq53kChU) | ezypto9bou | 26.7 KB | Lottie Simple License |

Rules applied: one cue at a time in the Room (no decorative motion), animations frozen when the OS reduced-motion setting is on (`MediaQuery.disableAnimations`), and the cue widget never touches the voice pipeline (pure UI driven by App State).
