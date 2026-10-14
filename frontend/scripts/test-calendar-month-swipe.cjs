const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// Actual calendar + synthetic queries/gestures. No network or financial writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),ts=require('typescript');
const file='frontend/app/calendar/index.tsx',source=fs.readFileSync(file,'utf8');
const compile=(s,f)=>ts.transpileModule(s,{fileName:f,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
const helpers={};vm.runInNewContext(compile(fs.readFileSync('frontend/src/calendar/shared.ts','utf8'),'shared.ts'),localeGlobals({exports:helpers,require:()=>({default:{language:'es'},localeTag:()=> 'es-MX'})}));
const find=(tree,id)=>!tree||typeof tree!=='object'?null:tree.props?.testID===id?tree:(tree.children||[]).flat(Infinity).map(n=>find(n,id)).find(Boolean);
const text=tree=>typeof tree==='string'||typeof tree==='number'?String(tree):(tree?.children||[]).flat(Infinity).map(text).join(' ');
function fixture(day){
 let index=0,ticks=1000,gesture,placeholder=false;const slots=[],queries=[],prefetch=[],effects=[];
 const react={createElement:(type,props,...children)=>typeof type==='function'?type({...props,children}):({type,props:props||{},children}),Fragment:'Fragment',memo:f=>f,
  useState:v=>{const i=index++;if(!(i in slots))slots[i]=typeof v==='function'?v():v;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},
  useRef:v=>{const i=index++;if(!(i in slots))slots[i]={current:v};return slots[i];},useMemo:f=>f(),useCallback:f=>f,useEffect:f=>effects.push(f)};react.default=react;
 class Pan{constructor(){this.options={};}enabled(v){this.options.enabled=v;return this;}maxPointers(v){this.options.pointers=v;return this;}activeOffsetX(v){this.options.x=v;return this;}failOffsetY(v){this.options.y=v;return this;}runOnJS(v){this.options.js=v;return this;}onEnd(f){this.end=f;gesture=this;return this;}}
 const styles=new Proxy({},{get:(_,tag)=>({tag})}),colors=new Proxy({},{get:()=> '#126046'});
 const qc={prefetchQuery:o=>prefetch.push(o.queryKey),invalidateQueries:()=>{}};
 const nativeDate=Date;class Clock extends nativeDate{constructor(...args){super(...(args.length?args:[day+'T12:00:00']));}static now(){return ticks;}}
 const mocks=localeMocks({react,'react-native':{View:'View',ScrollView:'ScrollView',ActivityIndicator:'Spinner',RefreshControl:'Refresh',useWindowDimensions:()=>({width:400})},
  '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},'@react-native-vector-icons/ionicons':{default:'Icon'},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},'expo-router':{useFocusEffect:()=>{},useRouter:()=>({push:()=>{throw Error('Unexpected navigation');},back:()=>{}})},
  '@tanstack/react-query':{keepPreviousData:x=>x,useQueryClient:()=>qc,useQuery:o=>{
    queries.push(o);const [kind,y,m]=o.queryKey;
    const event={id:'synthetic',kind:'income',subtype:'income',source:'transaction',ref_id:'fake',date:helpers.ymd(new Date(y,m,0)),amount:50,sign:1,counts_in_net:true,realized:true,status:'done',title:'Synthetic',time:null};
    return {data:kind==='calendar-events'?{events:[event]}:kind==='calendar-summary'?{income:{amount:y*12+m,count:1}}:{items:[]},isLoading:false,isFetching:placeholder,isPlaceholderData:placeholder&&kind!=='calendar-upcoming',isError:false,refetch:()=>{}};
  }},'@/src/api':{api:{calendarEvents:()=>{throw Error('No network');},calendarSummary:()=>{throw Error('No network');}}},
  '@/src/theme':{useTheme:()=>({colors,scheme:'light'}),makeStyles:()=>()=>styles,spacing:{lg:16,md:12,xl:24}},'@/src/i18n':{useTranslation:()=>({t:k=>k,i18n:{language:'es'}})},
  '@/src/format':{formatCurrencyInt:String},'@/src/components/sheets':{AppSheet:'Sheet'},'@/src/budgets/shared':{FOREST:'#126046',useMontserrat:()=>()=>({})},
  '@/src/calendar/shared':helpers,'@/src/components/elastic-scroll-view':{ElasticScrollView:'ScrollView'},'@/src/native-scroll':{NATIVE_VERTICAL_SCROLL:{overScrollMode:'always',bounces:true,alwaysBounceVertical:true}},'@/src/ui-scale':{us:x=>x},'react-native-gesture-handler':{Gesture:{Pan:()=>new Pan()},GestureDetector:'Detector'},
  'react-native-reanimated':{default:{View:'AnimatedView'},useSharedValue:v=>react.useRef(v),withTiming:(target,config)=>({target,config}),ReduceMotion:{System:'system'}}});
 // Shared values use .value rather than React refs' .current.
 mocks['react-native-reanimated'].useSharedValue=v=>{const r=react.useRef(undefined);if(r.value===undefined)r.value=v;return r;};
 const exports={};vm.runInNewContext(compile(source,file),localeGlobals({exports,require:name=>{assert(name in mocks,name);return mocks[name];},Date:Clock}));
 const render=()=>{index=0;effects.length=0;const tree=exports.default();effects.forEach(f=>f());return tree;};
 return {render,queries,prefetch,gesture:()=>gesture,advance:()=>ticks+=300,pending:v=>placeholder=v};
}
for(const [start,wanted] of [['2026-01-31','2026-02-28'],['2028-01-31','2028-02-29'],['2026-03-31','2026-04-30'],['2026-12-31','2027-01-31'],['2026-05-15','2026-06-15']]){
 const f=fixture(start);let tree=f.render();assert.deepEqual(Array.from(f.gesture().options.x),[-24,24]);assert.deepEqual(Array.from(f.gesture().options.y),[-12,12]);assert.equal(f.gesture().options.pointers,1);
 f.gesture().end({translationX:-80,translationY:2},true);tree=f.render();const selected=find(tree,'cal-day-'+wanted);assert(selected.props.style.some(s=>s?.backgroundColor));
 const d=helpers.parseYmd(wanted),keys=f.queries.slice(-3).map(q=>Array.from(q.queryKey));assert.deepEqual(keys[0],['calendar-events',d.getFullYear(),d.getMonth()+1]);assert.deepEqual(keys[1],['calendar-summary',d.getFullYear(),d.getMonth()+1]);
 const title=text(find(tree,'cal-title'));f.gesture().end({translationX:-90,translationY:0},true);tree=f.render();assert.equal(text(find(tree,'cal-title')),title);
 const animation=find(tree,'cal-month-page');const entry=animation.props.entering({targetOriginX:10,targetWidth:300});assert.equal(entry.initialValues.originX,310);assert.equal(entry.animations.originX.config.duration,240);assert.equal(entry.animations.originX.config.reduceMotion,'system');
 f.advance();f.gesture().end({translationX:80,translationY:0},true);tree=f.render();const exit=find(tree,'cal-month-page').props.exiting({currentOriginX:10,currentWidth:300});assert.equal(exit.animations.originX.target,310);
 assert.equal(f.prefetch.filter(k=>k[0]==='calendar-summary').length>0,true);
}
console.log('PASS: left/right, day preservation/clamping, leap years, December/January, month query keys, one transition and 240ms reduced-motion-aware animation.');
const f=fixture('2026-01-31');let tree=f.render(),initial=text(find(tree,'cal-title'));
for(const [x,y,success] of [[10,0,true],[70,60,true],[0,90,true],[-90,0,false]]){f.gesture().end({translationX:x,translationY:y},success);tree=f.render();assert.equal(text(find(tree,'cal-title')),initial);}
find(tree,'cal-next').props.onPress();tree=f.render();assert(text(find(tree,'cal-title')).includes('2026'));assert(find(tree,'cal-day-2026-02-28').props.style.some(s=>s?.backgroundColor));
f.advance();find(tree,'cal-prev').props.onPress();tree=f.render();assert(find(tree,'cal-day-2026-01-28').props.style.some(s=>s?.backgroundColor));
find(tree,'cal-mode-week').props.onPress();f.render();assert.equal(f.gesture().options.enabled,false);
console.log('PASS: short/vertical/cancelled gestures ignored; existing buttons work; week mode excludes the month gesture.');
const loading=fixture('2026-01-31');tree=loading.render();loading.pending(true);loading.gesture().end({translationX:-80,translationY:0},true);tree=loading.render();
assert(text(find(tree,'cal-sum-income')).includes('…'));assert(!text(find(tree,'cal-sum-income')).includes(String(2026*12+2)));
assert(!find(tree,'cal-month-empty'));loading.pending(false);tree=loading.render();assert(text(find(tree,'cal-sum-income')).includes(String(2026*12+2)));assert(text(find(tree,'cal-day-capsule')).includes('+50'));
console.log('PASS: pending month data never exposes stale totals or false empty results; fresh totals/events use the selected month/day.');
const base=cp.execFileSync('git',['show','HEAD:'+file],{encoding:'utf8'}),marker='const useStyles =';assert.equal(source.slice(source.indexOf(marker)),base.slice(base.indexOf(marker)));
const cell='const DayCell =';assert.equal(source.slice(source.indexOf(cell),source.indexOf(marker)),base.slice(base.indexOf(cell),base.indexOf(marker)));
console.log('PASS: all style definitions, day cells, event indicators and press actions unchanged.');
