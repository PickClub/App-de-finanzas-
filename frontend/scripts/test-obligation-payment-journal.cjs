// Synthetic storage and transport only: no native storage, real network or MongoDB.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('typescript'),root=path.resolve(__dirname,'..');
const compile=f=>ts.transpileModule(fs.readFileSync(path.join(root,f),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const out={};vm.runInNewContext(compile('src/obligation-payments/journal.ts'),{exports:out});
const A='11111111-1111-4111-8111-111111111111',B='22222222-2222-4222-8222-222222222222';
const target={kind:'bill',id:'bill',due:'2026-10-20'};
const payload={amount:100,account_id:'account',date:'2026-10-12T12:00:00.000Z',notes:null};
const context=()=>({version:1,environment_id:A,user_id:'default-user',mode:'single_user',capabilities:{bill_payment_context_headers:true,recurring_payment_context_headers:true,bill_payment_reconciliation:true,recurring_payment_reconciliation:true}});
function fixture(){const disk=new Map(),ledger=new Map(),flags={},calls=[];let keys=0,balance=1000,ctx=context();
 const storage={async getItem(k){if(flags.read)throw Error('read failed');return disk.get(k)??null;},async setItem(k,v){const r=JSON.parse(v);
  if(flags.write || (flags.confirm && ['confirmed','reconciled'].includes(r.state)))throw Error('write failed');disk.set(k,v);
  if(flags.readback){flags.read=true;throw Error('uncertain local write');}},async removeItem(k){if(flags.cleanup)throw Error('cleanup failed');disk.delete(k);}};
 const queries=[];
 const raw=()=>out.createObligationPayments({storage,readContext:async()=>{if(flags.context)throw Error('context unavailable');return ctx;},newKey:()=>`operation-${++keys}`,
  reconcile:async(t,p,k,c)=>{
   queries.push({t:structuredClone(t),p:structuredClone(p),k,c:structuredClone(c)});
   if(flags.queryError)throw Error('query unavailable');
   const existing=ledger.get(k),matches=existing?.signature===JSON.stringify({t,p});
   const status=flags.reconcileStatus||(existing?(matches?'matched':'discrepancy'):'not_found');
   const resolved=['matched','cancelled','tracking_removed'].includes(status);
   return {version:1,status,financial_state:resolved?(status==='cancelled'?'annulled':p.mode==='mark'?'none':'active'):'unknown',
    original_request_matches:resolved?true:status==='discrepancy'?false:null,environment_id:flags.badQueryContext?B:c.environment_id,user_id:c.user_id,
    origin:t.kind,parent_id:t.id,original_due_date:t.due,receipt:resolved&&existing?structuredClone(existing.record):null};
  },
  send:async(t,p,k,c)=>{calls.push({t:structuredClone(t),p:structuredClone(p),k,c:structuredClone(c)});assert.equal(c.environment_id,A);assert.equal(c.user_id,'default-user');
   if(flags.before)throw Error('network before response');
   if(flags.conflict){const e=Error('payload conflict');e.status=409;throw e;}
   const signature=JSON.stringify({t,p});let existing=ledger.get(k);
   if(existing&&existing.signature!==signature){const e=Error('different payload');e.status=409;throw e;}
   if(!existing){const record={id:'receipt-'+k,user_id:'default-user',amount:p.amount,account_id:p.account_id,date:p.date,
    transaction_id:p.mode==='mark'?null:p.transaction_id||'movement-'+k,
    ...(t.kind==='bill'?{bill_id:t.id}:{recurring_id:t.id,due_date:t.due,mode:p.mode,settles:false})};
    if(p.mode==='link'){record.amount=70;record.date='2026-10-01T12:00:00Z';record.account_id='source-account';}
    if(p.mode!=='mark'&&p.mode!=='link')balance-=p.amount;
    existing={signature,record};ledger.set(k,existing);}
   if(flags.lost){const e=Error('lost commit response');e.status=503;throw e;}
   if(flags.mismatch)return {...existing.record,bill_id:'another-bill'};
   return structuredClone(existing.record);
  }});
 const make=()=>{const c=raw();return {...c,submit:(t,p,expected=out.verifiedContext(context()))=>c.submit(t,p,expected)};};
 return {disk,ledger,flags,calls,queries,storage,make,counts:()=>({keys,balance,calls:calls.length}),context:c=>ctx=c};}
async function main(){
 for(const kind of ['bill','recurring']){
  const cap=kind==='bill'?'bill_payment_delete_context_headers':'recurring_payment_delete_context_headers';
  const valid={...context(),capabilities:{...context().capabilities,[cap]:true}};
  const pinned=out.verifiedDeletionContext(valid,kind);
  assert.throws(()=>out.verifiedDeletionContext(context(),kind));
  assert.throws(()=>out.verifiedDeletionContext({...valid,environment_id:B},kind,pinned));
  assert.throws(()=>out.verifiedDeletionContext({...valid,user_id:'someone'},kind,pinned));
  assert.deepEqual(out.verifiedDeletionContext(valid,kind,pinned),pinned);
 }
 const apiModule={},requests=[];
 vm.runInNewContext(compile('src/api.ts'),{exports:apiModule,process:{env:{EXPO_PUBLIC_BACKEND_URL:'http://synthetic.invalid'}},
  fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({ok:true})};}});
 const ctx=out.verifiedContext(context());
 await apiModule.api.billDeletePayment('payment',ctx);await apiModule.api.rpDeletePayment('record',ctx);
 for(const {options} of requests){assert.equal(options.method,'DELETE');assert.equal(options.headers['MoneyFlow-Environment-ID'],A);assert.equal(options.headers['MoneyFlow-User-ID'],'default-user');}
 await apiModule.api.reconcileBillPayment('bill',payload,'original-key',ctx);
 await apiModule.api.reconcileRecurringPayment('rp',payload,'original-key',ctx);
 for(const {url,options} of requests.slice(2)){assert.ok(url.endsWith('/payments/reconcile'));assert.equal(options.method,'POST');assert.equal(options.headers['Idempotency-Key'],'original-key');assert.equal(options.headers['MoneyFlow-Environment-ID'],A);assert.equal(options.body,JSON.stringify(payload));}
 for(const file of ['app/bills/[id].tsx','app/recurring/[id].tsx']){
  const source=fs.readFileSync(path.join(root,file),'utf8');
  assert.ok(source.includes('verifiedDeletionContext(await api.getFinancialContext()'));
  assert.ok(source.includes('deletionContext.current.context'));
  assert.ok(source.includes('deletionContext.current?.id !== id'));
 }
 console.log('PASS: protected DELETE headers, effective-context pin and current capabilities; no authentication or unprotected fallback');
 let f=fixture(),c=f.make(),r=await c.submit(target,payload);assert.equal(r.state,'confirmed');assert.equal(f.counts().balance,900);
 await assert.rejects(c.submit(target,payload));assert.equal(f.counts().keys,1);await c.acknowledge(target,r.key);
 r=await c.submit(target,payload);assert.equal(f.counts().balance,800);assert.equal(f.counts().keys,2);
 console.log('PASS: durable confirmation, explicit acknowledgment, second identical legitimate payment with new key');
 for(const failure of ['lost','before']){f=fixture();f.flags[failure]=true;await assert.rejects(f.make().submit(target,payload));
  const bytes=[...f.disk];f.flags[failure]=false;c=f.make();r=await c.recover(target);assert.equal(r.state,'pending');
  assert.deepEqual([...f.disk],bytes);const mutated={...payload,date:'2030-01-01T00:00:00Z',account_id:'changed',amount:150};
  await assert.rejects(c.submit(target,mutated));assert.equal(f.counts().keys,1);
  r=await c.retry(target,r.key);assert.equal(f.ledger.size,1);assert.equal(f.counts().balance,900);
  assert.deepEqual(f.calls[0].p,f.calls[1].p);assert.equal(f.calls[0].k,f.calls[1].k);}
 console.log('PASS: response loss/503, network error, remount/restart and device date change reuse exact original key/payload');
 f=fixture();const results=await Promise.allSettled([f.make().submit(target,payload),f.make().submit(target,payload)]);
 assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal(f.ledger.size,1);assert.equal(f.counts().keys,1);
 console.log('PASS: double touch and concurrent coordinators cannot create two intentions');
 for(const changed of [{...context(),environment_id:B},{...context(),user_id:'someone'}, {...context(),capabilities:{}},null]){
  f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));const bytes=[...f.disk];f.context(changed);
  await assert.rejects(f.make().recover(target));await assert.rejects(f.make().retry(target,'operation-1'));assert.deepEqual([...f.disk],bytes);assert.equal(f.calls.length,1);}
 f=fixture();f.context({...context(),capabilities:{}});await assert.rejects(f.make().submit(target,payload));assert.equal(f.counts().keys,0);assert.equal(f.calls.length,0);
 f=fixture();c=f.make();const prepared=await c.prepare(target);f.context({...context(),environment_id:B});
 await assert.rejects(c.submit(target,payload,prepared.context));assert.equal(f.counts().keys,0);assert.equal(f.calls.length,0);
 console.log('PASS: wrong context/effective user, context changed after opening and absent capabilities block without fallback or deletion');
 f=fixture();f.flags.conflict=true;await assert.rejects(f.make().submit(target,payload));r=await f.make().recover(target);assert.equal(r.state,'conflict');
 await assert.rejects(f.make().retry(target,r.key));await assert.rejects(f.make().submit(target,payload));assert.equal(f.calls.length,1);assert.equal(f.counts().keys,1);
 f=fixture();f.flags.mismatch=true;await assert.rejects(f.make().submit(target,payload));assert.equal((await f.make().recover(target)).state,'conflict');
 console.log('PASS: 409 and inconsistent receipt retain evidence and prohibit replay/new payment');
 for(const failure of ['read','write','readback']){f=fixture();f.flags[failure]=true;await assert.rejects(f.make().submit(target,payload));assert.equal(f.calls.length,0);}
 f=fixture();f.flags.confirm=true;await assert.rejects(f.make().submit(target,payload));f.flags.confirm=false;
 r=await f.make().recover(target);assert.equal(r.state,'pending');await f.make().retry(target,r.key);assert.equal(f.ledger.size,1);assert.equal(f.counts().balance,900);
 f=fixture();r=await f.make().submit(target,payload);f.flags.cleanup=true;await assert.rejects(f.make().acknowledge(target,r.key));
 r=await f.make().recover(target);assert.equal(r.state,'confirmed');await f.make().retry(target,r.key);assert.equal(f.calls.length,1);
 f.flags.cleanup=false;await f.make().acknowledge(target,r.key);assert.equal(f.disk.size,0);
 console.log('PASS: read/write/readback failures block send; confirmation/cleanup failures preserve safe recovery');
 f=fixture();f.disk.set('moneyflow:obligation-payment:v1','not-json');await assert.rejects(f.make().submit(target,payload));assert.equal(f.calls.length,0);assert.equal(f.disk.size,1);
 f=fixture();r=await f.make().submit(target,payload);await assert.rejects(f.make().acknowledge(target,'other-key'));assert.equal(f.disk.size,1);
 console.log('PASS: corrupted journal and mismatched cleanup ID never erase evidence');
 for(const mode of ['expense','mark','link']){f=fixture();const t={kind:'recurring',id:'rp',due:'2026-10-20'};
  const p={due_date:t.due,mode,amount:mode==='link'?null:100,account_id:'account',category_id:null,date:payload.date,notes:null,
   transaction_id:mode==='link'?'existing-movement':null,settles:true,allow_overpay:false};
  r=await f.make().submit(t,p);assert.equal(r.state,'confirmed');assert.equal(f.counts().balance,mode==='expense'?900:1000);}
 console.log('PASS: legacy/shared response semantics for expense, mark and link; link uses original movement references/date');
 f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));await assert.rejects(f.make().recover({kind:'recurring',id:'rp',due:target.due}));assert.equal(f.counts().keys,1);
 const invalidations=[];await out.invalidateObligationPayments({invalidateQueries:async({queryKey})=>invalidations.push(queryKey[0])});
 for(const key of ['bills','bill','bills-summary','rp-list','rp-overview','rp-detail','rp-occ','rp-cand','accounts','transactions','summary','calendar-events','calendar-summary','calendar-upcoming'])assert.ok(invalidations.includes(key));
 console.log('PASS: one unresolved intention across Bill/Recurring screens; complete dependent-query invalidation');
 f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));const original=[...f.disk];f.flags.lost=false;
 c=f.make();r=await c.recover(target);r=await c.reconcile(target,r.key);
 assert.equal(r.state,'reconciled');assert.equal(r.resolution.status,'matched');assert.equal(f.calls.length,1);assert.equal(f.counts().balance,900);
 assert.deepEqual(f.queries[0].p,payload);assert.equal(f.queries[0].k,'operation-1');
 await f.make().retry(target,r.key);assert.equal(f.calls.length,1);await f.make().acknowledge(target,r.key);assert.equal(f.disk.size,0);
 console.log('PASS reconcile: lost response/restart, exact original intent, durable read-only proof and explicit close; no financial retry');
 f=fixture();f.flags.mismatch=true;await assert.rejects(f.make().submit(target,payload));assert.equal((await f.make().recover(target)).state,'conflict');
 f.flags.mismatch=false;r=await f.make().reconcile(target,'operation-1');assert.equal(r.state,'reconciled');assert.equal(f.calls.length,1);
 console.log('PASS reconcile: persistent conflict can resolve only through matching server evidence, no key or new payment');
 f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));f.flags.lost=false;
 r=await f.make().reconcile(target,'operation-1');f.flags.cleanup=true;await assert.rejects(f.make().acknowledge(target,r.key));
 r=await f.make().recover(target);assert.equal(r.state,'reconciled');assert.equal(r.resolution.status,'matched');
 await f.make().retry(target,r.key);assert.equal(f.calls.length,1);f.flags.cleanup=false;await f.make().acknowledge(target,r.key);
 console.log('PASS reconcile: restart after durable proof or failed cleanup preserves the resolved outcome without another discount');
 for(const mode of ['expense','link','mark'])for(const status of ['matched','tracking_removed',...(mode==='mark'?[]:['cancelled'])]){
  f=fixture();const t={kind:'recurring',id:'rp',due:target.due},p={due_date:t.due,mode,amount:mode==='link'?null:100,account_id:'account',category_id:null,date:payload.date,notes:null,
   transaction_id:mode==='link'?'existing-movement':null,settles:true,allow_overpay:false};
  f.flags.lost=true;await assert.rejects(f.make().submit(t,p));f.flags.lost=false;f.flags.reconcileStatus=status;
  r=await f.make().reconcile(t,'operation-1');assert.equal(r.resolution.status,status);
  assert.ok(out.reconciliationMessage(r));await f.make().retry(t,r.key);assert.equal(f.calls.length,1);
 }
 console.log('PASS reconcile: annulled payment, retired link and administrative mark retain their real state and never resend');
 for(const status of ['not_found','discrepancy','unverifiable']){
  f=fixture();f.flags.before=true;await assert.rejects(f.make().submit(target,payload));const bytes=[...f.disk];f.flags.reconcileStatus=status;
  await assert.rejects(f.make().reconcile(target,'operation-1'));assert.deepEqual([...f.disk],bytes);
  await assert.rejects(f.make().submit(target,payload));assert.equal(f.calls.length,1);assert.equal(f.counts().keys,1);
 }
 for(const failure of ['queryError','badQueryContext','confirm']){
  f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));f.flags.lost=false;const bytes=[...f.disk];f.flags[failure]=true;
  await assert.rejects(f.make().reconcile(target,'operation-1'));assert.deepEqual([...f.disk],bytes);assert.equal(f.calls.length,1);
 }
 f=fixture();f.flags.lost=true;await assert.rejects(f.make().submit(target,payload));f.context({...context(),capabilities:{bill_payment_context_headers:true,recurring_payment_context_headers:true}});
 await assert.rejects(f.make().reconcile(target,'operation-1'));assert.equal(f.queries.length,0);
 f=fixture();f.context({...context(),capabilities:{bill_payment_context_headers:true,recurring_payment_context_headers:true}});
 await assert.rejects(f.make().submit(target,payload));assert.equal(f.calls.length,0);assert.equal(f.counts().keys,0);
 console.log('PASS reconcile: absence, discrepancy, incomplete proof, network/storage failure and missing capability preserve evidence and block new intentions');
 // No changes to styles or navigation definitions; both real handlers use the tested flow.
 for(const file of ['app/bills/pay.tsx','app/recurring/pay.tsx']){const source=fs.readFileSync(path.join(root,file),'utf8');
  const result=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.React},reportDiagnostics:true});assert.equal((result.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  assert.ok(source.includes('await payment.retry()'));assert.ok(source.includes('await payment.acknowledge(result.key)'));
  assert.ok(source.indexOf('await invalidateObligationPayments(qc)')<source.indexOf('await payment.acknowledge(result.key)'));
  assert.ok(source.includes('screenEpoch.current'));assert.ok(!source.includes('const idemKey'));}
 for(const file of ['app/bills/pay.tsx','app/recurring/pay.tsx']){
  const source=fs.readFileSync(path.join(root,file),'utf8');
  const start=source.indexOf('if (payment.record && payment.record.state !== "reconciled")');
  const end=source.indexOf('const result = payment.record ? await payment.retry()',start);
  const verifyBranch=source.slice(start,end);
  assert.ok(verifyBranch.includes('await payment.reconcile()'));
  assert.ok(verifyBranch.includes('await invalidateObligationPayments(qc)'));
  assert.ok(verifyBranch.includes('return;'));
  assert.ok(!verifyBranch.includes('payment.retry()')&&!verifyBranch.includes('payment.submit(')&&!verifyBranch.includes('payment.acknowledge('));
  assert.ok(source.includes('Cerrar verificación'));
 }
 console.log('PASS: actual screen handlers, frozen recovery, confirmation-before-cleanup, late-response navigation guard and TSX syntax');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
