// Actual Home component + React Query; synthetic reads, no device/server/database.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const cp=require('node:child_process'),ts=require('typescript');
const {QueryClient,QueryObserver}=require('@tanstack/react-query');
const root=path.resolve(__dirname,'../..'),file='frontend/app/(tabs)/index.tsx';
const source=fs.readFileSync(path.join(root,file),'utf8');
function compile(text,name){const out=ts.transpileModule(text,{fileName:name,reportDiagnostics:true,
  compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}});
  assert.equal((out.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);return out.outputText;}
const findAll=(tree,predicate)=>!tree||typeof tree!=='object'?[]:[...(predicate(tree)?[tree]:[]),...(tree.children||[]).flat(Infinity).flatMap(t=>findAll(t,predicate))];
const find=(tree,id)=>findAll(tree,n=>n.props?.testID===id)[0];
const text=node=>typeof node==='string'||typeof node==='number'?String(node):(node?.children||[]).flat(Infinity).map(text).join('');
const styled=(tree,name)=>findAll(tree,n=>[n.props?.style].flat(Infinity).some(s=>s?.tag===name));
const zero={total_balance:0,month_income:0,month_expense:0,debts:{i_owe:0,they_owe:0,paid_this_month:0,next_payment:null},accounts_count:0};
const positive={...zero,total_balance:1000,month_income:100,month_expense:20,debts:{...zero.debts,i_owe:500,they_owe:200,paid_this_month:30}};
function fixture(handler,debtList=[]){
  let fn=handler,index=0,query,observer,stop,calls=0;
  const slots=[],client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity}}});client.mount();
  const react={createElement:(type,props,...children)=>({type,props:props||{},children}),Fragment:'Fragment',
    useMemo:f=>f(),useCallback:f=>f,useEffect:()=>{},
    useRef:v=>{const i=index++;if(!(i in slots))slots[i]={current:v};return slots[i];},
    useState:v=>{const i=index++;if(!(i in slots))slots[i]=typeof v==='function'?v():v;return [slots[i],x=>{slots[i]=typeof x==='function'?x(slots[i]):x;}];}};
  react.default=react;
  const styles=new Proxy({},{get:(_,tag)=>({tag})});
  const colors=Object.fromEntries([...source.matchAll(/colors\.(\w+)/g)].map(m=>[m[1],'#345678']));
  const animation={duration:()=>({})};
  const format=v=>'$'+Number(v).toFixed(2);
  const mocks={react,'react-native':{View:'View',ScrollView:'ScrollView',RefreshControl:'RefreshControl',StyleSheet:{absoluteFill:{},absoluteFillObject:{}},
    Platform:{OS:'android'},Dimensions:{get:()=>({width:400,height:800})},useWindowDimensions:()=>({width:400,height:800}),Animated:{View:'View'}},
    'react-native-reanimated':{__esModule:true,default:{View:'View',ScrollView:'ScrollView',createAnimatedComponent:x=>x},useSharedValue:v=>({value:v}),
      useAnimatedScrollHandler:()=>()=>{},useAnimatedReaction:()=>{},useAnimatedProps:()=>({}),withTiming:v=>v,Easing:{out:x=>x,cubic:x=>x},FadeIn:animation,LinearTransition:animation},
    'react-native-svg':{__esModule:true,default:'Svg',Circle:'Circle',Path:'Path',Polyline:'Polyline'},'expo-linear-gradient':{LinearGradient:'Gradient'},
    '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},
    '@react-native-vector-icons/ionicons':{default:'Icon'},'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
    'expo-router':{useRouter:()=>({push:()=>{throw Error('Unexpected navigation during summary read');}}),useFocusEffect:()=>{}},
    '@/src/api':{api:{summary:async()=>{calls++;return fn();}}},
    '@tanstack/react-query':{useQuery:options=>{
      if(options.queryKey[0]!=='summary')return {data:options.queryKey[0]==='user'?{name:'Synthetic'}:options.queryKey[0]==='debts'?debtList:[],isSuccess:true,isError:false,refetch:async()=>{}};
      query=options;
      if(!observer){observer=new QueryObserver(client,options);stop=observer.subscribe(()=>{});}else observer.setOptions(options);
      return {...observer.getCurrentResult(),refetch:()=>observer.refetch({cancelRefetch:false})};
    }},
    '@/src/theme':{useTheme:()=>({colors,scheme:'light'}),makeStyles:()=>()=>styles,radius:{},spacing:{lg:16,xl:24,md:12}},
    '@/src/format':{formatCurrency:format,formatCurrencyInt:format,formatDateLong:x=>x,formatDateTime:x=>x,translateCategoryName:x=>x},
    '@/src/i18n':{__esModule:true,default:{language:'es'},useTranslation:()=>({t:x=>x})},'@/src/components/ui':{IconTile:'IconTile'},
    '@/src/lock':{useLock:()=>({guard:f=>f})},'@/src/components/animated-section-icons':{WalletIcon:'Icon',ChartIcon:'Icon',HandCoinIcon:'Icon'},
    '@/src/components/date-range-sheet':{DateRangeSheet:'DateRangeSheet'},'@/src/ui-scale':{us:x=>x,ufs:x=>x}};
  const exports={};vm.runInNewContext(compile(source,file),{exports,require:name=>{assert(name in mocks,name);return mocks[name];}});
  const render=()=>{index=0;return exports.default();};
  return {render,setHandler:f=>{fn=f;},settle:async()=>{await observer.refetch({cancelRefetch:false});return render();},
    query:()=>query,calls:()=>calls,close:()=>{stop?.();observer?.destroy();client.unmount();client.clear();}};
}
let cases=0;
async function check(name,fn){await fn();cases++;console.log('PASS:',name);}
async function main(){
  await check('loading has placeholders, never a fictitious zero summary',async()=>{
    let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));const tree=f.render();
    assert.equal(text(find(tree,'total-balance')),'…');
    assert.deepEqual(styled(tree,'statAmount').map(text),['…','…','…']);
    assert.equal(text(styled(tree,'growthText')[0]),'…');assert.equal(f.query().retry,false);
    finish(zero);await f.settle();f.close();
  });
  await check('successful zero is displayed as actual money, no Retry action',async()=>{
    const f=fixture(async()=>zero);f.render();const tree=await f.settle();
    assert.equal(text(find(tree,'total-balance')),'$0.00');assert.equal(find(tree,'total-balance').props.onPress,undefined);
    assert.deepEqual(styled(tree,'statAmount').map(text),['$0.00','$0.00','$0.00']);f.close();
  });
  for(const status of [409,503,'network'])await check(`${status}: failed query hides zero/stale amounts and allows an in-place retry`,async()=>{
    const error=new Error('Synthetic '+status);const f=fixture(async()=>positive);f.render();let tree=await f.settle();
    assert.equal(text(find(tree,'total-balance')),'$1000.00');
    f.setHandler(async()=>{throw error;});tree=await f.settle();
    assert.equal(text(find(tree,'total-balance')),'Reintentar');assert.equal(find(tree,'total-balance').props.accessibilityRole,'button');
    assert.deepEqual(styled(tree,'statAmount').map(text),['—','—','—']);assert.equal(text(styled(tree,'growthText')[0]),'—');
    assert(styled(tree,'debtQuadValue').every(n=>text(n)==='—'));
    assert(!styled(tree,'debtQuadFoot').some(n=>text(n)==='home.noUpcomingPayments'));
    const retry=find(tree,'total-balance').props.onPress;f.setHandler(async()=>zero);retry();tree=await f.settle();
    assert.equal(text(find(tree,'total-balance')),'$0.00');assert.equal(find(tree,'total-balance').props.onPress,undefined);f.close();
  });
  await check('income, expense, net and debts preserve their existing card positions/values',async()=>{
    const f=fixture(async()=>positive);f.render();const tree=await f.settle();
    assert.deepEqual(styled(tree,'statAmount').map(text),['$80.00','$20.00','$100.00']);
    assert.deepEqual(styled(tree,'debtQuadValue').map(text),['$500.00','$200.00','$30.00']);f.close();
  });
  await check('legacy debt catalog boundary never presents a partial count as complete',async()=>{
    for(const count of [2,500]){
      const list=Array.from({length:count},(_,i)=>({id:String(i),direction:'i_owe'}));
      const f=fixture(async()=>positive,list);f.render();const tree=await f.settle();
      const label=text(styled(tree,'debtQuadFoot')[0]);
      if(count===2)assert(label.includes('2 deudas'));else assert(!label.includes('deudas'));
      f.close();
    }
  });
  await check('real API preserves safe 409/503 and numeric summary contract',async()=>{
    const exports={};let status=200;
    vm.runInNewContext(compile(fs.readFileSync(path.join(root,'frontend/src/api.ts'),'utf8'),'api.ts'),{exports,process:{env:{}},URLSearchParams,
      fetch:async()=>({ok:status===200,status,json:async()=>zero,text:async()=>JSON.stringify({detail:'Synthetic'})})});
    assert.equal((await exports.api.summary()).total_balance,0);
    for(status of [409,503])await assert.rejects(exports.api.summary(),e=>e instanceof exports.ApiError&&e.status===status);
  });
  await check('styles, sizes, colors, fonts and navigation attributes are unchanged',async()=>{
    const base=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),marker='const useStyles =';
    assert.equal(source.slice(source.indexOf(marker)),base.slice(base.indexOf(marker)));
    function attributes(s){const tree=ts.createSourceFile(file,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out=[];
      function visit(n){if(ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n))for(const a of n.attributes.properties){
        if(a.name && ['style','size','color','numberOfLines','adjustsFontSizeToFit','minimumFontScale'].includes(a.name.getText(tree)))out.push(a.getText(tree));
        if(a.name?.getText(tree)==='onPress'&&a.getText(tree).includes('router.'))out.push(a.getText(tree));
      }ts.forEachChild(n,visit);}visit(tree);return out;}
    assert.deepEqual(attributes(source),attributes(base));
  });
  console.log(`RESULT: ${cases} summary/Home scenario groups passed.`);
}
let finished=false;process.on('beforeExit',()=>{if(!finished){console.error('FAIL: scenarios did not complete');process.exitCode=1;}});
main().then(()=>{finished=true;}).catch(error=>{finished=true;console.error(error);process.exitCode=1;});
