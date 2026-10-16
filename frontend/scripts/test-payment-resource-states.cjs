const {localeGlobals,localeMocks,normalizeHomeColors,normalizeUI}=require('./i18n-test-support.cjs');
// C7: render the actual screens against synthetic React Query/API responses.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const vm = require('node:vm'), cp = require('node:child_process'), ts = require('typescript');
const root = path.resolve(__dirname, '../..');
const files = { debt:'frontend/app/debts/[id]/pay.tsx', bill:'frontend/app/bills/pay.tsx' };
class ApiError extends Error { constructor(status) { super('HTTP '+status); this.status=status; } }
const clone = v => JSON.parse(JSON.stringify(v));
const source = file => process.env.C7_TEST_REF ? cp.execFileSync('git',['show',`${process.env.C7_TEST_REF}:${file}`],{cwd:root,encoding:'utf8'}) : fs.readFileSync(path.join(root,file),'utf8');
function fixture(kind, initial, pending = true, id = 'resource') {
  const q = {isLoading:false,isFetching:false,isError:false,data:undefined,error:null,...initial};
  const journal = { key:'original-key', payload:{amount:100,account_id:'a',date:'2026-10-01',notes:'Original'}, state:'pending', debtId:id };
  const before = JSON.stringify(journal);
  let reads=0, backs=0, writes=0, stateIndex=0, next;
  const data = { id, name:'Synthetic', amount:500, remaining:400, due_date:'2026-10-20',remaining_amount:400,status:'active',direction:'i_owe',color:'#126046' };
  let queryFn, enabled;
  q.refetch = async () => {
    q.isFetching=true;
    try { q.data=await queryFn(); q.error=null;q.isError=false; }
    catch(error) { q.error=error;q.isError=true; }
    finally {q.isFetching=false;q.isLoading=false;}
    return q;
  };
  const forbidden = () => {writes++;throw Error('C7 performed a financial/journal mutation');};
  const styles = new Proxy({}, {get:()=>({})});
  const react = {
    createElement:(type,props,...children)=>({type,props:props||{},children}),
    useState:value=>{const index=stateIndex++;return [kind==='debt'&&index===5&&pending?journal:value,()=>{}];},
    useRef:value=>({current:value}),useEffect:()=>{},useCallback:f=>f,
  };
  react.default=react;
  const api = new Proxy({getDebt:async()=>{reads++;return next();},billGet:async()=>{reads++;return next();},listAccounts:async()=>[]},{get:(target,key)=>target[key]||forbidden});
  const payment = {record:pending?journal:null,problem:null,ready:true,locked:pending,submit:forbidden,retry:forbidden,reconcile:forbidden,acknowledge:forbidden,recover:forbidden};
  const theme={useTheme:()=>({colors:styles,scheme:'light'}),makeStyles:()=>()=>styles,radius:{},spacing:{lg:16,md:12}};
  const mocks = localeMocks({
    react,'react-native':{View:'View',ScrollView:'ScrollView',ActivityIndicator:'ActivityIndicator',KeyboardAvoidingView:'KeyboardAvoidingView',Platform:{OS:'android',select:x=>x.default},Alert:{alert:()=>{}}},
    '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text',TextInput:'TextInput'},
    '@react-native-vector-icons/ionicons':{default:'Icon'},
    'expo-router':{useLocalSearchParams:()=>({id}),useRouter:()=>({back:()=>backs++}),useFocusEffect:()=>{}},
    'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
    '@tanstack/react-query':{useQuery:c=>{if(c.queryKey[0]===(kind==='debt'?'debt':'bill')) {queryFn=c.queryFn;enabled=c.enabled;return q;}return {data:[]};},useQueryClient:()=>({invalidateQueries:forbidden})},
    '@/src/api':{api,ApiError},'@/src/debt-payments/pending':{},'@/src/debt-payments/flow-v2':{},
    '@/src/debt-payments/local-flow':{localPaymentFlow:{recover:forbidden,verify:forbidden}},
    '@/src/theme':theme,'@/src/format':{formatCurrency:()=>'',formatCurrencyInt:()=>''},
    '@/src/components/ui':{IconTile:'IconTile'},'@/src/components/sheets':{AppSheet:'AppSheet',ConfirmSheet:'ConfirmSheet'},
    '@/src/components/elastic-scroll-view':{ElasticScrollView:'ScrollView'},'@/src/native-scroll':{NATIVE_VERTICAL_SCROLL:{overScrollMode:'always',bounces:true,alwaysBounceVertical:true}},'@/src/ui-scale':{us:x=>x},'@/src/debt-payments/view':{paymentView:()=>({title:'Pago',editable:false,preview:false,action:'Verificar registro'})},
    '@/src/i18n':{useTranslation:()=>({t:x=>x,i18n:{language:'es'}})},
    '@/src/components/date-range-sheet':{DateRangeSheet:'DateRangeSheet'},
    '@/src/bills/shared':{FOREST:'#126046',useMontserrat:()=>()=>({}),deepen:x=>x,safeHex:()=> '#126046',longDate:()=>'',toYmd:()=> '2026-10-20',parseAmount:Number},
    '@/src/obligation-payments/use-payment':{useObligationPayment:()=>payment},
    '@/src/obligation-payments/journal':{invalidateObligationPayments:forbidden,reconciliationMessage:()=> 'Original pending payment'},
  });
  const output=ts.transpileModule(source(files[kind]),{fileName:files[kind],reportDiagnostics:true,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}});
  assert.equal((output.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
  const exports={};vm.runInNewContext(output.outputText,localeGlobals({exports,require:n=>{assert(n in mocks,n);return mocks[n];}}));
  return {q,data,get enabled(){return enabled;},setNext:f=>next=f,render:()=>{stateIndex=0;const tree=exports.default();return typeof tree.type==='function' ? tree.type(tree.props) : tree;},counts:()=>({reads,backs,writes}),journalIntact:()=>assert.equal(JSON.stringify(journal),before)};
}
function find(tree,id) {
  if (!tree) return null;
  if (Array.isArray(tree)) {for(const n of tree){const found=find(n,id);if(found)return found;}return null;}
  if (typeof tree!=='object') return null;
  if (tree.props?.testID===id)return tree;
  return find(tree.children,id);
}
async function run() {
  for(const kind of ['debt','bill']) {
    const prefix=kind+'-pay';
    const originalDefect=fixture(kind,{isError:true,error:new ApiError(404)}).render();
    assert(/No se encontró (la deuda|la factura)/.test(JSON.stringify(originalDefect)), 'A definitive 404 must explain the missing resource, not render blank/spinner.');
    let f=fixture(kind,{isLoading:true,isFetching:true});let tree=f.render();
    assert(find(tree,prefix+'-loading'));assert(!find(tree,prefix+'-query-error'));
    assert(!find(tree,kind==='debt'?'confirm-pay':'bill-pay-save'));
    find(tree,prefix+'-back').props.onPress();assert.equal(f.counts().backs,1);
    f.journalIntact();assert.equal(f.counts().writes,0);
    for(const error of [new ApiError(404),new ApiError(500),new Error('offline')]) {
      f=fixture(kind,{isError:true,error});tree=f.render();
      assert(find(tree,prefix+'-query-error'));assert(!find(tree,prefix+'-loading'));
      assert(find(tree,prefix+'-preserved'));assert(!find(tree,kind==='debt'?'confirm-pay':'bill-pay-save'));
      f.setNext(()=>new Promise(resolve=>{f.finish=resolve;}));
      find(tree,prefix+'-retry').props.onPress();
      tree=f.render();assert.equal(find(tree,prefix+'-retry').props.disabled,true);
      assert.equal(f.counts().reads,1);assert.equal(f.counts().writes,0);f.journalIntact();
      f.finish(f.data);await new Promise(r=>setImmediate(r));
      tree=f.render();assert(!find(tree,prefix+'-query-error'));assert(find(tree,kind==='debt'?'confirm-pay':'bill-pay-save'));
      f.journalIntact();assert.equal(f.counts().writes,0);
    }
    f=fixture(kind,{isError:true,error:new Error('offline')},false);
    f.setNext(async()=>{throw new ApiError(503);});find(f.render(),prefix+'-retry').props.onPress();
    await new Promise(r=>setImmediate(r));tree=f.render();
    assert(find(tree,prefix+'-query-error'));assert.equal(find(tree,prefix+'-retry').props.disabled,false);
    assert(!find(tree,prefix+'-preserved'));find(tree,prefix+'-back').props.onPress();
    assert.deepEqual(f.counts(),{reads:1,backs:1,writes:0});
    for(const initial of [{},{data:{id:'cached'},isError:true,error:new ApiError(404)},{data:{id:'cached'},isError:true,error:new ApiError(500)}]) {
      f=fixture(kind,initial);tree=f.render();assert(find(tree,prefix+'-query-error'));
      assert(!find(tree,kind==='debt'?'confirm-pay':'bill-pay-save'));f.journalIntact();
      if(kind==='bill')assert.equal(find(tree,'bill-pay-sheet').props.visible,false);
    }
    f=fixture(kind,{},true,'');tree=f.render();
    assert(find(tree,prefix+'-query-error'));
    assert.equal(f.enabled,false);assert(!find(tree,prefix+'-retry'));assert.equal(f.counts().reads,0);
    f=fixture(kind,{data:{id:'resource',remaining:400,due_date:'2026-10-20',remaining_amount:400,color:'#126046'}},false);
    tree=f.render();assert(find(tree,kind==='debt'?'confirm-pay':'bill-pay-save'));assert(!find(tree,prefix+'-query-error'));
    assert.equal(f.counts().writes,0);
    console.log('PASS '+kind+': loaded, initial/delayed GET, 404/HTTP/network error, successful/failed retry, cached errors, Back and untouched pending journal.');
  }
  if(!process.env.C7_TEST_REF)for(const file of Object.values(files)){
    const previous=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),current=source(file);
    const marker='const useStyles =';assert.equal(normalizeHomeColors(current.slice(current.indexOf(marker))),normalizeHomeColors(previous.slice(previous.indexOf(marker))));
    function protectedCode(text){const tree=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),blocks=[];
      function visit(n){if(ts.isVariableDeclaration(n)&&['save','ask'].includes(n.name.getText(tree))&&file!==files.debt)blocks.push(n.initializer.getText(tree));
        if(file!==files.debt&&ts.isCallExpression(n)&&['useEffect','useFocusEffect'].includes(n.expression.getText(tree)))blocks.push(n.getText(tree));ts.forEachChild(n,visit);}visit(tree);return blocks;}
    const normalizeRecovery = code => file === files.debt ? normalizeUI(code).replace(/\n\s*setReady\(false\);/g, '') : normalizeUI(code);
    // Debt initialization/navigation are covered by the actual-form lifecycle tests.
    assert.deepEqual(protectedCode(current).map(normalizeRecovery),protectedCode(previous).map(normalizeRecovery));
  }
  console.log('PASS: resource guards remain protected; bill financial handlers/effects and all styles match HEAD. Debt save behavior is covered by test-debt-payment-form.cjs.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
