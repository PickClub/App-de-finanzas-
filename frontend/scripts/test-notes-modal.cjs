// Render the actual editor JSX with synthetic props; no device or storage writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { createInstance } = require('i18next');
const source = fs.readFileSync('frontend/app/(tabs)/notes.tsx', 'utf8');
const ast = ts.createSourceFile('notes.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let modal, previewModal, styles;
function visit(node) {
  if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'Modal'
      && node.openingElement.attributes.properties.some(p => p.name?.getText(ast) === 'visible' && p.initializer?.getText(ast) === '{editorOpen}')) modal = node.getText(ast);
  if (ts.isJsxElement(node) && node.openingElement.tagName.getText(ast) === 'Modal'
      && node.openingElement.attributes.properties.some(p => p.name?.getText(ast) === 'visible' && p.initializer?.getText(ast) === '{!!previewNote}')) previewModal = node.getText(ast);
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'useStyles') styles = node.initializer.getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast);assert(modal && styles);
const engine = createInstance();
engine.init({ lng: 'en-US', fallbackLng: 'en-US', resources: {
  'en-US': { translation: require('../src/i18n/locales/en.json') },
  es: { translation: require('../src/i18n/locales/es.json') },
}, initImmediate: false });
const flatten = value => Array.isArray(value) ? Object.assign({}, ...value.map(flatten)) : value || {};
const all = tree => !tree || typeof tree !== 'object' ? [] : [tree, ...(tree.children || []).flat(Infinity).flatMap(all)];
const text = tree => typeof tree === 'string' || typeof tree === 'number' ? String(tree) : (tree?.children || []).flat(Infinity).map(text).join('');
function render(language, mode, dark = false, editing = null, previewNote = null) {
  engine.changeLanguage(language);
  const events = [];
  const context = {
    React: { createElement: (type, props, ...children) => ({ type, props: props || {}, children }) },
    View: 'View', Text: 'Text', TextInput: 'Input', NoteItemInput:'ItemInput', Pressable: 'Pressable', Modal: 'Modal', ScrollView: 'Scroll', KeyboardAvoidingView: 'Keyboard', Ionicons: 'Icon', OrderedGlyph: 'OrderedGlyph', ColorSwatch: 'ColorSwatch',
    makeStyles: factory => factory, us: x => x, ufs: x => x,
    radius: { md: 12, pill: 99, cardLg: 24, lg: 20 }, spacing: { lg: 20, sm: 8, xl: 24, xxl: 32 },
    colors: new Proxy({}, { get: () => '#176F78' }), scheme: dark ? 'dark' : 'light', isDark: dark,
    previewNote, parseListItems: (content, mode) => content.split('\n').map(line => ({text:line.replace(/^\[( |x)\] /,''),checked:mode==='check'&&line.startsWith('[x] ')})),
    formatDateTime: () => engine.language==='es'?'15 de enero de 2026':'January 15, 2026',
    setPreviewNote: value => events.push(['preview',value]), openEditor: value => events.push(['edit',value]), requestPreviewDelete: () => events.push(['confirmDelete']),
    tr: (key, options) => engine.t(key, options), editorOpen: true, editing, editorFontsReady: true, deleteBusy: false, confirmDelete: false,
    insets: { top: 24, bottom: 24 }, Platform: { OS: 'android' },
    draftTitle: 'Custom title ñ', draftContent: 'User body\nunchanged', draftListMode: mode,
    draftItems: [{ id: 'synthetic', text: 'Item', checked: false }], draftPalette: 'green',
    PALETTE_ORDER: ['green'], NOTE_PALETTES: { green: { bgLight: '#DCE9DD', bgDark: '#1B2A22' } },
    noteGreen: '#146448', subColor: '#68746D', editorLine: '#DCE9DD',
    closeEditor: outside => events.push(['close', outside]), toggleListMode: mode => events.push(['mode', mode]),
    saveNote: () => events.push(['save']),togglePreviewItem:index=>events.push(['toggleCheck',index]),
    editorScroll:{current:null},scrollLayout:{current:{origin:0,height:0,offset:0,ready:false}},focusedItem:{current:null},submittedItem:{current:null},itemLayouts:{current:new Map()},itemInputReady:()=>{},revealItem:()=>{},submitItem:id=>events.push(['submit',id]),
  };
  for (const name of ['setDraftTitle', 'setDraftContent', 'changeTitle', 'changeContent', 'toggleItemCheck', 'updateItemText', 'addItem', 'removeItem', 'setDraftPalette', 'setConfirmDelete', 'deleteNote']) context[name] = () => {};
  vm.createContext(context);
  const code = `globalThis.styles = (${styles})(colors, scheme); globalThis.rendered = (${previewNote ? previewModal : modal});`;
  vm.runInContext(ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React } }).outputText, context);
  const nodes = all(context.rendered), find = id => nodes.find(n => n.props?.testID === id);
  return { ...context, nodes, find, events };
}
for (const lang of ['en-US', 'es']) for (const dark of [false, true]) for (const mode of ['plain', 'check', 'ordered']) {
  const f = render(lang, mode, dark), card = flatten(f.find('notes-editor-card').props.style);
  assert.equal(card.width, '90%');assert.equal(card.maxHeight, '75%');assert.equal(card.borderRadius, 24);
  assert.equal(flatten(f.find('notes-editor-backdrop').props.style).backgroundColor, 'rgba(0,0,0,0.18)');
  assert.equal(f.nodes.find(n => n.type === 'Keyboard').props.behavior, 'height');
  assert.equal(f.nodes.find(n => n.type === 'Scroll').props.keyboardShouldPersistTaps, 'handled');
  assert.equal(f.find('notes-title-input').props.value, 'Custom title ñ');
  assert.equal(flatten(f.find('notes-title-input').props.style).fontFamily, 'NoteMontserrat');
  const bodyInput=f.find(mode==='plain'?'notes-content-input':'notes-item-input-0');
  assert.equal(flatten(bodyInput.props.style).fontFamily,'NoteMontserratRegular');
  assert.equal(flatten(bodyInput.props.style).fontWeight,'400');
  if(mode!=='plain'){
    assert.equal(bodyInput.props.submitBehavior,'submit');assert.equal(bodyInput.props.blurOnSubmit,false);
    bodyInput.props.onSubmitEditing();assert.deepEqual(f.events.pop(),['submit','synthetic']);
  }

  assert(text(f.rendered).includes(lang === 'es' ? 'Nueva nota' : 'New note'));
  for (const [tool, label] of [['check', 'ui.checklist'], ['ordered', 'ui.numbered_list']]) {
    const button = f.find('notes-tool-' + tool);
    assert.equal(button.props.accessibilityLabel, engine.t(label));
    assert.equal(button.props.accessibilityState.selected, mode === tool);
    assert.equal(text(button), '');assert.equal(flatten(button.props.style).width, 36);
    button.props.onPress();assert.deepEqual(f.events.pop(), ['mode', tool]);
  }
  // Backdrop is a sibling behind the card, never its pressable parent.
  assert.equal(f.nodes.find(n => n.type === 'Keyboard').children[0].props.testID, 'notes-editor-backdrop');
  f.find('notes-editor-backdrop').props.onPress();assert.deepEqual(f.events.pop(), ['close', undefined]);
  f.find('notes-cancel-btn').props.onPress();assert.deepEqual(f.events.pop(), ['close', undefined]);
  f.rendered.props.onRequestClose();assert.deepEqual(f.events.pop(), ['close', undefined]);
  f.find('notes-save-btn').props.onPress();assert.deepEqual(f.events.pop(), ['save']);
  assert(!f.nodes.some(n => n.props?.refreshControl));
}
for(const lang of ['en-US','es']) for(const dark of [false,true]) for(const mode of ['plain','check','ordered']){
 const editing=render(lang,mode,dark,{id:'existing'});
 assert.equal(editing.rendered.props.animationType,'fade');
 assert.equal(flatten(editing.find('notes-editor-card').props.style).width,'90%');
 assert.equal(flatten(editing.find('notes-editor-card').props.style).maxHeight,'75%');
 assert.equal(flatten(editing.find('notes-editor-backdrop').props.style).backgroundColor,'rgba(0,0,0,0.18)');
 assert.equal(flatten(editing.nodes.find(n=>n.type==='Keyboard').props.style).justifyContent,'center');
 assert.equal(flatten(editing.find('notes-title-input').props.style).fontFamily,'NoteMontserrat');
 const body=editing.find(mode==='plain'?'notes-content-input':'notes-item-input-0');
 assert.equal(flatten(body.props.style).fontFamily,'NoteMontserratRegular');

 assert(text(editing.rendered).includes(lang==='es'?'Editar nota':'Edit note'));
 assert(!editing.find('notes-cancel-btn'));assert(!editing.find('notes-delete-btn'));assert(!editing.find('notes-save-btn'));
 const scroll=editing.nodes.find(n=>n.type==='Scroll');
 assert(!all(scroll).includes(editing.find('notes-editor-save')));assert(!all(scroll).includes(editing.find('notes-editor-close')));
 assert.equal(editing.find('notes-editor-save').props.accessibilityLabel,engine.t('ui.save'));
 editing.find('notes-editor-save').props.onPress();assert.deepEqual(editing.events.pop(),['save']);
 for(const close of [()=>editing.find('notes-editor-close').props.onPress(),()=>editing.find('notes-editor-backdrop').props.onPress(),()=>editing.rendered.props.onRequestClose()]){
  close();assert.deepEqual(editing.events.pop(),['close',undefined]);
 }
}
console.log('PASS: 24 actual create/edit JSX variants (English/Spanish, light/dark, plain/checklist/ordered), shared centered sizing, soft overlay, Montserrat, accessible compact tools, fixed save/close actions and identical close-path wiring.');

for(const lang of ['en-US','es']) for(const dark of [false,true]) for(const mode of ['plain','check','ordered']){
  const content=mode==='plain'?'Verbatim user content ñ\n'.repeat(300)+'LAST LINE':Array.from({length:75},(_,i)=>(mode==='check'?(i%2?'[x] ':'[ ] '):'')+'Item '+i).join('\n');
  const note={id:'legacy',title:'An old title '.repeat(15),content,listMode:mode,updatedAt:'2026-01-15',color:'#146448'};
  const f=render(lang,mode,dark,null,note),scroll=f.find('notes-preview-content');
  assert.equal(flatten(f.find('notes-preview-card').props.style).maxHeight,'75%');
  assert.equal(flatten(f.find('notes-preview-backdrop').props.style).backgroundColor,'rgba(0,0,0,0.18)');
  assert.equal(text(f.find('notes-preview-title')),note.title);
  assert(!all(scroll).some(n=>n.props.testID==='notes-preview-title'||n.props.testID==='notes-preview-date'||n.props.testID==='notes-preview-edit'));
  assert.equal(scroll.props.bounces,false);assert.equal(scroll.props.overScrollMode,'never');
  if(mode==='plain')assert.equal(text(f.find('notes-preview-text')),content);
  else {assert(text(scroll).includes('Item 74'));assert.equal(all(scroll).filter(n=>n.type==='Icon').length,mode==='check'?75:0);}
  assert(!all(scroll).some(n=>n.props.onChangeText));
  const interactive=all(scroll).filter(n=>n.props.onPress);
  assert.equal(interactive.length,mode==='check'?75:0);
  if(mode==='check'){
    const check=f.find('notes-preview-check-1');assert.equal(check.props.accessibilityRole,'checkbox');assert.equal(check.props.accessibilityState.checked,true);
    check.props.onPress();assert.deepEqual(f.events.pop(),['toggleCheck',1]);
  }
  for(const id of ['notes-preview-close','notes-preview-edit','notes-preview-delete'])assert(f.find(id).props.accessibilityLabel);
  f.find('notes-preview-backdrop').props.onPress();assert.deepEqual(f.events.pop(),['preview',null]);
  f.find('notes-preview-delete').props.onPress();assert.deepEqual(f.events.pop(),['confirmDelete']);
  f.find('notes-preview-edit').props.onPress();assert.deepEqual(f.events.pop(),['edit',note]);assert.deepEqual(f.events.pop(),['preview',null]);
}
console.log('PASS: 12 preview variants with body text read-only and interactive checkboxes render complete long legacy text/75 checklist rows in both languages/themes, fixed title/date/actions outside body scroll, localized accessible actions and safe event wiring.');
