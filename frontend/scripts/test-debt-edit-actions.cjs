// Execute actual debt form/menu handlers with synthetic queries and API responses only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const {createInstance}=require('i18next');
const engine=createInstance();engine.init({lng:'en-US',fallbackLng:'en-US',initImmediate:false,resources:{'en-US':{translation:require('../src/i18n/locales/en.json')},es:{translation:require('../src/i18n/locales/es.json')}}});
const clone=x=>JSON.parse(JSON.stringify(x));
const original={id:'debt-one',name:'Nombre del usuario',direction:'i_owe',person:'Persona ñ',original_amount:500,minimum_payment:20,payment_frequency:'monthly',interest_rate:3,notes:'User notes\nuntouched',color:'#123456',icon:'cash-outline',account_id:'linked-account',category_id:'category-one',start_date:'2025-01-05T10:20:30Z',due_date:'2027-02-02',total_paid:100,remaining_amount:400,status:'active'};
class ApiError extends Error {constructor(status,message){super(message);this.status=status;}}
const all=n=>!n||typeof n!=='object'?[]:[n,...[n.props?.children].flat(Infinity).flatMap(all)];
function fixture(file, options={}) {
 let cursor=0;const cells=[],effects=[],cleanups=[],events=[],calls=[],alerts=[],cache={debts:[clone(original),{id:'unrelated'}]};
 const state={debt:clone(original),payments:[{id:'payment-one',amount:100}],...options};
 const ref=value=>{const i=cursor++;return cells[i]??(cells[i]={current:value});};
 const react={useRef:ref,useState:value=>{const c=ref(value);return [c.current,v=>{c.current=typeof v==='function'?v(c.current):v;}];},useCallback:f=>f,useMemo:f=>f(),memo:f=>f,useEffect:(fn,deps)=>{const c=ref(null);if(!c.current||deps.some((d,i)=>c.current[i]!==d)){c.current=deps;effects.push(fn);}}};react.default=react;
 const api={getDebt:async id=>{calls.push(['get',id]);return clone(state.current??state.debt);},listDebtPayments:async id=>{calls.push(['payments',id]);return clone(state.currentPayments??state.payments);},
  updateDebt:async(id,payload)=>{calls.push(['update',id,clone(payload)]);if(state.updateError)throw state.updateError;return {...clone(state.debt),...payload,id};},
  createDebt:async payload=>{calls.push(['create',clone(payload)]);return {id:'created'};},
  deleteDebt:async id=>{calls.push(['delete',id]);if(state.hold)await state.hold;if(state.deleteError)throw state.deleteError;return state.deleteResult??{ok:true};},listCategories:async()=>[]};
 const qc={setQueryData:(key,value)=>{const k=key.join(':');cache[k]=typeof value==='function'?value(cache[k]):value;},removeQueries:config=>events.push(['remove',config.queryKey]),invalidateQueries:config=>{events.push(['invalidate',config]);return state.refreshError?Promise.reject(state.refreshError):Promise.resolve();}};
 const router={push:route=>events.push(['push',route]),back:()=>events.push(['back']),dismissTo:route=>events.push(['dismissTo',route])};
 const colors=new Proxy({},{get:()=> '#126046'});
 const editor={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/debts/editor.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,editor);
 const mocks={react,'react/jsx-runtime':{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})},
  'react-native':{View:'View',ScrollView:'Scroll',Alert:{alert:(...a)=>alerts.push(a)},KeyboardAvoidingView:'Keyboard',Platform:{OS:'android',select:values=>values.android??values.default},Keyboard:{dismiss(){}}},
  '@/src/i18n':{tr:engine.t.bind(engine),useTranslation:()=>({t:engine.t.bind(engine)})},'@/src/i18n/errors':{localizedError:e=>e?.message??String(e)},
  '@/src/components/elastic-scroll-view':{ElasticScrollView:'Elastic'},'@/src/native-scroll':{NATIVE_VERTICAL_SCROLL:{}},
  '@/src/components/pressable':{Pressable:'Pressable'},'./pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text',TextInput:'TextInput'},'./typography':{Text:'Text'},
  'react-native-reanimated':{default:{View:'Animated'},Easing:{},useSharedValue:()=>{},useAnimatedStyle:()=>{},withTiming:()=>{}},
  '@react-native-vector-icons/ionicons':{default:'Icon'},'expo-router':{useRouter:()=>router,useLocalSearchParams:()=>state.create?{}:{id:state.debt.id}},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:24,bottom:24})},'@tanstack/react-query':{useQueryClient:()=>qc,useQuery:({queryKey})=>{
   const kind=queryKey[0];if(kind==='categories')return {data:[{id:'category-one',type:'expense',name:'Custom category'}]};
   return {data:kind==='debt'?state.debt:state.payments,isSuccess:!state.loadError,isError:!!state.loadError,isFetching:false,refetch:()=>events.push(['refetch',kind])};
  }},'@/src/api':{api,ApiError},'@/src/debts/editor':editor.exports,
  '@/src/theme':{useTheme:()=>({colors,scheme:'light'}),makeStyles:f=>()=>f(colors,'light'),radius:{cardLg:28,lg:24,pill:999},spacing:{xs:4,sm:8,md:12,lg:16}},
  '@/src/components/ui':{IconTile:'IconTile'},'@/src/components/sheets':{AppSheet:'AppSheet'},'./sheets':{AppSheet:'AppSheet'},
  '@/src/ui-scale':{us:x=>x,ufs:x=>x},'@/src/color-palette':{COLOR_PALETTE:['#123456']}};
 const context={exports:{},require:name=>{assert(name in mocks,name);return mocks[name];}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:false}}).outputText,context);
 const component=context.exports.default??context.exports.DebtActions;
 function render(){cursor=0;const tree=component(file.includes('debt-actions')?{debt:state.debt,onClose:()=>events.push(['close']),...(state.detailReturn?{onDeleted:()=>events.push(['deleted',state.debt.id])}:{})}:{});effects.splice(0).forEach(f=>cleanups.push(f()));return tree;}
 function find(id){return all(render()).find(n=>n.props?.testID===id);}
 render();render();return {render,find,state,calls,events,alerts,cache,unmount:()=>cleanups.filter(Boolean).forEach(f=>f())};
}
const tick=()=>new Promise(setImmediate);
async function main(){
 for(const language of ['en-US','es']) {
  engine.changeLanguage(language);
  for(const direction of ['i_owe','they_owe']) {
   const f=fixture('frontend/app/debts/new.tsx',{debt:{...original,direction}});
   assert.equal(f.find('debt-name').props.value,original.name);assert.equal(f.find('debt-person').props.value,original.person);assert.equal(f.find('debt-amount').props.editable,false);
   f.find('debt-name').props.onChangeText('Edited only');
   await f.find('save-debt').props.onPress();
   const update=f.calls.find(c=>c[0]==='update');assert(update);assert.equal(update[1],original.id);assert(!f.calls.some(c=>c[0]==='create'));
   assert.equal(update[2].name,'Edited only');assert.equal(update[2].original_amount,original.original_amount);assert.equal(update[2].direction,direction);
   for(const key of ['notes','start_date','due_date','account_id','category_id'])assert.equal(update[2][key],original[key]);
   for(const key of ['id','user_id','total_paid','remaining_amount','status'])assert(!(key in update[2]));
   assert.equal(f.cache.debts.length,2);assert.equal(f.cache.debts[1].id,'unrelated');assert.equal(f.cache.debts[0].total_paid,100);assert(f.events.some(e=>e[0]==='dismissTo'));
  }
  let f=fixture('frontend/app/debts/new.tsx');const back=all(f.render()).find(n=>n.type==='Pressable'&&n.props.onPress&&!n.props.testID);back.props.onPress();assert.equal(f.calls.length,0);
  f=fixture('frontend/app/debts/new.tsx',{debt:{...original,total_paid:0,remaining_amount:500},payments:[]});assert.equal(f.find('debt-amount').props.editable,true);f.find('debt-amount').props.onChangeText('650');await f.find('save-debt').props.onPress();assert.equal(f.calls.find(c=>c[0]==='update')[2].original_amount,650);
  for(const changed of ['original_amount','total_paid','account_id','name','notes']) {
   f=fixture('frontend/app/debts/new.tsx',{current:{...original,[changed]:changed.includes('amount')||changed==='total_paid'?999:'concurrent'}});await f.find('save-debt').props.onPress();assert(!f.calls.some(c=>c[0]==='update'));assert(f.alerts.length);
  }
  f=fixture('frontend/app/debts/new.tsx',{debt:{...original,total_paid:0,remaining_amount:500},payments:[],currentPayments:[{id:'new-zero-payment',amount:0}]});f.find('debt-amount').props.onChangeText('600');await f.find('save-debt').props.onPress();assert(!f.calls.some(c=>c[0]==='update'));
  f=fixture('frontend/app/debts/new.tsx',{loadError:true});assert(!f.find('save-debt'));assert(f.find('debt-edit-status'));f.find('debt-edit-retry').props.onPress();assert.equal(f.events.length,2);
  f=fixture('frontend/app/debts/new.tsx',{debt:{...original,person:null,notes:null}});await f.find('save-debt').props.onPress();assert.equal(f.calls.find(c=>c[0]==='update')[2].person,null);assert.equal(f.calls.find(c=>c[0]==='update')[2].notes,null);
  f=fixture('frontend/app/debts/new.tsx',{updateError:new ApiError(409,'Server conflict')});await f.find('save-debt').props.onPress();assert(f.alerts.length);assert(!f.events.some(e=>e[0]==='dismissTo'));
  f=fixture('frontend/app/debts/new.tsx');const save=f.find('save-debt').props.onPress;await Promise.all([save(),save()]);assert.equal(f.calls.filter(c=>c[0]==='update').length,1);
  f=fixture('frontend/app/debts/new.tsx',{create:true});f.find('dir-i-owe').props.onPress();f.find('debt-name').props.onChangeText('New');f.find('debt-amount').props.onChangeText('250');await f.find('save-debt').props.onPress();assert.equal(f.calls.filter(c=>c[0]==='create').length,1);assert(!f.calls.some(c=>c[0]==='update'));
  f=fixture('frontend/src/components/debt-actions.tsx');f.find('debt-action-edit').props.onPress();assert.equal(f.events.at(-1)[1].params.id,original.id);assert.equal(f.events.at(-1)[1].pathname,'/debts/new');assert.equal(f.calls.length,0);
  for(const cancel of [f=>f.render().props.onClose(),f=>f.find('debt-actions-cancel').props.onPress()]){f=fixture('frontend/src/components/debt-actions.tsx');cancel(f);assert.equal(f.calls.length,0);assert.deepEqual(f.events,[['close']]);}
  f=fixture('frontend/src/components/debt-actions.tsx');f.find('debt-action-delete').props.onPress();assert.equal(f.calls.length,0);f.find('debt-actions-cancel').props.onPress();assert.equal(f.calls.length,0);
  f=fixture('frontend/src/components/debt-actions.tsx');f.find('debt-action-delete').props.onPress();assert(all(f.render()).some(n=>n.type==='Text'&&n.props.children?.includes?.(original.name)));const confirm=f.find('debt-delete-confirm').props.onPress;confirm();confirm();await tick();assert.deepEqual(f.calls,[['delete',original.id]]);assert.equal(f.cache.debts.length,1);assert.equal(f.cache.debts[0].id,'unrelated');assert(f.events.some(e=>e[0]==='close'));
  for(const failure of [new ApiError(409,'Linked records'),new ApiError(503,'Unavailable')]) {
   f=fixture('frontend/src/components/debt-actions.tsx',{deleteError:failure});f.find('debt-action-delete').props.onPress();f.find('debt-delete-confirm').props.onPress();await tick();assert.equal(f.cache.debts.length,2);assert(f.find('debt-delete-error'));assert(!f.events.some(e=>e[0]==='close'));if(failure.status===409)assert.equal(f.find('debt-delete-error').props.children,engine.t('debts.deleteLinked'));
  }
  let release;const hold=new Promise(resolve=>release=resolve);f=fixture('frontend/src/components/debt-actions.tsx',{hold});f.find('debt-action-delete').props.onPress();f.find('debt-delete-confirm').props.onPress();f.render().props.onClose();assert(!f.events.some(e=>e[0]==='close'));f.unmount();release();await tick();assert.equal(f.cache.debts.length,1);assert(!f.events.some(e=>e[0]==='close'));
  for(const deleteError of [null,new ApiError(409,'Linked')]) {
   f=fixture('frontend/src/components/debt-actions.tsx',{detailReturn:true,deleteError});f.find('debt-action-delete').props.onPress();f.find('debt-delete-confirm').props.onPress();await tick();
   assert.equal(f.events.filter(e=>e[0]==='deleted').length,deleteError?0:1);
  }
  f=fixture('frontend/src/components/debt-actions.tsx',{refreshError:new Error('refresh')});f.find('debt-action-delete').props.onPress();f.find('debt-delete-confirm').props.onPress();await tick();assert.equal(f.cache.debts.length,1);assert(!f.find('debt-delete-confirm'));assert.equal(f.find('debt-delete-error').props.children,engine.t('debts.deleteRefreshFailed'));
 }
 console.log('PASS: actual creation/edit hydration, same-ID PUT without POST, protected amounts/payments/identity/hidden fields, stale source/new payment detection, cancel, load/retry, server errors and double-save; English/Spanish.');
 console.log('PASS: actual Edit route, named custom confirmation, outside/cancel without writes, one selected DELETE, server 409/503, confirmed-only cache updates, unrelated records preserved and refresh failure without repeat deletion.');
 console.log('DEVICE LIMIT: synthetic handlers only; Android touch targets, corner/ring spacing, sheets and keyboard require Expo Go review.');
}
let done=false;process.on('beforeExit',()=>{if(!done)process.exitCode=1;});main().then(()=>{done=true;}).catch(e=>{done=true;console.error(e);process.exitCode=1;});
