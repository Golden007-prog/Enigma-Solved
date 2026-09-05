
# FlutterFlow phone ↔ Windows/RTX-4090 local voice-AI stack — research report (Sept 5, 2026)

Research budget note: the web-search budget ran out mid-task; everything below after the first ~25 searches was gathered by direct fetches of known documentation URLs and Hugging Face listings. Anything I could not confirm is marked **[UNVERIFIED]**.

---

## 0. Recommended architecture (TL;DR)

**Transport: one WebSocket per session (binary PCM frames + JSON control frames) between the FlutterFlow app and a Python server on the laptop. The Python server is the only thing exposed on the LAN; LM Studio stays bound to 127.0.0.1 and is called by Python.**

Why this over WebRTC or per-turn HTTP:
- It is implementable entirely inside FlutterFlow custom code with three well-maintained pub.dev packages, works on Android/iOS/exported-web, and needs no signaling server, no ICE, no native-plugin gymnastics.
- Per-turn HTTP multipart (FlutterFlow's built-in Start/Stop Audio Recording + API Call + Audio Player) needs zero custom code but adds the full utterance length + upload + full-TTS-synthesis before first sound (seconds), and cannot do barge-in. Keep it as the zero-code / web fallback.
- WebRTC (`flutter_webrtc` 1.6.1 + Pipecat SmallWebRTC/aiortc) gives you the best echo cancellation for free and Opus, and Pipecat's docs confirm "ICE servers are optional for local network development", but the Flutter client side for Pipecat is immature (see §2.4) and it is harder to debug inside FlutterFlow. Treat it as the upgrade path.

### Package set (pin these; all versions verified on pub.dev this week)

| Role | Package | Version (date) | Notes |
|---|---|---|---|
| Mic → PCM16 stream | `record` | **7.1.1** (Jun 29 2026) — needs Dart ≥3.12; use **6.2.1** (May 22 2026, Dart ≥3.5) if FlutterFlow is still on Flutter 3.38.x | `startStream(RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1, echoCancel: true, noiseSuppress: true, autoGain: true, androidConfig: AndroidRecordConfig(audioSource: voiceCommunication, audioManagerMode: modeInCommunication, speakerphone: true), iosConfig: IosRecordConfig(categoryOptions: [defaultToSpeaker, allowBluetooth])))`. Android min SDK 23, iOS 12.0. |
| WebSocket | `web_socket_channel` | **3.0.3** (Apr 17 2025) | verified publisher tools.dart.dev; Android/iOS/web/desktop. `sink.add(Uint8List)` sends binary. |
| TTS playback (streamed PCM) | `flutter_soloud` | **5.0.0** (Sep 3 2026 — brand new major; 4.x if you hit issues) | `setBufferStream(format: s16le/f32le/opus, bufferingType: released, bufferingTimeNeeds: …)`, `addAudioDataStream(Uint8List)`, `setDataIsEnded()`. Android 21+, iOS 13+, web (needs its web setup). |
| Audio session / focus | `audio_session` | **0.2.4** (Jun 29 2026) | iOS `playAndRecord` + `voiceChat` + `defaultToSpeaker`/`allowBluetooth`; Android `voiceCommunication` usage + focus gain type. |
| QR pairing | `mobile_scanner` | **7.4.0** (Jul 20 2026) | Android/iOS/macOS/web; adds 3–10 MB (bundled MLKit) or 600 KB unbundled. |
| Avatar | `rive` | **0.14.11** (Aug 3 2026, depends on `rive_native` 0.1.11); 0.15.0-dev.1 prerelease | see §3 for the FlutterFlow version-conflict caveat. |
| Optional discovery | `bonsoir` 7.1.5 (Aug 11 2026) or `nsd` 5.0.1 (Apr 4 2026) | | Python side: `zeroconf` 0.151.3. |

Server: Python 3.12 + `uv`, FastAPI/uvicorn (or `pipecat-ai` 1.8.1, Aug 27 2026, Python ≥3.11), `faster-whisper` 1.2.1 or `onnx-asr` 0.12.0 (Parakeet-TDT 0.6B v3), `kokoro` 0.9.4 / `kokoro-onnx`, Silero VAD, `torch` 2.14.0 (Sep 2 2026) CUDA wheels; LM Studio (`lms server start --bind 127.0.0.1 --port 1234`) or Ollama.

### Wire protocol sketch (one WS, `ws://<laptop-ip>:8765/ws`)

Client → server
- JSON `{"type":"hello","token":"<from QR>","mode":"tutor"|"interview","in":{"fmt":"pcm16","sr":16000,"ch":1},"out":{"fmt":"pcm16","sr":24000}}`
- binary frames: 20 ms PCM16 mono @16 kHz = **640 bytes** each (the same framing Pipecat's FastAPI WebSocket transport documents: "640 bytes for 20ms at 16kHz PCM16 mono")
- JSON `{"type":"ptt","state":"down"|"up"}` (optional push-to-talk), `{"type":"cancel"}`, `{"type":"ping"}`

Server → client
- `{"type":"ready","session":"…"}`
- `{"type":"vad","state":"speech_start"|"speech_end"}` → app flips Rive `isListening`
- `{"type":"stt","text":"…","final":true}`
- `{"type":"llm","delta":"…"}` (drive "thinking" state until first token)
- `{"type":"correction","original":"…","corrected":"…","explanation":"…","score":0-100}` (tutor mode) / `{"type":"interviewer","reaction":"nod"|"unimpressed"|"neutral"}` (interview mode)
- `{"type":"tts_start","sr":24000,"fmt":"pcm16"}`, then binary PCM frames, then `{"type":"tts_end"}`
- `{"type":"mouth","t_ms":…,"open":0.0-1.0}` every 40–50 ms, or `{"type":"viseme","t_ms":…,"id":0-9}` (see §3.3 for how to compute)
- `{"type":"interrupt"}` when server VAD hears the user during TTS → app calls `SoLoud.stop()` and flushes the buffer stream.

Ordering guarantee: WebSocket is ordered, so the `mouth`/`viseme` JSON frames can be interleaved with binary audio and the client schedules them against `SoLoud.getStreamTimeConsumed()`/its own play clock.

---

## 1. FlutterFlow custom code in 2026

Sources: docs.flutterflow.io pages (last-updated dates shown).

- **Three code types** ([Writing Custom Code](https://docs.flutterflow.io/concepts/custom-code/)): Custom Functions ("Custom Dart functions that can be used to set Widget or Action properties" — must compile, **cannot add custom imports/dependencies**); Custom Actions ("always return a `Future`", may add pubspec dependencies, may receive `BuildContext` via "Include Build Context toggle", may take Callback Actions); Custom Widgets (may import pub.dev packages, "it is mandatory to specify both width and height", support callback actions and Widget Builders, "cannot return a value at the moment"). Plus **Code Files** for "custom classes, enums, and logic" — use one for your WebSocket/audio singleton so it survives page navigation.
- **Pubspec dependencies**: allowed sources are pub.dev, public Git URLs, and private Git with PAT ("supports the use of unpublished packages"). FlutterFlow's own evaluation checklist asks you to check "WEB" support because Test/Run mode is web. Custom Widgets/Actions "don't need to be compiled to export code or test your app"; there is an "Exclude From Compilation" toggle.
- **Native config files** ([Configuration Files](https://docs.flutterflow.io/concepts/custom-code/configuration-files/), updated Jul 15 2026): editable `AndroidManifest.xml`, `build.gradle`, `proguard-rules.pro`, `Info.plist`, `Runner.entitlements`, `AppDelegate.swift`, `main.dart`. Two modes: snippet injection at predefined locations (Android: Activity/Application/App Component tags) or Manual Edit Mode ("Re-locking it will reset the file to a version generated by FlutterFlow, which will overwrite any manual changes"). Documented examples include `minSdkVersion` in build.gradle, `UIBackgroundModes` in Info.plist, and "If your app needs to communicate with HTTP-only servers, you must modify Info.plist" via `NSAllowsArbitraryLoads`.
- **Permissions & minSdk** ([Project Setup](https://docs.flutterflow.io/resources/projects/settings/project-setup/), Jul 15 2026): "We automatically add permissions whenever you add features that access the user's private data. You still need to add permission messages." You can add a custom permission by entering an iOS key (e.g. `NSLocalNetworkUsageDescription`) plus an Android permission name; "You cannot show custom permission messages on Android". Minimum SDK Version is a setting ("the lowest version of Android that your app can run on"); compile/target SDK and Kotlin version are under advanced settings. Default minSdk value **[UNVERIFIED]** — check the project; `record` needs 23, `flutter_webrtc` 23, `pipecat` Dart SDK 24.
- **Background audio**: no FlutterFlow-specific doc; you add `UIBackgroundModes` (audio) via Info.plist snippet. Note `record` 7.0.0 **removed background recording on Android** (changelog).
- **Flutter version**: FlutterFlow announced the **Flutter 3.38.5** upgrade on Jan 28 2026 (applied Feb 3 2026) and warned "you may need to make changes to custom code or dependencies." Flutter's own site now shows 3.47 (Aug 2026). Whether FlutterFlow has moved past 3.38.x since is **[UNVERIFIED]** — it decides whether you can use `record` 7.x (Dart ≥3.12 ⇒ Flutter ≥3.44). Projects can be pinned to a FlutterFlow version ("Pinned FlutterFlow Version" in General Settings, Jul 10 2026).
- **Streaming APIs** ([Streaming API](https://docs.flutterflow.io/resources/backend-logic/streaming-api), May 29 2025): built-in SSE support — toggle "Process Streaming Response" in the API's Advanced Settings; callbacks `onMessage`/`onError`/`onClose`, chunk via `OnMessageInput`, parsers "Server Sent Event Data JSON/Text". Doc says "WebSockets can also be used depending on the application's requirements" but WebSockets themselves are custom-code only (community examples use `web_socket_channel`/`web_socket_client` in a custom action and push into `FFAppState()`; a Jan 2024 community post used `(context as Element).reassemble()` to refresh — avoid that; use a Code-File stream + a custom widget).
- **API calls** ([REST API](https://docs.flutterflow.io/resources/backend-logic/rest-api), May 15 2025): body types JSON/Text/x-www-form-urlencoded/**Multipart with "Uploaded File" variables**; variables can be embedded anywhere in the URL ("how you can use a variable to create a dynamic base URL") — so `http://[host]:[port]/turn` from App State works for the HTTP fallback.
- **Test mode is web** ([Run your app](https://docs.flutterflow.io/testing/run-your-app/)): Test Mode lacks "Native plugins and packages unsupported on web", "Audio Recording actions", and "Custom code assets rendering properly". Run Mode is also web. So the real pipeline must be tested via **Local Run** ([Local Run](https://docs.flutterflow.io/testing/local-run/), May 22 2026: "Testing on mobile devices requires downloading code, for which you must be on paid plans"; supports iOS/Android/desktop; changes in the IDE "will not sync … and will be overwritten") or via exported code.
- **Export & APK**: [flutterflow_cli](https://github.com/FlutterFlow/flutterflow-cli) `dart pub global activate flutterflow_cli`; `flutterflow export-code --project <id> --dest <dir> --token <token>` with `--branch-name`, `--[no]-include-assets`, `--[no]-fix`, `--[no]-as-module`, `--project-environment`; API tokens need "active subscriptions"; `.flutterflowignore` preserves local files across re-exports ([Exporting](https://docs.flutterflow.io/flutterflow-cli/exporting), Apr 29 2026). Build the APK yourself with the standard Flutter toolchain (`flutter pub get && flutter build apk --release`) — the docs do not spell this out. [Pricing](https://www.flutterflow.io/pricing) as fetched: Free $0 (no code download, no custom code), Basic $39/mo ("Code Download", "APK Download", "Test On Local Devices", "Code Extensibility", 1 AI agent), Growth $80/mo (adds GitHub), Business $150/mo ("CLI Access"). Note the pricing page lists "CLI Access" only on Business — but the CLI docs only say "active subscriptions". Treat plan gating as **[UNVERIFIED]**; check your account. A GitHub issue titled "Export Code, Local Run & CLI BROKEN since Flutter upgrade (#6881)" exists — not fetched, but it is a reminder to keep a working export before each FlutterFlow release.
- **`flutterflow ai` (agentic CLI)** ([Build with AI Agents](https://docs.flutterflow.io/flutterflow-cli/build/), Jul 21 2026; [Claude Code plugin](https://docs.flutterflow.io/flutterflow-cli/claude-code/), Jul 20 2026): `flutterflow ai init` (workspace + MCP config; `--env beta`), `inspect`, `resources`, `search`, `status`, `plan`, `validate`, `run`, `trace`, `history`, `context-check`, `refresh-context <project-id>`. The agent "Writes changes as declarative Dart files, checks them with `flutterflow ai validate` first, and only then applies them with `flutterflow ai run`." In scope: pages, components, app state, theme, navigation, action blocks, **custom functions/actions/widgets, classes and enums, dependencies (Pub/library), API endpoints**. Out of scope: deployment, app execution, Firebase project creation, secrets, App Store. Optimistic concurrency (push rejected if the live project changed). Prereqs: CLI, FF API key, MCP-capable agent (Claude Code, Gemini CLI, Codex), Dart. Install: `/plugin marketplace add FlutterFlow/flutterflow-claude` then `/plugin install flutterflow@flutterflow`. (A `flutterflow:build` skill is available in this environment for that.)
- **2026 real-time/audio features**: nothing WebSocket- or raw-audio-specific was found in FlutterFlow's own docs beyond SSE streaming and the built-in Start/Stop Audio Recording actions + Audio Player widget (which do not work in web Test Mode). Real-time audio is custom-code territory.

**Practical FlutterFlow structure for this app**
1. Code File `VoiceLink` (singleton): owns `WebSocketChannel`, `AudioRecorder`, `SoLoud` buffer stream, and broadcast `Stream<VoiceEvent>`.
2. Custom Action `connectVoice(host, port, token, mode)` / `disconnectVoice()` / `startTurn()` / `stopTurn()` — thin wrappers, update a few App State fields (connection status, last correction) at low frequency.
3. Custom Widget `InterviewerAvatar(width, height)` — Rive widget that subscribes directly to `VoiceLink.events` for 25–50 Hz mouth updates (never route those through App State; every `FFAppState().update()` rebuilds listeners).
4. Custom Widget `PairScanner` (mobile_scanner) with a callback action returning the parsed QR payload.
5. Config files: AndroidManifest `<application android:usesCleartextTraffic="true">` (Manual Edit Mode — a `network_security_config.xml` res file cannot be added from FlutterFlow), Info.plist `NSMicrophoneUsageDescription`, `NSLocalNetworkUsageDescription`, `NSBonjourServices` (only if you use mDNS), `NSAppTransportSecurity → NSAllowsLocalNetworking` (or `NSAllowsArbitraryLoads` as the docs show).

---

## 2. Streaming microphone audio and TTS playback

### 2.1 Capture options
| Package | Version | Streaming PCM API | Verdict |
|---|---|---|---|
| `record` | 7.1.1 / 6.2.1 | `startStream()` → `Stream<Uint8List>`; `pcm16bits` best cross-platform; Android/iOS/web/desktop; per-platform `AndroidRecordConfig` (`audioSource`, `useLegacy`, `muteAudio`, `manageBluetooth`, `speakerphone`, `audioManagerMode`) and `IosRecordConfig` (`categoryOptions`, e.g. `defaultToSpeaker`, `allowBluetooth`). Web caveat: "Sample rate output is determined by your settings in OS. Bit depth is likely 32 bits" (so resample/convert server-side for the web build). Known issue #604: iOS `startStream()` first call can take 3+ s and block the UI (engine recreated per start; `setActive(true)` called unconditionally) — pre-warm at page load. | **Use this.** BSD-3, verified publisher, actively released. |
| `flutter_sound` | 9.30.0 (Nov 27 2025) | records to and plays from Dart streams ("PCM Float32 or PCM Int16"); Android 21+, iOS 10+ | MPL-2.0 weak copyleft; 9.x is "legacy plugin", maintainer moving to Taudio 10.0 alpha; AEC issue #1134 unresolved (`enableVoiceProcessing` iOS-only and "does not work"). Skip. |
| `mic_stream` | 0.7.2 (Mar 1 2025) | `Stream<Uint8List> MicStream.microphone(...)` 8/16-bit PCM; Android/iOS/macOS | **GPL-3.0** — disqualifying for a closed app. |
| `sound_stream` | 0.4.2 (Sep 27 2023) | PCM16 mono recorder+player streams | Android/iOS only, stale. Skip. |

### 2.2 Transport comparison
- **WebSocket** (`web_socket_channel` 3.0.3): binary frames, ordered, trivial on Windows (uvicorn). Added latency is essentially the Wi-Fi RTT plus your 20 ms framing. Local Wi-Fi RTT is typically low-single-digit to ~10 ms with occasional power-save spikes **[UNVERIFIED — no measurement source; measure with `ping` from the phone]**.
- **WebRTC** (`flutter_webrtc` 1.6.1, Sep 1 2026; Android min SDK 23, ProGuard rules mandatory for release, iOS needs `ONLY_ACTIVE_ARCH = 'YES'`; no built-in signaling). Server: Pipecat SmallWebRTC (aiortc, `pip install pipecat-ai[webrtc]`; "ICE servers are optional for local network development"). Pipecat's Android client is `ai.pipecat:small-webrtc-transport:1.2.0`, iOS has `pipecat-client-ios-small-webrtc`; the pub.dev `pipecat_flutter` **5.0.0 (Aug 31 2026) is Daily-transport-only and community-published**. A Medium series (Apr 25 2026) describes a `pipecat` Dart package v0.2.0 with `SmallWebRTCTransport`, "sub-500 ms latency", iOS 13+/Android minSdk 24 — I could not verify that package on pub.dev **[UNVERIFIED]**. Jitter buffers/Opus add ~20–60 ms but give you WebRTC's AEC3/NS/AGC for barge-in.
- **Per-turn HTTP multipart**: FlutterFlow-native (Start/Stop Audio Recording → Multipart "Uploaded File" → Audio Player). Highest latency, no barge-in, but zero custom code and works for the web build (via HTTP-served web, see risks).

**Verdict: WebSocket + `record` + `flutter_soloud` is the simplest robust option inside FlutterFlow.** Move to WebRTC only if echo/barge-in on speakerphone proves unmanageable.

### 2.3 Playback of streamed TTS
| Package | Version | Streaming fit |
|---|---|---|
| `flutter_soloud` | 5.0.0 (Sep 3 2026) | Purpose-built: `setBufferStream` with `bufferingType` `preserved`/`released`, `bufferingTimeNeeds` ("If playback reaches the end of the current buffer, it will pause and wait"), `maxBufferSizeBytes`/`maxBufferSizeDuration`, formats `s8`, `s16le`, `s32le`, `f32le`, `opus` ("Ogg container with Opus codec"); `addAudioDataStream(Uint8List)`, `setDataIsEnded()`. Docs list "Working with OpenAI or other streaming APIs" as a use case. MIT (Dart side). **Recommended.** |
| `flutter_pcm_sound` | 3.3.3 (Oct 4 2025) | `setup(sampleRate, channelCount)`, `feed(PcmArrayInt16)`, `setFeedThreshold`, feed callback; Android/iOS/macOS only, no web. Solid fallback for mobile. |
| `just_audio` | 0.10.6 (Jun 29 2026) | `StreamAudioSource.request(start,end)` byte-range model; fine for progressive WAV/MP3 but not designed for open-ended PCM push; requires `usesCleartextTraffic`/ATS tweaks for http. Use only for the HTTP-per-turn fallback (play the returned WAV URL). |
| `audioplayers` | — | file/URL based; no PCM feed API **[not fetched; from general knowledge]**. Fallback-only. |
| `sound_stream` | 0.4.2 (2023) | stale. |

### 2.4 Barge-in, echo, focus
- **Android**: AOSP requires that "implementations should provide an acoustic echo canceler (AEC) on the capture path when capturing with `VOICE_COMMUNICATION`" (Android 10+), and `AcousticEchoCanceler` docs say it is "automatically enabled" for the `VOICE_COMMUNICATION` source on supported devices; availability is device-dependent (`isAvailable()`). So set `audioSource: voiceCommunication`, `echoCancel: true`, `noiseSuppress: true`, `audioManagerMode: modeInCommunication`, `speakerphone: true` in `record`, and request audio focus with `USAGE_VOICE_COMMUNICATION` via `audio_session` (focus loss types `AUDIOFOCUS_LOSS/_TRANSIENT/_CAN_DUCK` — "you cannot duck a microphone"; Android 14+ needs `foregroundServiceType="microphone"` only if you record in a foreground service — you won't).
- **iOS**: use `audio_session` with `AVAudioSessionCategory.playAndRecord`, **mode `voiceChat`**, options `defaultToSpeaker`, `allowBluetooth`. A field report (Apr 22 2026) on VoiceProcessingIO: "`.voiceChat` is the mode VPIO is tuned for. `.videoChat` behaves similarly. Any other combination — `.default`, `.measurement`, `.spokenAudio` — you are on your own." Its measured echo-risk window after playback stops: "200–500ms in typical rooms", WebRTC AEC3 tail "100–300ms", Pipecat's `stop_secs` default 800 ms; it recommends a **500–800 ms mic gate after TTS ends** (armed when the playback buffer drains, disarmed when new TTS arrives). Apple also has `AVAudioSession.setPrefersEchoCancelledInput(_:)` ("Sets a preference to enable echo-canceled input on supported hardware") — version/constraints **[UNVERIFIED — page needs JS]**. Beware iOS `startStream()` cold-start delay (record #604).
- **Speakerphone self-interruption is real**: LiveKit Flutter issue #689 (Jan 2025, iOS 18.1.1) — "if the agent is on speaker phone it interrupts itself … it triggers the VAD system from its own voice", closed "not planned". Mitigations that don't depend on device AEC: (a) server-side "echo-aware" gating — ignore VAD triggers whose energy correlates with the TTS the server is currently sending; (b) require ≥300–400 ms of speech before `interrupt`; (c) the post-TTS mic gate above; (d) headphones for the judges' demo.

---

## 3. Rive avatar in FlutterFlow

### 3.1 What FlutterFlow gives natively
[Rive Animation widget](https://docs.flutterflow.io/concepts/animations/rive-animation/): drag-drop `RiveAnimation`, source Network/Asset, artboard + animation selection, "Once"/"Continuous", Auto Animate, and a "Rive Animation Action" on tap/double-tap/long-press. **No state-machine input support** — a Sept 2023 community post confirms "the Rive widget only supports Rive animation and not Rive State Machines", and issue #1846 (Nov 2023) notes custom widgets were needed for state machines. Nothing newer contradicts this in the docs.

### 3.2 Custom widget route (required)
- Current runtime: `rive` **0.14.11** (Aug 3 2026) on `rive_native` **0.1.11**; legacy 0.13.20 lives in `rive-flutter-legacy`. Renderers `Factory.rive` (native, Vector Feathering, `RivePanel` shared texture) or `Factory.flutter`. Needs `await RiveNative.init();` before use; Dart ≥3.5, Flutter ≥3.3.
- State-machine inputs, new API: `final sm = controller.stateMachine; sm.number('viseme').value = 3; sm.boolean('isListening').value = true; sm.trigger('nod').fire();` (migration guide). Legacy 0.13 API: `StateMachineController.fromArtboard(...)`, `findInput<double>('viseme') as SMINumber`.
- Data binding (`controller.dataBind(DataBind.auto())`) is the recommended alternative to inputs in 0.14+.
- `rive_native` downloads prebuilt native libs during build ("The required native libraries should be automatically downloaded during the build step"; `dart run rive_native:setup`) — do this while you still have internet; a Rive community thread reports an iOS build failure with rive_native (details truncated).
- **Version conflict risk**: FlutterFlow's built-in Rive widget pins its own `rive` version (a Apr 2025 community post got "the dependency is outdated" warnings when adding the latest rive to a custom widget). Only one `rive` version can exist in the pubspec. Either match FlutterFlow's pinned version and use its API (legacy `findInput` if it's 0.13.x) or remove all built-in Rive widgets from the project. Exact pinned version **[UNVERIFIED — read the exported pubspec.yaml]**.

### 3.3 Lip-synced avatar feasibility — yes, with a "mouth" number input
- Pattern from a Feb 21 2026 guide: a Number input `viseme` with "8–10 grouped visemes instead of full phoneme mapping" (e.g. 0 Neutral, 1 Closed, 2 Open, 3 Wide), "immediate transitions" not blends; expressions as Booleans (`isListening`, `isThinking`) plus Triggers (`nod`, `unimpressed`). Timing comes from the TTS engine's phoneme/word timestamps. Kokoro (via `misaki` G2P) knows the phonemes it synthesizes, but the open-source pipeline does not expose per-phoneme timestamps out of the box → simplest robust approach for the demo: **server computes RMS energy per 40 ms of the TTS PCM it is about to send and emits `{"type":"mouth","open":0..1}`**; the Rive state machine maps `mouthOpen` (0–100) to a blend of 3–4 mouth shapes. Exact phoneme-accurate visemes: nice-to-have, **[feasibility of per-phoneme timing with Kokoro UNVERIFIED]**.
- Ready-made assets: Rive Marketplace "Custom Talking Avatar: Real-Time Lip Sync for Your App" by stvfunm (Jun 16 2025, **CC BY, free**) — "audio analyzed and converted into smooth mouth movements … phoneme mapping"; input names not documented, open it in the Rive editor. A Rive community "Lip sync animation + free tool" wires a viseme state machine to ElevenLabs (details not extractable). Expect to author the expression booleans yourself.
- **3D alternative** (comparison): `flutter_3d_controller` 2.3.0 (Sep 13 2025) renders GLB via Google model-viewer in a WebView — animation play/pause/camera API but **no documented blendshape/morph-target weight API**, so real-time visemes are not possible without injecting JS. Ready Player Me avatars ship "the viseme blend shapes required for real-time audio-based facial animation" (Oculus 15 visemes: `viseme_sil, PP, FF, TH, DD, kk, CH, SS, nn, RR, aa, E, I, O, U`; ARKit 52), and the MIT `TalkingHead` project does text→viseme lip-sync ("around 80% lip-sync accuracy" for English) — but it is browser/three.js only, no Flutter port. Rive is the right call for FlutterFlow.

---

## 4. Pairing and networking

### 4.1 Discovery
- **QR (recommended)**: server prints/serves a QR with `voicetutor://pair?h=192.168.137.1&p=8765&t=<32-hex token>&v=1`; app scans with `mobile_scanner` 7.4.0 (iOS needs `NSCameraUsageDescription`), stores in App State, connects, sends `hello`. Server also shows the same as text for manual entry.
- **mDNS (optional)**: `bonsoir` 7.1.5 / `nsd` 5.0.1 + Python `zeroconf` 0.151.3 (CPython 3.8+). iOS requires `NSLocalNetworkUsageDescription` **and** `NSBonjourServices` (e.g. `_voicetutor._tcp`); Android needs `INTERNET` + `CHANGE_WIFI_MULTICAST_STATE`. Apple TN3179: browsing arbitrary service types needs the multicast entitlement — list your exact type instead. Windows mDNS responders work but can be flaky across hotspot virtual adapters; keep QR as primary.

### 4.2 Windows 11 Mobile Hotspot with no upstream internet — the biggest gotcha
- Microsoft Q&A (2021–2025 thread): "Windows 11/10 Mobile Hotspot feature **requires an active internet connection to start**"; "Windows can keep a local hotspot running without internet" but "cannot start/initiate a hotspot without an internet connection". The WinRT API confirms why: `NetworkOperatorTetheringManager.CreateFromConnectionProfile(ConnectionProfile)` needs a connection profile; the PowerShell trick fails when `GetInternetConnectionProfile()` returns null ("Invalid pointer"). "No native Windows solution exists" as of Jan 2025 in that thread.
- Workarounds, in order of reliability:
  1. **Bootstrap**: connect the laptop to any network (e.g. your phone's hotspot or any venue Wi-Fi) → turn on Mobile Hotspot → disconnect the upstream. Per the thread the hotspot "continues running independently". **[Community-reported, not MS-documented; rehearse it.]**
  2. **Reverse the roles**: make the *Android phone* the hotspot (Android hotspot works with mobile data off **[UNVERIFIED]**) and have the laptop join it; the server binds to the laptop's IP on that network. This also sidesteps Android's "no internet" behaviour because the phone is the AP. iOS cannot do this: Apple says Personal Hotspot "requires a wireless carrier that supports Personal Hotspot" and "make sure that Cellular Data is turned on".
  3. Legacy `netsh wlan set hostednetwork` — only if `netsh wlan show drivers` shows "Hosted network supported: Yes" (most modern Wi-Fi 6/6E drivers say No **[UNVERIFIED]**).
  4. Third-party hotspot apps (Microsoft Store "WiFi Hotspot (Access Point)" is cited); the KM-TEST loopback-adapter trick is mentioned but a separate MS Q&A shows KM-TEST breaking phone-hotspot internet — avoid.
  5. A cheap travel router with no WAN is the most boring, most reliable option.
- **Power saving auto-off**: Windows turns the hotspot off after **5 minutes with no clients**. Disable: Settings → Network & internet → Mobile hotspot → "Power saving" off, or registry `HKLM\SYSTEM\CurrentControlSet\Services\icssvc\Settings\PeerlessTimeoutEnabled = 0` (REG_DWORD). API equivalent: `NetworkOperatorTetheringManager.DisableNoConnectionsTimeout()` (Windows 10 2004+).
- Default hotspot subnet is 192.168.137.x with the laptop at 192.168.137.1 **[UNVERIFIED — common default]**.

### 4.3 Keeping the phone on an internet-less Wi-Fi
- Android capabilities: `NET_CAPABILITY_INTERNET` ≠ `NET_CAPABILITY_VALIDATED`; a captive-portal/no-DNS network never becomes VALIDATED. Default-network ranking (AOSP `NetworkRanker.getBestNetworkByPolicy`, verbatim order): invincible → VPN → **"Selected & Accept-unvalidated policy"** (`POLICY_EVER_USER_SELECTED && POLICY_ACCEPT_UNVALIDATED`) → "If any network is validated (or should be accepted even if it's not validated), then don't choose one that isn't." → yield-to-bad-wifi → … → transport preference. **Meaning: if the user explicitly picked the laptop's network and tapped "Yes/Stay connected" on the "no internet" prompt, that Wi-Fi beats validated cellular as the default network.** If they dismiss the prompt, mobile data can become default and connections to 192.168.x.x fail. Demo procedure: enable airplane mode, then re-enable Wi-Fi (all Android versions allow this **[UNVERIFIED for persistence across toggles]**), pick the SSID, accept "Stay connected". Also switch off "Switch to mobile data automatically" (Pixel: Network preferences) **[setting name varies by OEM — UNVERIFIED]**. Android 10+ apps can alternatively request a local-only peer network via `WifiNetworkSpecifier` ("Creating a connection using this API does not provide an internet connection … use the Wi-Fi Suggestion API instead") — not exposed in FlutterFlow without a plugin.
- iOS: Wi-Fi can be re-enabled while Airplane Mode is on **[Apple support page 404'd; UNVERIFIED]**. Local Network privacy (TN3179, rev. Feb 17 2026): the first "outgoing TCP connection" or "UDP unicast" to a local address prompts; if the app is backgrounded or the user denies, connections fail ("connection enters the waiting state" / `localNetworkDenied`); reset by deleting the app or Settings → General → Transfer or Reset → Reset Location & Privacy; "The simulator doesn't support local network privacy." Add `NSLocalNetworkUsageDescription` (iOS 14+). WebViews are exempt.
- Android cleartext: "Starting with Android 9 (API level 28), cleartext support is disabled by default." Either `android:usesCleartextTraffic="true"` on `<application>` (FlutterFlow Manual Edit Mode) or a `network_security_config` with `<domain-config cleartextTrafficPermitted="true"><domain>192.168.137.1</domain>` (numeric IPs are accepted in `<domain>`; only possible after export since FlutterFlow can't add res/xml files). Note: `ws://` over `dart:io` is also cleartext-policed on Android.
- iOS ATS: Dart's `dart:io` sockets are not NSURLSession, but add `NSAppTransportSecurity/NSAllowsLocalNetworking = YES` anyway; FlutterFlow docs show `NSAllowsArbitraryLoads` for HTTP-only servers.

### 4.4 Windows Defender Firewall
`New-NetFirewallRule -DisplayName "VoiceTutor WS" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Program "C:\path\.venv\Scripts\python.exe" -Profile Private,Public` (the hotspot's virtual adapter is often categorised Public **[UNVERIFIED]**, so include Public). Keep LM Studio on `--bind 127.0.0.1` (LM Studio's own note: "Any bind other than 127.0.0.1 exposes the server beyond localhost; we recommend enabling authentication") and Ollama on the default `127.0.0.1:11434` — only the Python server needs a rule. If you must expose LM Studio, its default port is 1234.

### 4.5 Wired fallback
`adb reverse tcp:8765 tcp:8765` makes the phone's `localhost:8765` reach the laptop over USB (USB debugging on). The official adb page only documents `adb forward tcp:6100 tcp:7100` in the excerpt I fetched; `adb reverse` syntax is from general knowledge **[UNVERIFIED in docs]**. USB tethering is another option (phone shares nothing but the laptop gets an IP on the phone's USB network). Android only — iOS has no equivalent without a Mac.

---

## 5. Server side on Windows

### 5.1 Framework choice for a single-user local server
- **FastAPI + `websockets`/uvicorn**: full control, trivially matches the protocol in §0, ~300 lines. Recommended.
- **Pipecat 1.8.1** (Python ≥3.11): `FastAPIWebsocketTransport` exists (params `add_wav_header`, `serializer`, `session_timeout`, `fixed_audio_packet_size`; framing "640 bytes for 20ms at 16kHz PCM16 mono") but Pipecat says WebSocket transports "are best suited for prototyping and controlled network environments" and the FastAPI one is aimed at "telephony applications". Its local services are attractive: `WhisperSTTService` (faster-whisper; `Model.LARGE_V3_TURBO`, `DISTIL_LARGE_V3`, default `DISTIL_MEDIUM_EN`; `device="cuda"`, `compute_type="float16"|"int8"`; segmented after VAD), `KokoroTTSService` (kokoro-onnx ≥0.5.0, auto-downloads `kokoro-v1.0.onnx` + `voices-v1.0.bin` to `~/.cache/pipecat/kokoro-onnx/`, streams frames incrementally, CPU/ONNX Runtime), Silero VAD (`[silero]`), OpenAI-compatible LLM pointing at LM Studio. Good if you also want SmallWebRTC later; the client protocol (RTVI/Protobuf serializer) then has to be implemented in Dart.
- **LiveKit**: server v1.13.x ships `livekit_1.13.1_windows_amd64.zip` (Jun 8 2026; latest tag v1.13.6 late Aug 2026), `livekit-server --dev --bind 0.0.0.0`, dev key `devkey`/`secret`, signal on `:7880`. Full SFU + Agents framework is overkill for one phone and adds UDP port ranges to firewall — skip unless you already know it.

### 5.2 LLM host
- **LM Studio**: headless via **llmster** (`irm https://lmstudio.ps1 | iex`, `lms daemon up`) or desktop "run the LLM server on login"; `lms server start --port 1234 --bind 127.0.0.1`; `lms load <model> --gpu=max --context-length N`; JIT loading with TTL auto-unload; OpenAI-compatible `/v1/chat/completions` (+ Anthropic-compatible + native REST). Pre-download with `lms get`.
- **Ollama on Windows**: native tray app ("will run in the background"), API `http://localhost:11434`, models in `%HOMEPATH%\.ollama`, needs "551.61 or newer" NVIDIA drivers; `OLLAMA_HOST` via user env vars (quit → set → restart); `OLLAMA_KEEP_ALIVE=-1` or per-request `keep_alive: -1` to pin the model ("By default models are kept in memory for 5 minutes"); `OLLAMA_NUM_PARALLEL` default 1; "If the model will entirely fit on any single GPU, Ollama will load the model on that GPU".

### 5.3 Sharing one 16 GB GPU between LM Studio and the Python STT/TTS process
- WDDM gives every process its own GPU virtual address space and over-commits segments; when dedicated VRAM is exhausted the NVIDIA driver (since **536.40**) silently spills CUDA allocations to "shared GPU memory" (system RAM over PCIe) — this is the "silent slowdown". Driver **546.01+** exposes NVIDIA Control Panel → Manage 3D Settings → **"CUDA – Sysmem Fallback Policy" → "Prefer No Sysmem Fallback"** so overflow fails fast instead of crawling (per NVIDIA KB 5490). Set it per-program for `python.exe` and LM Studio if you prefer to keep the default globally.
- LM Studio has a "limit offload to dedicated GPU memory" GPU setting (mentioned in the 0.3.15 changelog, Apr 24 2025) **[exact UI name UNVERIFIED]** — enable it, and watch Task Manager's "Dedicated GPU memory" vs "Shared GPU memory".
- Budget for the RTX 4090 Laptop (16 GB) — **estimates, not measured**: LLM ~5–8 GB (e.g. an 8B Q4_K_M with 8k context, or Gemma-class 12B Q4 ≈ 7.5 GB), faster-whisper `large-v3-turbo` fp16 ≈ 1.6 GB or `distil-large-v3` ≈ 1.5 GB (or Parakeet-TDT-0.6B int8 ≈ 0.67 GB via onnx-asr), Kokoro on CPU (kokoro-onnx) or ~0.5 GB on GPU, Silero VAD on CPU, plus ~0.3–0.5 GB CUDA context per process and Windows' own usage. Leave ≥2 GB headroom; each process loads exactly once at startup.

### 5.4 Python / CUDA / PyTorch that work on Windows today
- `torch` **2.14.0** (PyPI, Sep 2 2026; "Python >=3.10", wheels for CPython 3.10–3.14; the GitHub release notes also mention 3.15 experimental **[inconsistent between sources]**). PyTorch's previous-versions page lists Windows/Linux wheel indexes for 2.13.0/2.12.x as **`cu126`, `cu130`, `cu132`** (plus cpu) — pick `cu126` for widest driver compatibility or `cu130`; the wheels bundle the CUDA runtime, no toolkit install needed. With uv: `[[tool.uv.index]] name="pytorch-cu126" url="https://download.pytorch.org/whl/cu126" explicit=true` + `[tool.uv.sources] torch=[{index="pytorch-cu126", marker="sys_platform == 'win32'"}]`, or simply `uv pip install torch --torch-backend=auto` / `UV_TORCH_BACKEND=auto`.
- `faster-whisper` **1.2.1** (Oct 31 2025 — may have moved; **[check]**) needs "cuBLAS for CUDA 12" and "cuDNN 9 for CUDA 12": `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*` and put their `bin` dirs on `PATH` (classic Windows pitfall: `cudnn_ops64_9.dll` not found).
- `onnx-asr` **0.12.0** (Jul 15 2026; Python 3.10–3.14): Parakeet-TDT 0.6B v3, Canary, Whisper, GigaAM, Zipformer; CUDA/TensorRT/DirectML providers; built-in VAD long-form. Needs `onnxruntime-gpu` + the same CUDA 12/cuDNN 9 DLLs.
- `kokoro` **0.9.4** (Apr 5 2025; Apache-2.0; 82 M params; `KPipeline` generator yields 24 kHz chunks; on Windows install espeak-ng from its `.msi`), or `kokoro-onnx` (what Pipecat uses).
- Python **3.12** is the safe intersection of all of the above.

### 5.5 Packaging for the judges' demo
- `uv init`, commit `pyproject.toml` + `uv.lock`; `uv sync` once with internet.
- Pre-download every model with internet: `hf download <repo> --local-dir models\…` (Kokoro ONNX + voices, Whisper/Parakeet, Silero), `lms get <llm>` or `ollama pull`. Then run with `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
- `run_demo.bat`: (1) set env vars; (2) `lms server start --port 1234 --bind 127.0.0.1` and `lms load <model> --gpu=max --context-length 8192` (or `ollama serve` with `OLLAMA_KEEP_ALIVE=-1`); (3) `uv run python server.py --host 0.0.0.0 --port 8765` which prints the LAN IP + token and opens `http://localhost:8765/pair` showing the QR; (4) a self-test that transcribes a bundled WAV and synthesises one sentence so you know the GPU path works before anyone connects.
- Disable Windows sleep/hibernate and hotspot power saving; plug the laptop in (RTX 4090 Laptop throttles hard on battery **[UNVERIFIED for your model]**).

---

## 6. On-device fallback (when the laptop is unreachable)

### 6.1 STT/TTS/VAD — `sherpa_onnx` 1.13.7 (3 days old), Apache-2.0
Prebuilt native libs per platform (`sherpa_onnx_android_arm64`, `_ios`, `_windows`, `_web`, …); streaming + non-streaming ASR, TTS, VAD, KWS, diarization. Model sizes (bytes from Hugging Face listings):
- Streaming Zipformer **en-20M** int8: encoder 42,845,182 + decoder 539,499 + joiner 259,572 ≈ **43.6 MB** (tokens 5 KB). The larger en-2023-06-26 int8 is ≈ 72.7 MB. Real-time on any recent phone (Raspberry Pi 4 figures elsewhere in the docs are <1× RTF).
- Moonshine tiny-en int8 ≈ **242 MB** total (RTF 0.032 on the doc's test machine); base ≈ 560 MB. Whisper tiny.en int8: encoder 12 MB + decoder 105 MB (RTF 0.386–0.547 on Raspberry Pi 4).
- Parakeet-TDT 0.6B v3 int8: encoder **652 MB** — too big for a phone fallback.
- Silero VAD v5: **643,854 bytes**.
- TTS: Piper `en_US-lessac-medium.onnx` **63.2 MB** (+ espeak-ng-data); Kokoro en v0.19 int8 `model.onnx` **134.2 MB** + `voices.bin` 5.8 MB (fp32 is 330 MB; RTF 2.8–6.6 on Raspberry Pi 4 — expect roughly real-time or slower on mid-range phones **[UNVERIFIED]**; Piper is the safer phone TTS).
- Alternatives: `whisper_ggml` 2.6.0 (Aug 3 2026; Android 21+/iOS 15.6+; Metal on Apple; models auto-download or ship as assets), `flutter_gemma_speech` 0.4.3 (Aug 15 2026; STT moonshine-tiny, TTS Matcha 22.05 kHz via LiteRT; app must supply PCM I/O; has a `VoiceSession` "push-to-talk turn with barge-in").

### 6.2 On-device LLM
| Option | Version | Models & sizes | Notes |
|---|---|---|---|
| `flutter_gemma` (LiteRT-LM / MediaPipe) | **1.7.0** (Aug 31 2026) | Gemma 4 E2B `.litertlm` **2,588,147,712 B (2.59 GB)**, E4B 3.66 GB; Gemma 3n E2B int4 3.66 GB; Gemma 3 1B int4 `.task` **554,661,243 B (0.55 GB)**; Qwen3 0.6B 586 MB, FunctionGemma 270M 284 MB | Android/iOS/web/desktop; iOS ≥15 (16 with MediaPipe); function calling + thinking mode on Gemma 4; downloads from HF or bundled asset. Google lists Flutter as **"Community"** support on the LiteRT-LM page; MediaPipe LLM Inference is "maintenance-only mode" and "optimized for high-end Android devices, such as Pixel 8 and Samsung S23 or later". |
| Google published Gemma 4 E2B speeds (1024 prefill/256 decode) | — | **S26 Ultra: CPU 46.9 tok/s decode, 1.8 s TTFT, 1,733 MB RAM; GPU 52.1 tok/s, 0.3 s TTFT, 676 MB. iPhone 17 Pro: CPU 25.0 / GPU 56.5 tok/s. RTX 4090 (Linux): 143.4 tok/s.** Weights "as low as 0.8 GB" in memory for text-only. | These are flagships. **Mid-range Android figures are not published [UNVERIFIED]** — expect a fraction of the above and multi-second TTFT; Raspberry Pi 5 does 7.6 tok/s for scale. |
| `cactus` | 1.3.0 (Dec 19 2025) | qwen3-0.6, gemma3-270m, lfm2-vl-450m, whisper-tiny/base STT | Android API 24+, iOS 12+; license "Unknown" on pub.dev, telemetry on by default, NPU behind a Pro key. |
| `llama_cpp_dart` 0.2.2 (Jan 2 2026) / `fllama` (git only, GPL-2 or commercial) | — | any GGUF | you build/ship libllama yourself; unverified publisher. Not for a hackathon timeline. |
| Apple Foundation Models (iOS 26) | — | on-device ~3B **[size UNVERIFIED]** | Swift-only framework ("To use Apple Foundation Models, people need a device that supports Apple Intelligence"); guided generation + tools. No Flutter plugin verified (pub.dev search blocked). Would need a platform channel — only worth it if iOS is your primary demo device, which it isn't. |

### 6.3 Verdict
- **STT + TTS + VAD on device: yes, ship it.** `sherpa_onnx` with Zipformer-en-20M int8 (44 MB) + Silero v5 (0.6 MB) + Piper lessac-medium (63 MB) ≈ **110 MB of assets**, runs on mid-range Android and iOS, Apache-2.0, works in exported FlutterFlow builds (native plugin ⇒ not in web Test Mode).
- **On-device LLM for grammar correction: conditional.** Gemma 4 E2B (2.6 GB) is the quality floor I would trust for "correct this sentence and explain briefly", and even on flagships TTFT is 0.3–1.8 s; Gemma 3 1B (0.55 GB) is fast but weak. Whether a 1–4B model corrects grammar "acceptably" is **[UNVERIFIED — I found no benchmark for this task on these models]**; mitigate with a rigid prompt (return JSON `{corrected, errors[]}`), few-shot examples, and constrained decoding/`thinking` off. Model files cannot ship inside the APK realistically; for a no-internet demo **have the phone download the `.litertlm` from the Python server over the laptop's Wi-Fi** (or `adb push` it) — no internet is needed at any point.
- FlutterFlow compatibility: all of these are pubspec dependencies with native code ⇒ work in Local Run / exported APK, not in web Test Mode. Watch Android minSdk (raise to 24 to be safe), APK size (mobile_scanner +3–10 MB, sherpa_onnx libs, rive_native libs — total **[UNVERIFIED]**; measure), and `flutter_gemma`'s iOS 15/16 minimum.

---

## 7. Judges' demo checklist (pairing runbook)

Before the day (with internet):
1. Export FlutterFlow code (`flutterflow export-code …`), `flutter build apk --release`, install on the demo phone(s); also `flutter build web` and serve it from the Python server over **http** (the FlutterFlow-hosted https web build cannot open `ws://`/`http://` to a LAN IP — browsers block mixed content; Test Mode on app.flutterflow.io has the same problem).
2. `uv sync`; pre-download all models; run the self-test; set NVIDIA "Prefer No Sysmem Fallback" for python.exe and LM Studio; disable hotspot Power saving (`PeerlessTimeoutEnabled=0`); create the firewall rule; disable sleep; set LM Studio to run on login (or write the `.bat`).
3. Rehearse the hotspot bootstrap (connect laptop to phone hotspot → start Mobile Hotspot → turn phone hotspot off → confirm laptop hotspot stays up and phones can still join). Note the laptop's hotspot IP (Settings → Mobile hotspot shows it; typically 192.168.137.1).
4. Pre-approve iOS "Local Network" and Android "Stay connected" prompts on each demo phone by running the pairing once.

On the day (no internet anywhere):
1. Laptop on AC power → start hotspot via the rehearsed bootstrap → run `run_demo.bat` → wait for "READY (LLM loaded, STT/TTS warm)" and the QR page.
2. Phone: airplane mode ON → Wi-Fi ON → join the laptop's SSID → tap "Yes / Stay connected" on the no-internet warning (Android) → open the app → Scan QR → status turns green (`hello` → `ready`).
3. Say a test sentence with a deliberate error; confirm transcript, correction, TTS, avatar mouth movement; test barge-in once (talk over the interviewer) with headphones or at moderate volume.
4. Fallback ladder if step 2/3 fails: (a) `adb reverse tcp:8765 tcp:8765` over USB and pair with `127.0.0.1:8765`; (b) phone becomes the hotspot, laptop joins, re-scan the QR (server re-prints IP); (c) app's "Offline mode" switch → sherpa_onnx STT/TTS + on-device LLM (or rule-based feedback) so the airplane-mode criterion is still shown.

---

## 8. Risks (ranked)

1. **Windows hotspot cannot start without an upstream connection** — bootstrap trick or phone-as-AP; rehearse. (High)
2. **Android routes traffic over mobile data when Wi-Fi has no internet** unless the network is user-selected + accepted-unvalidated — airplane mode + Wi-Fi is the reliable state. (High)
3. **FlutterFlow Flutter/Dart version vs package minimums** (record 7.x needs Dart 3.12; flutter_soloud 5.0.0 is 2 days old) — pin `record ^6.2.1`, and test `flutter_soloud` 4.x vs 5.x in Local Run early. (High)
4. **Rive version pin conflict** with FlutterFlow's built-in Rive widget; `rive_native` needs a one-time internet download at build. (Medium)
5. **Echo/self-interruption on speakerphone** despite AEC; add server-side gating and the 500–800 ms post-TTS mic gate; keep headphones handy. (Medium)
6. **iOS**: Local Network prompt timing (foreground only; simulator unsupported), `startStream()` 3 s cold start, ATS/cleartext. Android first is the right call. (Medium)
7. **GPU memory spill into shared memory** → 10× slowdown with no error; use the NVIDIA policy + LM Studio dedicated-memory limit + a startup self-test that measures tok/s. (Medium)
8. **Web build**: mixed-content blocking, `record` web gives float32 at OS sample rate, `flutter_soloud` web needs extra setup — treat web as HTTP-per-turn only. (Medium)
9. **On-device LLM quality/speed on mid-range phones** unproven; make the offline mode's LLM optional with a rule-based fallback. (Medium)
10. **Pricing/plan gating** of code export/CLI and FlutterFlow release breakage (issue #6881) — keep a known-good export zipped. (Low–Medium)

---

## Sources

FlutterFlow (official docs first)
- https://docs.flutterflow.io/concepts/custom-code/
- https://docs.flutterflow.io/concepts/custom-code/custom-widgets/
- https://docs.flutterflow.io/concepts/custom-code/custom-actions/
- https://docs.flutterflow.io/concepts/custom-code/configuration-files/
- https://docs.flutterflow.io/concepts/animations/rive-animation/
- https://docs.flutterflow.io/flutterflow-cli/
- https://docs.flutterflow.io/flutterflow-cli/build/
- https://docs.flutterflow.io/flutterflow-cli/claude-code/
- https://docs.flutterflow.io/flutterflow-cli/exporting
- https://docs.flutterflow.io/testing/local-run/
- https://docs.flutterflow.io/testing/run-your-app/
- https://docs.flutterflow.io/resources/backend-logic/streaming-api
- https://docs.flutterflow.io/resources/backend-logic/rest-api
- https://docs.flutterflow.io/resources/projects/settings/project-setup/
- https://docs.flutterflow.io/resources/projects/settings/general-settings/
- https://docs.flutterflow.io/generated-code/project-structure/
- https://docs.flutterflow.io/sitemap.xml
- https://www.flutterflow.io/pricing
- https://community.flutterflow.io/c/whats-new-in-flutterflow/post/flutter-3-38-5-upgrade-8d1rtf39DD4H2WA
- https://github.com/FlutterFlow/flutterflow-cli
- https://github.com/FlutterFlow/flutterflow-claude
- https://pub.dev/packages/flutterflow_cli
- https://community.flutterflow.io/discussions/post/successfully-connected-websocket-in-flutter-flow---sharing-my-code-and-oNYPdCqJDNRTYS5
- https://community.flutterflow.io/discussions/post/rive-limitations-or-out-of-date-nnHrKJIw0UbrAmK
- https://github.com/FlutterFlow/flutterflow-issues/issues/1846
- https://community.flutterflow.io/ask-the-community/post/rive-dependency-error-warning-nGP82rpiDVzF7Iw
- https://github.com/FlutterFlow/flutterflow-issues/issues/6881 (title only, not fetched)
- https://docs.flutter.dev/release/archive

Flutter audio / transport
- https://pub.dev/packages/record · https://pub.dev/packages/record/changelog · https://pub.dev/packages/record/versions
- https://raw.githubusercontent.com/llfbandit/record/master/record/README.md
- https://github.com/llfbandit/record/issues/604
- https://pub.dev/packages/flutter_sound · https://github.com/Canardoux/flutter_sound/issues/1134
- https://pub.dev/packages/mic_stream · https://pub.dev/packages/sound_stream
- https://pub.dev/packages/web_socket_channel
- https://pub.dev/packages/flutter_webrtc
- https://pub.dev/packages/flutter_pcm_sound
- https://pub.dev/packages/flutter_soloud · https://docs.page/alnitak/flutter_soloud_docs/advanced/streaming
- https://pub.dev/packages/just_audio · https://pub.dev/packages/audio_session
- https://pub.dev/packages/pipecat_flutter
- https://medium.com/@tri.dev.dhm/building-real-time-voice-ai-agents-in-flutter-with-pipecat-6abbc6d223f0
- https://medium.com/@tri.dev.dhm/how-we-built-pluggable-voice-ai-transports-in-flutter-with-pipecat-7ac0b9b7b686
- https://docs.pipecat.ai/api-reference/server/services/transport/small-webrtc
- https://docs.pipecat.ai/client/android/transports/small-webrtc
- https://docs.pipecat.ai/server/services/transport/websocket-server
- https://docs.pipecat.ai/server/services/transport/fastapi-websocket
- https://docs.pipecat.ai/server/services/stt/whisper · https://docs.pipecat.ai/server/services/tts/kokoro
- https://pypi.org/project/pipecat-ai/
- https://source.android.com/docs/core/audio/implement-pre-processing
- https://developer.android.com/reference/android/media/audiofx/AcousticEchoCanceler
- https://barock.dev/2026/04/22/why-your-ios-voice-agent-still-hears-itself
- https://developer.apple.com/documentation/avfaudio/avaudiosession/setprefersechocancelledinput(_:)
- https://github.com/livekit/client-sdk-flutter/issues/689
- https://dev.to/agnihotripushkar/everything-that-can-interrupt-your-microphone-on-android-and-how-to-handle-it-68b

Rive / avatar
- https://pub.dev/packages/rive · https://pub.dev/packages/rive_native
- https://rive.app/docs/runtimes/flutter/flutter · https://rive.app/docs/runtimes/flutter/migration-guide
- https://verygood.ventures/blog/rive-flutter-genui-integration/
- https://dev.to/uianimation/how-to-build-real-time-ai-lip-sync-using-rive-state-machine-viseme-data-26o7
- https://rive.app/marketplace/21097-39720-custom-talking-avatar-real-time-lip-sync-for-your-app/
- https://community.rive.app/c/resources/lip-sync-animation-free-tool
- https://community.rive.app/c/support/can-not-building-on-flutter-with-rive_native
- https://pub.dev/packages/flutter_3d_controller
- https://github.com/met4citizen/TalkingHead
- https://docs.readyplayer.me/ready-player-me/api-reference/avatars/morph-targets/oculus-ovr-libsync

Networking / pairing
- https://learn.microsoft.com/en-au/answers/questions/675210/turn-on-mobile-hotspot-without-any-internet-to-sta
- https://learn.microsoft.com/en-us/answers/a/939293
- https://learn.microsoft.com/en-us/answers/questions/3854040/im-unable-to-use-the-hotspot-on-window11-on-my-lap
- https://learn.microsoft.com/en-us/answers/questions/1342245/it-is-an-issue-that-after-installing-microsoft-km
- https://www.elevenforum.com/t/enable-or-disable-mobile-hotspot-power-saving-in-windows-11.3574/
- https://learn.microsoft.com/en-us/uwp/api/windows.networking.networkoperators.networkoperatortetheringmanager
- https://developer.android.com/develop/connectivity/network-ops/reading-network-state
- https://developer.android.com/develop/connectivity/wifi/wifi-bootstrap
- https://android.googlesource.com/platform/packages/modules/Connectivity/+/refs/heads/main/service/src/com/android/server/connectivity/NetworkRanker.java
- https://developer.android.com/privacy-and-security/security-config
- https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy
- https://developer.apple.com/documentation/bundleresources/information-property-list/nslocalnetworkusagedescription
- https://support.apple.com/en-us/111785
- https://pub.dev/packages/bonsoir · https://pub.dev/packages/nsd · https://python-zeroconf.readthedocs.io/en/latest/
- https://pub.dev/packages/mobile_scanner · https://pub.dev/packages/qr_flutter
- https://developer.android.com/tools/adb
- https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule

Server / GPU / Python
- https://lmstudio.ai/docs/developer/core/headless · https://lmstudio.ai/docs/developer/core/server
- https://lmstudio.ai/docs/cli · https://lmstudio.ai/docs/cli/server-start
- https://lmstudio.ai/blog/lmstudio-v0.3.15 · https://lmstudio.ai/blog/lmstudio-v0.3.10
- https://docs.ollama.com/faq · https://docs.ollama.com/windows
- https://pypi.org/project/torch/ · https://pytorch.org/get-started/previous-versions/ · https://github.com/pytorch/pytorch/releases/latest
- https://docs.astral.sh/uv/guides/integration/pytorch/
- https://nvidia.custhelp.com/app/answers/detail/a_id/5490
- https://learn.microsoft.com/en-us/windows-hardware/drivers/display/gpu-virtual-memory-in-wddm-2-0
- https://pypi.org/project/faster-whisper/ · https://pypi.org/project/kokoro/ · https://pypi.org/project/onnx-asr/
- https://docs.livekit.io/home/self-hosting/local/ · https://api.github.com/repos/livekit/livekit/releases/latest

On-device
- https://pub.dev/packages/sherpa_onnx
- https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html
- https://k2-fsa.github.io/sherpa/onnx/moonshine/models.html
- https://k2-fsa.github.io/sherpa/onnx/pretrained_models/whisper/tiny.en.html
- https://k2-fsa.github.io/sherpa/onnx/flutter/pre-built-app.html
- https://pub.dev/packages/flutter_gemma · https://pub.dev/packages/flutter_gemma_speech
- https://pub.dev/packages/cactus · https://pub.dev/packages/llama_cpp_dart · https://github.com/Telosnex/fllama
- https://pub.dev/packages/whisper_ggml
- https://developers.google.com/edge/litert-lm/overview
- https://developers.google.com/edge/mediapipe/solutions/genai/llm_inference/android
- https://developer.apple.com/documentation/foundationmodels
- https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm · https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm
- https://huggingface.co/google/gemma-3n-E2B-it-litert-lm · https://huggingface.co/litert-community/Gemma3-1B-IT
- https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17
- https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-06-26
- https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8
- https://huggingface.co/csukuangfj/vits-piper-en_US-lessac-medium
- https://huggingface.co/RuiSumida/sherpa-onnx-kokoro-int8-en-v0_19
- https://huggingface.co/R4kSo1997/sherpa-onnx-silero-vad-v5
