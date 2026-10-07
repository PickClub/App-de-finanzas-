// Isolated hook tests using existing TypeScript; no Expo server or API/database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
function compile(file) {
  const result = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    fileName: file, reportDiagnostics: true,
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020 },
  });
  assert.equal((result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  return result.outputText;
}
const apiExports = {};
vm.runInNewContext(compile('src/api.ts'), { exports: apiExports, process: { env: {} } });
const { ApiError } = apiExports;
function hook(destination) {
  const alerts = [], navigation = [], refreshes = [], states = [], effects = [];
  const exports = {};
  const mocks = {
    react: { useRef: v => ({ current: v }), useState: () => [false, v => states.push(v)],
      useCallback: fn => fn, useEffect: fn => effects.push(fn) },
    'react-native': { Alert: { alert: (...args) => alerts.push(args) } },
    'expo-router': { useRouter: () => ({ dismissTo: route => navigation.push(route) }) },
    '@tanstack/react-query': { useQueryClient: () => ({ invalidateQueries: args => {
      refreshes.push(args); return new Promise(() => {});
    } }) },
    './api': { ApiError },
  };
  vm.runInNewContext(compile('src/use-resource-deletion.ts'), { exports, require: name => mocks[name] });
  return { deletion: exports.useResourceDeletion(destination, [['transactions'], ['accounts']]),
    alerts, navigation, refreshes, states, effects, missing: exports.useMissingResource };
}
async function main() {
  const accountExports = {};
  vm.runInNewContext(compile('src/account-deletion-navigation.ts'), {
    exports: accountExports, require: () => ({ useNavigation: () => ({}) }),
  });
  for (const withList of [false, true]) {
    const routes = [{ name: '(tabs)', key: 'home' }];
    if (withList) routes.push({ name: 'accounts/index', key: 'existing-list' });
    routes.push({ name: 'accounts/[id]', key: 'preview', params: { id: 'B' } });
    routes.push({ name: 'accounts/new', key: 'editor', params: { id: 'B' } });
    const result = accountExports.accountListAfterRemoval({ routes }, 'B');
    assert.equal(result.routes.at(-1).name, 'accounts/index');
    assert.equal(result.routes.filter(r => r.name === 'accounts/index').length, 1);
    assert(!result.routes.some(r => r.params?.id === 'B'));
    assert.equal(result.routes[result.index - 1].name, '(tabs)');
    if (withList) assert.equal(result.routes.at(-1).key, 'existing-list');
  }

  for (const route of ['/accounts', '/categories', '/(tabs)']) {
    let t = hook(route), finish, count = 0;
    const pending = t.deletion.remove(() => { count++; return new Promise(r => finish = r); });
    assert(t.deletion.locked.current);
    await t.deletion.remove(async () => { count++; });
    assert.equal(count, 1);
    finish(); await pending;
    assert.deepEqual(t.navigation, [route]); // Never wait for pending refreshes.
    assert(t.deletion.locked.current && t.deletion.deleted.current);
    await t.deletion.remove(async () => { count++; });
    assert.equal(count, 1);
    assert.equal(t.refreshes.length, 2);
    t = hook(route);
    await t.deletion.remove(async () => { throw new ApiError(409, '{"detail":"Referenced by synthetic movements"}'); });
    assert.equal(t.navigation.length, 0);
    assert.equal(t.alerts[0][1], 'Referenced by synthetic movements');
    assert.equal(t.deletion.locked.current, false);
    assert.equal(t.states.at(-1), false);
    await t.deletion.remove(async () => { throw new ApiError(404, '{}'); });
    assert.deepEqual(t.navigation, [route]);
    assert(t.deletion.deleted.current);
    t = hook(route);
    t.missing(true, t.deletion.unavailable); t.effects.forEach(fn => fn());
    assert.deepEqual(t.navigation, [route]);
    assert(t.deletion.locked.current);
  }
  for (const file of ['app/accounts/new.tsx', 'app/accounts/[id].tsx', 'app/categories/new.tsx',
    'app/transactions/new.tsx', 'app/transactions/[id].tsx', 'app/debts/[id]/index.tsx', 'app/(tabs)/notes.tsx']) compile(file);
  for (const file of ['app/categories/index.tsx', 'app/transactions/new.tsx']) {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    const tree = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let initializer;
    function visitCatalog(node) {
      if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect' &&
          node.arguments[0]?.getText(tree).includes('api.initDefaultCategories()')) initializer = node.arguments[0].getText(tree);
      ts.forEachChild(node, visitCatalog);
    }
    visitCatalog(tree); assert(initializer);
    let calls = 0;
    const context = { ensuredRef: { current: false }, q: { isSuccess: true }, cats: [{ id: 'c' }],
      catQ: { isSuccess: true, data: [{ id: 'c' }] }, api: { initDefaultCategories: async () => { calls++; } },
      qc: { invalidateQueries: async () => {} } };
    vm.runInNewContext(`globalThis.run = ${initializer};`, context);
    context.run(); context.cats = []; context.catQ.data = []; context.run();
    assert.equal(calls, 0); // Deleting the last category must not repopulate it.
  }
  // Exercise the actual local-note handler: persistence failure must keep its editor/data.
  const noteSource = fs.readFileSync(path.join(root, 'app/(tabs)/notes.tsx'), 'utf8');
  const noteTree = ts.createSourceFile('notes.tsx', noteSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(noteTree) === 'deleteNote') handler = node.initializer.getText(noteTree);
    ts.forEachChild(node, visit);
  }
  visit(noteTree); assert(handler);
  for (const success of [true, false]) {
    const states = {}, alerts = [], noteDeleting = { current: false };
    let finish, writes = 0;
    const context = { noteDeleting, deletedNotes: { current: new Set() }, notes: [{ id: 'n' }], STORAGE_KEY: 'synthetic',
      storage: { setItem: () => { writes++; return new Promise(r => finish = r); } },
      Alert: { alert: (...args) => alerts.push(args) } };
    for (const key of ['DeleteBusy', 'Notes', 'EditorOpen', 'Editing', 'MenuNote', 'ConfirmDelete']) context['set' + key] = v => states[key] = v;
    const code = ts.transpileModule(`const handler = ${handler};`, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
    vm.runInNewContext(code + '\nglobalThis.run = handler;', context);
    const pending = context.run('n'); await context.run('n'); assert.equal(writes, 1);
    finish(success); await pending;
    assert.equal(noteDeleting.current, false);
    if (success) {
      assert.equal(states.Notes.length, 0); assert.equal(states.EditorOpen, false); assert.equal(states.Editing, null);
      await context.run('n'); assert.equal(writes, 1);
    }
    else { assert.equal(states.Notes, undefined); assert.equal(states.EditorOpen, undefined); assert.equal(alerts.length, 1); }
  }
  console.log('PASS: 3 destinations × success, double press, pending refresh, 409, 404, missing resource; TSX syntax.');
  console.log('PASS: local-note deletion commits storage before closing; double press and storage failure controlled.');
  console.log('PASS: deleting the last category does not trigger catalog initialization in the existing screens.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
