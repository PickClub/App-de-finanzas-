const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// C9: execute the real TSX handlers with synthetic storage; no device/API writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const cp = require('node:child_process');
const file = 'frontend/app/(tabs)/notes.tsx';
const root = path.resolve(__dirname, '../..');
const source = process.env.NOTES_TEST_REF
  ? cp.execFileSync('git', ['show', `${process.env.NOTES_TEST_REF}:${file}`], { cwd: root, encoding: 'utf8' })
  : fs.readFileSync(path.join(root, file), 'utf8');
const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = ['editorDraftSignature', 'persist', 'saveNote', 'togglePin', 'deleteNote', 'openEditor', 'closeEditor', 'validateDraft', 'changeTitle', 'changeContent', 'toggleListMode', 'updateItemText', 'addItem', 'submitItem', 'revealItem', 'itemInputReady', 'togglePreviewItem', 'requestPreviewDelete'];
const handlers = {};
let load;
function visit(n) {
  if (ts.isVariableDeclaration(n) && names.includes(n.name.getText(tree))) handlers[n.name.getText(tree)] = n.initializer.getText(tree);
  if (ts.isCallExpression(n) && n.expression.getText(tree) === 'useEffect' && n.arguments[0]?.getText(tree).includes('storage.getItem(STORAGE_KEY')) load = n.arguments[0].getText(tree);
  ts.forEachChild(n, visit);
}
visit(tree);
assert.equal(Object.keys(handlers).length, names.length);
assert(load);
const limitModule = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'frontend/src/notes/limits.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,limitModule);
const checklistModule={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'frontend/src/notes/checklist.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,checklistModule);
const clone = value => JSON.parse(JSON.stringify(value));
const note = (id = 'n') => ({ id, title: 'Confirmed', content: 'Original', pinned: false, color: 'green', palette: 'cream', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:00:00Z' });
function fixture(initial = [], editing = null) {
  let stored = JSON.stringify(initial), writes = 0, sequence = 0;
  const alerts = [];
  const ctx = {
    notes: clone(initial), confirmedNotes: { current: clone(initial) }, notesReady: { current: true }, saveComplete: { current: false }, editorSnapshot: {current:{signature:'',revision:0,active:true}}, discardPrompt: {current:false},
    noteDeleting: { current: false }, deletedNotes: { current: new Set() },
    ...limitModule.exports, ...checklistModule.exports,
    pendingItemFocus:{current:null},focusedItem:{current:null},submittedItem:{current:null},
    itemInputs:{current:new Map()},itemLayouts:{current:new Map()},scrollLayout:{current:{origin:0,height:0,offset:0,ready:false}},
    editorScroll:{current:{scrollTo:()=>{}}},us:x=>x,
    lastLimitNotice: {current:0},
    editing, editorOpen: true, draftTitle: 'Draft title', draftContent: 'Draft text', draftListMode: 'plain', draftItems: [], draftPalette: 'green', previewNote: editing,
    deleteBusy: false, STORAGE_KEY: 'synthetic', NOTE_COLORS: ['green'],
    useCallback: f => f, genId: () => `new-${++sequence}`,
    serializeItems: items => JSON.stringify(items), parseListItems: () => [],
    makeSeed: () => [note('seed')], Alert: { alert: (...a) => alerts.push(a) },
  };
  ctx.storage = {
    getItem: async () => stored,
    setItem: async (key, value) => { writes++; stored = value; return true; },
  };
  for (const k of ['Notes','PreviewNote','EditorOpen','Editing','MenuNote','ConfirmDelete','DeleteBusy','DraftTitle','DraftContent','DraftListMode','DraftItems','DraftPalette']) {
    const property = k[0].toLowerCase()+k.slice(1);
    ctx['set'+k] = value => { ctx[property] = typeof value==='function'?value(ctx[property]):value; };
  }
  vm.createContext(localeGlobals(ctx));
  const code = names.map(n => `const ${n} = ${handlers[n]};`).join('\n') +
    `\nglobalThis.run = {${names.join(',')}, load:${load}};`;
  vm.runInContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText, ctx);
  ctx.editorSnapshot.current.signature=ctx.run.editorDraftSignature({title:editing?.title||'',content:editing?.content||'',mode:editing?.listMode||'plain',items:[],palette:editing?.palette??null});
  return { ctx, alerts, run: ctx.run, snapshot: () => JSON.parse(stored), get writes() { return writes; } };
}
function delay(f) {
  let resolve;
  const original = f.ctx.storage.setItem;
  f.ctx.storage.setItem = async (...args) => {
    await new Promise(r => resolve = r);
    return original(...args);
  };
  return () => resolve();
}
async function tick() { await new Promise(r => setImmediate(r)); }
async function main() {
  let f = fixture();
  await f.run.saveNote();
  assert.equal(f.snapshot().length, 1);
  assert.equal(f.snapshot()[0].content, 'Draft text');
  assert.equal(f.ctx.editorOpen, false);
  f = fixture([note()], note());
  await f.run.saveNote();
  assert.equal(f.snapshot().length, 1);
  assert.equal(f.snapshot()[0].id, 'n');
  assert.equal(f.snapshot()[0].content, 'Draft text');
  assert.equal(f.snapshot()[0].createdAt, note().createdAt);
  console.log('PASS: create/edit confirmed; IDs, format, palette and creation history preserved.');

  f = fixture();
  const finish = delay(f);
  const pending = f.run.saveNote();
  await f.run.saveNote();
  assert.equal(f.ctx.editorOpen, true);
  assert.equal(f.ctx.notes.length, 0);
  assert.equal(f.ctx.noteDeleting.current, true);
  finish(); await pending;
  await f.run.saveNote(); // Late second tap while the successful editor is closing.
  assert.equal(f.writes, 1);
  assert.equal(f.snapshot().length, 1);
  assert.equal(f.ctx.noteDeleting.current, false);
  f.run.openEditor(null);
  f.ctx.draftTitle = 'Second legitimate note';
  f.ctx.draftContent = 'Second content';
  const second = f.run.saveNote(); finish(); await second;
  assert.equal(f.snapshot().length, 2); // A genuinely new editor permits a new note.
  console.log('PASS: delayed storage does not close/update optimistically; double Save creates one note.');

  for (const editing of [false, true]) for (const failure of [() => false, () => { throw Error('sync'); }, () => Promise.reject(Error('async'))]) {
    f = fixture(editing ? [note()] : [], editing ? note() : null);
    f.ctx.draftListMode = 'check';
    f.ctx.draftItems = [{ id:'item', text:'Unconfirmed item', checked:true }];
    const before = clone({ title:f.ctx.draftTitle, content:f.ctx.draftContent, items:f.ctx.draftItems, palette:f.ctx.draftPalette, mode:f.ctx.draftListMode });
    const good = f.ctx.storage.setItem;
    f.ctx.storage.setItem = failure;
    await f.run.saveNote();
    assert.equal(f.ctx.editorOpen, true);
    assert.deepEqual(f.snapshot(), editing ? [note()] : []);
    assert.deepEqual(clone(f.ctx.notes), editing ? [note()] : []);
    assert.deepEqual(clone({ title:f.ctx.draftTitle, content:f.ctx.draftContent, items:f.ctx.draftItems, palette:f.ctx.draftPalette, mode:f.ctx.draftListMode }), before);
    assert.equal(f.alerts.length, 1);
    assert.equal(f.ctx.noteDeleting.current, false);
    assert.equal(f.ctx.deleteBusy, false);
    f.ctx.storage.setItem = good;
    await f.run.saveNote();
    assert.equal(f.ctx.editorOpen, false);
    assert.equal(f.snapshot()[0].content, JSON.stringify(before.items));
  }
  console.log('PASS: false, sync exception and rejection preserve complete draft/confirmed data; manual retry unlocks.');

  for (const first of ['saveNote','togglePin','deleteNote']) {
    f = fixture([note()], note());
    const done = delay(f);
    const operation = f.run[first]('n');
    for (const other of ['saveNote','togglePin','deleteNote']) await f.run[other]('n');
    assert.equal(f.ctx.notes[0].content, 'Original');
    done(); await operation;
    assert.equal(f.writes, 1);
    assert.equal(f.ctx.noteDeleting.current, false);
    assert.equal(f.ctx.deleteBusy, false);
  }
  // Reuse stale event closures intentionally; all mutations must see confirmed data.
  f = fixture([note()], note());
  await f.run.saveNote(); await f.run.togglePin('n');
  assert.equal(f.snapshot()[0].content, 'Draft text');
  assert.equal(f.snapshot()[0].pinned, true);
  await f.run.deleteNote('n');
  f.ctx.editing = note(); // An old React event closure still captures this note.
  await f.run.saveNote();
  assert.equal(f.snapshot().length, 0);
  console.log('PASS: save/pin/delete exclusion in all orders, latest confirmed snapshots and no deleted-note resurrection.');

  for (const action of ['togglePin','deleteNote']) {
    f = fixture([note()], note());
    const good = f.ctx.storage.setItem;
    f.ctx.storage.setItem = async () => false;
    await f.run[action]('n');
    assert.deepEqual(f.snapshot(), [note()]);
    assert.equal(f.ctx.noteDeleting.current, false);
    f.ctx.storage.setItem = good;
    await f.run[action]('n');
    assert.equal(f.writes, 1);
  }
  console.log('PASS: failed pin/delete keep data and release gate; existing deletion guarantees retained.');

  f = fixture([note()], note());
  await f.run.saveNote();
  const confirmed = f.snapshot();
  const restarted = fixture(confirmed);
  restarted.ctx.notes = [];
  restarted.ctx.confirmedNotes.current = [];
  restarted.ctx.notesReady.current = false;
  restarted.run.load(); await tick();
  assert.deepEqual(clone(restarted.ctx.notes), confirmed);
  assert.equal(restarted.writes, 0);
  restarted.ctx.editing = restarted.ctx.notes[0];
  restarted.ctx.draftContent = 'Lost attempt';
  restarted.ctx.storage.setItem = async () => false;
  await restarted.run.saveNote();
  assert.deepEqual(restarted.snapshot(), confirmed);
  console.log('PASS: actual load effect after simulated restart restores last confirmed content; failed next save cannot destroy it.');

  f = fixture();
  f.ctx.notesReady.current = false;
  f.ctx.storage.getItem = async () => '';
  const seedDone = delay(f);
  f.run.load(); await tick();
  await f.run.saveNote(); assert.equal(f.ctx.notes.length, 0);
  seedDone(); await tick();
  assert.equal(f.snapshot()[0].id, 'seed');
  assert.equal(f.ctx.notesReady.current, true);
  console.log('PASS: first-run seed cannot race with saving or appear persisted before confirmation.');

  for(const outside of [false,true]){
    f=fixture();f.ctx.draftListMode='check';f.ctx.draftItems=[{text:'Do not save',checked:true}];
    f.run.closeEditor(outside);
    assert.equal(f.ctx.editorOpen,false);assert.equal(f.ctx.draftTitle,'');assert.equal(f.ctx.draftContent,'');
    assert.equal(f.ctx.draftListMode,'plain');assert.equal(f.ctx.draftItems.length,0);assert.equal(f.ctx.draftPalette,null);assert.equal(f.writes,0);
    f.run.openEditor(null);assert.equal(f.ctx.draftTitle,'');assert.equal(f.ctx.draftContent,'');
  }
  f=fixture([note()],note());f.run.closeEditor();
  assert.equal(f.ctx.editorOpen,true);assert.equal(f.ctx.draftTitle,'Draft title');assert.equal(f.writes,0);
  assert.equal(f.alerts.length,1);f.run.closeEditor();assert.equal(f.alerts.length,1);
  await f.run.saveNote();assert.equal(f.writes,0); // A discard dialog owns this visit.
  f.alerts[0][2][0].onPress();assert.equal(f.ctx.editorOpen,true);assert.equal(f.ctx.draftTitle,'Draft title');
  f.run.closeEditor();f.alerts[1][2][1].onPress();
  assert.equal(f.ctx.editorOpen,false);assert.equal(f.ctx.draftTitle,'');assert.equal(f.ctx.editing,null);assert.equal(f.writes,0);
  assert.equal(f.snapshot()[0].content,'Original');
  f.ctx.editing=note();f.ctx.draftTitle='Queued stale title';f.ctx.draftContent='Queued stale body';await f.run.saveNote();assert.equal(f.writes,0);
  f=fixture([note()],note());f.run.openEditor(note());f.run.closeEditor();assert.equal(f.ctx.editorOpen,false);assert.equal(f.alerts.length,0);
  f=fixture([note()],note());f.run.closeEditor();const oldDiscard=f.alerts[0][2][1].onPress;
  f.run.openEditor(note('other'));oldDiscard();assert.equal(f.ctx.editorOpen,true);assert.equal(f.ctx.editing.id,'other');
  f=fixture();f.ctx.noteDeleting.current=true;f.run.closeEditor();assert.equal(f.ctx.editorOpen,true);
  console.log('PASS: new drafts discard without writes; existing dirty edits confirm once, Cancel retains drafts, Discard clears without writes, unchanged edits close directly, stale dialogs cannot close another editor and pending saves are protected.');

  const compiled = ts.transpileModule(source,{ fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.React,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020} });
  assert.equal((compiled.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  if (!process.env.NOTES_TEST_REF) {
    assert(source.includes('editable={!deleteBusy}'));
    assert(source.includes('pointerEvents={deleteBusy ? "none" : "auto"}'));
    assert(source.includes('if (noteDeleting.current || discardPrompt.current) return;'));
    const old = cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'});
    const styleEntries = text => {
      const ast=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
      const result={};
      function visit(n){
        if(ts.isVariableDeclaration(n)&&n.name.getText(ast)==='useStyles'){
          const body=n.initializer.arguments[0].body;
          const value=body.statements.find(ts.isReturnStatement).expression;
          for(const p of value.properties)result[p.name.getText(ast)]=p.initializer.getText(ast);
        }else ts.forEachChild(n,visit);
      }visit(ast);return result;
    };
    const before=styleEntries(old),after=styleEntries(source);
    const editorChanges=new Set(['toolsRow','toolBtn','sheetActions','sheetHandle','menuBackdrop','menuSheet','menuItem','menuItemText']);
    for(const key of Object.keys(before))if(!editorChanges.has(key))assert.equal(after[key],before[key],`Unrelated style changed: ${key}`);
  }
  console.log('PASS: TSX syntax; editor input/close guards; unchanged non-editor style definitions.');
}
module.exports={fixture,note};
if(require.main===module) main().catch(error => { console.error(error); process.exitCode=1; });
