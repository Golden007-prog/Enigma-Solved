/// Follow-up edits after the first Interview Cracker push (brownfield helpers only).
///   * pin `path_provider ^2.1.5` via a dependency override — every flutter_soloud 3.x needs it,
///     FlutterFlow's generated pubspec pins 2.1.4 (the first run guarded on `findPubDependency`,
///     which found FlutterFlow's own path_provider entry and skipped the override — hence unguarded now)
///
///   flutterflow ai run dsl/edit_followup.dart --project-id 1cEe3vhxwe7pRqSEeiKi --commit-message "path_provider override"
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
    try {
      addDependencyOverride(project, name: 'path_provider', version: '^2.1.5');
      stderr.writeln('dependency_overrides: path_provider ^2.1.5 added');
    } catch (e) {
      stderr.writeln('dependency override not added (already present?): $e');
    }
  });
}
