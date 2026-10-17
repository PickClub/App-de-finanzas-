const {localeGlobals,localeMocks,normalizeUI,headerActionNodes}=require('./i18n-test-support.cjs');
// Actual screen + React Query, synthetic API only: no Expo server or database.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const vm = require('node:vm'), cp = require('node:child_process'), ts = require('typescript');
const { QueryClient, QueryObserver, onlineManager } = require('@tanstack/react-query');
const root = path.resolve(__dirname, '../..'), screen = 'frontend/app/transactions/all.tsx';
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
function compile(file) {
  const out = ts.transpileModule(read(file), { fileName:file, reportDiagnostics:true,
    compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React} });
  assert.equal((out.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0);
  return out.outputText;
}
const find = (tree,id) => !tree || typeof tree !== 'object' ? null : tree.props?.testID === id ? tree
  : [...(tree.children || []), ...(tree.props?.children ? [tree.props.children] : []), ...headerActionNodes(tree)].flat(Infinity).map(x => find(x,id)).find(Boolean);
const text = tree => typeof tree === 'string' ? tree : (tree?.children || []).flat(Infinity).map(text).join(' ');
const plain = value => JSON.parse(JSON.stringify(value));
const apiExports = {};
let fetchResponse, requests = [];
vm.runInNewContext(compile('frontend/src/api.ts'), localeGlobals({exports:apiExports,process:{env:{}},URLSearchParams,
  fetch:async (url,options) => {requests.push({url,options});return fetchResponse();} }));
const { ApiError } = apiExports;
const row = (id, rest={}) => ({id:String(id),type:'expense',date:'2026-10-10T12:00:00Z',amount:'70',account_id:'A',category_id:'C',name:`Synthetic ${id}`,...rest});
function createFixture(backend, initialParams={}) {
  const slots = [], calls = [], pushes = [], displayedAmounts = [];
  const client = new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
  client.mount(); // Match QueryClientProvider's online/focus subscriptions.
  let index=0, params=initialParams, observer, stop, key, focus, first=true, backs=0, effects=[];
  const same = (a,b) => a && b && a.length === b.length && a.every((x,i) => Object.is(x,b[i]));
  const memo = (fn,deps) => {const i=index++;if(!slots[i] || !same(slots[i].deps,deps)) slots[i]={deps,value:fn()};return slots[i].value;};
  const react = {
    createElement:(type,props,...children) => ({type,props:props||{},children}),
    useState:initial => {const i=index++;if(!(i in slots))slots[i]=typeof initial==='function'?initial():initial;
      return [slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},
    useRef:initial => {const i=index++;if(!(i in slots))slots[i]={current:initial};return slots[i];},
    useMemo:memo, useCallback:(fn,deps)=>memo(()=>fn,deps),
    useEffect:(fn,deps)=>{const i=index++;if(!slots[i]||!same(slots[i].deps,deps)){slots[i]={deps};effects.push(fn);}},
  };react.default=react;
  const styles = new Proxy({}, {get:()=>({})});
  const api = {listCategories:async()=>[],getTransactionPage:async (filters,cursor,signal)=>{
    calls.push({filters:plain(filters),cursor,signal});return backend(filters,cursor,signal);
  }, listTransactions:()=>{throw Error('Downloaded legacy history');}};
  const mocks = localeMocks({react,
    'react-native':{View:'View',ScrollView:'ScrollView',Platform:{OS:'android'},RefreshControl:'RefreshControl'},
    'react-native-reanimated':{default:{View:'AnimatedView'},FadeIn:{duration:()=>({})}},
    '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},
    '@react-native-vector-icons/ionicons':{default:'Icon'},
    'expo-router':{useLocalSearchParams:()=>params,useRouter:()=>({push:route=>pushes.push(route),back:()=>backs++}),useFocusEffect:fn=>{focus=fn;}},
    'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
    '@tanstack/react-query':{useQuery:options=>{
      if(options.queryKey[0]==='categories')return {data:[]};
      const nextKey=JSON.stringify(options.queryKey);
      if(nextKey!==key){stop?.();observer?.destroy();observer=new QueryObserver(client,options);stop=observer.subscribe(()=>{});key=nextKey;}
      else observer.setOptions(options);
      return {...observer.getCurrentResult(),refetch:()=>observer.refetch({cancelRefetch:false})};
    }},
    '@/src/api':{api,ApiError},'@/src/theme':{useTheme:()=>({colors:styles,scheme:'light'}),makeStyles:()=>()=>styles,radius:{},spacing:{lg:16}},
    '@/src/format':{formatCurrency:value=>{displayedAmounts.push(value);return String(value);},formatDateTime:value=>value,translateCategoryName:value=>value},
    '@/src/i18n':{default:{language:'es'},useTranslation:()=>({t:x=>x})},
    '@/src/components/ui':{IconTile:'IconTile'},'@/src/lock':{useLock:()=>({guard:fn=>fn})},
    '@/src/components/sheets':{AppSheet:'AppSheet'},'@/src/components/date-range-sheet':{DateRangeSheet:'DateRangeSheet'},'@/src/components/elastic-scroll-view':{ElasticScrollView:'ScrollView'},'@/src/native-scroll':{NATIVE_VERTICAL_SCROLL:{overScrollMode:'always',bounces:true,alwaysBounceVertical:true}},'@/src/ui-scale':{us:x=>x},
  });
  const NativeDate=Date;
  class FixedDate extends NativeDate {constructor(...args){super(...(args.length?args:['2026-10-15T12:00:00Z']));}}
  const exports={};vm.runInNewContext(compile(screen),localeGlobals({exports,require:name=>{assert(name in mocks,name);return mocks[name];},Date:FixedDate}));
  const render=()=>{index=0;effects=[];const tree=exports.default();effects.forEach(fn=>fn());if(first){first=false;focus();}return tree;};
  return {render,calls,pushes,displayedAmounts,client,
    settle:async()=>{await observer.refetch({cancelRefetch:false});return render();},
    navigate:newParams=>{params=newParams;return render();},focus:()=>{focus();return render();},
    query:()=>observer.getCurrentResult(),close:()=>{stop?.();observer?.destroy();client.unmount();client.clear();},backs:()=>backs};
}
function syntheticBackend(records) {
  return async (filters,cursor) => {
    let items=records.filter(r=>(!filters.account_id || r.account_id===filters.account_id || (r.type==='transfer' && r.to_account_id===filters.account_id))
      && (!filters.category_id || r.category_id===filters.category_id) && (!filters.types || filters.types.includes(r.type))
      && (!filters.start || new Date(r.date)>=new Date(filters.start)) && (!filters.end || new Date(r.date)<new Date(filters.end)));
    // Integer fixtures only; exact high-precision ordering is supplied separately.
    items.sort((a,b)=>filters.order==='high'||filters.order==='low'
      ? (BigInt(a.amount)>BigInt(b.amount)?1:BigInt(a.amount)<BigInt(b.amount)?-1:0)*(filters.order==='high'?-1:1)
      : (a.id>b.id?1:-1)*(filters.order==='recent'?-1:1));
    const offset=cursor===undefined?0:Number(cursor);
    return {items:items.slice(offset,offset+20),total:items.length,has_more:offset+20<items.length,next_cursor:offset+20<items.length?String(offset+20):null};
  };
}
let cases=0;
async function check(name,fn){await fn();cases++;console.log('PASS:',name);}
async function main(){
  await check('actual GET serializes repeated types, dates, special IDs, cursor, signal and exact decimal text',async()=>{
    const signal=new AbortController().signal;
    fetchResponse=()=>({ok:true,json:async()=>({items:[row('x',{amount:'1.000000000000000000000000000002'})],total:10001,has_more:true,next_cursor:'opaque'})});
    const result=await apiExports.api.getTransactionPage({order:'low',account_id:'A / ?&',category_id:'C',types:['expense','debt_payment'],start:'2026-10-01T00:00:00Z',end:'2026-11-01T00:00:00Z'},'a+/=',signal);
    const req=requests.at(-1), url=new URL(req.url,'http://synthetic');
    assert.equal(url.pathname,'/api/transactions/page');assert.equal(url.searchParams.get('limit'),'20');
    assert.deepEqual(url.searchParams.getAll('type'),['expense','debt_payment']);assert.equal(url.searchParams.get('account_id'),'A / ?&');
    assert.equal(url.searchParams.get('cursor'),'a+/=');assert.equal(req.options.signal,signal);assert.equal(req.options.method,undefined);
    assert.equal(result.items[0].amount,'1.000000000000000000000000000002');
    for(const status of [409,503]){
      fetchResponse=()=>({ok:false,status,text:async()=>JSON.stringify({detail:'Synthetic error'})});
      await assert.rejects(apiExports.api.getTransactionPage({order:'recent'}),error=>error instanceof ApiError && error.status===status);
    }
  });
  for(const count of [501,2001,10001])await check(`all ${count} movements: forward/back cursors, real total, no eager history load`,async()=>{
    const records=Array.from({length:count},(_,i)=>row(String(i).padStart(6,'0'))),before=JSON.stringify(records);
    const f=createFixture(syntheticBackend(records));let tree=f.render();assert(text(tree).includes('Cargando'));
    tree=await f.settle();const seen=[];
    assert.equal(f.calls.length,1);assert(text(find(tree,'all-tx-count')).includes(String(count)));
    assert(find(tree,`all-tx-page-${Math.ceil(count/20)}`).props.disabled);
    for(let p=1;;p++){
      const rows=f.query().data.items;assert(rows.length<=20);seen.push(...rows.map(x=>x.id));
      assert.equal(f.query().data.total,count);
      if(!f.query().data.has_more)break;
      find(tree,'all-tx-page-next').props.onPress();tree=f.render();assert(text(tree).includes('Cargando'));
      tree=await f.settle();
    }
    assert.equal(seen.length,count);assert.equal(new Set(seen).size,count);assert.equal(f.calls.length,Math.ceil(count/20));
    assert(find(tree,'all-tx-page-next').props.disabled);assert(text(find(tree,'all-tx-navigation-info')).includes('Fin del historial'));
    find(tree,'all-tx-page-prev').props.onPress();f.render();tree=await f.settle();assert.equal(f.calls.at(-1).cursor,String((Math.ceil(count/20)-2)*20));
    find(tree,'all-tx-page-1').props.onPress();f.render();tree=await f.settle();assert.equal(f.calls.at(-1).cursor,undefined);
    assert.equal(JSON.stringify(records),before);f.close();
  });
  await check('account/category/date/type filters and transfers; all four server orders reset cursors',async()=>{
    const records=[row('out',{type:'transfer',to_account_id:'B'}),row('in',{type:'transfer',account_id:'B',to_account_id:'A'}),
      row('bad',{account_id:'B',to_account_id:'A'}),row('expense'),row('receipt',{type:'debt_payment'}),row('income',{type:'income'}),
      row('loan',{type:'loan_received'}),row('old',{date:'2000-01-01T00:00:00Z'}),row('cat',{category_id:'X'})];
    const f=createFixture(syntheticBackend(records),{accountId:'A',categoryId:'C'});f.render();let tree=await f.settle();
    assert.deepEqual(f.query().data.items.map(r=>r.id).sort(),['expense','in','income','loan','out','receipt']);
    assert(find(tree,'all-tx-active-filters'));assert(f.calls[0].filters.start.endsWith('Z'));
    assert.equal(f.calls[0].filters.end,new Date(2026,9,16).toISOString());
    for(const [type,ids] of [['income',['income','loan']],['expense',['expense','receipt']],['transfer',['in','out']]]){
      find(tree,`all-tx-type-${type}`).props.onPress();f.render();tree=await f.settle();
      assert.deepEqual(f.query().data.items.map(r=>r.id).sort(),ids);assert.equal(f.calls.at(-1).cursor,undefined);
    }
    for(const order of ['high','low','oldest','recent']){
      find(tree,`all-tx-sort-${order}`).props.onPress();f.render();tree=await f.settle();
      assert.equal(f.calls.at(-1).filters.order,order);assert.equal(f.calls.at(-1).cursor,undefined);
    }
    find(tree,'all-tx-period-7d').props.onPress();f.render();await f.settle();assert.equal(f.calls.at(-1).cursor,undefined);
    f.navigate({accountId:'B',categoryId:'X'});await f.settle();assert.equal(f.calls.at(-1).filters.account_id,'B');assert.equal(f.calls.at(-1).cursor,undefined);
    f.close();
  });
  await check('precision is preserved to formatting; server order and detail route remain unchanged',async()=>{
    const records=[row('third',{amount:'1.000000000000000000000000000003'}),row('second',{amount:'1.000000000000000000000000000002'}),row('first',{amount:'1.000000000000000000000000000001'})];
    const f=createFixture(async()=>({items:records,total:3,has_more:false,next_cursor:null}));f.render();let tree=await f.settle();
    find(tree,'all-tx-sort-high').props.onPress();f.render();tree=await f.settle();
    assert.deepEqual(f.query().data.items.map(r=>r.id),['third','second','first']);assert(f.displayedAmounts.includes(records[0].amount));
    find(tree,'all-tx-row-third').props.onPress();assert.deepEqual(f.pushes,['/transactions/third']);
    find(tree,'all-tx-back').props.onPress();assert.equal(f.backs(),1);f.close();
  });
  for(const status of [409,503])await check(`${status}: explicit error, no fake zero/empty success, manual recovery only`,async()=>{
    let fail=true;const f=createFixture(async()=>{if(fail)throw new ApiError(status,'{"detail":"Synthetic"}');return {items:[],total:0,has_more:false,next_cursor:null};});
    f.render();let tree=await f.settle();assert(find(tree,'all-tx-error'));assert(!find(tree,'all-tx-empty'));
    assert(text(find(tree,'all-tx-count')).includes('no disponible'));assert.equal(f.calls.length,1);
    fail=false;find(tree,'all-tx-retry').props.onPress();tree=await f.settle();assert(find(tree,'all-tx-empty'));assert(!find(tree,'all-tx-error'));f.close();
  });
  await check('offline-paused request is pending, never a successful empty history',async()=>{
    onlineManager.setOnline(false);const f=createFixture(syntheticBackend([row('online')]));
    try{
      const tree=f.render();assert(text(tree).includes('Cargando'));assert(!find(tree,'all-tx-empty'));assert.equal(f.calls.length,0);
      onlineManager.setOnline(true);const loaded=await f.settle();assert(find(loaded,'all-tx-row-online'));
    }finally{onlineManager.setOnline(true);f.close();}
  });
  await check('late responses cannot mix filter scopes; aborted requests and cursor resets',async()=>{
    let finish;const f=createFixture((filters,cursor,signal)=>filters.account_id==='A'?new Promise(resolve=>finish=resolve):Promise.resolve({items:[row('B')],total:1,has_more:false,next_cursor:null}),{accountId:'A'});
    f.render();await Promise.resolve();f.navigate({accountId:'B'});let tree=await f.settle();
    assert.equal(f.calls.at(-1).cursor,undefined);assert(f.calls[0].signal.aborted);
    finish({items:[row('old-A')],total:501,has_more:true,next_cursor:'old'});await new Promise(setImmediate);tree=f.render();
    assert(find(tree,'all-tx-row-B'));assert(!find(tree,'all-tx-row-old-A'));f.close();
  });
  await check('returning to an earlier filter scope resets visited cursors; failed next page can go back',async()=>{
    const records=Array.from({length:45},(_,i)=>row(i));let fail=false;
    const backend=syntheticBackend(records),f=createFixture(async(filters,cursor)=>{
      if(fail && cursor==='20')throw new ApiError(503,'Unavailable');return backend(filters,cursor);
    },{accountId:'A'});
    f.render();let tree=await f.settle();find(tree,'all-tx-page-next').props.onPress();f.render();tree=await f.settle();
    assert.equal(f.calls.at(-1).cursor,'20');f.navigate({accountId:'B'});await f.settle();
    f.navigate({accountId:'A'});tree=await f.settle();assert.equal(f.calls.at(-1).cursor,undefined);
    fail=true;find(tree,'all-tx-page-next').props.onPress();f.render();tree=await f.settle();assert(find(tree,'all-tx-error'));
    find(tree,'all-tx-error-prev').props.onPress();f.render();tree=await f.settle();assert.equal(f.calls.at(-1).cursor,undefined);
    assert(!find(tree,'all-tx-error'));f.close();
  });
  await check('focus restarts at first page; invalidation remains active without pull-to-refresh',async()=>{
    const f=createFixture(syntheticBackend(Array.from({length:45},(_,i)=>row(i))));f.render();let tree=await f.settle();
    find(tree,'all-tx-page-next').props.onPress();f.render();tree=await f.settle();assert.equal(f.calls.at(-1).cursor,'20');
    tree=f.focus();tree=await f.settle();assert.equal(f.calls.at(-1).cursor,undefined);
    const before=f.calls.length;await f.client.invalidateQueries({queryKey:['transactions']});tree=f.render();assert(f.calls.length>before);
    function refreshControl(node){if(!node||typeof node!=='object')return;return node.props?.refreshControl || (node.children||[]).flat(Infinity).map(refreshControl).find(Boolean);}
    assert.equal(refreshControl(tree),undefined);assert.equal(f.calls.at(-1).cursor,undefined);f.close();
  });
  await check('style definitions unchanged; no local filtering/sorting/slicing or legacy list request',async()=>{
    const source=read(screen),base=cp.execFileSync('git',['show',`HEAD:${screen}`],{cwd:root,encoding:'utf8'}),marker='const useStyles =';
    assert.equal(source.slice(source.indexOf(marker)),base.slice(base.indexOf(marker)));
    assert(!source.includes('api.listTransactions'));assert(!source.includes('sorted.sort'));assert(!source.includes('filtered.slice'));
    assert(source.includes('gcTime: 0'));assert(source.includes('signal'));
  });
  console.log(`RESULT: ${cases} scenario groups passed.`);
}
module.exports={createFixture,syntheticBackend,row,find,text,read,plain};
if(require.main===module){
  let finished=false;
  process.on('beforeExit',()=>{if(!finished){console.error('FAIL: scenario run did not finish');process.exitCode=1;}});
  main().then(()=>{finished=true;}).catch(error=>{finished=true;console.error(error);process.exitCode=1;});
}
