/// Reference: greenfield mock backend DSL surface.
///
/// Demonstrates building a runnable app with ZERO real backend — declare a
/// data struct + API endpoints, then declare backend-agnostic mock datasets
/// and attach the endpoints to them. Flip the project to the mock data source
/// and the app boots against stateful in-app data in Test Mode, Run Mode, and
/// downloaded code.
///
/// Demonstrates:
/// - `app.mockDataset(name, seedRows:, dataStructName:, idFieldName:, uuidIds:)`
///   — the backend-agnostic data core (no endpoint concept)
/// - `app.mockApi(endpointName, body:, statusCode:)` — fixed static response
/// - `app.mockApiWithDataset(endpointName, dataset:, operation:, ...)` —
///   stateful list / getById / create / update / delete against a dataset
/// - `app.useMockDataSource(useMock: true)` — flip the Live/Mock toggle
///
/// This is the GREENFIELD path. When editing a pulled project, use the
/// brownfield helpers (`addMockDataset`, `mockApiWithDataset`, ...) instead —
/// don't mix the two in one script.
library;

import 'dart:io';

import 'package:flutterflow_ai/flutterflow_ai.dart';

Future<void> main(List<String> args) async {
  final options = _parseCliOptions(args);
  await flutterFlowAI(
    buildMockBackendDemo,
    apiKey: options.apiKey,
    baseUrl: options.baseUrl,
    projectName: options.projectName,
    projectId: options.projectId,
    findOrCreate: options.findOrCreate,
    dryRun: options.dryRun,
    commitMessage: options.commitMessage,
  );
}

void buildMockBackendDemo(App app) {
  // Minimal theme so the page renders cleanly.
  app.themeColor('primary', 0xFF4B39EF);
  app.themeColor('primaryBackground', 0xFFF1F4F8);
  app.themeColor('secondaryBackground', 0xFFFFFFFF);
  app.themeColor('primaryText', 0xFF14181B);
  app.themeColor('secondaryText', 0xFF57636C);
  app.primaryFont('Inter');

  // ---------------------------------------------------------------------------
  // 1. Data model — the dataset schema aligns to this struct.
  // ---------------------------------------------------------------------------
  final task = app.struct('Task', {'id': int_, 'title': string, 'done': bool_});

  // ---------------------------------------------------------------------------
  // 2. API endpoints — the real endpoints the app would call in Live mode.
  // ---------------------------------------------------------------------------
  // KEY PATTERN: declare endpoints exactly as you would for a real backend.
  // The mock bindings below intercept them when the data source is Mock.
  final listTasks = Endpoint.get(
    'ListTasks',
    'https://api.example.com/tasks',
    variables: {'limit': int_, 'offset': int_},
    response: listOf(task),
  );
  final getTask = Endpoint.get(
    'GetTask',
    'https://api.example.com/tasks/[id]',
    variables: {'id': int_},
    response: task,
  );
  final createTask = Endpoint.post(
    'CreateTask',
    'https://api.example.com/tasks',
    variables: {'title': string},
    body: const {'title': '<title>', 'done': false},
    response: task,
  );
  final updateTask = Endpoint.patch(
    'UpdateTask',
    'https://api.example.com/tasks/[id]',
    variables: {'id': int_, 'done': bool_},
    body: const {'done': '<done>'},
    response: task,
  );
  final deleteTask = Endpoint.delete(
    'DeleteTask',
    'https://api.example.com/tasks/[id]',
    variables: {'id': int_},
  );
  final health = Endpoint.get('Health', 'https://api.example.com/health');
  // Standalone endpoints — the mock bindings below resolve them by name. (To
  // mock a grouped endpoint, pass `groupName:` to `mockApiWithDataset` /
  // `mockApi`.)
  app.api(listTasks);
  app.api(getTask);
  app.api(createTask);
  app.api(updateTask);
  app.api(deleteTask);
  app.api(health);

  // ---------------------------------------------------------------------------
  // 3. Mock dataset — backend-agnostic. Knows nothing about endpoints.
  // ---------------------------------------------------------------------------
  // KEY PATTERN: `app.mockDataset(...)` returns a handle you pass to the
  // bindings below. Seed rows make the app boot with data. `dataStructName`
  // keeps the dataset on the project's data model.
  final tasks = app.mockDataset(
    'tasks',
    dataStructName: 'Task',
    seedRows: [
      {'id': 1, 'title': 'Write the spec', 'done': true},
      {'id': 2, 'title': 'Ship the feature', 'done': false},
      {'id': 3, 'title': 'Write the tests', 'done': false},
    ],
  );

  // ---------------------------------------------------------------------------
  // 4. Bindings — API calls are the v1 binding adapter. Each binding maps one
  //    endpoint to a stateful dataset operation (or a fixed response).
  // ---------------------------------------------------------------------------
  // KEY PATTERN: writes through one endpoint are visible to reads through
  // others during a session, so a list after a create reflects the new row.
  app.mockApiWithDataset(
    'ListTasks',
    dataset: tasks,
    operation: 'list',
    orderByField: 'id',
    limitVariable: 'limit',
    offsetVariable: 'offset',
    responseTemplate: '<rows>',
  );
  app.mockApiWithDataset(
    'GetTask',
    dataset: tasks,
    operation: 'getById',
    idVariable: 'id',
  );
  app.mockApiWithDataset('CreateTask', dataset: tasks, operation: 'create');
  app.mockApiWithDataset(
    'UpdateTask',
    dataset: tasks,
    operation: 'update',
    idVariable: 'id',
    writes: {'done': 'done'},
  );
  app.mockApiWithDataset(
    'DeleteTask',
    dataset: tasks,
    operation: 'delete',
    idVariable: 'id',
  );
  // A static response for an endpoint that has no backing dataset.
  //
  // Per-endpoint Live/Mock override: `dataSource:` forces a single endpoint
  // regardless of the project/environment data source. 'live' always calls the
  // real backend (even in Mock), 'mock' always serves the mock (even in Live),
  // 'follow' (default) tracks the project setting. Here Health always hits the
  // live service so a real health check runs even while the rest of the app
  // boots on mocks.
  app.mockApi(
    'Health',
    body: {'status': 'ok'},
    statusCode: 200,
    dataSource: 'live',
  );

  // ---------------------------------------------------------------------------
  // 5. Flip the project to the mock data source — the app now boots against
  //    the seed rows above with no real backend, keys, or CORS setup.
  // ---------------------------------------------------------------------------
  app.useMockDataSource(useMock: true);

  // ---------------------------------------------------------------------------
  // 6. A page that reads + mutates the mock data.
  // ---------------------------------------------------------------------------
  app.page(
    'TasksPage',
    route: '/',
    isInitial: true,
    description: 'Reads and mutates the mock tasks dataset.',
    state: {'tasks': listOf(task)},
    onLoad: [
      ApiCall(
        listTasks,
        outputAs: 'listResult',
        params: {'limit': 50, 'offset': 0},
        onSuccess: (res) => [SetState('tasks', res)],
      ),
    ],
    body: Scaffold(
      appBar: AppBar(title: 'Mock Tasks'),
      body: Column(
        scrollable: true,
        padding: 16,
        spacing: 12,
        crossAxis: CrossAxis.start,
        children: [
          Button(
            'Add a task',
            onTap: ApiCall(
              createTask,
              outputAs: 'createResult',
              params: {'title': 'New task'},
              onSuccess:
                  (res) => [
                    ApiCall(
                      listTasks,
                      outputAs: 'refreshResult',
                      params: {'limit': 50, 'offset': 0},
                      onSuccess: (rows) => [SetState('tasks', rows)],
                    ),
                  ],
            ),
          ),
          ListView(
            source: State('tasks'),
            shrinkWrap: true,
            spacing: 8,
            itemBuilder:
                (item) => Container(
                  padding: 12,
                  borderRadius: 8,
                  color: Colors.secondaryBackground,
                  child: Text(item['title'], style: Styles.bodyLarge),
                ),
          ),
        ],
      ),
    ),
  );
}

// -- CLI boilerplate --
final class _CliOptions {
  const _CliOptions({
    this.apiKey,
    this.baseUrl,
    this.projectName,
    this.projectId,
    this.findOrCreate = false,
    this.dryRun = false,
    this.commitMessage,
  });
  final String? apiKey;
  final String? baseUrl;
  final String? projectName;
  final String? projectId;
  final bool findOrCreate;
  final bool dryRun;
  final String? commitMessage;
}

_CliOptions _parseCliOptions(List<String> args) {
  String? apiKey, baseUrl, projectName, projectId, commitMessage;
  var findOrCreate = false, dryRun = false;
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
      case '--find-or-create':
        findOrCreate = true;
      case '--dry-run':
        dryRun = true;
      default:
        stderr.writeln('Unknown option: ${args[i]}');
        exit(64);
    }
  }
  return _CliOptions(
    apiKey: apiKey,
    baseUrl: baseUrl,
    projectName: projectName,
    projectId: projectId,
    findOrCreate: findOrCreate,
    dryRun: dryRun,
    commitMessage: commitMessage,
  );
}
