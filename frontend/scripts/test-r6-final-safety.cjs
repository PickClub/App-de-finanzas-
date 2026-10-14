const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// In-memory regressions only. Never uses native storage, network or MongoDB.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('typescript'),root=path.resolve(__dirname,'..');
const compile=f=>ts.transpileModule(fs.readFileSync(path.join(root,f),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const journal={},v2={},v1={};class ApiError extends Error{constructor(status){super('HTTP '+status);this.status=status;}}
vm.runInNewContext(compile('src/debt-payments/journal-v2.ts'),localeGlobals({exports:journal}));
vm.runInNewContext(compile('src/debt-payments/flow-v2.ts'),localeGlobals({exports:v2,require:n=>n==='../api'?{ApiError}:journal}));
vm.runInNewContext(compile('src/debt-payments/pending.ts'),localeGlobals({exports:v1,require:n=>n==='./journal-v2'?journal:n.includes('async-storage')?{default:{}}:{ApiError,api:{},debtPaymentBackend:()=>''}}));
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const payload={debt_id:'d',amount:100,account_id:'a',notes:'',date:null};
const context={version:1,environment_id:A,user_id:'default-user',mode:'single_user',capabilities:{expected_context_headers:true,debt_payment_reconciliation:true,cross_device_recovery:false}};
const plain=x=>JSON.parse(JSON.stringify(x));
const record=(state='pending',environment=A)=>({version:2,environment_id:environment,user_id:'default-user',key:'original-v2',payload:{...payload},state,
  ...(state==='confirmed'?{receipt:{id:'p-original-v2',transaction_id:'t-original-v2'}}:{})});
const slot=r=>`moneyflow:debt-payment:v2:${r.environment_id}:${r.user_id}`;
function fixture(){
 const disk=new Map(),ledger=new Map(),flags={};let keys=0,sends=0,queries=0,url='http://first.invalid',balance=1000,remaining=500;
 const storage={async getAllKeys(){if(flags.list)throw Error('list failure');return [...disk.keys()];},async getItem(k){if(flags.read)throw Error('read failure');return disk.get(k)??null;},
  async setItem(k,v){disk.set(k,v)},async removeItem(k){disk.delete(k)}};
 async function send(p,k){sends++;if(!ledger.has(k)){balance-=p.amount;remaining-=p.amount;ledger.set(k,{...plain(p),id:'p-'+k,transaction_id:'t-'+k});}if(flags.lost)throw Error('lost response');return ledger.get(k);}
 async function reconcile(p,k){queries++;if(flags.query)throw Error('query unavailable');if(flags.status)return {status:flags.status};const existing=ledger.get(k);
  return existing?{status:'matched',original_request_matches:true,current_payment:existing}:{status:'not_found'};}
 const legacy=()=>v1.createPaymentCoordinator({storage,backend:()=>url,newKey:()=>`v1-${++keys}`,send,reconcile});
 const modern=()=>v2.createV2PaymentFlow({storage,expected:context,readContext:async()=>{if(flags.context)throw Error('context unavailable');return context;},newKey:()=>`v2-${++keys}`,send,reconcile});
 function selected(env={},dev=true){const out={};vm.runInNewContext(compile('src/debt-payments/local-flow.ts'),localeGlobals({exports:out,__DEV__:dev,process:{env},
  require:n=>n.includes('async-storage')?{default:storage}:n==='../api'?{api:{getFinancialContext:async()=>context,createContextProtectedDebtPayment:send,reconcileDebtPayment:reconcile}}:
   n==='./pending'?{pendingDebtPayments:legacy()}:v2}));return out.localPaymentFlow;}
 return {disk,ledger,flags,legacy,modern,selected,counts:()=>({keys,sends,queries,balance,remaining}),alias:()=>url='http://alias.invalid'};
}
async function main(){
 let f=fixture();f.flags.lost=true;await assert.rejects(f.modern().submit(payload));const bytes=[...f.disk];f.flags.lost=false;
 for(const [env,dev] of [[{},true],[{EXPO_PUBLIC_R6_LOCAL_V2:'0'},true],[{EXPO_PUBLIC_R6_LOCAL_V2:'1'},true],
  [{EXPO_PUBLIC_R6_LOCAL_V2:'1',EXPO_PUBLIC_R6_EXPECTED_ENVIRONMENT_ID:B},true],[{EXPO_PUBLIC_R6_LOCAL_V2:'1'},false]]){
  const c=f.selected(env,dev);await assert.rejects(c.recover());await assert.rejects(c.submit(payload));
  assert.deepEqual([...f.disk],bytes);assert.equal(f.counts().keys,1);assert.equal(f.counts().sends,1);
 }
 f.alias();await assert.rejects(f.legacy().submit({...payload,debt_id:'another-debt'}));assert.equal(f.counts().sends,1);
 console.log('PASS final R6: unresolved v2 blocks disabled, absent, incomplete, changed and production configuration; alias/debt cannot evade it');

 for(const state of ['pending','conflict'])for(const environment of [A,B]){
  f=fixture();const r=record(state,environment);f.disk.set(slot(r),JSON.stringify(r));const before=[...f.disk];
  await assert.rejects(f.legacy().recover());await assert.rejects(f.legacy().submit(payload));assert.equal(f.counts().keys,0);assert.equal(f.counts().sends,0);assert.deepEqual([...f.disk],before);
 }
 console.log('PASS final R6: pending/discrepancy in any unverifiable environment is retained and blocks v1');

 for(const flag of ['list','read']){
  f=fixture();f.flags[flag]=true;await assert.rejects(f.legacy().submit(payload));assert.equal(f.counts().keys,0);assert.equal(f.counts().sends,0);
 }
 for(const bad of ['{}','not-json',JSON.stringify({...record('confirmed'),receipt:{id:'p'}})]){
  f=fixture();f.disk.set(slot(record()),bad);await assert.rejects(f.legacy().submit(payload));assert.equal(f.counts().keys,0);assert.equal(f.disk.get(slot(record())),bad);
 }
 f=fixture();f.disk.set(slot(record()),JSON.stringify(record('confirmed',B)));await assert.rejects(f.legacy().submit(payload));assert.equal(f.counts().sends,0);
 console.log('PASS final R6: unreadable, corrupt, unverified confirmation and identity/slot mismatch fail closed');

 f=fixture();const resolved=record('confirmed');f.disk.set(slot(resolved),JSON.stringify(resolved));const raw=f.disk.get(slot(resolved));
 await f.legacy().submit({...payload,amount:150});assert.equal(f.counts().sends,1);assert.equal(f.disk.get(slot(resolved)),raw);
 // An older v1 intention is still recovered and retried using its own original key.
 f=fixture();const old={version:1,backend:'http://first.invalid',debtId:'d',key:'old-v1',payload:{...payload},state:'pending'};
 f.disk.set('moneyflow:debt-payment:v1:'+encodeURIComponent(old.backend),JSON.stringify(old));
 assert.equal((await f.legacy().recover()).key,'old-v1');await f.legacy().submit(payload);assert(f.ledger.has('old-v1'));assert.equal(f.counts().keys,0);
 console.log('PASS final R6: validated confirmed v2 permits legitimate payment; old v1 recovery preserves original key');

 f=fixture();f.flags.lost=true;await assert.rejects(f.modern().submit(payload));f.flags.lost=false;
 const before=f.counts();const verified=await f.modern().verify();assert.equal(verified.state,'confirmed');assert.equal(f.counts().sends,before.sends);assert.equal(f.counts().keys,before.keys);
 await f.modern().startNew();await f.modern().submit({...payload,amount:150});
 assert.deepEqual([...f.ledger.values()].map(p=>p.amount),[100,150]);assert.equal(f.counts().balance,750);assert.equal(f.counts().remaining,250);
 console.log('PASS final R6: read-only verification resolves response loss; 100 + legitimate 150 yields 750/250 with two records');

 for(const status of ['not_found','unverifiable','discrepancy','cancelled']){
  f=fixture();const r=record();f.disk.set(slot(r),JSON.stringify(r));f.flags.status=status;
  if(['discrepancy','cancelled'].includes(status))await assert.rejects(f.modern().verify());else assert.equal((await f.modern().verify()).state,'pending');
  assert.equal(f.counts().sends,0);assert.equal(f.counts().keys,0);const kept=JSON.parse(f.disk.get(slot(r)));assert.equal(kept.key,r.key);assert.deepEqual(kept.payload,payload);
 }
 console.log('PASS final R6: absent, uncertain, discrepant and cancelled verification never creates payments or keys');

 const screen=fs.readFileSync(path.join(root,'app/debts/[id]/pay.tsx'),'utf8'),source=ts.createSourceFile('pay.tsx',screen,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let handler;
 function visit(n){if(ts.isVariableDeclaration(n)&&n.name.getText(source)==='save')handler=n.initializer.getText(source);ts.forEachChild(n,visit)}visit(source);
 f=fixture();f.flags.lost=true;await assert.rejects(f.modern().submit(payload));f.flags.lost=false;f.flags.context=true;
 const ui={exports:{},pendingDebtPayments:f.modern(),operation:null,d:{id:'d'},amt:100,accountId:'a',notes:'',recoveryReady:{current:false},recoveryError:{current:Error('previous failure')},savingRef:{current:false},
  qc:{invalidateQueries(){}},setOperation:r=>ui.operation=r,setAmount(){},setAccountId(){},setNotes(){},setSaving(){},setReady(){},Alert:{alert(){}}};
 vm.runInNewContext(ts.transpileModule('exports.save='+handler,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,localeGlobals(ui));
 await ui.exports.save();assert.equal(ui.recoveryReady.current,false);assert.equal(f.counts().sends,1);
 f.flags.context=false;await ui.exports.save();assert.equal(ui.operation.state,'confirmed');assert.equal(ui.recoveryReady.current,true);assert.equal(f.counts().sends,1);assert.equal(f.counts().keys,1);
 console.log('PASS final R6: actual Verify register button retries after temporary error and reconciles; never calls payment creation');
}
main().catch(e=>{console.error(e);process.exitCode=1});
