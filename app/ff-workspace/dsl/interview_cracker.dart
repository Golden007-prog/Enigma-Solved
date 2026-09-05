/// Interview Cracker — FlutterFlow app built from the BLUEPRINT (§4.1 protocol, §6 avatar, §7 pages).
///
/// Run (from the workspace root, branch interview-cracker):
///   flutterflow ai run dsl/interview_cracker.dart --project-id enigma-solved-ctlkqt --commit-message "Interview Cracker app"
///
/// Everything the phone needs to talk to the laptop lives in custom code:
///   * VoiceLinkHost (custom widget file) — also defines the VoiceLink singleton (WebSocket, mic, playback, events)
///   * InterviewerAvatar (CustomPaint, ten mouth shapes, mood/blink/nod), QuestionCard, CountdownRing,
///     TranscriptTicker, PairScanner, ReportView
///   * custom actions connectVoice / disconnectVoice / cancelRound / fetchReport
/// Pages: PasteJD → Pair → Prep → Room → Report (+ History, hidden for guests).
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

Future<void> main(List<String> args) async {
  final options = _parseCliOptions(args);
  try {
    await flutterFlowAI(
      buildInterviewCracker,
      apiKey: options.apiKey,
      baseUrl: options.baseUrl,
      projectName: options.projectName,
      projectId: options.projectId,
      findOrCreate: options.findOrCreate,
      allowNewProject: options.allowNewProject,
      dryRun: options.dryRun,
      commitMessage: options.commitMessage,
    );
  } catch (error) {
    stderr.writeln('Error: ${formatFlutterFlowAIError(error)}');
    exit(1);
  }
}

// ---------------------------------------------------------------------------
// The app
// ---------------------------------------------------------------------------

void buildInterviewCracker(App app) {
  // ---- theme: warm, calm, fresher-friendly ----------------------------------
  app.themeColor('primary', 0xFF0F6E56);
  app.themeColor('secondary', 0xFF1F3A5F);
  app.themeColor('tertiary', 0xFFE07A2F);
  app.themeColor('alternate', 0xFFE3ECE8);
  app.themeColor('primaryBackground', 0xFFF7F6F2);
  app.themeColor('secondaryBackground', 0xFFFFFFFF);
  app.themeColor('primaryText', 0xFF17201C);
  app.themeColor('secondaryText', 0xFF5B6B64);
  app.themeColor('success', 0xFF2A9D4B);
  app.themeColor('warning', 0xFFE0A100);
  app.themeColor('error', 0xFFC03A2B);
  app.primaryFont('Inter');

  // ---- pub dependencies (pins verified against pub.dev for FlutterFlow's Dart 3.10) ----
  app.pubDependency('record', '6.2.1');
  app.pubDependency('web_socket_channel', '3.0.3');
  app.pubDependency('flutter_soloud', '3.5.4');
  app.pubDependency('audio_session', '0.2.4');
  app.pubDependency('mobile_scanner', '7.4.0');
  app.pubDependency('audioplayers', '^6.1.0');
  app.pubDependency('http', '^1.2.0');

  // ---- app state (master prompt Phase 4 list + the scalars the custom code fills) ----
  app.state('serverHost', string.withDefault(''), persisted: true);
  app.state('serverPort', int_.withDefault(8765), persisted: true);
  app.state('sessionToken', string.withDefault(''), persisted: true);
  app.state('pairingText', string.withDefault(''), persisted: true);
  app.state('sessionId', string.withDefault(''));
  app.state('connectionState', string.withDefault('disconnected'));
  app.state('pressureDial', string.withDefault('realistic'), persisted: true);
  app.state('voiceId', string.withDefault('af_heart'), persisted: true);
  app.state('jdText', string.withDefault(''), persisted: true);
  app.state('currentQuestion', json);
  app.state('currentQuestionId', string.withDefault(''));
  app.state('currentQuestionText', string.withDefault(''));
  app.state('whyCompetency', string.withDefault(''));
  app.state('whyQuote', string.withDefault(''));
  app.state('whyStrategy', string.withDefault(''));
  app.state('whyRung', string.withDefault(''));
  app.state('whyTrigger', string.withDefault(''));
  app.state('timeLimitSeconds', int_.withDefault(0));
  app.state('lastReaction', string.withDefault('neutral'));
  app.state('mood', int_.withDefault(0));
  app.state('isListening', bool_.withDefault(false));
  app.state('isSpeaking', bool_.withDefault(false));
  app.state('countdownSeconds', int_.withDefault(0));
  app.state('reportJson', json);
  app.state('reportUrl', string.withDefault(''));
  app.state('isGuest', bool_.withDefault(true), persisted: true);
  app.state('competencyChips', listOf(string));
  app.state('roleTitle', string.withDefault(''));
  app.state('questionCount', int_.withDefault(8));
  app.state('transcriptTail', string.withDefault(''));
  app.state('roundOver', bool_.withDefault(false));
  app.state('deviceId', string.withDefault(''), persisted: true);

  // ---- custom widgets ---------------------------------------------------------
  app.customWidget(
    'VoiceLinkHost',
    parameters: {'navigateOnEvents': bool_},
    description: 'Status pill; its file also hosts the VoiceLink singleton (WebSocket + mic + playback + events). Set navigateOnEvents on Prep/Room so the first question / report event moves the user on.',
    code: _voiceLinkHostCode,
  );
  app.customWidget(
    'InterviewerAvatar',
    parameters: {'debugCycle': bool_},
    description: 'CustomPaint interviewer: ten mouth shapes driven by viseme events on the playback clock, mood brows, blink, listening tilt, nod (BLUEPRINT §6.1).',
    code: _interviewerAvatarCode,
  );
  app.customWidget(
    'PairScanner',
    parameters: const <String, DslType>{},
    description: 'QR scanner for interviewcracker://pair?h=&p=&t=&v=1; connects VoiceLink on a valid scan.',
    code: _pairScannerCode,
  );
  app.customWidget(
    'QuestionCard',
    parameters: const <String, DslType>{},
    description: 'The current question; tap flips it to the why-trace (competency, JD quote, ladder rung, strategy, trigger).',
    code: _questionCardCode,
  );
  app.customWidget(
    'CountdownRing',
    parameters: const <String, DslType>{},
    description: 'Ring + seconds left for the current question; red under 10 s. Hidden when no time limit.',
    code: _countdownRingCode,
  );
  app.customWidget(
    'TranscriptTicker',
    parameters: const <String, DslType>{},
    description: 'Live single-line caption of what the server heard (stt events) and the listening state.',
    code: _transcriptTickerCode,
  );
  app.customWidget(
    'ReportView',
    parameters: const <String, DslType>{},
    description: 'Renders the evidence-locked report: band, top fixes with tap-to-replay, per-question STAR strip, coverage matrix, delivery metrics.',
    code: _reportViewCode,
  );

  // ---- custom actions (thin wrappers) ------------------------------------------
  app.customAction(
    'connectVoice',
    args: {'pairing': string, 'pressure': string, 'voice': string, 'jd': string},
    returns: bool_,
    description: 'Connect to the laptop server. pairing = "ip:port:token" or interviewcracker://pair?h=&p=&t=&v=1. Sends hello with the JD + pressure dial; true when ready.',
    code: _connectVoiceCode,
  );
  app.customAction(
    'disconnectVoice',
    description: 'Close the voice link and stop mic + playback.',
    code: _disconnectVoiceCode,
  );
  app.customAction(
    'cancelRound',
    description: 'Ask the server to end the round now (report is still generated).',
    code: _cancelRoundCode,
  );
  app.customAction(
    'fetchReport',
    args: {'url': string},
    returns: json,
    description: 'GET the report JSON from the laptop (http://<host>:8765/report/<session>) and store it in App State.',
    code: _fetchReportCode,
  );

  // ---- pages ------------------------------------------------------------------
  app.page(
    'PasteJD',
    description: 'Lobby: paste the JD, pick the pressure dial and voice, start.',
    route: '/',
    isInitial: true,
    body: Scaffold(
      appBar: AppBar(title: 'Interview Cracker'),
      body: Column(
        scrollable: true,
        padding: 20,
        spacing: 14,
        crossAxis: CrossAxis.start,
        children: [
          Text('Paste the job description', style: Styles.titleLarge),
          Text('The interviewer reads it and asks questions grounded in its exact sentences. Nothing leaves your laptop.', style: Styles.bodyMedium, color: Colors.secondaryText),
          TextField(
            label: 'Job description',
            hint: 'Paste the full JD here…',
            name: 'jdField',
            maxLines: 9,
            onChanged: UpdateAppState.set('jdText', TextValue()),
          ),
          Text('Pressure', style: Styles.titleMedium),
          Row(
            spacing: 8,
            children: [
              Button('Warm-up', variant: ButtonVariant.outlined, onTap: UpdateAppState.set('pressureDial', 'warmup')),
              Button('Realistic', variant: ButtonVariant.outlined, onTap: UpdateAppState.set('pressureDial', 'realistic')),
              Button('Tough', variant: ButtonVariant.outlined, onTap: UpdateAppState.set('pressureDial', 'tough')),
            ],
          ),
          Row(spacing: 6, children: [Text('Selected:', color: Colors.secondaryText), Text(AppState('pressureDial'), style: Styles.bodyLarge, color: Colors.primary)]),
          Text('Interviewer voice', style: Styles.titleMedium),
          Row(
            spacing: 8,
            children: [
              Button('Asha (female)', variant: ButtonVariant.outlined, onTap: UpdateAppState.set('voiceId', 'af_heart')),
              Button('Michael (male)', variant: ButtonVariant.outlined, onTap: UpdateAppState.set('voiceId', 'am_michael')),
            ],
          ),
          Row(spacing: 6, children: [Text('Voice:', color: Colors.secondaryText), Text(AppState('voiceId'), color: Colors.primary)]),
          Button(
            'Start interview',
            icon: 'play_arrow',
            width: double.infinity,
            color: Colors.primary,
            textColor: Colors.primaryBackground,
            borderRadius: 14,
            padding: EdgeInsets.symmetric(vertical: 16),
            onTap: If(
              Equals(AppState('connectionState'), 'connected'),
              then: Navigate('Prep'),
              orElse: Navigate('Pair'),
            ),
          ),
          Button('History', variant: ButtonVariant.outlined, width: double.infinity, visible: Not(AppState('isGuest')), onTap: Navigate('History')),
          Text('Guest mode: results stay on this phone and the laptop. Sign in later to sync.', style: Styles.bodySmall, color: Colors.secondaryText, visible: AppState('isGuest')),
        ],
      ),
    ),
  );

  app.page(
    'Pair',
    description: 'Scan the laptop QR (or type ip:port:token) to connect the voice link.',
    route: '/pair',
    body: Scaffold(
      appBar: AppBar(title: 'Pair with the laptop'),
      body: Column(
        scrollable: true,
        padding: 20,
        spacing: 14,
        crossAxis: CrossAxis.start,
        children: [
          Text('Open http://<laptop>:8765/pair on the laptop and scan the QR.', style: Styles.bodyMedium, color: Colors.secondaryText),
          Container(
            width: double.infinity,
            height: 300,
            borderRadius: 16,
            color: Colors.alternate,
            child: CustomWidget(widgetName: 'PairScanner', arguments: const <String, Object?>{}, name: 'PairScannerWidget'),
          ),
          Text('Or type it', style: Styles.titleMedium),
          TextField(
            label: 'ip:port:token',
            hint: '192.168.137.1:8765:abcd…',
            name: 'pairingField',
            onChanged: UpdateAppState.set('pairingText', TextValue()),
          ),
          Button(
            'Connect',
            icon: 'link',
            width: double.infinity,
            color: Colors.primary,
            textColor: Colors.primaryBackground,
            borderRadius: 14,
            onTap: [
              CallCustomAction.named(
                'connectVoice',
                args: {'pairing': string, 'pressure': string, 'voice': string, 'jd': string},
                returnType: bool_,
                arguments: {
                  'pairing': AppState('pairingText'),
                  'pressure': AppState('pressureDial'),
                  'voice': AppState('voiceId'),
                  'jd': AppState('jdText'),
                },
                outputAs: 'connected',
              ),
              If(Equals(AppState('connectionState'), 'connected'), then: Navigate('Prep'), orElse: Snackbar('Could not connect — check the laptop is on the same Wi-Fi and the token is right.')),
            ],
          ),
          Container(width: double.infinity, height: 44, child: CustomWidget(widgetName: 'VoiceLinkHost', arguments: {'navigateOnEvents': false}, name: 'PairStatus')),
          Text('Emulator: use 10.0.2.2:8765:<token>. USB: adb reverse tcp:8765 tcp:8765 then 127.0.0.1:8765:<token>.', style: Styles.bodySmall, color: Colors.secondaryText),
        ],
      ),
    ),
  );

  app.page(
    'Prep',
    description: '20-second "how this works" while the laptop builds the rubric and the first question; shows competency chips (no questions).',
    route: '/prep',
    body: Scaffold(
      appBar: AppBar(title: 'Get ready'),
      body: Column(
        scrollable: true,
        padding: 20,
        spacing: 14,
        crossAxis: CrossAxis.start,
        children: [
          Text('How this works', style: Styles.titleLarge),
          Text('•  One question at a time.', style: Styles.bodyLarge),
          Text('•  No going back, no skipping, no preview.', style: Styles.bodyLarge),
          Text('•  Speak, don’t type. Answer with specifics: what you did, which tool, what number changed.', style: Styles.bodyLarge),
          Divider(),
          Row(spacing: 6, children: [Text('Role:', color: Colors.secondaryText), Text(AppState('roleTitle'), style: Styles.titleMedium)]),
          Text('The panel will ask about:', style: Styles.titleMedium),
          ListView(
            source: AppState('competencyChips'),
            itemBuilder: (item) => Container(
              padding: 10,
              margin: EdgeInsets.only(bottom: 6),
              borderRadius: 10,
              color: Colors.alternate,
              child: Text(item, style: Styles.bodyMedium),
            ),
          ),
          Text('The first question starts automatically when the interviewer is ready.', style: Styles.bodySmall, color: Colors.secondaryText),
          Container(width: double.infinity, height: 44, child: CustomWidget(widgetName: 'VoiceLinkHost', arguments: {'navigateOnEvents': true}, name: 'PrepStatus')),
        ],
      ),
    ),
  );

  app.page(
    'Room',
    description: 'The interview room: avatar, question card (flip for the why-trace), countdown, live caption. No back, no skip.',
    route: '/room',
    body: Scaffold(
      body: Column(
        padding: 12,
        spacing: 10,
        children: [
          Container(
            width: double.infinity,
            height: 320,
            borderRadius: 20,
            color: Colors.alternate,
            child: CustomWidget(widgetName: 'InterviewerAvatar', arguments: {'debugCycle': false}, name: 'Avatar'),
          ),
          Container(width: double.infinity, height: 190, child: CustomWidget(widgetName: 'QuestionCard', arguments: const <String, Object?>{}, name: 'QuestionCardWidget')),
          Row(
            spacing: 10,
            children: [
              Container(width: 90, height: 90, child: CustomWidget(widgetName: 'CountdownRing', arguments: const <String, Object?>{}, name: 'Countdown')),
              Expanded(Container(height: 90, child: CustomWidget(widgetName: 'TranscriptTicker', arguments: const <String, Object?>{}, name: 'Ticker'))),
            ],
          ),
          Container(width: 1, height: 1, child: CustomWidget(widgetName: 'VoiceLinkHost', arguments: {'navigateOnEvents': true}, name: 'RoomLink')),
          Button(
            'End round early',
            variant: ButtonVariant.outlined,
            onTap: CallCustomAction.named('cancelRound', arguments: const <String, Object?>{}),
          ),
        ],
      ),
    ),
  );

  app.page(
    'Report',
    description: 'Evidence-locked report: top-3 fixes with tap-to-replay, STAR strip, coverage matrix, delivery.',
    route: '/report',
    body: Scaffold(
      appBar: AppBar(title: 'Your report'),
      body: Column(
        padding: 12,
        spacing: 10,
        children: [
          Expanded(Container(width: double.infinity, child: CustomWidget(widgetName: 'ReportView', arguments: const <String, Object?>{}, name: 'ReportViewWidget'))),
          Button(
            'New interview',
            icon: 'refresh',
            width: double.infinity,
            color: Colors.primary,
            textColor: Colors.primaryBackground,
            borderRadius: 14,
            onTap: [
              CallCustomAction.named('disconnectVoice', arguments: const <String, Object?>{}),
              Navigate('PasteJD', replaceRoute: true),
            ],
          ),
        ],
      ),
    ),
  );

  app.page(
    'History',
    description: 'Past sessions (Supabase-backed once signed in; hidden for guests).',
    route: '/history',
    body: Scaffold(
      appBar: AppBar(title: 'History'),
      body: Column(
        padding: 20,
        spacing: 12,
        crossAxis: CrossAxis.start,
        children: [
          Text('Your past rounds sync to Supabase when the laptop is online and you are signed in.', style: Styles.bodyMedium, color: Colors.secondaryText),
          Text('Guest rounds live on the laptop: open http://<laptop>:8765/sessions.', style: Styles.bodySmall, color: Colors.secondaryText, visible: AppState('isGuest')),
        ],
      ),
    ),
  );

  // The template HomePage is an untouched placeholder; PasteJD is the initial page. HomePage is removed
  // in a follow-up edit script (removePage) once this push has landed.
}

// ---------------------------------------------------------------------------
// Custom code — VoiceLinkHost (file also defines the VoiceLink singleton)
// ---------------------------------------------------------------------------

const String _voiceLinkHostCode = r'''
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:audio_session/audio_session.dart';
import '/app_state.dart';

/// One event from the laptop (BLUEPRINT §4.1). Binary audio frames are not events.
class VoiceEvent {
  VoiceEvent(this.type, this.data);
  final String type;
  final Map<String, dynamic> data;
}

/// Pairing payload: interviewcracker://pair?h=<ip>&p=8765&t=<token>&v=1  or  ip:port:token
class Pairing {
  Pairing(this.host, this.port, this.token);
  final String host;
  final int port;
  final String token;
  static Pairing? parse(String raw) {
    final s = raw.trim();
    if (s.isEmpty) return null;
    if (s.startsWith('interviewcracker://')) {
      final u = Uri.tryParse(s);
      if (u == null) return null;
      final h = u.queryParameters['h'];
      final p = int.tryParse(u.queryParameters['p'] ?? '8765') ?? 8765;
      final t = u.queryParameters['t'];
      if (h == null || t == null) return null;
      return Pairing(h, p, t);
    }
    final parts = s.split(':');
    if (parts.length >= 3) {
      final p = int.tryParse(parts[1]) ?? 8765;
      return Pairing(parts[0], p, parts.sublist(2).join(':'));
    }
    return null;
  }
}

/// Singleton owning the WebSocket, the microphone stream (640-byte / 20 ms PCM16 16 kHz
/// frames), the 24 kHz playback buffer stream and the broadcast event stream. Survives
/// page navigation. Viseme events are scheduled against the playback clock, never wall time.
class VoiceLink {
  VoiceLink._();
  static final VoiceLink I = VoiceLink._();

  final StreamController<VoiceEvent> _events = StreamController<VoiceEvent>.broadcast();
  Stream<VoiceEvent> get events => _events.stream;
  final ValueNotifier<int> mouth = ValueNotifier<int>(0);
  final ValueNotifier<int> mood = ValueNotifier<int>(0);
  final ValueNotifier<bool> listening = ValueNotifier<bool>(false);
  final ValueNotifier<int> nodTick = ValueNotifier<int>(0);
  final ValueNotifier<String> caption = ValueNotifier<String>('');
  final ValueNotifier<bool> speaking = ValueNotifier<bool>(false);

  WebSocketChannel? _ws;
  StreamSubscription? _wsSub;
  final AudioRecorder _rec = AudioRecorder();
  StreamSubscription<Uint8List>? _micSub;
  final BytesBuilder _carry = BytesBuilder(copy: false);
  static const int kFrameBytes = 640;

  AudioSource? _src;
  SoundHandle? _handle;
  bool _soloudReady = false;
  final List<List<int>> _visemes = <List<int>>[]; // [t_ms, id]
  Timer? _visemeTimer;
  int _lastQuestionIdx = 0;
  Pairing? pairing;
  String state = 'disconnected';
  bool _micRunning = false;

  void _setState(String s) {
    state = s;
    FFAppState().update(() { FFAppState().connectionState = s; });
  }

  Future<bool> connect(Pairing p, {required String jd, required String pressure, required String voice, String? deviceId}) async {
    await disconnect();
    pairing = p;
    _setState('connecting');
    try {
      await _ensureAudio();
      final uri = Uri.parse('ws://${p.host}:${p.port}/ws');
      final ch = WebSocketChannel.connect(uri);
      await ch.ready.timeout(const Duration(seconds: 8));
      _ws = ch;
      final ready = Completer<bool>();
      _wsSub = ch.stream.listen((raw) {
        if (raw is Uint8List || raw is List<int>) {
          _onAudio(raw is Uint8List ? raw : Uint8List.fromList(raw as List<int>));
          return;
        }
        final Map<String, dynamic> m = jsonDecode(raw as String) as Map<String, dynamic>;
        if (m['type'] == 'ready' && !ready.isCompleted) ready.complete(true);
        if (m['type'] == 'error' && m['fatal'] == true && !ready.isCompleted) ready.complete(false);
        _onEvent(m);
      }, onDone: () { _setState('disconnected'); }, onError: (_) { _setState('error'); });
      ch.sink.add(jsonEncode({
        'type': 'hello', 'token': p.token, 'mode': 'interview',
        'in': {'fmt': 'pcm16', 'sr': 16000, 'ch': 1}, 'out': {'fmt': 'pcm16', 'sr': 24000},
        'jd': jd, 'pressure': pressure, 'voice': voice, 'device_id': deviceId,
      }));
      final ok = await ready.future.timeout(const Duration(seconds: 15), onTimeout: () => false);
      if (!ok) { await disconnect(); _setState('error'); return false; }
      _setState('connected');
      await _startMic();
      return true;
    } catch (e) {
      debugPrint('VoiceLink connect failed: $e');
      _setState('error');
      return false;
    }
  }

  Future<void> disconnect() async {
    _visemeTimer?.cancel();
    await _micSub?.cancel(); _micSub = null;
    if (_micRunning) { try { await _rec.stop(); } catch (_) {} _micRunning = false; }
    await _wsSub?.cancel(); _wsSub = null;
    try { await _ws?.sink.close(); } catch (_) {}
    _ws = null;
    _stopPlayback();
    if (state != 'disconnected') _setState('disconnected');
  }

  void sendCancel() { _ws?.sink.add(jsonEncode({'type': 'cancel'})); }
  void sendPing() { _ws?.sink.add(jsonEncode({'type': 'ping', 't': DateTime.now().millisecondsSinceEpoch})); }

  // ------------------------------------------------------------------ audio in
  Future<void> _ensureAudio() async {
    final session = await AudioSession.instance;
    await session.configure(AudioSessionConfiguration(
      avAudioSessionCategory: AVAudioSessionCategory.playAndRecord,
      avAudioSessionCategoryOptions: AVAudioSessionCategoryOptions.defaultToSpeaker | AVAudioSessionCategoryOptions.allowBluetooth,
      avAudioSessionMode: AVAudioSessionMode.voiceChat,
      androidAudioAttributes: const AndroidAudioAttributes(
        contentType: AndroidAudioContentType.speech,
        usage: AndroidAudioUsage.voiceCommunication,
      ),
      androidAudioFocusGainType: AndroidAudioFocusGainType.gain,
    ));
    if (!_soloudReady) {
      await SoLoud.instance.init(sampleRate: 24000, channels: Channels.mono);
      _soloudReady = true;
    }
  }

  Future<void> _startMic() async {
    if (_micRunning) return;
    if (!await _rec.hasPermission()) { debugPrint('mic permission denied'); return; }
    final stream = await _rec.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1,
      echoCancel: true, noiseSuppress: true, autoGain: true,
      androidConfig: AndroidRecordConfig(
        audioSource: AndroidAudioSource.voiceCommunication,
        audioManagerMode: AudioManagerMode.modeInCommunication,
        speakerphone: true,
      ),
      iosConfig: IosRecordConfig(categoryOptions: [IosAudioCategoryOption.defaultToSpeaker, IosAudioCategoryOption.allowBluetooth]),
    ));
    _micRunning = true;
    _micSub = stream.listen((chunk) {
      _carry.add(chunk);
      if (_carry.length < kFrameBytes) return;
      final all = _carry.takeBytes();
      var off = 0;
      while (off + kFrameBytes <= all.length) {
        _ws?.sink.add(Uint8List.sublistView(all, off, off + kFrameBytes));
        off += kFrameBytes;
      }
      if (off < all.length) _carry.add(all.sublist(off));
    });
  }

  // ------------------------------------------------------------------ audio out
  void _startPlayback() {
    if (!_soloudReady) return;
    _stopPlayback();
    _src = SoLoud.instance.setBufferStream(
      maxBufferSizeBytes: 1024 * 1024 * 24,
      bufferingType: BufferingType.released,
      bufferingTimeNeeds: 0.15,
      sampleRate: 24000,
      channels: Channels.mono,
      format: BufferType.s16le,
    );
    _visemes.clear();
    mouth.value = 0;
    speaking.value = true;
    FFAppState().update(() { FFAppState().isSpeaking = true; });
    _visemeTimer?.cancel();
    _visemeTimer = Timer.periodic(const Duration(milliseconds: 25), (_) => _tickVisemes());
  }

  void _onAudio(Uint8List pcm) {
    final src = _src;
    if (src == null) return;
    try {
      SoLoud.instance.addAudioDataStream(src, pcm);
      if (_handle == null) {
        SoLoud.instance.play(src).then((h) => _handle = h);
      }
    } catch (e) {
      debugPrint('addAudioDataStream: $e');
    }
  }

  void _endPlayback() {
    final src = _src;
    if (src != null) { try { SoLoud.instance.setDataIsEnded(src); } catch (_) {} }
    // let the tail play out, then drop the mouth
    Timer(const Duration(milliseconds: 1500), () { if (!speaking.value) mouth.value = 0; });
    speaking.value = false;
    FFAppState().update(() { FFAppState().isSpeaking = false; });
  }

  void _stopPlayback() {
    _visemeTimer?.cancel();
    final src = _src;
    if (src != null) {
      try { SoLoud.instance.setDataIsEnded(src); } catch (_) {}
      try { if (_handle != null) SoLoud.instance.stop(_handle!); } catch (_) {}
      try { SoLoud.instance.disposeSource(src); } catch (_) {}
    }
    _src = null; _handle = null; _visemes.clear(); mouth.value = 0;
  }

  void _tickVisemes() {
    final src = _src;
    if (src == null || _visemes.isEmpty) return;
    int playedMs;
    try { playedMs = SoLoud.instance.getStreamTimeConsumed(src).inMilliseconds; } catch (_) { return; }
    int? id;
    while (_visemes.isNotEmpty && _visemes.first[0] <= playedMs) { id = _visemes.removeAt(0)[1]; }
    if (id != null) mouth.value = id;
  }

  // ------------------------------------------------------------------ events
  void _onEvent(Map<String, dynamic> m) {
    final t = m['type'] as String? ?? '';
    switch (t) {
      case 'ready':
        FFAppState().update(() { FFAppState().sessionId = (m['session'] ?? '').toString(); FFAppState().roundOver = false; });
        break;
      case 'rubric':
        final comps = (m['competencies'] as List? ?? const []).map((c) => (c['name'] ?? '').toString()).toList();
        FFAppState().update(() {
          FFAppState().competencyChips = comps;
          FFAppState().roleTitle = (m['role_title'] ?? '').toString();
          FFAppState().questionCount = (m['n_questions'] as num?)?.toInt() ?? 8;
        });
        break;
      case 'question':
        _lastQuestionIdx++;
        final why = (m['why'] as Map?) ?? const {};
        final trig = why['triggered_by'] as Map?;
        FFAppState().update(() {
          FFAppState().currentQuestion = m;
          FFAppState().currentQuestionId = (m['id'] ?? '').toString();
          FFAppState().currentQuestionText = (m['text'] ?? '').toString();
          FFAppState().whyCompetency = (why['competency_id'] ?? '').toString();
          FFAppState().whyQuote = (why['jd_quote'] ?? '').toString();
          FFAppState().whyStrategy = (why['strategy'] ?? '').toString();
          FFAppState().whyRung = (why['ladder_rung'] ?? '').toString();
          FFAppState().whyTrigger = trig == null ? '' : (trig['quote'] ?? '').toString();
          FFAppState().timeLimitSeconds = (m['time_limit_s'] as num?)?.toInt() ?? 0;
          FFAppState().transcriptTail = '';
        });
        caption.value = '';
        break;
      case 'vad':
        final on = m['state'] == 'speech_start';
        listening.value = on;
        FFAppState().update(() { FFAppState().isListening = on; });
        break;
      case 'stt':
        caption.value = (m['text'] ?? '').toString();
        FFAppState().update(() { FFAppState().transcriptTail = caption.value; });
        break;
      case 'reaction':
        final moodName = (m['mood'] ?? 'neutral').toString();
        const idx = {'neutral': 0, 'interested': 1, 'thinking': 2, 'unimpressed': 3};
        mood.value = idx[moodName] ?? 0;
        if (m['nod'] == true) nodTick.value++;
        FFAppState().update(() { FFAppState().lastReaction = moodName; FFAppState().mood = mood.value; });
        break;
      case 'tts_start':
        _startPlayback();
        break;
      case 'viseme':
        _visemes.add([(m['t_ms'] as num).toInt(), (m['id'] as num).toInt()]);
        break;
      case 'tts_end':
        _endPlayback();
        break;
      case 'interrupt':
        _stopPlayback();
        speaking.value = false;
        FFAppState().update(() { FFAppState().isSpeaking = false; });
        break;
      case 'report':
        FFAppState().update(() { FFAppState().reportUrl = (m['url'] ?? '').toString(); FFAppState().roundOver = true; });
        break;
      default:
        break;
    }
    _events.add(VoiceEvent(t, m));
  }
}

/// Small status pill. With navigateOnEvents it moves Prep → Room on the first question
/// and Room → Report on the report event (the server owns the state machine).
class VoiceLinkHost extends StatefulWidget {
  const VoiceLinkHost({super.key, this.width, this.height, this.navigateOnEvents = false});
  final double? width;
  final double? height;
  final bool navigateOnEvents;
  @override
  State<VoiceLinkHost> createState() => _VoiceLinkHostState();
}

class _VoiceLinkHostState extends State<VoiceLinkHost> {
  StreamSubscription<VoiceEvent>? _sub;
  String _state = VoiceLink.I.state;

  @override
  void initState() {
    super.initState();
    _sub = VoiceLink.I.events.listen((ev) {
      if (!mounted) return;
      setState(() { _state = VoiceLink.I.state; });
      if (!widget.navigateOnEvents) return;
      final route = GoRouterState.of(context).name ?? '';
      if (ev.type == 'question' && route != 'Room') {
        context.goNamed('Room');
      } else if (ev.type == 'report' && route != 'Report') {
        context.goNamed('Report');
      }
    });
  }

  @override
  void dispose() { _sub?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final s = VoiceLink.I.state;
    final color = s == 'connected' ? const Color(0xFF2A9D4B) : s == 'connecting' ? const Color(0xFFE0A100) : s == 'error' ? const Color(0xFFC03A2B) : const Color(0xFF8A9A93);
    return SizedBox(
      width: widget.width, height: widget.height,
      child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 8),
        Text(s == 'connected' ? 'Connected to the laptop' : s == 'connecting' ? 'Connecting…' : s == 'error' ? 'Connection failed' : 'Not connected', style: TextStyle(color: color, fontWeight: FontWeight.w600)),
      ]),
    );
  }
}
''';

// ---------------------------------------------------------------------------
// InterviewerAvatar — CustomPaint puppet (BLUEPRINT §6.1 contract: mouth 0–9, mood 0–3, listening, nod)
// ---------------------------------------------------------------------------

const String _interviewerAvatarCode = r'''
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import '/custom_code/widgets/voice_link_host.dart';

class InterviewerAvatar extends StatefulWidget {
  const InterviewerAvatar({super.key, this.width, this.height, this.debugCycle = false});
  final double? width;
  final double? height;
  final bool debugCycle;
  @override
  State<InterviewerAvatar> createState() => _InterviewerAvatarState();
}

class _InterviewerAvatarState extends State<InterviewerAvatar> with TickerProviderStateMixin {
  late final AnimationController _blink;   // 0..1, fires every 3–6 s
  late final AnimationController _nod;     // one-shot
  Timer? _blinkTimer;
  Timer? _cycle;
  int _mouth = 0;
  int _mood = 0;
  bool _listening = false;
  final math.Random _rng = math.Random();

  @override
  void initState() {
    super.initState();
    _blink = AnimationController(vsync: this, duration: const Duration(milliseconds: 160));
    _nod = AnimationController(vsync: this, duration: const Duration(milliseconds: 520));
    _scheduleBlink();
    final vl = VoiceLink.I;
    vl.mouth.addListener(_onMouth);
    vl.mood.addListener(_onMood);
    vl.listening.addListener(_onListening);
    vl.nodTick.addListener(_onNod);
    _mood = vl.mood.value; _listening = vl.listening.value;
    if (widget.debugCycle) {
      _cycle = Timer.periodic(const Duration(milliseconds: 83), (_) => setState(() => _mouth = (_mouth + 1) % 10));
    }
  }

  void _onMouth() { if (mounted && _mouth != VoiceLink.I.mouth.value) setState(() => _mouth = VoiceLink.I.mouth.value); }
  void _onMood() { if (mounted) setState(() => _mood = VoiceLink.I.mood.value); }
  void _onListening() { if (mounted) setState(() => _listening = VoiceLink.I.listening.value); }
  void _onNod() { if (mounted) _nod.forward(from: 0); }

  void _scheduleBlink() {
    _blinkTimer = Timer(Duration(milliseconds: 3000 + _rng.nextInt(3000)), () async {
      if (!mounted) return;
      await _blink.forward(from: 0);
      await _blink.reverse();
      _scheduleBlink();
    });
  }

  @override
  void dispose() {
    _blinkTimer?.cancel(); _cycle?.cancel();
    final vl = VoiceLink.I;
    vl.mouth.removeListener(_onMouth); vl.mood.removeListener(_onMood);
    vl.listening.removeListener(_onListening); vl.nodTick.removeListener(_onNod);
    _blink.dispose(); _nod.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width, height: widget.height,
      child: AnimatedBuilder(
        animation: Listenable.merge([_blink, _nod]),
        builder: (context, _) => CustomPaint(
          painter: _AvatarPainter(mouth: _mouth, mood: _mood, listening: _listening, blink: _blink.value, nod: math.sin(_nod.value * math.pi) * (1 - _nod.value * 0.5)),
        ),
      ),
    );
  }
}

class _AvatarPainter extends CustomPainter {
  _AvatarPainter({required this.mouth, required this.mood, required this.listening, required this.blink, required this.nod});
  final int mouth; final int mood; final bool listening; final double blink; final double nod;

  static const Color skin = Color(0xFFE8B98A);
  static const Color skinDark = Color(0xFFC98F5E);
  static const Color hair = Color(0xFF2B1E17);
  static const Color shirt = Color(0xFF1F3A5F);
  static const Color lip = Color(0xFF9E3B3B);
  static const Color mouthIn = Color(0xFF4A1E1E);
  static const Color teeth = Color(0xFFF7F3EA);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final cx = w / 2;
    final scale = math.min(w, h) / 320.0;
    canvas.save();
    // head tilt when listening, nod = small vertical dip
    final tilt = listening ? -0.06 : 0.0;
    canvas.translate(cx, h * 0.52 + nod * 10 * scale);
    canvas.rotate(tilt);
    canvas.scale(scale);
    canvas.translate(0, -0.52 * 320);
    final cy = 165.0;

    // shoulders / shirt
    final shirtPath = Path()
      ..moveTo(-150, 330)..quadraticBezierTo(-140, 240, -60, 235)..lineTo(60, 235)..quadraticBezierTo(140, 240, 150, 330)..close();
    canvas.drawPath(shirtPath, Paint()..color = shirt);
    // neck
    canvas.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(-26, 210, 52, 40), const Radius.circular(10)), Paint()..color = skinDark);
    // head
    final head = RRect.fromRectAndRadius(Rect.fromCenter(center: Offset(0, cy), width: 150, height: 180), const Radius.circular(70));
    canvas.drawRRect(head, Paint()..color = skin);
    // hair block
    final hairPath = Path()
      ..moveTo(-78, cy - 40)..quadraticBezierTo(-80, cy - 110, 0, cy - 112)..quadraticBezierTo(80, cy - 110, 78, cy - 40)
      ..lineTo(60, cy - 40)..quadraticBezierTo(40, cy - 78, 0, cy - 80)..quadraticBezierTo(-40, cy - 78, -60, cy - 40)..close();
    canvas.drawPath(hairPath, Paint()..color = hair);
    // ears
    canvas.drawCircle(Offset(-76, cy), 14, Paint()..color = skinDark);
    canvas.drawCircle(Offset(76, cy), 14, Paint()..color = skinDark);

    // brows: angle by mood (0 neutral, 1 interested = raised, 2 thinking = one up, 3 unimpressed = flat/low)
    final browPaint = Paint()..color = hair..strokeWidth = 6..strokeCap = StrokeCap.round..style = PaintingStyle.stroke;
    double lyL = cy - 42, lyR = cy - 42, angL = 0, angR = 0;
    switch (mood) {
      case 1: lyL -= 8; lyR -= 8; angL = -0.15; angR = 0.15; break;
      case 2: lyL -= 10; angL = -0.35; angR = 0.05; break;
      case 3: lyL += 4; lyR += 4; angL = 0.2; angR = -0.2; break;
    }
    _brow(canvas, browPaint, Offset(-32, lyL), angL);
    _brow(canvas, browPaint, Offset(32, lyR), angR);

    // eyes with blink
    final eyeH = 12.0 * (1 - blink) + 1.0;
    for (final ex in [-32.0, 32.0]) {
      canvas.drawOval(Rect.fromCenter(center: Offset(ex, cy - 18), width: 26, height: eyeH * 2), Paint()..color = Colors.white);
      if (blink < 0.7) {
        final look = listening ? 2.0 : 0.0;
        canvas.drawCircle(Offset(ex + look, cy - 18), 6.5 * (1 - blink), Paint()..color = const Color(0xFF2B1E17));
        canvas.drawCircle(Offset(ex + look + 2, cy - 20), 2 * (1 - blink), Paint()..color = Colors.white);
      }
    }
    // nose
    canvas.drawPath(Path()..moveTo(0, cy - 4)..lineTo(-7, cy + 14)..lineTo(7, cy + 14), Paint()..color = skinDark..style = PaintingStyle.stroke..strokeWidth = 3..strokeCap = StrokeCap.round);

    // mouth — ten shapes, instant switches
    _mouth(canvas, Offset(0, cy + 44), mouth);
    canvas.restore();

    // listening indicator ring (subtle)
    if (listening) {
      canvas.drawCircle(Offset(w - 22, 22), 8, Paint()..color = const Color(0xFF2A9D4B));
    }
  }

  void _brow(Canvas c, Paint p, Offset center, double angle) {
    c.save(); c.translate(center.dx, center.dy); c.rotate(angle);
    c.drawLine(const Offset(-16, 0), const Offset(16, 0), p);
    c.restore();
  }

  void _mouth(Canvas c, Offset o, int id) {
    final lipP = Paint()..color = lip;
    final inP = Paint()..color = mouthIn;
    final teethP = Paint()..color = teeth;
    switch (id) {
      case 0: // rest: soft closed line
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 46, height: 7), const Radius.circular(4)), lipP);
        break;
      case 1: // M/B/P: pressed lips
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 40, height: 10), const Radius.circular(5)), lipP);
        c.drawLine(Offset(o.dx - 18, o.dy), Offset(o.dx + 18, o.dy), Paint()..color = mouthIn..strokeWidth = 1.5);
        break;
      case 2: // F/V: upper teeth on lower lip
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 44, height: 12), const Radius.circular(6)), lipP);
        c.drawRect(Rect.fromCenter(center: Offset(o.dx, o.dy - 2), width: 30, height: 5), teethP);
        break;
      case 3: // TH: slight open, tongue tip
        c.drawOval(Rect.fromCenter(center: o, width: 42, height: 16), lipP);
        c.drawOval(Rect.fromCenter(center: o, width: 30, height: 8), inP);
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy + 1), width: 14, height: 6), Paint()..color = const Color(0xFFD96A6A));
        break;
      case 4: // L: open, tongue up
        c.drawOval(Rect.fromCenter(center: o, width: 40, height: 22), lipP);
        c.drawOval(Rect.fromCenter(center: o, width: 30, height: 14), inP);
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy - 3), width: 12, height: 8), Paint()..color = const Color(0xFFD96A6A));
        break;
      case 5: // D/T/N/S/Z: teeth together
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 46, height: 14), const Radius.circular(7)), lipP);
        c.drawRect(Rect.fromCenter(center: o, width: 34, height: 6), teethP);
        break;
      case 6: // R: rounded small
        c.drawOval(Rect.fromCenter(center: o, width: 30, height: 18), lipP);
        c.drawOval(Rect.fromCenter(center: o, width: 18, height: 10), inP);
        break;
      case 7: // Ah: wide open
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy + 4), width: 44, height: 34), lipP);
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy + 5), width: 34, height: 26), inP);
        c.drawRect(Rect.fromCenter(center: Offset(o.dx, o.dy - 6), width: 26, height: 5), teethP);
        break;
      case 8: // Ee: wide, thin
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 58, height: 16), const Radius.circular(8)), lipP);
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 46, height: 8), const Radius.circular(4)), inP);
        c.drawRect(Rect.fromCenter(center: Offset(o.dx, o.dy - 1), width: 40, height: 4), teethP);
        break;
      case 9: // Oh/Oo: round
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy + 2), width: 28, height: 28), lipP);
        c.drawOval(Rect.fromCenter(center: Offset(o.dx, o.dy + 2), width: 16, height: 18), inP);
        break;
      default:
        c.drawRRect(RRect.fromRectAndRadius(Rect.fromCenter(center: o, width: 46, height: 7), const Radius.circular(4)), lipP);
    }
  }

  @override
  bool shouldRepaint(covariant _AvatarPainter old) =>
      old.mouth != mouth || old.mood != mood || old.listening != listening || old.blink != blink || old.nod != nod;
}
''';

// ---------------------------------------------------------------------------
// PairScanner — QR (mobile_scanner 7.4.0)
// ---------------------------------------------------------------------------

const String _pairScannerCode = r'''
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import '/app_state.dart';
import '/custom_code/widgets/voice_link_host.dart';

class PairScanner extends StatefulWidget {
  const PairScanner({super.key, this.width, this.height});
  final double? width;
  final double? height;
  @override
  State<PairScanner> createState() => _PairScannerState();
}

class _PairScannerState extends State<PairScanner> {
  final MobileScannerController _ctl = MobileScannerController(detectionSpeed: DetectionSpeed.noDuplicates, formats: const [BarcodeFormat.qrCode]);
  bool _busy = false;
  String _status = 'Point the camera at the QR on the laptop';

  @override
  void dispose() { _ctl.dispose(); super.dispose(); }

  Future<void> _onDetect(BarcodeCapture cap) async {
    if (_busy) return;
    for (final b in cap.barcodes) {
      final raw = b.rawValue;
      final p = raw == null ? null : Pairing.parse(raw);
      if (p == null) continue;
      _busy = true;
      setState(() => _status = 'Connecting to ${p.host}:${p.port}…');
      FFAppState().update(() {
        FFAppState().serverHost = p.host; FFAppState().serverPort = p.port; FFAppState().sessionToken = p.token;
        FFAppState().pairingText = '${p.host}:${p.port}:${p.token}';
      });
      final ok = await VoiceLink.I.connect(p, jd: FFAppState().jdText, pressure: FFAppState().pressureDial, voice: FFAppState().voiceId, deviceId: FFAppState().deviceId);
      if (!mounted) return;
      if (ok) {
        await _ctl.stop();
        context.goNamed('Prep');
      } else {
        setState(() { _status = 'Could not connect. Same Wi-Fi? Server running?'; _busy = false; });
      }
      break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width, height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Stack(fit: StackFit.expand, children: [
          MobileScanner(controller: _ctl, onDetect: _onDetect, errorBuilder: (c, e) => Center(child: Padding(padding: const EdgeInsets.all(16), child: Text('Camera unavailable (${e.errorCode.name}). Type the code below instead.', textAlign: TextAlign.center)))),
          Positioned(left: 0, right: 0, bottom: 0, child: Container(color: Colors.black54, padding: const EdgeInsets.all(8), child: Text(_status, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)))),
        ]),
      ),
    );
  }
}
''';

// ---------------------------------------------------------------------------
// QuestionCard — tap to flip to the why-trace
// ---------------------------------------------------------------------------

const String _questionCardCode = r'''
import 'dart:async';
import 'package:flutter/material.dart';
import '/custom_code/widgets/voice_link_host.dart';

class QuestionCard extends StatefulWidget {
  const QuestionCard({super.key, this.width, this.height});
  final double? width;
  final double? height;
  @override
  State<QuestionCard> createState() => _QuestionCardState();
}

class _QuestionCardState extends State<QuestionCard> {
  bool _flipped = false;
  Map<String, dynamic> _q = const {};
  StreamSubscription<VoiceEvent>? _sub;

  @override
  void initState() {
    super.initState();
    _sub = VoiceLink.I.events.listen((ev) {
      if (ev.type == 'question' && mounted) setState(() { _q = ev.data; _flipped = false; });
    });
  }
  @override
  void dispose() { _sub?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final why = (_q['why'] as Map?) ?? const {};
    final trig = why['triggered_by'] as Map?;
    final text = (_q['text'] ?? 'Waiting for the interviewer…').toString();
    final id = (_q['id'] ?? '').toString();
    return GestureDetector(
      onTap: () => setState(() => _flipped = !_flipped),
      child: Container(
        width: widget.width, height: widget.height,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: _flipped ? const Color(0xFF1F3A5F) : Colors.white, borderRadius: BorderRadius.circular(18), boxShadow: const [BoxShadow(color: Color(0x22000000), blurRadius: 10, offset: Offset(0, 4))]),
        child: _flipped
            ? SingleChildScrollView(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Why I asked this', style: const TextStyle(color: Colors.white70, fontSize: 12, letterSpacing: 1)),
                const SizedBox(height: 6),
                Text('From your JD: “${why['jd_quote'] ?? ''}”', style: const TextStyle(color: Colors.white, fontSize: 15, fontStyle: FontStyle.italic)),
                const SizedBox(height: 8),
                Text('${why['competency_id'] ?? ''} · ${why['ladder_rung'] ?? ''} · ${why['strategy'] ?? ''}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
                if (trig != null) Padding(padding: const EdgeInsets.only(top: 6), child: Text('You said: “${trig['quote']}” at ${(trig['t'] as List?)?.first ?? ''}s', style: const TextStyle(color: Color(0xFFFFD27A), fontSize: 13))),
              ]))
            : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text(id.isEmpty ? '' : id, style: const TextStyle(color: Color(0xFF0F6E56), fontWeight: FontWeight.w700)),
                  const Spacer(),
                  const Text('tap for why', style: TextStyle(color: Color(0xFF8A9A93), fontSize: 11)),
                ]),
                const SizedBox(height: 6),
                Expanded(child: SingleChildScrollView(child: Text(text, style: const TextStyle(fontSize: 18, height: 1.3, color: Color(0xFF17201C))))),
              ]),
      ),
    );
  }
}
''';

// ---------------------------------------------------------------------------
// CountdownRing
// ---------------------------------------------------------------------------

const String _countdownRingCode = r'''
import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import '/custom_code/widgets/voice_link_host.dart';

class CountdownRing extends StatefulWidget {
  const CountdownRing({super.key, this.width, this.height});
  final double? width;
  final double? height;
  @override
  State<CountdownRing> createState() => _CountdownRingState();
}

class _CountdownRingState extends State<CountdownRing> {
  StreamSubscription<VoiceEvent>? _sub;
  Timer? _tick;
  int _limit = 0;
  DateTime? _startsAt;   // when the interviewer stops speaking the clock starts
  bool _armed = false;

  @override
  void initState() {
    super.initState();
    _sub = VoiceLink.I.events.listen((ev) {
      if (ev.type == 'question') { _limit = (ev.data['time_limit_s'] as num?)?.toInt() ?? 0; _armed = true; _startsAt = null; }
      if (ev.type == 'tts_end' && _armed) { _startsAt = DateTime.now(); _armed = false; }
      if (ev.type == 'vad' && ev.data['state'] == 'speech_end') { _startsAt = null; _limit = 0; }
      if (mounted) setState(() {});
    });
    _tick = Timer.periodic(const Duration(milliseconds: 250), (_) { if (mounted && _startsAt != null) setState(() {}); });
  }
  @override
  void dispose() { _sub?.cancel(); _tick?.cancel(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    if (_limit <= 0) return SizedBox(width: widget.width, height: widget.height, child: const Center(child: Icon(Icons.timer_off_outlined, color: Color(0xFF8A9A93))));
    final elapsed = _startsAt == null ? 0.0 : DateTime.now().difference(_startsAt!).inMilliseconds / 1000.0;
    final left = math.max(0.0, _limit - elapsed);
    final frac = (left / _limit).clamp(0.0, 1.0);
    final warn = left <= 10;
    return SizedBox(
      width: widget.width, height: widget.height,
      child: CustomPaint(
        painter: _RingPainter(frac, warn ? const Color(0xFFC03A2B) : const Color(0xFF0F6E56)),
        child: Center(child: Text('${left.ceil()}', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: warn ? const Color(0xFFC03A2B) : const Color(0xFF17201C)))),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter(this.frac, this.color);
  final double frac; final Color color;
  @override
  void paint(Canvas c, Size s) {
    final r = math.min(s.width, s.height) / 2 - 6;
    final center = Offset(s.width / 2, s.height / 2);
    c.drawCircle(center, r, Paint()..color = const Color(0xFFE3ECE8)..style = PaintingStyle.stroke..strokeWidth = 8);
    c.drawArc(Rect.fromCircle(center: center, radius: r), -math.pi / 2, 2 * math.pi * frac, false, Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 8..strokeCap = StrokeCap.round);
  }
  @override
  bool shouldRepaint(covariant _RingPainter old) => old.frac != frac || old.color != color;
}
''';

// ---------------------------------------------------------------------------
// TranscriptTicker
// ---------------------------------------------------------------------------

const String _transcriptTickerCode = r'''
import 'package:flutter/material.dart';
import '/custom_code/widgets/voice_link_host.dart';

class TranscriptTicker extends StatelessWidget {
  const TranscriptTicker({super.key, this.width, this.height});
  final double? width;
  final double? height;
  @override
  Widget build(BuildContext context) {
    final vl = VoiceLink.I;
    return SizedBox(
      width: width, height: height,
      child: AnimatedBuilder(
        animation: Listenable.merge([vl.caption, vl.listening, vl.speaking]),
        builder: (context, _) {
          final listening = vl.listening.value; final speaking = vl.speaking.value;
          final label = speaking ? 'Interviewer is speaking' : listening ? 'I’m listening…' : 'Your turn — speak when ready';
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(color: const Color(0xFFF7F6F2), borderRadius: BorderRadius.circular(14), border: Border.all(color: listening ? const Color(0xFF2A9D4B) : const Color(0xFFE3ECE8), width: 2)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.center, children: [
              Row(children: [
                Icon(speaking ? Icons.record_voice_over : listening ? Icons.mic : Icons.mic_none, size: 18, color: listening ? const Color(0xFF2A9D4B) : const Color(0xFF5B6B64)),
                const SizedBox(width: 6),
                Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF5B6B64))),
              ]),
              const SizedBox(height: 4),
              Text(vl.caption.value.isEmpty ? '…' : vl.caption.value, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, color: Color(0xFF17201C))),
            ]),
          );
        },
      ),
    );
  }
}
''';

// ---------------------------------------------------------------------------
// ReportView — fetches /report/<session> and renders it; tap a quote to replay the clip
// ---------------------------------------------------------------------------

const String _reportViewCode = r'''
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:audioplayers/audioplayers.dart';
import '/app_state.dart';

class ReportView extends StatefulWidget {
  const ReportView({super.key, this.width, this.height});
  final double? width;
  final double? height;
  @override
  State<ReportView> createState() => _ReportViewState();
}

class _ReportViewState extends State<ReportView> {
  Map<String, dynamic>? _data;
  String? _error;
  final AudioPlayer _player = AudioPlayer();

  @override
  void initState() { super.initState(); _load(); }
  @override
  void dispose() { _player.dispose(); super.dispose(); }

  Future<void> _load() async {
    final url = FFAppState().reportUrl;
    if (url.isEmpty) { setState(() => _error = 'No report yet.'); return; }
    try {
      final r = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 10));
      if (r.statusCode != 200) throw Exception('HTTP ${r.statusCode}');
      final d = jsonDecode(r.body) as Map<String, dynamic>;
      FFAppState().update(() { FFAppState().reportJson = d['report']; });
      if (mounted) setState(() => _data = d);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load the report: $e');
    }
  }

  Future<void> _play(String? clipUrl, double t0) async {
    if (clipUrl == null) return;
    await _player.stop();
    await _player.play(UrlSource(clipUrl), position: Duration(milliseconds: (t0 * 1000).round()));
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) return Center(child: Padding(padding: const EdgeInsets.all(16), child: Text(_error!, textAlign: TextAlign.center)));
    final d = _data;
    if (d == null) return const Center(child: CircularProgressIndicator());
    final rep = (d['report'] as Map?) ?? const {};
    final turns = <int, Map>{ for (final t in (d['turns'] as List? ?? const [])) (t['idx'] as num).toInt(): t as Map };
    final fixes = (rep['top_fixes'] as List? ?? const []);
    final perQ = (rep['per_question'] as List? ?? const []);
    final cov = ((rep['coverage_matrix'] as Map?)?['rows'] as List? ?? const []);
    final delivery = (rep['delivery'] as Map?) ?? const {};
    TextStyle h(double s) => TextStyle(fontSize: s, fontWeight: FontWeight.w700, color: const Color(0xFF17201C));
    return SizedBox(
      width: widget.width, height: widget.height,
      child: ListView(padding: const EdgeInsets.all(4), children: [
        Container(padding: const EdgeInsets.all(14), decoration: BoxDecoration(color: const Color(0xFF1F3A5F), borderRadius: BorderRadius.circular(16)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('OVERALL', style: TextStyle(color: Colors.white70, fontSize: 11, letterSpacing: 1.2)),
          Text((rep['overall_band'] ?? '—').toString(), style: const TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text((rep['band_mover'] ?? '').toString(), style: const TextStyle(color: Color(0xFFFFD27A), fontSize: 14)),
        ])),
        const SizedBox(height: 14),
        Text('Top fixes', style: h(18)),
        const SizedBox(height: 6),
        for (final f in fixes) _fixCard(f as Map, turns),
        const SizedBox(height: 14),
        Text('Per question', style: h(18)),
        const SizedBox(height: 6),
        for (final q in perQ) _starRow(q as Map, turns),
        const SizedBox(height: 14),
        Text('Coverage', style: h(18)),
        const SizedBox(height: 6),
        for (final r in cov) _covRow(r as Map),
        const SizedBox(height: 14),
        Text('Delivery', style: h(18)),
        const SizedBox(height: 6),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _chip('WPM', delivery['wpm']), _chip('Pauses >1s', delivery['pause_count']), _chip('Hedges', delivery['hedge_count']),
          _chip('First word (s)', delivery['latency_to_first_word_s']), _chip('Monotone', delivery['monotone']),
        ]),
        const SizedBox(height: 24),
      ]),
    );
  }

  Widget _fixCard(Map f, Map<int, Map> turns) {
    final aid = (f['answer_id'] ?? 'A0').toString();
    final idx = int.tryParse(aid.substring(1)) ?? 0;
    final clip = turns[idx]?['clip_url']?.toString();
    final t = (f['t'] as List?) ?? const [0, 0];
    return Container(margin: const EdgeInsets.only(bottom: 10), padding: const EdgeInsets.all(12), decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: const Color(0xFFE3ECE8))), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text((f['behaviour'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
      const SizedBox(height: 6),
      InkWell(onTap: () => _play(clip, (t.first as num).toDouble()), child: Row(children: [
        Icon(clip == null ? Icons.format_quote : Icons.play_circle_fill, color: const Color(0xFF0F6E56)),
        const SizedBox(width: 6),
        Expanded(child: Text('“${f['quote'] ?? ''}”  ($aid, ${(t.first as num).toStringAsFixed(1)}s)', style: const TextStyle(fontStyle: FontStyle.italic, color: Color(0xFF1F3A5F)))),
      ])),
      const SizedBox(height: 6),
      Text((f['why_it_matters'] ?? '').toString(), style: const TextStyle(color: Color(0xFF5B6B64))),
      const SizedBox(height: 6),
      Text('Stronger: ${f['stronger_version'] ?? ''}', style: const TextStyle(color: Color(0xFF0F6E56))),
    ]));
  }

  Widget _starRow(Map q, Map<int, Map> turns) {
    final star = (q['star'] as Map?) ?? const {};
    Widget pill(String k) { final on = star[k] == true; return Container(margin: const EdgeInsets.only(right: 4), padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3), decoration: BoxDecoration(color: on ? const Color(0xFF2A9D4B) : const Color(0xFFE3ECE8), borderRadius: BorderRadius.circular(8)), child: Text(k, style: TextStyle(color: on ? Colors.white : const Color(0xFF5B6B64), fontWeight: FontWeight.w700))); }
    final aid = (q['answer_id'] ?? '').toString();
    final idx = int.tryParse(aid.length > 1 ? aid.substring(1) : '') ?? 0;
    final question = (turns[idx]?['question'] as Map?)?['text']?.toString() ?? '';
    return Container(margin: const EdgeInsets.only(bottom: 8), padding: const EdgeInsets.all(10), decoration: BoxDecoration(color: const Color(0xFFF7F6F2), borderRadius: BorderRadius.circular(12)), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(question, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
      const SizedBox(height: 6),
      Row(children: [pill('S'), pill('T'), pill('A'), pill('R'), const Spacer(), Text((q['verdict'] ?? '').toString(), style: const TextStyle(color: Color(0xFF5B6B64)))]),
    ]));
  }

  Widget _covRow(Map r) {
    final cells = (r['cells'] as List? ?? const []);
    final must = r['priority'] == 'must_have';
    return Padding(padding: const EdgeInsets.only(bottom: 8), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('${must ? '★ ' : ''}${r['name'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w600)),
      Wrap(spacing: 6, runSpacing: 4, children: [for (final c in cells) Container(padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2), decoration: BoxDecoration(color: c['level'] == 'strong' ? const Color(0xFF2A9D4B) : c['level'] == 'weak' ? const Color(0xFFE0A100) : const Color(0xFFE3ECE8), borderRadius: BorderRadius.circular(8)), child: Text('${c['evidence_item']}', style: TextStyle(fontSize: 12, color: c['level'] == 'none' ? const Color(0xFF5B6B64) : Colors.white)))]),
    ]));
  }

  Widget _chip(String label, Object? v) => Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6), decoration: BoxDecoration(color: const Color(0xFFE3ECE8), borderRadius: BorderRadius.circular(10)), child: Text('$label: ${v ?? '—'}'));
}
''';

// ---------------------------------------------------------------------------
// Custom actions
// ---------------------------------------------------------------------------

const String _connectVoiceCode = r'''
import 'dart:math';
import '/app_state.dart';
import '/custom_code/widgets/voice_link_host.dart';

Future<bool> connectVoice(String pairing, String pressure, String voice, String jd) async {
  final p = Pairing.parse(pairing);
  if (p == null) {
    FFAppState().update(() { FFAppState().connectionState = 'error'; });
    return false;
  }
  if (FFAppState().deviceId.length < 32) {
    final rnd = Random.secure();
    final id = List.generate(32, (_) => rnd.nextInt(16).toRadixString(16)).join();
    FFAppState().update(() { FFAppState().deviceId = id; });
  }
  FFAppState().update(() {
    FFAppState().serverHost = p.host; FFAppState().serverPort = p.port; FFAppState().sessionToken = p.token;
  });
  return VoiceLink.I.connect(p, jd: jd, pressure: pressure, voice: voice, deviceId: FFAppState().deviceId);
}
''';

const String _disconnectVoiceCode = r'''
import '/custom_code/widgets/voice_link_host.dart';

Future<void> disconnectVoice() async {
  await VoiceLink.I.disconnect();
}
''';

const String _cancelRoundCode = r'''
import '/custom_code/widgets/voice_link_host.dart';

Future<void> cancelRound() async {
  VoiceLink.I.sendCancel();
}
''';

const String _fetchReportCode = r'''
import 'dart:convert';
import 'package:http/http.dart' as http;
import '/app_state.dart';

Future<dynamic> fetchReport(String url) async {
  if (url.isEmpty) return null;
  final r = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 10));
  if (r.statusCode != 200) return null;
  final d = jsonDecode(r.body);
  FFAppState().update(() { FFAppState().reportJson = d is Map ? d['report'] : d; });
  return d;
}
''';

// ---------------------------------------------------------------------------
// CLI plumbing (same as dsl/edit.dart)
// ---------------------------------------------------------------------------

final class _CliOptions {
  const _CliOptions({this.apiKey, this.baseUrl, this.projectName, this.projectId, this.findOrCreate = false, this.allowNewProject = false, this.dryRun = false, this.commitMessage});
  final String? apiKey;
  final String? baseUrl;
  final String? projectName;
  final String? projectId;
  final bool findOrCreate;
  final bool allowNewProject;
  final bool dryRun;
  final String? commitMessage;
}

_CliOptions _parseCliOptions(List<String> args) {
  String? apiKey, baseUrl, projectName, projectId, commitMessage;
  var findOrCreate = false, allowNewProject = false, dryRun = false;
  for (var i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--api-key': apiKey = args[++i];
      case '--base-url': baseUrl = args[++i];
      case '--project-name': projectName = args[++i];
      case '--project-id': projectId = args[++i];
      case '--commit-message': commitMessage = args[++i];
      case '--find-or-create': findOrCreate = true;
      case '--allow-new-project': allowNewProject = true;
      case '--dry-run': dryRun = true;
      case '--help' || '-h':
        stdout.writeln('Usage: flutterflow ai run dsl/interview_cracker.dart --project-id <id> --commit-message <msg>');
        exit(0);
      default:
        stderr.writeln('Unknown option: ${args[i]}');
        exit(64);
    }
  }
  return _CliOptions(apiKey: apiKey, baseUrl: baseUrl, projectName: projectName, projectId: projectId, findOrCreate: findOrCreate, allowNewProject: allowNewProject, dryRun: dryRun, commitMessage: commitMessage);
}
