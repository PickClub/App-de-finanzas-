const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// Synthetic storage and server ledger only; no network or MongoDB access.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ts = require('typescript'), root = path.resolve(__dirname, '..');
const compile = file => ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;
class ApiError extends Error { constructor(status) { super('HTTP '+status); this.status=status; } }
const journal = {}, flow = {};
vm.runInNewContext(compile('src/debt-payments/journal-v2.ts'),localeGlobals({exports:journal}));
vm.runInNewContext(compile('src/debt-payments/flow-v2.ts'),localeGlobals({exports:flow,require:n=>n==='../api'?{ApiError}:journal}));
const A='11111111-1111-4111-8111-111111111111', B='22222222-2222-4222-8222-222222222222';
const payload={debt_id:'d',amount:100,account_id:'a',notes:'original',date:null};
const plain=x=>JSON.parse(JSON.stringify(x));
function fixture() {
  const disk=new Map(), ledger=new Map(), flags={}; let next=0, sends=0, reads=0, url='first', environment=A, user='default-user', balance=1000;
  const context=async()=>{if(flags.network)throw Error('offline');return {version:1,environment_id:environment,user_id:user,mode:'single_user',
    capabilities:{expected_context_headers:true,debt_payment_reconciliation:true,cross_device_recovery:false}};};
  const storage={async getAllKeys(){if(flags.read)throw Error('read');return [...disk.keys()];},
    async getItem(k){if(flags.read)throw Error('read');return disk.get(k)??null;},
    async setItem(k,v){if(flags.write || (flags.confirmWrite && JSON.parse(v).state==='confirmed'))throw Error('write');disk.set(k,v);},
    async removeItem(k){if(flags.remove)throw Error('remove');disk.delete(k);}};
  const fresh=()=>flow.createV2PaymentFlow({storage,expected:{environment_id:A,user_id:'default-user'},readContext:context,newKey:()=>`key-${++next}`,
    reconcile:async(p,key,c)=>{reads++;assert.equal(c.environment_id,A);if(flags.queryFail)throw Error('query offline');
      if(flags.status)return {status:flags.status};const found=ledger.get(key);
      if(!found)return {status:'not_found'};
      if(JSON.stringify(plain(p))!==JSON.stringify(found.original))return {status:'discrepancy'};
      return {status:'matched',original_request_matches:true,current_payment:found.payment};},
    send:async(p,key,c)=>{sends++;assert.equal(c.environment_id,A);assert.equal(c.user_id,'default-user');
      if(flags.http409)throw new ApiError(409);if(flags.beforeCommit)throw Error('offline before commit');
      if(!ledger.has(key)){balance-=p.amount;ledger.set(key,{original:plain(p),payment:{...plain(p),id:'p-'+key,transaction_id:'t-'+key,date:'generated'}});}
      if(flags.lost)throw Error('response lost');return ledger.get(key).payment;}});
  return {disk,ledger,flags,fresh,counts:()=>({sends,reads,balance}),alias:()=>url='second',environment:v=>environment=v,user:v=>user=v};
}
async function main(){
  // Actual gate: other deployments default to legacy; only explicit development opt-in uses v2.
  const legacy={recover:()=>null};
  for(const [dev,env,enabled] of [[true,{},false],[false,{EXPO_PUBLIC_R6_LOCAL_V2:'1'},false],
      [true,{EXPO_PUBLIC_R6_LOCAL_V2:'1',EXPO_PUBLIC_R6_EXPECTED_ENVIRONMENT_ID:A,EXPO_PUBLIC_R6_EXPECTED_USER_ID:'default-user'},true]]) {
    const gate={};let constructed=0, supplied;
    vm.runInNewContext(compile('src/debt-payments/local-flow.ts'),localeGlobals({exports:gate,__DEV__:dev,process:{env},
      require:n=>n.includes('async-storage')?{default:{}}:n==='../api'?{api:{}}:n==='./pending'?{pendingDebtPayments:legacy}:
        {createV2PaymentFlow:d=>{constructed++;supplied=d;return {prepared:true};}}}));
    assert.equal(gate.LOCAL_V2_ENABLED,enabled);assert.equal(constructed,enabled?1:0);
    if(enabled)assert.deepEqual(plain(supplied.expected),{environment_id:A,user_id:'default-user'});
    else assert.equal(gate.localPaymentFlow.recover,legacy.recover);
  }
  console.log('PASS flow: explicit local development activation; default and production stay legacy');

  let f=fixture(), c=f.fresh();f.flags.lost=true;
  await assert.rejects(c.submit(payload));assert.equal(f.counts().balance,900);
  c=f.fresh();const pending=await c.recover();assert.equal(pending.state,'pending');assert.equal(f.counts().sends,1);
  f.alias();f.flags.lost=false;const confirmed=await c.submit({...payload});assert.equal(confirmed.state,'confirmed');
  assert.equal(confirmed.key,pending.key);assert.deepEqual(plain(confirmed.payload),payload);assert.equal(f.counts().sends,1);assert.equal(f.counts().reads,1);
  console.log('PASS flow: restart, alias and lost response reconcile without a second discount');

  await assert.rejects(c.submit(payload));assert.equal(f.counts().sends,1);
  f.flags.remove=true;await assert.rejects(c.startNew());assert.equal((await c.recover()).state,'confirmed');await assert.rejects(c.submit(payload));
  f.flags.remove=false;await c.startNew();const second=await c.submit(payload);assert.notEqual(second.key,confirmed.key);assert.equal(f.counts().balance,800);
  console.log('PASS flow: confirmation, failed cleanup and explicit identical second payment');

  f=fixture();f.flags.beforeCommit=true;await assert.rejects(f.fresh().submit(payload));
  const original=await f.fresh().recover();f.flags.beforeCommit=false;
  await assert.rejects(f.fresh().submit({...payload,account_id:'other'}));assert.equal(f.counts().sends,1);
  await f.fresh().submit(payload);assert.equal(f.counts().reads,1);assert.equal([...f.ledger.keys()][0],original.key);assert.equal(f.counts().balance,900);
  console.log('PASS flow: not found retries original key/payload; changed payload blocked');

  for(const change of [f=>f.environment(B),f=>f.user('other'),f=>f.flags.network=true]){
    f=fixture();f.flags.lost=true;await assert.rejects(f.fresh().submit(payload));const bytes=[...f.disk];change(f);
    await assert.rejects(f.fresh().recover());await assert.rejects(f.fresh().submit(payload));assert.equal(f.counts().sends,1);assert.deepEqual([...f.disk],bytes);
  }
  console.log('PASS flow: different environment/user and unavailable context preserve and block pending');

  f=fixture();const bad=flow.createV2PaymentFlow({storage:{async getAllKeys(){return [];},async getItem(){return null;},async setItem(){throw Error('must not write');},async removeItem(){}},
    expected:{environment_id:'',user_id:''},readContext:async()=>({version:1,environment_id:A,user_id:'default-user',mode:'single_user',
      capabilities:{expected_context_headers:true,debt_payment_reconciliation:true,cross_device_recovery:false}}),
    reconcile:async()=>{throw Error('must not query');},send:async()=>{throw Error('must not send');},newKey:()=>{throw Error('must not generate');}});
  await assert.rejects(bad.recover());await assert.rejects(bad.submit(payload));
  console.log('PASS flow: enabled gate with missing identity blocks storage, recovery and sending');

  f=fixture();f.flags.http409=true;await assert.rejects(f.fresh().submit(payload));assert.equal((await f.fresh().recover()).state,'conflict');
  f.flags.http409=false;await assert.rejects(f.fresh().submit(payload));assert.equal(f.counts().sends,1);
  for(const status of ['discrepancy','cancelled','unverifiable']){f.flags.status=status;await assert.rejects(f.fresh().submit(payload));assert.equal(f.counts().sends,1);}
  console.log('PASS flow: 409, cancelled, discrepancy and unverifiable never authorize a new discount');

  f=fixture();f.flags.lost=true;await assert.rejects(f.fresh().submit(payload));f.flags.http409=true;f.flags.lost=false;
  // A previously blocked key can be resolved only by a verifiable matching reconciliation.
  f.flags.status='discrepancy';await assert.rejects(f.fresh().submit(payload));delete f.flags.status;
  assert.equal((await f.fresh().submit(payload)).state,'confirmed');assert.equal(f.counts().sends,1);
  console.log('PASS flow: matching reconciliation resolves discrepancy without sending');

  f=fixture();f.flags.confirmWrite=true;await assert.rejects(f.fresh().submit(payload));assert.equal(f.counts().balance,900);
  f.flags.confirmWrite=false;assert.equal((await f.fresh().submit(payload)).state,'confirmed');assert.equal(f.counts().sends,1);
  console.log('PASS flow: shutdown window before durable confirmation recovers by reconciliation');

  for(const flag of ['read','write','network']){f=fixture();f.flags[flag]=true;await assert.rejects(f.fresh().submit(payload));assert.equal(f.counts().sends,0);}
  f=fixture();f.disk.set('moneyflow:debt-payment:v1:old','legacy bytes');await assert.rejects(f.fresh().recover());await assert.rejects(f.fresh().submit(payload));
  assert.equal(f.disk.get('moneyflow:debt-payment:v1:old'),'legacy bytes');assert.equal(f.counts().sends,0);
  console.log('PASS flow: storage failures and unverifiable legacy record block all sends');

  f=fixture();const results=await Promise.allSettled([f.fresh().submit(payload),f.fresh().submit(payload)]);
  assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal(f.counts().balance,900);assert.equal(f.counts().sends,1);
  console.log('PASS flow: simultaneous instances serialize; no second intention or discount');

  // Execute the actual screen handler with the prepared v2 service and synthetic hooks.
  const screen=fs.readFileSync(path.join(root,'app/debts/[id]/pay.tsx'),'utf8');
  const source=ts.createSourceFile('pay.tsx',screen,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let handler;function find(node){if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='save')handler=node.initializer.getText(source);ts.forEachChild(node,find);}find(source);
  assert(handler);
  f=fixture();f.flags.lost=true;const alerts=[];
  const ui={exports:{},pendingDebtPayments:f.fresh(),operation:null,d:{id:'d'},amt:100,accountId:'a',notes:'original',
    recoveryReady:{current:true},recoveryError:{current:null},savingRef:{current:false},qc:{invalidateQueries(){}},
    setOperation:r=>ui.operation=r,setAmount(){},setAccountId(){},setNotes(){},setSaving(){},setReady(){},
    Alert:{alert:(...a)=>alerts.push(a)}};
  vm.runInNewContext(ts.transpileModule('exports.save = '+handler,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,localeGlobals(ui));
  await ui.exports.save();assert.equal(ui.operation.state,'pending');assert.equal(f.counts().balance,900);
  ui.pendingDebtPayments=f.fresh();f.flags.lost=false;await ui.exports.save();assert.equal(ui.operation.state,'confirmed');assert.equal(f.counts().sends,1);
  await ui.exports.save();assert.equal(ui.operation,null);assert.equal(f.counts().sends,1);
  await ui.exports.save();assert.equal(ui.operation.state,'confirmed');assert.equal(f.counts().balance,800);
  // A displayed conflict must perform reconciliation rather than a blind resend.
  f=fixture();f.flags.http409=true;ui.pendingDebtPayments=f.fresh();ui.operation=null;
  await ui.exports.save();assert.equal(ui.operation.state,'conflict');f.flags.http409=false;
  await ui.exports.save();assert.equal(f.counts().reads,1);assert.equal(f.counts().sends,1);
  console.log('PASS flow: actual screen handler recovers v2, reconciles conflicts and separates explicit new payment');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
