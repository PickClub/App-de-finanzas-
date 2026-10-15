// Synthetic storage and native-input handles only; no device or real-note writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const {fixture,note}=require('./test-note-persistence.cjs');
const helpers={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/notes/checklist.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,helpers);
const {toggleChecklistLine:toggle,itemScrollOffset:offset}=helpers.exports;
assert.equal(toggle(' [ ]  Keep spacing\r\n\t[X] Second\n\nLast',0),' [x]  Keep spacing\r\n\t[X] Second\n\nLast');
assert.equal(toggle('\t[X] Second',0),'\t[ ] Second');assert.equal(toggle('Plain legacy row',0),'[x] Plain legacy row');
assert.equal(toggle('one',-1),null);assert.equal(toggle('one',1),null);assert.equal(toggle('one',0.5),null);
assert.equal(offset(140,32,100,0,12),84);assert.equal(offset(20,32,100,0,12),null);assert.equal(offset(NaN,32,100,0,12),null);
const source=fs.readFileSync('frontend/app/(tabs)/notes.tsx','utf8');
const ast=ts.createSourceFile('notes.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const component=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text==='NoteItemInput').getText(ast);
(async()=>{
 const saved={...note(),content:'[ ] First\n[x] Second\n [ ]  Third  ',listMode:'check',categories:['Verbatim ñ'],custom:{keep:true}};
 const other=note('other');let f=fixture([saved,other],saved);
 await f.run.togglePreviewItem(0);assert.equal(f.snapshot()[0].content,'[x] First\n[x] Second\n [ ]  Third  ');
 assert.equal(f.ctx.previewNote.id,saved.id);assert.equal(f.ctx.editorOpen,true);assert.equal(f.snapshot()[0].title,saved.title);
 assert.deepEqual(f.snapshot()[0].custom,saved.custom);assert.deepEqual(f.snapshot()[0].categories,saved.categories);assert.deepEqual(f.snapshot()[1],other);
 await f.run.togglePreviewItem(0);assert.equal(f.snapshot()[0].content,saved.content);
 for(const failure of [()=>false,()=>{throw Error('synthetic');},()=>Promise.reject(Error('synthetic'))]){
  f=fixture([saved,other],saved);f.ctx.storage.setItem=failure;await f.run.togglePreviewItem(1);
  assert.equal(f.ctx.previewNote.content,saved.content);assert.deepEqual(f.snapshot(),[saved,other]);assert.equal(f.ctx.noteDeleting.current,false);assert.equal(f.alerts.length,1);
 }
 f=fixture([saved],saved);let finish;
 const write=f.ctx.storage.setItem;
 f.ctx.storage.setItem=(...args)=>new Promise(resolve=>{finish=async()=>resolve(await write(...args));});
 const first=f.run.togglePreviewItem(0);await f.run.togglePreviewItem(0);assert.equal(f.ctx.noteDeleting.current,true);assert.equal(f.ctx.previewNote.content,saved.content);
 finish();await first;assert.equal(f.writes,1);assert.equal(f.ctx.previewNote.content.split('\n')[0],'[x] First');
 const second=f.run.togglePreviewItem(1);f.ctx.previewNote=null;finish();await second;assert.equal(f.ctx.previewNote,null);assert.equal(f.writes,2);
 f=fixture([saved],saved);await f.run.togglePreviewItem(99);assert.equal(f.writes,0);
 for(const editing of [null,saved]){
  f=fixture(editing?[saved]:[],editing);f.ctx.draftListMode='check';f.ctx.draftItems=[{id:'a',text:'Previous',checked:false},{id:'b',text:'Middle',checked:true},{id:'c',text:'Last',checked:false}];
  f.run.submitItem('b');const inserted=f.ctx.draftItems[2];assert.equal(inserted.text,'');assert.equal(f.ctx.draftItems[1].text,'Middle');assert.equal(f.ctx.draftItems[3].id,'c');
  f.run.submitItem('b');assert.equal(f.ctx.draftItems.length,4);
  let cleanup,committed;const nativeCalls=[],native={focus:()=>nativeCalls.push('focus'),setNativeProps:props=>nativeCalls.push(JSON.parse(JSON.stringify(props)))};
  const context={React:{useRef:()=>({current:native}),createElement:(type,props)=>({type,props})},useEffect:fn=>{committed=fn;},NativeTextInput:'Input',ready:f.run.itemInputReady};
  vm.createContext(context);vm.runInContext(ts.transpileModule(component+'\nglobalThis.tree=NoteItemInput({itemId:'+JSON.stringify(inserted.id)+',onReady:ready});',{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText,context);
  assert.equal(nativeCalls.length,0); // No focus during render.
  cleanup=committed();assert.deepEqual(nativeCalls,['focus',{selection:{start:0,end:0}}]);assert.equal(f.ctx.focusedItem.current,inserted.id);assert.equal(f.ctx.pendingItemFocus.current,null);
  f.run.itemInputReady(inserted.id,native);assert.equal(nativeCalls.length,2); // Normal rerenders do not steal the cursor.
  f.run.submitItem('b');assert.equal(f.ctx.draftItems.length,4);
  f.run.submitItem(inserted.id);assert.equal(f.ctx.draftItems.length,5);cleanup();assert(!f.ctx.itemInputs.current.has(inserted.id));
 }
 f=fixture();f.ctx.draftListMode='check';f.ctx.draftItems=Array.from({length:50},(_,i)=>({id:String(i),text:'Keep '+i,checked:false}));
 f.ctx.focusedItem.current='49';f.run.submitItem('49');assert.equal(f.ctx.draftItems.length,50);assert.equal(f.ctx.focusedItem.current,'49');assert.equal(f.ctx.pendingItemFocus.current,null);assert.equal(f.alerts.length,1);
 f=fixture();f.ctx.draftListMode='check';f.ctx.draftItems=[{id:'a',text:'Keep',checked:false}];f.run.submitItem('a');const pending=f.ctx.pendingItemFocus.current.id;
 f.run.closeEditor();let focused=0;f.run.itemInputReady(pending,{focus:()=>focused++,setNativeProps:()=>{}});assert.equal(focused,0);
 assert(source.includes('submitBehavior="submit"'));assert(source.includes('blurOnSubmit={false}'));assert(!source.includes('Keyboard.dismiss'));
 assert(!/setTimeout|requestAnimationFrame/.test(component));
 console.log('PASS: exact per-row marker updates, confirmed-only autosave, rapid tap exclusion, storage failures, closed preview safety, stable mounted input refs, middle-row insertion, duplicate Enter protection, caret at zero, consecutive inserts, 50-row ceiling and no delayed focus after close.');
})().catch(error=>{console.error(error);process.exitCode=1;});
