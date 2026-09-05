/// Edit: swap the phone's playback backend from flutter_soloud to flutter_pcm_sound.
/// Why: every flutter_soloud 3.x needs path_provider ^2.1.5, FlutterFlow's generated pubspec pins
/// 2.1.4 and its code generator drops the dependency override we added, so `flutter pub get`
/// failed on every export. flutter_pcm_sound has no dependencies at all.
///
///   flutterflow ai validate dsl/edit_audio_backend.dart
///   flutterflow ai run dsl/edit_audio_backend.dart --project-id 1cEe3vhxwe7pRqSEeiKi --commit-message "..."
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

import 'interview_cracker.dart' show kVoiceLinkHostCode;

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

void buildEdit(App app) {
  app.raw((project) {
    if (findPubDependency(project, name: 'flutter_soloud') != null) {
      removePubDependency(project, name: 'flutter_soloud');
      stderr.writeln('removed pub dependency flutter_soloud');
    }
    if (findPubDependency(project, name: 'flutter_pcm_sound') == null) {
      addPubDependency(project, name: 'flutter_pcm_sound', version: '3.3.3');
      stderr.writeln('added pub dependency flutter_pcm_sound 3.3.3');
    }
    updateCustomWidget(project, name: 'VoiceLinkHost', code: kVoiceLinkHostCode);
    stderr.writeln('VoiceLinkHost code updated (${kVoiceLinkHostCode.length} chars)');
  });
}
