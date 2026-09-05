// Planner probe: exercises the DSL constructs PLAN.md relies on.
// validate-only — never `run` this file. It is safe to delete.
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

Future<void> main(List<String> args) async {
  String? apiKey, baseUrl, projectName, projectId, commitMessage;
  var dryRun = false;
  for (var i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--api-key':
        apiKey = args[++i];
      case '--base-url':
        baseUrl = args[++i];
      case '--project-name':
        projectName = args[++i];
      case '--project-id':
        projectId = args[++i];
      case '--commit-message':
        commitMessage = args[++i];
      case '--dry-run':
        dryRun = true;
      default:
        stderr.writeln('Unknown option: ${args[i]}');
        exit(64);
    }
  }
  try {
    await flutterFlowAI(
      buildProbe,
      apiKey: apiKey,
      baseUrl: baseUrl,
      projectName: projectName,
      projectId: projectId,
      dryRun: dryRun,
      commitMessage: commitMessage,
    );
  } catch (error) {
    stderr.writeln('Error: ${formatFlutterFlowAIError(error)}');
    exit(1);
  }
}

void buildProbe(App app) {
  app.themeColor('primary', 0xFFD9673A, dark: 0xFFF08A5D);
  app.primaryFont('Nunito');
  app.typography('titleLarge', fontSize: 22, fontWeight: 700);
  app.spacingToken('icMd', 16);
  app.radiusToken('icMd', 16);
  app.shadowToken(
    'icCard',
    blurRadius: 8,
    dy: 4,
    spreadRadius: 0,
    color: 0x14000000,
  );

  app.state('probeQuestion', json);
  app.state('probeMood', int_.withDefault(0));
  app.state('probeListening', bool_.withDefault(false));
  app.state('probeState', string.withDefault('disconnected'));
  app.state('probeChips', listOf(string));
  app.state('probeReduce', bool_.withDefault(false));
  app.state('probeJd', string.withDefault(''));

  final fix = app.struct('ProbeFix', {
    'title': string,
    'quote': string,
    'clipUrl': string,
  });

  app.pubDependency('web_socket_channel', '3.0.3');

  app.customClass(
    'ProbeLink',
    code: r'''
import 'dart:async';

sealed class ProbeEvent {
  const ProbeEvent();
}

class ProbeViseme extends ProbeEvent {
  const ProbeViseme(this.id);
  final int id;
}

class ProbeLink {
  ProbeLink._();
  static final ProbeLink instance = ProbeLink._();
  final StreamController<ProbeEvent> _events =
      StreamController<ProbeEvent>.broadcast();
  Stream<ProbeEvent> get events => _events.stream;
}
''',
  );

  final questionText = app.customFunction(
    'probeQuestionText',
    args: {'q': json},
    returns: string,
    code: r'''
if (q is Map) {
  return (q['text'] ?? '').toString();
}
return '';
''',
    description: 'Probe: reads text from a question JSON.',
  );

  final topFixes = app.customFunction(
    'probeTopFixes',
    args: {'report': json},
    returns: listOf(fix),
    code: r'''
final out = <ProbeFixStruct>[];
if (report is Map && report['top_fixes'] is List) {
  for (final f in (report['top_fixes'] as List)) {
    if (f is Map) {
      out.add(ProbeFixStruct(
        title: (f['behaviour'] ?? '').toString(),
        quote: (f['quote'] ?? '').toString(),
        clipUrl: (f['clip_url'] ?? '').toString(),
      ));
    }
  }
}
return out;
''',
    description: 'Probe: json -> list of struct.',
  );

  app.customAction(
    'probeConnect',
    args: {'host': string, 'port': int_, 'token': string, 'mode': string},
    returns: bool_,
    code: r'''
Future<bool> probeConnect(
  String host,
  int port,
  String token,
  String mode,
) async {
  return host.isNotEmpty && port > 0;
}
''',
    description: 'Probe connect.',
  );

  app.customAction(
    'probeAwait',
    args: {'kind': string, 'timeoutMs': int_},
    returns: bool_,
    code: r'''
Future<bool> probeAwait(String kind, int timeoutMs) async {
  await Future<void>.delayed(const Duration(milliseconds: 10));
  return true;
}
''',
    description: 'Probe await.',
  );

  final dynamic scanner = app.customWidget(
    'ProbeScanner',
    parameters: {'hint': string},
    description: 'Probe custom widget with a callback parameter.',
    code: r'''
import 'package:flutter/material.dart';

class ProbeScanner extends StatefulWidget {
  const ProbeScanner({
    super.key,
    this.width,
    this.height,
    required this.hint,
  });

  final double? width;
  final double? height;
  final String hint;

  @override
  State<ProbeScanner> createState() => _ProbeScannerState();
}

class _ProbeScannerState extends State<ProbeScanner> {
  @override
  Widget build(BuildContext context) => SizedBox(
        width: widget.width,
        height: widget.height,
        child: TextButton(
          onPressed: () {},
          child: Text(widget.hint),
        ),
      );
}
''',
  );

  final dynamic avatar = app.customWidget(
    'ProbeAvatar',
    parameters: {'mood': int_},
    description: 'Probe avatar.',
    code: r'''
import 'package:flutter/material.dart';

class ProbeAvatar extends StatelessWidget {
  const ProbeAvatar({
    super.key,
    this.width,
    this.height,
    required this.mood,
  });
  final double? width;
  final double? height;
  final int mood;
  @override
  Widget build(BuildContext context) => SizedBox(
        width: width,
        height: height,
        child: CustomPaint(painter: _P(mood)),
      );
}

class _P extends CustomPainter {
  _P(this.mood);
  final int mood;
  @override
  void paint(Canvas canvas, Size size) {}
  @override
  bool shouldRepaint(covariant _P old) => old.mood != mood;
}
''',
  );

  final room = app.page(
    'ProbeRoom',
    route: '/probe-room',
    description: 'Probe room: no app bar, android back disabled via raw.',
    onLoad: [
      CallCustomAction.named(
        'probeAwait',
        args: {'kind': string, 'timeoutMs': int_},
        returnType: bool_,
        arguments: {'kind': 'report', 'timeoutMs': 0},
        outputAs: 'reportReady',
      ),
      If(
        ActionOutput('reportReady'),
        then: [Navigate('ProbeReport', allowBack: false, replaceRoute: true)],
        orElse: [
          Snackbar('Connection lost'),
          Navigate('ProbeHome', replaceRoute: true),
        ],
      ),
    ],
    body: Scaffold(
      body: Column(
        children: [
          avatar(name: 'Avatar', mood: AppState('probeMood')),
          FlippableCard(
            name: 'QuestionCard',
            front: Container(
              padding: 16,
              borderRadius: 16,
              color: Colors.secondaryBackground,
              child: Text(
                CustomFunction(
                  questionText,
                  args: {'q': AppState('probeQuestion')},
                ),
                style: Styles.titleLarge,
                maxLines: 6,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            back: Container(
              padding: 16,
              child: RichText(
                spans: [
                  RichTextSpan('Why: '),
                  RichTextSpan(
                    CustomFunction(
                      questionText,
                      args: {'q': AppState('probeQuestion')},
                    ),
                    bold: true,
                    color: Colors.primary,
                  ),
                ],
              ),
            ),
          ),
          Container(
            name: 'ReduceMotionGate',
            visible: Not(AppState('probeReduce')),
            child: Lottie(
              'assets/jsons/listening.json',
              source: AnimationSource.asset,
              playback: LottiePlayback.loop,
              autoPlay: true,
              width: 80,
              height: 40,
              name: 'ListeningCue',
              visible: AppState('probeListening'),
            ),
          ),
          Lottie(
            'assets/jsons/thinking.json',
            source: AnimationSource.asset,
            width: 60,
            height: 30,
            name: 'ThinkingCue',
            visible: Equals(AppState('probeMood'), 2),
          ),
        ],
      ),
    ),
  );

  app.page(
    'ProbeReport',
    route: '/probe-report',
    description: 'Probe report list from json via custom function.',
    body: Scaffold(
      appBar: AppBar(title: 'Report'),
      body: Column(
        children: [
          Expanded(
            ListView(
              source: CustomFunction(
                topFixes,
                args: {'report': AppState('probeQuestion')},
              ),
              spacing: 8,
              itemBuilder: (item) => Container(
                padding: 12,
                borderRadius: 12,
                color: Colors.secondaryBackground,
                onTap: [Snackbar(item['clipUrl'])],
                child: Column(
                  crossAxis: CrossAxis.start,
                  children: [
                    Text(item['title'], style: Styles.titleMedium),
                    Text(
                      item['quote'],
                      style: Styles.bodyMedium,
                      color: Colors.secondaryText,
                    ),
                  ],
                ),
              ),
            ),
          ),
          Wrap(
            spacing: 8,
            children: [
              Chip(
                'Warm-up',
                selected: true,
                visible: Equals(AppState('probeState'), 'warmup'),
              ),
              Chip(
                'Warm-up',
                selected: false,
                visible: Not(Equals(AppState('probeState'), 'warmup')),
                onTap: UpdateAppState.set('probeState', 'warmup'),
              ),
            ],
          ),
          Container(
            height: 40,
            child: ListView(
              source: AppState('probeChips'),
              horizontal: true,
              spacing: 8,
              itemBuilder: (item) => Container(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                borderRadius: 999,
                color: Colors.accent1,
                child: Text(item, style: Styles.labelMedium),
              ),
            ),
          ),
        ],
      ),
    ),
  );

  app.page(
    'ProbeHome',
    route: '/probe-home',
    isInitial: true,
    description: 'Probe home with scanner callback + jd field + start chain.',
    state: {'jdDraft': string.withDefault('')},
    body: Scaffold(
      appBar: AppBar(title: 'Probe'),
      body: Column(
        scrollable: true,
        padding: 16,
        spacing: 12,
        children: [
          TextField(
            name: 'jdField',
            label: 'Job description',
            maxLines: 8,
            onChanged: SetState('jdDraft', TextValue()),
          ),
          scanner(
            name: 'Scanner',
            hint: 'Scan',
          ),
          Button(
            'Start',
            width: double.infinity,
            color: Colors.primary,
            textColor: Colors.primaryBackground,
            borderRadius: 14,
            onTap: [
              UpdateAppState.set(
                'probeJd',
                WidgetState('jdField', WidgetStateProperty.text),
              ),
              If(
                Equals(AppState('probeState'), 'connected'),
                then: [
                  Navigate(
                    room,
                    transition: NavigateTransition(
                      NavigateTransitionType.fadeIn,
                      durationMillis: 250,
                    ),
                  ),
                ],
                orElse: [Navigate('ProbeReport')],
              ),
            ],
          ),
        ],
      ),
    ),
  );

  app.raw((project) {
    final page = findPage(project, name: 'ProbeRoom');
    if (page != null) {
      page.node.props.scaffold.disableAndroidBackButton = true;
    }
    final report = findPage(project, name: 'ProbeReport');
    if (report != null) {
      for (final child in report.node.children) {
        if (child.type == FFWidgetType.AppBar) {
          child.props.appBar.defaultBackButtonValue = FFBooleanValue(
            inputValue: false,
          );
        }
      }
    }
  });
}
