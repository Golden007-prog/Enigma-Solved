/// Edit: compile fixes found by `flutter analyze` on the generated tree + web (dart2js) readiness.
///   * VoiceLinkHost: flutter_pcm_sound import prefix renamed (the `Uint8List pcm` parameters shadowed `pcm.`)
///   * StateCue: gzip via package:archive (GZipDecoder) instead of dart:io, which dart2js cannot compile;
///     `archive` added as an explicit pub dependency at the version lottie 3.3.3 resolves
///
///   flutterflow ai run dsl/edit_fix_web.dart --project-id 1cEe3vhxwe7pRqSEeiKi --commit-message "..."
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

import 'interview_cracker.dart' show kVoiceLinkHostCode, kArchiveVersion;
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

void buildEdit(App app) {
  app.raw((project) {
    if (findPubDependency(project, name: 'archive') == null) {
      addPubDependency(project, name: 'archive', version: kArchiveVersion);
      stderr.writeln('added pub dependency archive $kArchiveVersion');
    }
    updateCustomWidget(project, name: 'VoiceLinkHost', code: kVoiceLinkHostCode);
    updateCustomWidget(project, name: 'StateCue', code: kStateCueCode);
    stderr.writeln('VoiceLinkHost (${kVoiceLinkHostCode.length} chars) and StateCue (${kStateCueCode.length} chars) updated');
  });
}
