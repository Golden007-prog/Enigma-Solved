/// Follow-up edits after the first Interview Cracker push (brownfield helpers only).
///   * pin `path_provider ^2.1.5` via a dependency override — flutter_soloud 3.5.4 needs it, FlutterFlow pins 2.1.4
///   * remove the template HomePage (PasteJD is the initial page)
///
///   flutterflow ai run dsl/edit_followup.dart --project-id 1cEe3vhxwe7pRqSEeiKi --commit-message "path_provider override, drop HomePage"
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

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
    await flutterFlowAI(buildFollowup, apiKey: apiKey, baseUrl: baseUrl, projectId: projectId, dryRun: dryRun, commitMessage: commitMessage);
  } catch (error) {
    stderr.writeln('Error: ${formatFlutterFlowAIError(error)}');
    exit(1);
  }
}

void buildFollowup(App app) {
  app.raw((project) {
    if (findPubDependency(project, name: 'path_provider') == null) {
      addDependencyOverride(project, name: 'path_provider', version: '^2.1.5');
    }
  });
  app.removePage('HomePage');
}
