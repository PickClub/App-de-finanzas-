// Execute the note-only validation and real editor handlers against synthetic storage.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const compiled=ts.transpileModule(fs.readFileSync('frontend/src/notes/limits.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const moduleContext={exports:{}};vm.runInNewContext(compiled,moduleContext);
const {noteLimitViolation:violation,noteTextLength:length}=moduleContext.exports;
const {fixture,note}=require('./test-note-persistence.cjs');
const base={title:'T',content:'Body',mode:'plain',items:[]};
assert.equal(length('😀'.repeat(80)),80);
for(const [field,maximum]of [['title',80],['content',5000]]){
 assert.equal(violation({...base,[field]:'a'.repeat(maximum)}),null);
 assert.equal(violation({...base,[field]:'a'.repeat(maximum+1)}),field);
 const original={title:'T',content:'Body',[field]:'a'.repeat(maximum+20)};
 assert.equal(violation({...base,[field]:'b'.repeat(maximum+20)},original),null);
 assert.equal(violation({...base,[field]:'b'.repeat(maximum+21)},original),field);
}
for(const mode of ['check','ordered']){
 assert.equal(violation({...base,mode,items:Array.from({length:50},()=>({text:'a'.repeat(200)}))}),null);
 assert.equal(violation({...base,mode,items:Array.from({length:51},()=>({text:'a'}))}),'items');
 assert.equal(violation({...base,mode,items:[{text:'a'.repeat(201)}]}),'item');
 const original={...note(),listMode:mode,content:Array.from({length:60},()=> 'a'.repeat(230)).join('\n')};
 const items=Array.from({length:60},()=>({text:'b'.repeat(230),originalLength:230}));
 assert.equal(violation({...base,mode,items},original),null);
 assert.equal(violation({...base,mode,items:[...items,{text:'new'}]},original),'items');
 assert.equal(violation({...base,mode,items:[{text:'a'.repeat(231),originalLength:230}]},original),'item');
}
(async()=>{
 let f=fixture();f.ctx.draftTitle='Existing draft';f.run.changeTitle('a'.repeat(81));assert.equal(f.ctx.draftTitle,'Existing draft');assert.equal(f.alerts.length,1);
 f.run.changeContent('a'.repeat(5001));assert.equal(f.ctx.draftContent,'Draft text');assert.equal(f.writes,0);
 f.run.changeTitle('😀'.repeat(80));assert.equal(length(f.ctx.draftTitle),80);
 f.run.changeContent('a'.repeat(5000));assert.equal(f.ctx.draftContent.length,5000);
 f.ctx.draftContent+='a';await f.run.saveNote();assert.equal(f.writes,0);assert.equal(f.ctx.editorOpen,true);
 f=fixture();f.ctx.draftContent='a'.repeat(201);f.run.toggleListMode('check');assert.equal(f.ctx.draftListMode,'plain');assert.equal(f.ctx.draftContent.length,201);
 f=fixture();f.ctx.draftListMode='check';f.ctx.draftItems=Array.from({length:50},(_,i)=>({id:String(i),text:'Item',checked:false}));
 f.run.addItem();assert.equal(f.ctx.draftItems.length,50);
 f.run.updateItemText('0','a'.repeat(201));assert.equal(f.ctx.draftItems[0].text,'Item');
 f.run.updateItemText('0','a'.repeat(200));assert.equal(f.ctx.draftItems[0].text.length,200);
 f.ctx.draftItems.push({id:'51',text:'Extra'});await f.run.saveNote();assert.equal(f.writes,0);
 const notesAst=ts.createSourceFile('notes.tsx',fs.readFileSync('frontend/app/(tabs)/notes.tsx','utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const listHelpers=notesAst.statements.filter(n=>ts.isFunctionDeclaration(n)&&['parseListItems','serializeItems'].includes(n.name?.text)).map(n=>n.getText(notesAst)).join('\n');
 const helpers={};vm.createContext(helpers);vm.runInContext(ts.transpileModule(listHelpers+'\nglobalThis.parse=parseListItems;globalThis.serialize=serializeItems;',{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,helpers);
 for(const mode of ['check','ordered']){
  const legacy={...note(),listMode:mode,content:Array.from({length:60},(_,i)=>(mode==='check'?'[x] ':'')+'a'.repeat(220)).join('\n')};
  f=fixture([legacy],legacy);f.ctx.parseListItems=helpers.parse;f.ctx.serializeItems=helpers.serialize;
  f.run.openEditor(legacy);assert.equal(f.ctx.draftItems.length,60);assert.equal(f.ctx.draftItems[0].originalLength,220);
  f.run.updateItemText(f.ctx.draftItems[0].id,'b'.repeat(220));f.run.addItem();assert.equal(f.ctx.draftItems.length,60);
  f.run.updateItemText(f.ctx.draftItems[0].id,'c'.repeat(221));assert.equal(f.ctx.draftItems[0].text,'b'.repeat(220));
  await f.run.saveNote();assert.equal(f.snapshot()[0].content.split('\n').length,60);assert(f.snapshot()[0].content.includes('b'.repeat(220)));assert(!f.snapshot()[0].content.includes('originalLength'));
 }
 const original={...note(),title:'a'.repeat(100),content:'a'.repeat(6000)};
 f=fixture([original],original);f.ctx.draftTitle=original.title;f.ctx.draftContent=original.content;
 f.run.changeTitle('b'.repeat(100));f.run.changeContent('b'.repeat(6000));await f.run.saveNote();
 assert.equal(f.snapshot()[0].content,'b'.repeat(6000));assert.equal(f.snapshot()[0].title,'b'.repeat(100));
 f=fixture([original],original);f.ctx.draftTitle=original.title;f.ctx.draftContent=original.content;
 f.run.changeContent('c'.repeat(6001));assert.equal(f.ctx.draftContent,original.content);
 f=fixture([note()],note());f.run.requestPreviewDelete();assert.equal(f.writes,0);assert.equal(f.snapshot().length,1);
 const buttons=f.alerts[0][2];assert.equal(buttons[0].style,'cancel');assert(!buttons[0].onPress);
 await buttons[1].onPress();assert.equal(f.snapshot().length,0);assert.equal(f.ctx.previewNote,null);
 f=fixture([note()],note());f.ctx.storage.setItem=async()=>false;f.run.requestPreviewDelete();await f.alerts[0][2][1].onPress();assert.equal(f.snapshot().length,1);assert.equal(f.ctx.previewNote.id,'n');
 const en=require('../src/i18n/locales/en.json'),es=require('../src/i18n/locales/es.json');
 for(const lang of [en,es])for(const key of ['heading','title','content','items','item'])assert(lang.notes.limits[key]);
 console.log('PASS: exact character/item boundaries, Unicode, rejected paste preserves drafts, mode-conversion guards, pre-save validation, legacy corrections without expansion, translated notices, explicit deletion confirmation and storage-failure preservation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
