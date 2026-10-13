// C8/C12: actual handlers, synthetic mutation/refetch/cache; no backend writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const cp=require('node:child_process'),ts=require('typescript');
const root=path.resolve(__dirname,'../..');
const files={goal:'frontend/app/goals/contribute.tsx',list:'frontend/app/bills/index.tsx',detail:'frontend/app/bills/[id].tsx'};
const read=file=>process.env.C8_C12_TEST_REF?cp.execFileSync('git',['show',`${process.env.C8_C12_TEST_REF}:${file}`],{cwd:root,encoding:'utf8'}):fs.readFileSync(path.join(root,file),'utf8');
function inspect(text,file){const tree=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),variables={},calls=[],refresh={};
  function visit(n){if(ts.isVariableDeclaration(n)&&n.initializer)variables[n.name.getText(tree)]=n.initializer.getText(tree);
    if(ts.isCallExpression(n)&&n.expression.getText(tree)==='api.createGoalContribution')calls.push(n.getText(tree));
    if((ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n))&&n.tagName.getText(tree)==='RefreshControl')for(const a of n.attributes.properties){if(a.name&&a.initializer?.expression)refresh[a.name.getText(tree)]=a.initializer.expression.getText(tree);}
    ts.forEachChild(n,visit);}visit(tree);return {variables,calls,refresh};}
const sources=Object.fromEntries(Object.entries(files).map(([k,f])=>[k,read(f)]));
const parsed=Object.fromEntries(Object.entries(files).map(([k,f])=>[k,inspect(sources[k],f)]));
const compile=code=>ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText;
const plain=v=>JSON.parse(JSON.stringify(v));
class ApiError extends Error{constructor(status){super('HTTP '+status);this.status=status;this.detail='Synthetic failure';}}
function goal(realOn=false){let requests=0,backs=0,finish,fail;const keys=[],calls=[];
  const ctx={savingRef:{current:false},g:{current_amount:100},amount:'25.129',parseAmount:Number,isDeposit:true,id:'goal',kind:'deposit',accountId:'a',notes:' Original ',realOn,idemKey:'original-intent',
    dateIso:()=> '2026-10-13T12:00:00Z',formatCurrencyInt:String,t:k=>k,ApiError,Error,Math,
    setSaving:v=>ctx.saving=v,setError:v=>ctx.error=v,router:{back:()=>backs++},qc:{invalidateQueries:({queryKey})=>{keys.push(queryKey[0]);return Promise.resolve();}},
    api:{createGoalContribution:(...args)=>{requests++;calls.push(plain(args));return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});}},
  };
  vm.createContext(ctx);vm.runInContext(compile('globalThis.save='+parsed.goal.variables.save),ctx);
  return {ctx,keys,calls,run:ctx.save,finish:()=>finish({id:'contribution'}),fail:()=>fail(new ApiError(503)),counts:()=>({requests,backs})};
}
function refresh(kind,functions={}){const counts={};
  const ctx={refreshing:false,refreshingRef:{current:false},setRefreshing:v=>ctx.refreshing=v};
  for(const name of kind==='list'?['listQ','sumQ']:['q']){
    counts[name]=0;ctx[name]={isFetching:true,refetch:options=>{counts[name]++;assert.deepEqual(plain(options),{cancelRefetch:false});return functions[name]?.();}};
  }
  vm.createContext(ctx);
  vm.runInContext(compile('globalThis.run='+(parsed[kind].variables.onRefresh||parsed[kind].refresh.onRefresh)),ctx);
  return {ctx,counts,run:ctx.run,visible:()=>vm.runInContext(parsed[kind].refresh.refreshing,ctx)};
}
const tick=()=>new Promise(r=>setImmediate(r));
async function main(){
  const previousGoals=['goals-overview','goal-detail','goal-contribs','goals'],calendar=['calendar-events','calendar-summary','calendar-upcoming'];
  for(const real of [false,true]){
    const f=goal(real),pending=f.run();assert.equal(f.keys.length,0);assert.equal(f.counts().backs,0);
    f.finish();await pending;
    assert.deepEqual(f.keys,[...previousGoals,...calendar,...(real?['accounts','transactions','summary']:[])]);
    assert.deepEqual(f.calls,[['goal',{kind:'deposit',amount:25.13,date:'2026-10-13T12:00:00Z',account_id:'a',notes:'Original',real_movement:real},'original-intent']]);
    assert.equal(f.counts().backs,1);
  }
  let f=goal(true),pending=f.run();f.fail();await pending;assert.equal(f.keys.length,0);assert.equal(f.counts().backs,0);assert.equal(f.ctx.savingRef.current,false);
  const retry=f.run();f.finish();await retry;assert(calendar.every(k=>f.keys.includes(k)));
  console.log('PASS C8: tracking/real contribution success invalidates all calendar prefixes and preserves previous keys; failed POST invalidates nothing; retry and exact financial payload/key retained.');

  for(const kind of ['list','detail']){
    const queries=kind==='list'?['listQ','sumQ']:['q'];let done={},functions={};
    for(const query of queries)functions[query]=()=>new Promise(resolve=>done[query]=resolve);
    f=refresh(kind,functions);assert.equal(f.visible(),false,'Background fetching must not display manual refresh');
    pending=f.run();assert.equal(f.visible(),true);await tick();await f.run();
    assert(queries.every(q=>f.counts[q]===1));
    done[queries[0]]();await tick();if(queries.length>1)assert.equal(f.visible(),true,'Wait for the remaining query');
    for(const q of queries.slice(1))done[q]();await pending;
    assert.equal(f.visible(),false);assert.equal(f.ctx.refreshingRef.current,false);
    const repeat=f.run();await tick();for(const q of queries)done[q]();await repeat;
    assert(queries.every(q=>f.counts[q]===2));assert.equal(f.visible(),false);
    console.log('PASS C12 '+kind+': manual-only indicator, delayed queries, concurrent gestures coalesced and completion reset.');
    for(const errorMode of ['reject','throw']){
      const failing={};for(const q of queries)failing[q]=()=>errorMode==='reject'?Promise.reject(Error('synthetic')):(()=>{throw Error('synthetic');})();
      f=refresh(kind,failing);await f.run();assert.equal(f.visible(),false);assert.equal(f.ctx.refreshingRef.current,false);assert(queries.every(q=>f.counts[q]===1));
      await f.run();assert(queries.every(q=>f.counts[q]===2));assert.equal(f.visible(),false);
    }
  }
  let release;
  f=refresh('list',{listQ:()=>Promise.reject(Error('list failed')),sumQ:()=>new Promise(r=>release=r)});
  pending=f.run();await tick();assert.equal(f.visible(),true);release();await pending;assert.equal(f.visible(),false);
  console.log('PASS C12: rejected/synchronous failures reset indicator, permit later retry and wait for the other list query.');

  if(!process.env.C8_C12_TEST_REF){
    for(const [kind,file] of Object.entries(files)){
      const old=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),base=inspect(old,file),marker='const useStyles =';
      assert.equal(sources[kind].slice(sources[kind].indexOf(marker)),old.slice(old.indexOf(marker)));
      if(kind==='goal'){assert.deepEqual(parsed.goal.calls,base.calls);assert.equal(parsed.goal.variables.dateIso,base.variables.dateIso);assert.equal(parsed.goal.variables.idemKey,base.variables.idemKey);}
      if(kind==='detail')assert.equal(parsed.detail.variables.doConfirm,base.variables.doConfirm);
      const out=ts.transpileModule(sources[kind],{fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}});
      assert.equal((out.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
    }
  }
  console.log('PASS: exact financial mutation/date/idempotency and bill deletion handlers preserved; identical styles; TSX syntax.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
