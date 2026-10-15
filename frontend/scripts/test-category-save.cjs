const {localeGlobals,localeMocks,normalizeHomeColors,normalizeUI}=require('./i18n-test-support.cjs');
// C10/R7 Categories: actual form handlers with synthetic API/cache/navigation.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const vm=require('node:vm'),cp=require('node:child_process'),ts=require('typescript');
const root=path.resolve(__dirname,'../..'),file='frontend/app/categories/new.tsx';
const source=process.env.CATEGORY_TEST_REF?cp.execFileSync('git',['show',`${process.env.CATEGORY_TEST_REF}:${file}`],{cwd:root,encoding:'utf8'}):fs.readFileSync(path.join(root,file),'utf8');
const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),functions={};
let disabled;
function visit(n){
  if(ts.isVariableDeclaration(n)&&['save','remove'].includes(n.name.getText(tree)))functions[n.name.getText(tree)]=n.initializer.getText(tree);
  if(ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n)){
    const a=n.attributes.properties;
    if(a.some(p=>p.name?.getText(tree)==='testID'&&p.initializer?.text==='save-category'))disabled=a.find(p=>p.name?.getText(tree)==='disabled')?.initializer?.expression?.getText(tree);
  }
  ts.forEachChild(n,visit);
}visit(tree);assert(functions.save&&functions.remove);
class ApiError extends Error{constructor(status,detail){super('HTTP '+status);this.status=status;this.detail=detail;}}
const plain=v=>JSON.parse(JSON.stringify(v));
function fixture(edit=false){
  let backs=0,refreshes=0;
  const alerts=[],calls=[];
  const ctx={params:edit?{id:'category'}:{},resourceLoaded:true,saving:false,savingRef:{current:false},saveComplete:{current:false},mounted:{current:true},
    name:'My category',type:'expense',icon:'cart-outline',color:'#FF8A3D',isGroup:false,parentId:'group',ApiError,Error,
    Alert:{alert:(...a)=>alerts.push(a)},router:{back:()=>backs++},
    qc:{invalidateQueries:()=>{refreshes++;return Promise.resolve();}},setSaving:v=>ctx.saving=v,
    deletion:{locked:{current:false},busy:false},
  };
  const response=()=>({id:ctx.params.id||'new-category'});
  ctx.api={createCategory:async payload=>{calls.push(['POST',plain(payload)]);return response();},
    updateCategory:async(id,payload)=>{calls.push(['PUT',id,plain(payload)]);return response();},
    deleteCategory:async id=>calls.push(['DELETE',id])};
  ctx.deletion.remove=async operation=>{if(ctx.deletion.locked.current)return;ctx.deletion.locked.current=true;try{return await operation();}finally{ctx.deletion.locked.current=false;}};
  vm.createContext(localeGlobals(ctx));
  const code=Object.entries(functions).map(([n,value])=>`const ${n}=${value};`).join('\n')+'\nglobalThis.run={save,remove};';
  vm.runInContext(ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,ctx);
  return {ctx,run:ctx.run,alerts,calls,counts:()=>({backs,refreshes}),draft:()=>plain({name:ctx.name,type:ctx.type,icon:ctx.icon,color:ctx.color,isGroup:ctx.isGroup,parentId:ctx.parentId}),
    disabled:()=>{if(!disabled)return false;vm.runInContext('globalThis.buttonDisabled='+disabled,ctx);return ctx.buttonDisabled;}};
}
async function tick(){await new Promise(r=>setImmediate(r));}
async function main(){
  // Real original failure: repeated touches call the POST repeatedly while pending.
  let f=fixture(),finish;
  const original=f.ctx.api.createCategory;
  f.ctx.api.createCategory=payload=>{const p=original(payload);return new Promise(r=>finish=()=>p.then(r));};
  const pending=f.run.save();
  const repeats=[f.run.save(),f.run.save(),f.run.save()];
  assert.equal(f.calls.length,1,'Repeated Save must not create multiple pending POSTs');
  assert.equal(f.counts().backs,0);assert.equal(f.counts().refreshes,0);
  assert.equal(f.ctx.savingRef.current,true);assert.equal(f.disabled(),true);
  finish();await pending;await Promise.all(repeats);
  assert.deepEqual(f.counts(),{backs:1,refreshes:1});assert.equal(f.ctx.savingRef.current,false);assert.equal(f.ctx.saving,false);
  await f.run.save();assert.equal(f.calls.length,1);
  console.log('PASS: delayed POST, double/multiple presses and late touch after confirmation create exactly one category.');

  for(const edit of [false,true]){
    f=fixture(edit);const before=f.draft();await f.run.save();
    assert.equal(f.calls.length,1);assert.equal(f.calls[0][0],edit?'PUT':'POST');
    assert.deepEqual(f.calls[0].at(-1),{name:before.name,type:before.type,icon:before.icon,color:before.color,is_group:false,parent_id:before.parentId});
    assert.deepEqual(f.draft(),before);assert.equal(f.counts().backs,1);assert.equal(f.alerts.length,0);
    assert.equal(f.ctx.savingRef.current,false);assert.equal(f.ctx.saving,false);
    for(const error of [new ApiError(422,'Invalid parent category'),new ApiError(409,'Conflict'),new ApiError(503,'Unknown commit'),new Error('Network request failed')]){
      f=fixture(edit);const snapshot=f.draft(),key=edit?'updateCategory':'createCategory',good=f.ctx.api[key];
      f.ctx.api[key]=async()=>{throw error;};
      await f.run.save();assert.equal(f.counts().backs,0);assert.equal(f.counts().refreshes,0);
      assert.deepEqual(f.draft(),snapshot);assert.equal(f.ctx.savingRef.current,false);assert.equal(f.ctx.saving,false);assert.equal(f.disabled(),false);
      assert.equal(f.alerts.length,1);
      if(error instanceof ApiError&&error.status<500){assert.equal(f.alerts[0][0],'No se pudo guardar');assert.equal(f.alerts[0][1],error.detail);}
      else{assert.equal(f.alerts[0][0],'No se pudo confirmar el guardado');assert(f.alerts[0][1].includes('revisa la lista'));}
      f.ctx.api[key]=good;await f.run.save();assert.equal(f.counts().backs,1);assert.equal(f.calls.length,1);
    }
  }
  console.log('PASS: create/edit use unchanged payloads; HTTP/network errors preserve every form field, explain failure and allow manual retry.');
  f=fixture();f.ctx.isGroup=true;await f.run.save();assert.equal(f.calls[0].at(-1).parent_id,null);assert.equal(f.ctx.parentId,'group');

  for(const result of [null,{},false,{id:''},{id:123},{id:'other'}]){
    f=fixture(true);f.ctx.api.updateCategory=async()=>result;const before=f.draft();
    await f.run.save();assert.equal(f.counts().backs,0);assert.equal(f.alerts.length,1);assert.deepEqual(f.draft(),before);
    assert.equal(f.ctx.savingRef.current,false);assert.equal(f.disabled(),false);
  }
  f=fixture();f.ctx.name='  ';await f.run.save();assert.equal(f.calls.length,0);assert.equal(f.alerts[0][0],'Falta nombre');
  f=fixture(true);f.ctx.resourceLoaded=false;await f.run.save();assert.equal(f.calls.length,0);
  f=fixture();f.ctx.deletion.locked.current=true;await f.run.save();assert.equal(f.calls.length,0);
  console.log('PASS: null/unverifiable response never closes; original name/loading/deletion validations retained.');

  f=fixture(true);const update=f.ctx.api.updateCategory;
  f.ctx.api.updateCategory=(...args)=>{const result=update(...args);return new Promise(r=>finish=()=>result.then(r));};
  const save=f.run.save();await f.run.remove();assert.equal(f.calls.length,1);finish();await save;
  f=fixture(true);f.ctx.api.deleteCategory=async()=>new Promise(r=>finish=r);
  const remove=f.run.remove();await f.run.save();assert.equal(f.calls.length,0);finish();await remove;
  console.log('PASS: Save and Delete cannot overlap in either order; deletion hook unchanged.');

  f=fixture();f.ctx.qc.invalidateQueries=()=>Promise.reject(Error('refetch failed'));await f.run.save();await tick();
  assert.equal(f.counts().backs,1);assert.equal(f.ctx.saveComplete.current,true);assert.equal(f.alerts[0][0],'Actualizar categorías');
  await f.run.save();assert.equal(f.calls.length,1);
  f=fixture();f.ctx.mounted.current=false;await f.run.save();assert.equal(f.counts().backs,0);
  console.log('PASS: confirmed save plus refresh error is not reported as a failed POST; no duplicate retry or navigation after unmount.');

  const base=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),marker='const useStyles =';
  assert.equal(normalizeHomeColors(source.slice(source.indexOf(marker))),normalizeHomeColors(base.slice(base.indexOf(marker))));
  assert(source.includes('editable={!saving && !deletion.busy}'));
  assert(source.includes('pointerEvents={deletion.busy || saving ? "none" : "auto"}'));
  const compiled=ts.transpileModule(source,{fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}});
  assert.equal((compiled.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  console.log('PASS: input/button guards, unchanged non-color styles, approved Home color aliases and TSX syntax; no backend/database calls.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
