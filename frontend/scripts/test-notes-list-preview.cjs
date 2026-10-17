// Render the actual note-list cards with synthetic saved notes; no storage or editor writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync('frontend/app/(tabs)/notes.tsx', 'utf8');
const ast = ts.createSourceFile('notes.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let card; const helpers = [];
function visit(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'renderCard') card = node.initializer.getText(ast);
  if (ts.isFunctionDeclaration(node) && ['toItems', 'parseListItems', 'notePreviewBlocks'].includes(node.name?.text)) helpers.push(node.getText(ast));
  ts.forEachChild(node, visit);
}
visit(ast); assert(card);
const jsx = (type, props, ...children) => ({ type, props: props || {}, children });
const styles = new Proxy({}, { get: (_, key) => key });
const context = {
  React: { createElement: jsx }, Pressable: 'Pressable', ContextActionsTrigger: 'ContextActionsTrigger', View: 'View', Text: 'Text', Ionicons: 'Icon',
  styles, isDark: false, NOTE_PALETTES: {}, subColor: '#68746D', us: n => n,
  tintOf: c => c, formatDateTime: () => 'date', noteDeleting: { current: false }, deleteBusy: false,
  tr: key => key, openEditor() {}, togglePin() {}, deleteNote() {},
  setPreviewNote() { throw Error('Preview render must not change state'); }, setMenuNote() { throw Error('Unexpected state change'); },
};
vm.createContext(context);
vm.runInContext(ts.transpileModule(helpers.join('\n') + '\nglobalThis.renderCard = ' + card, { compilerOptions: { target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React } }).outputText, context);
const walk = n => !n || typeof n !== 'object' ? [] : [n, ...n.children.flat(Infinity).flatMap(walk)];
const note = fields => ({ id: 'saved-note', title: 'Recordar', content: '', pinned: false, color: '#126046', updatedAt: '2026-10-17', ...fields });
function inspect(saved) {
  const before = JSON.stringify(saved), nodes = walk(context.renderCard(saved));
  assert.equal(JSON.stringify(saved), before);
  const actions = nodes.find(n => n.type === 'ContextActionsTrigger');
  assert(actions, 'Each note card keeps a shared contextual action trigger');
  assert.equal(JSON.stringify(actions.props.actions.map(action => action.id)), JSON.stringify(['edit', 'pin', 'delete']));
  return {
    markers: nodes.filter(n => n.type === 'Icon' && ['ellipse-outline', 'checkbox', 'square-outline'].includes(n.props.name)),
    numbers: nodes.filter(n => Array.isArray(n.props.style) && n.props.style.includes('itemNum')),
    body: nodes.filter(n => n.props.style === 'itemText' || Array.isArray(n.props.style) && n.props.style.includes('itemText')),
  };
}
for (const content of ['Long plain sentence. Another sentence! Final sentence? '.repeat(35), 'First paragraph\n\nSecond paragraph\nThird paragraph', '[ ] Literal notation, not a checklist\n1. Literal numbered text']) {
  for (const listMode of [undefined, 'plain']) for (const pinned of [false, true]) {
    const result = inspect(note({ content, listMode, pinned }));
    assert.equal(result.markers.length, 0, 'Plain text must not acquire checklist markers');
    assert.equal(result.numbers.length, 0); assert.equal(result.body.length, 1);
    assert.equal(result.body[0].children.join(''), content.slice(0, 720));
    assert.equal(result.body[0].props.numberOfLines, 3);
  }
}
let result = inspect(note({ listMode: 'check', content: '[ ] First\n[x] Done' }));
assert.deepEqual(result.markers.map(n => n.props.name), ['square-outline', 'checkbox']); assert.equal(result.numbers.length, 0);
result = inspect(note({ listMode: 'ordered', content: 'First\nSecond' })); assert.equal(result.numbers.length, 2); assert.equal(result.markers.length, 0);
result = inspect(note({ listMode: 'check', content: 'Plain introduction\n[ ] Explicit task\n[x] Finished task' }));
assert.equal(result.markers.length, 2); assert.equal(result.body[0].children.join(''), 'Plain introduction');
result = inspect(note({ listMode: 'ordered', content: 'Plain introduction\n1. First\n2. Second' })); assert.equal(result.numbers.length, 2);
result = inspect(note({ listMode: 'check', content: 'Legacy first\nLegacy second' })); assert.equal(result.markers.length, 2, 'Explicit legacy checklist metadata is preserved');
assert.equal(inspect(note({ content: '' })).body.length, 0);
console.log('PASS: actual card previews: long/plain paragraphs, pinned/unpinned, absent/plain metadata, literal markers, checklists, numbered lists, mixed blocks, legacy lists, truncation and immutable saved content.');
