/// Edit: Add-on A - Lottie state cues (docs/ASSETS.md). Adds the `lottie` package, the `StateCue`
/// custom widget (ten recoloured animations embedded gzip+base64, offline-safe) and one cue per page:
///   Room    -> StateCue(cue: 'room')   picks speaking | listening | thinking | countdown | idle from App State
///   Pair    -> StateCue(cue: 'pair')   qr_scan | connected_check | offline
///   Prep    -> thinking_dots           while the laptop builds the rubric and first question
///   Report  -> report_success (once)
///   History -> empty_history           (the page has no list yet, so it is always empty)
///
///   flutterflow ai validate dsl/edit_lottie_cues.dart --project-id 1cEe3vhxwe7pRqSEeiKi
///   flutterflow ai run dsl/edit_lottie_cues.dart --project-id 1cEe3vhxwe7pRqSEeiKi --commit-message "..."
library;

import 'dart:io';

import 'package:ff_workspace/flutterflow_project.dart' as ff;
import 'package:flutterflow_ai/flutterflow_ai.dart';

import 'state_cue_code.dart' show kStateCueCode;

Future<void> main(List<String> args) async {
  String? apiKey, baseUrl, projectId, commitMessage;
  var dryRun = false;
  for (var i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--api-key': apiKey = args[++i];
      case '--base-url': baseUrl = args[++i];
      case '--project-id': projectId = args[++i];
      case '--commit-message': commitMessage = args[++i];
      case '--dry-run': dryRun = true;
      default: stderr.writeln('Unknown option: ${args[i]}'); exit(64);
    }
  }
  try {
    await flutterFlowAI(buildEdit, apiKey: apiKey, baseUrl: baseUrl, projectId: projectId, dryRun: dryRun, commitMessage: commitMessage);
  } catch (error) {
    stderr.writeln('Error: ${formatFlutterFlowAIError(error)}');
    exit(1);
  }
}

DslWidget cue(String boxName, String widgetName, String cueName, {required double height, bool loop = true, double? width}) => Container(
      width: width ?? double.infinity,
      height: height,
      name: boxName,
      child: CustomWidget(widgetName: 'StateCue', arguments: {'cue': cueName, 'loop': loop}, name: widgetName),
    );

void buildEdit(App app) {
  // lottie 3.3.x: Dart ^3.9 / Flutter >= 3.35 (FlutterFlow builds with 3.38.6); 3.4+ needs Flutter 3.44
  app.pubDependency('lottie', '3.3.3');
  app.pubDependency('archive', '4.2.0'); // StateCue gunzips with package:archive (web-safe)

  app.customWidget(
    'StateCue',
    parameters: {'cue': string, 'loop': bool_},
    description: 'Add-on A Lottie state cue. cue = asset name (mic_idle, listening_wave, thinking_dots, speaking, countdown_warning, qr_scan, connected_check, offline, empty_history, report_success) or a page rule: room / pair. Animations embedded (gzip+base64), reduced-motion aware, pure UI.',
    code: kStateCueCode,
  );

  // Room: one state cue between the avatar and the question card (no decorative motion beyond it)
  app.editPage(ff.Pages.room, (page) {
    page.ensureInsertedAfter(page.findByKey('Container_o4a2iseu'), cue('RoomCueBox', 'RoomCue', 'room', height: 40));
  });
  // Pair: scanning / connected / offline cue above "Or type it"
  app.editPage(ff.Pages.pair, (page) {
    page.ensureInsertedBefore(page.findByKey('Text_5qs5wf3s'), cue('PairCueBox', 'PairCue', 'pair', height: 72));
  });
  // Prep: thinking dots while the interviewer prepares
  app.editPage(ff.Pages.prep, (page) {
    page.ensureInsertedBefore(page.findByKey('Container_25addv7o'), cue('PrepCueBox', 'PrepCue', 'thinking_dots', height: 48));
  });
  // Report: a single celebratory run when the report lands
  app.editPage(ff.Pages.report, (page) {
    page.ensureInsertedBefore(page.findByKey('Container_1vxnshrx'), cue('ReportCueBox', 'ReportCue', 'report_success', height: 64, loop: false));
  });
  // History: empty-state illustration
  app.editPage(ff.Pages.history, (page) {
    page.ensureInsertedAfter(page.findByKey('Text_majkj1gu'), cue('HistoryCueBox', 'HistoryCue', 'empty_history', height: 160));
  });
}
