// C3 block 1: actual API and screens, synthetic reads, no server or storage.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const vm = require('node:vm'), cp = require('node:child_process'), ts = require('typescript');
const { QueryClient, QueryObserver } = require('@tanstack/react-query');
const root = path.resolve(__dirname, '../..');
const files = { detail:'frontend/app/transactions/[id].tsx', form:'frontend/app/transactions/new.tsx' };
const read = file => process.env.C3_DIRECT_TEST_REF
  ? cp.execFileSync('git', ['show', `${process.env.C3_DIRECT_TEST_REF}:${file}`], { cwd:root, encoding:'utf8' })
  : fs.readFileSync(path.join(root, file), 'utf8');
function compile(file) {
  const result = ts.transpileModule(read(file), { fileName:file, reportDiagnostics:true,
    compilerOptions:{ target:ts.ScriptTarget.ES2020, module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.React } });
  assert.equal((result.diagnostics || []).filter(x => x.category === ts.DiagnosticCategory.Error).length, 0);
  return result.outputText;
}
const apiExports = {};
let fetchResult, requests = [];
vm.runInNewContext(compile('frontend/src/api.ts'), { exports:apiExports, process:{env:{}}, fetch:async (url, options) => {
  requests.push({url,options}); return fetchResult();
} });
const { ApiError } = apiExports;
const row = (id, type='expense') => ({id,type,amount:70,name:`Synthetic ${id}`,date:'2026-10-01T12:00:00Z',
  account_id:'A',to_account_id:type==='transfer'?'B':undefined,category_id:'C',notes:'Original'});
const find = (tree,id) => !tree || typeof tree !== 'object' ? null : tree.props?.testID === id ? tree
  : (tree.children || []).flat(Infinity).map(x => find(x,id)).find(Boolean);
const text = tree => typeof tree === 'string' ? tree : (tree?.children || []).flat(Infinity).map(text).join(' ');
function fixture(kind, initialParams) {
  let params = initialParams, hook = 0, effects = [], calls = [], backs = 0, writes = [], invalidations = [];
  const slots = [], queries = new Map(), next = new Map();
  const deletion = {locked:{current:false},deleted:{current:false},busy:false,
    unavailable:()=>{deletion.locked.current=true;deletion.deleted.current=true;backs++;},
    remove:async fn=>{await fn();}};
  const react = { createElement:(type,props,...children)=>({type,props:props||{},children}),
    useState:initial=>{const i=hook++;if (!(i in slots))slots[i]=typeof initial==='function'?initial():initial;
      return [slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},
    useRef:initial=>{const i=hook++;if (!(i in slots))slots[i]={current:initial};return slots[i];},
    useMemo:f=>f(),useCallback:f=>f,useEffect:f=>effects.push(f) };
  react.default=react;
  const styles = new Proxy({}, {get:()=>({})});
  const api = { getTransaction:async id=>{calls.push(id);return next.get(id)();},
    listTransactions:()=>{throw Error('Individual lookup downloaded global history');},
    updateTransaction:async (id,payload)=>{writes.push({method:'PUT',id,payload});},
    createTransaction:async payload=>{writes.push({method:'POST',payload});},
    deleteTransaction:async id=>{writes.push({method:'DELETE',id});} };
  const mocks = {react,
    'react-native':{View:'View',ScrollView:'ScrollView',KeyboardAvoidingView:'KeyboardAvoidingView',
      Platform:{OS:'android'},Keyboard:{dismiss:()=>{}},Alert:{alert:()=>{}}},
    '@/src/components/pressable':{Pressable:'Pressable'},
    '@/src/components/typography':{Text:'Text',TextInput:'TextInput'},
    '@react-native-vector-icons/ionicons':{default:'Icon'},
    'expo-router':{useLocalSearchParams:()=>params,useRouter:()=>({back:()=>backs++,push:()=>{}})},
    'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
    '@/src/api':{api,ApiError},
    '@/src/use-resource-deletion':{useResourceDeletion:()=>deletion,useMissingResource:(missing,fn)=>{if(missing)effects.push(fn);}},
    '@tanstack/react-query':{useQuery:c=>{
      if(c.queryKey[0]!=='transactions')return {data:[]};
      const key=JSON.stringify(c.queryKey);let q=queries.get(key);
      if(!q){q={data:undefined,error:null,isError:false,isLoading:!!c.enabled,isSuccess:false,isFetching:false};queries.set(key,q);}
      q.options=c;
      q.refetch=async()=>{q.isFetching=true;try{q.data=await c.queryFn();q.error=null;q.isError=false;q.isSuccess=true;}
        catch(error){q.error=error;q.isError=true;q.isSuccess=false;}finally{q.isLoading=false;q.isFetching=false;}return q;};
      return q;
    },useQueryClient:()=>({invalidateQueries:args=>invalidations.push(args)})},
    '@/src/theme':{useTheme:()=>({colors:styles,scheme:'light'}),makeStyles:()=>()=>styles,radius:{},spacing:{lg:16,md:12}},
    '@/src/components/ui':{IconTile:'IconTile'},'@/src/components/sheets':{AppSheet:'AppSheet',ConfirmSheet:'ConfirmSheet'},
    '@/src/format':{formatCurrency:v=>String(v)},'@/src/ui-scale':{us:x=>x} };
  const exports={};vm.runInNewContext(compile(files[kind]),{exports,require:name=>{assert(name in mocks,name);return mocks[name];},setTimeout});
  const render=()=>{hook=0;effects=[];const tree=exports.default();const pending=effects;effects=[];pending.forEach(f=>f());return tree;};
  const q=id=>queries.get(JSON.stringify(['transactions','detail',id]));
  return {render,q,next:(id,f)=>next.set(id,f),navigate:p=>{params=p;},calls,writes,invalidations,
    backs:()=>backs,deletion,settle:async id=>{await q(id).refetch();render();return render();}};
}
function initializer(source,name) {
  const tree=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let result;
  function visit(n){if(ts.isVariableDeclaration(n)&&n.name.getText(tree)===name)result=n.initializer.getText(tree);ts.forEachChild(n,visit);}visit(tree);return result;
}
async function main() {
  // Fails against the previous revision: it has no direct API method.
  assert.equal(typeof apiExports.api.getTransaction,'function');
  fetchResult=()=>({ok:true,json:async()=>row('old/900')});
  assert.equal((await apiExports.api.getTransaction('old/900')).id,'old/900');
  assert.equal(requests.at(-1).url,'/api/transactions/old%2F900');
  assert.equal(requests.at(-1).options.method,undefined);
  for(const status of [404,409,503]){
    fetchResult=()=>({ok:false,status,text:async()=>JSON.stringify({detail:`Synthetic ${status}`})});
    await assert.rejects(apiExports.api.getTransaction('old'),e=>e instanceof ApiError && e.status===status && e.detail===`Synthetic ${status}`);
  }
  console.log('PASS: actual direct GET, encoded ID, and exact 404/409/503 propagation.');
  for(const kind of ['detail','form'])for(const mode of kind==='form'?['edit','duplicate']:['detail']){
    const params=id=>mode==='duplicate'?{dupFrom:id}:{id};
    let f=fixture(kind,params('old-2001')),tree=f.render();
    assert(!find(tree,'save-tx'));assert(text(tree).includes('Cargando'));
    assert.equal(f.q('old-2001').options.retry,false);assert.equal(f.q('old-2001').options.enabled,true);
    f.next('old-2001',async()=>row('old-2001'));tree=await f.settle('old-2001');
    assert.equal(f.calls.length,1);assert.equal(f.writes.length,0);
    if(kind==='form'){
      assert.equal(find(tree,'name-input').props.value,'Synthetic old-2001');
      find(tree,'name-input').props.onChangeText('Draft');tree=f.render();
      // Refetch must not overwrite a hydrated draft.
      tree=await f.settle('old-2001');assert.equal(find(tree,'name-input').props.value,'Draft');
      await find(tree,'save-tx').props.onPress();
      assert.equal(f.writes[0].method,mode==='edit'?'PUT':'POST');assert.equal(f.writes[0].payload.name,'Draft');
      assert.equal(f.writes[0].payload.notes,'Original');assert.equal(f.invalidations.length,1);assert.equal(f.backs(),1);
    }else assert(text(tree).includes('Synthetic old-2001'));
    for(const error of [new ApiError(404,'{"detail":"Missing"}'),new ApiError(409,'{"detail":"Ambiguous"}'),
      new ApiError(503,'{"detail":"Unavailable"}'),new Error('Network')]){
      f=fixture(kind,params('old'));f.render();f.next('old',async()=>{throw error;});tree=await f.settle('old');
      assert(!find(tree,'save-tx'));assert.equal(f.writes.length,0);
      const retry=find(tree,kind==='form'?'transaction-source-retry':'transaction-detail-retry');
      if(error.status===404)assert(!retry);else{
        assert(retry);f.next('old',async()=>{throw error;});retry.props.onPress();await new Promise(setImmediate);tree=f.render();assert(!find(tree,'save-tx'));
        f.next('old',async()=>row('old'));retry.props.onPress();await new Promise(setImmediate);f.render();tree=f.render();
        assert(kind==='form'?find(tree,'save-tx'):text(tree).includes('Synthetic old'));
      }
      const before=f.backs();find(tree,'back-btn').props.onPress();assert.equal(f.backs(),before+1);
    }
    // Delayed A arrives after navigating to B: never hydrates B with A.
    f=fixture(kind,params('A'));f.render();let finish;
    f.next('A',()=>new Promise(r=>finish=r));const pending=f.q('A').refetch();
    f.navigate(params('B'));tree=f.render();assert(text(tree).includes('Cargando'));
    finish(row('A'));await pending;tree=f.render();assert(!text(tree).includes('Synthetic A'));
    f.next('B',async()=>row('B'));tree=await f.settle('B');
    assert(kind==='form'?find(tree,'name-input').props.value==='Synthetic B':text(tree).includes('Synthetic B'));
    console.log(`PASS ${mode}: old ID, loading, errors, manual retries, Back, draft, save and out-of-order reads.`);
  }
  for(const type of ['expense','income','transfer','loan_given','loan_received','debt_payment']){
    const f=fixture('form',{id:'linked'});f.render();f.next('linked',async()=>({...row('linked',type),debt_payment_id:type==='debt_payment'?'receipt':undefined}));
    const tree=await f.settle('linked');await find(tree,'save-tx').props.onPress();
    assert.equal(f.writes[0].payload.type,type);assert.equal(f.writes[0].payload.account_id,'A');
    assert.equal(f.writes[0].payload.to_account_id,type==='transfer'?'B':undefined);
    assert(!('_history_keys' in f.writes[0].payload));
  }
  console.log('PASS: existing type/payload handling including linked debt payment is unchanged.');
  const fresh=fixture('form',{});let freshTree=fresh.render();
  assert.equal(fresh.q(undefined).options.enabled,false);assert(find(freshTree,'save-tx'));assert.equal(fresh.calls.length,0);
  find(freshTree,'back-btn').props.onPress();assert.equal(fresh.backs(),1);assert.equal(fresh.writes.length,0);
  const both=fixture('form',{id:'edit',dupFrom:'copy'});both.render();
  assert(both.q('edit'));assert.equal(both.q('copy'),undefined);
  // A linked bill remains a plain, unchanged update request; only the existing
  // backend decides whether that edit is permitted. Read failure cannot submit.
  const bill=fixture('form',{id:'bill'});bill.render();bill.next('bill',async()=>({...row('bill'),bill_payment_id:'original-receipt'}));
  const billTree=await bill.settle('bill');await find(billTree,'save-tx').props.onPress();
  assert.equal(bill.writes[0].method,'PUT');assert.equal(bill.writes[0].id,'bill');
  console.log('PASS: fresh form performs no lookup; edit precedence, cancel and linked bill request preserved.');
  // Real React Query: an old request remains in its own cache; broad existing
  // transactions invalidations still include the newly keyed details.
  const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});
  let finish;const a=client.fetchQuery({queryKey:['transactions','detail','A'],queryFn:()=>new Promise(r=>finish=r)});
  const observer=new QueryObserver(client,{queryKey:['transactions','detail','B'],queryFn:async()=>row('B')});
  const stop=observer.subscribe(()=>{});await observer.refetch();finish(row('A'));await a;
  assert.equal(observer.getCurrentResult().data.id,'B');
  await client.invalidateQueries({queryKey:['transactions'],refetchType:'none'});
  assert(client.getQueryState(['transactions','detail','A']).isInvalidated);
  assert(client.getQueryState(['transactions','detail','B']).isInvalidated);stop();observer.destroy();client.clear();
  if(!process.env.C3_DIRECT_TEST_REF){
    const oldApi=cp.execFileSync('git',['show','HEAD:frontend/src/api.ts'],{cwd:root,encoding:'utf8'});
    // Both approved C3 read methods are additive. Compare every other API
    // method symmetrically, regardless of whether either is already in HEAD.
    const withoutDirectRead = source => {
      const tree=ts.createSourceFile('api.ts',source,ts.ScriptTarget.Latest,true);
      let methods;
      function visit(node){
        if(ts.isVariableDeclaration(node)&&node.name.getText(tree)==='api')
          methods=Object.fromEntries(node.initializer.properties
            .filter(p=>!['getTransaction','getTransactionPage'].includes(p.name.getText(tree)))
            .map(p=>[p.name.getText(tree),p.initializer.getText(tree)]));
        ts.forEachChild(node,visit);
      }
      visit(tree);return methods;
    };
    const currentApi = read('frontend/src/api.ts');
    assert.deepEqual(withoutDirectRead(currentApi),withoutDirectRead(oldApi));
    for(const file of Object.values(files)){
      const old=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),current=read(file);
      assert.equal(current.slice(current.indexOf('const useStyles =')),old.slice(old.indexOf('const useStyles =')));
      assert(!current.includes('api.listTransactions'));
      for(const name of file===files.form?['remove']:['doEdit','doDuplicate','doDelete','saveCategory','saveRecurring'])
        assert.equal(initializer(current,name),initializer(old,name));
      if(file===files.form)assert.equal(initializer(current,'save'),initializer(old,'save'));
    }
  }
  console.log('PASS: real cache isolation/invalidation, unchanged financial handlers and style definitions.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
