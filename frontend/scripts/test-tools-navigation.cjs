// Exercise real navigation/FAB handlers with synthetic hooks, without device or API writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync('frontend/app/(tabs)/_layout.tsx', 'utf8');
const home = fs.readFileSync('frontend/app/(tabs)/index.tsx', 'utf8');
const catalogs = ['en', 'es'].map(language => JSON.parse(fs.readFileSync(`frontend/src/i18n/locales/${language}.json`, 'utf8')));
let language = 0, slots = [], cursor = 0, effects = [], frames = [], pathname = '/', focusCleanup, backHandler;
const events = [];
const ref = {};
function slot(create) { const i = cursor++; return slots[i] ?? (slots[i] = create()); }
const useRef = value => slot(() => ({ current: value }));
const useState = value => { const cell = slot(() => ({value})); return [cell.value, value => {cell.value = value;}]; };
const useEffect = (fn, dependencies) => {
  const cell = slot(() => ({ dependencies: null }));
  if (!cell.dependencies || dependencies.some((d,i) => d !== cell.dependencies[i])) {
    cell.dependencies = dependencies; effects.push(fn);
  }
};
const useCallback = (fn, deps) => {const cell = slot(() => ({deps:null})); if(!cell.deps || deps.some((d,i)=>d!==cell.deps[i])) {cell.deps=deps;cell.fn=fn;}return cell.fn;};
const t = key => key.split('.').reduce((value, part) => value?.[part], catalogs[language]);
const router = {push: route => events.push(['push', route])};
const react = {useState,useRef,useEffect,useCallback,memo:x=>x,forwardRef:x=>x,useImperativeHandle:(ref,fn)=>Object.assign(ref,fn())};
react.default = react;
const jsx = (type, props) => ({type,props});
const animations = {
  default: {View:'Animated.View'}, cancelAnimation:()=>events.push(['cancel']),
  useSharedValue: value => {const cell = useRef(null); return cell.current ?? (cell.current={value,get(){return this.value;},set(v){this.value=v;}});},
  useAnimatedStyle:fn=>fn(), withTiming:(value,options,done)=>{if(done)frames.push(()=>done(true));return value;},
  runOnJS:fn=>fn, interpolate:()=>0, Extrapolation:{CLAMP:0}, Easing:{linear:0},
};
const mocks = {
  react, 'react/jsx-runtime':{jsx,jsxs:jsx},
  'expo-router':{Tabs:'Tabs',useRouter:()=>router,usePathname:()=>pathname,useFocusEffect:fn=>{focusCleanup=fn();}},
  'react-native':{View:'View',BackHandler:{addEventListener:(_event,handler)=>{backHandler=handler;return {remove(){}};}}},
  '@/src/components/pressable':{Pressable:'Pressable'}, '@/src/components/typography':{Text:'Text'},
  '@/src/i18n':{tr:t,useTranslation:()=>({t})},
  'react-native-reanimated':animations,'@react-native-vector-icons/ionicons':{default:'Icon'},
  'expo-haptics':{impactAsync:()=>Promise.resolve(),ImpactFeedbackStyle:{Soft:0,Rigid:1}},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({bottom:0})},
  '@/src/theme':{useTheme:()=>({colors:{},scheme:'light'}),makeStyles:factory=>()=>factory({},'light')},
  '@/src/ui-scale':{us:x=>x,touchSlop:x=>x},
};
const context = {exports:{},require:name=>{assert(name in mocks,name); return mocks[name];},Math};
vm.runInNewContext(ts.transpileModule(source+'\nexport { QuickMenu, CustomTabBar, TAB_CONFIG };',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:false}}).outputText,context);
function render() {cursor=0; const tree=context.exports.QuickMenu({geometry:{x:200,y:700,width:400,barTop:670}},ref);const pending=effects;effects=[];pending.forEach(fn=>fn());return tree;}
function walk(node) {if(!node || typeof node!=='object')return [];return [node,...[node.props?.children].flat(Infinity).flatMap(walk)];}
function center(tree) {return walk(tree).find(n=>n.props?.testID==='fab-add-btn');}
function complete() {const callbacks=frames;frames=[];callbacks.forEach(fn=>fn());}
function open() {let tree=render();center(tree).props.onPress();complete();tree=render();assert.equal(center(tree).props.accessibilityState.expanded,true);return tree;}
assert.deepEqual(Object.keys(context.exports.TAB_CONFIG),['index','transactions','reports','more']);
assert.equal(context.exports.TAB_CONFIG.more.icon,'grid');
for(language=0;language<2;language++) {
  assert.equal(t(context.exports.TAB_CONFIG.more.labelKey),language?'Herramientas':'Tools');
  let tree=open();
  const actions=walk(tree).filter(n=>n.props?.item);
  assert.equal(actions.length,5);
  assert.deepEqual(actions.slice(0,4).map(n=>n.props.item.route),['/transactions/new?type=expense','/transactions/new?type=income','/transactions/new?type=transfer','/debts/new?direction=i_owe']);
  assert.equal(actions[4].props.item.route,'/(tabs)/notes');
  assert.equal(actions[4].props.item.label,language?'Notas':'Notes');
  assert.equal(actions[4].props.item.icon,'document-text');
  const shield=walk(tree).find(n=>n.props?.testID==='fab-dismiss-overlay');
  assert(shield, 'An open menu must capture outside touches');
  assert.equal(shield.props.pointerEvents,'auto');
  assert.equal(shield.props.style.position,'absolute');
  for(const edge of ['top','right','bottom','left'])assert.equal(shield.props.style[edge],0);
  assert.equal(shield.props.style.backgroundColor,undefined,'Touch shield must not darken the tab bar');
  actions[4].props.onSelect(actions[4].props.item.route);complete();render();assert.deepEqual(events.at(-1),['push','/(tabs)/notes']);
  open();ref.close();complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
}
language=0;
function outsideTap(underlying) {
  const shield = walk(render()).find(n=>n.props?.testID==='fab-dismiss-overlay');
  assert(shield, 'A full-screen touch shield must exist independently of the visual backdrop');
  if (shield.props.pointerEvents === 'auto') shield.props.onPress();
  else underlying();
}
for(const route of ['index','transactions','reports','more']) {
  open(); const navigation={emit:()=>({defaultPrevented:false}),navigate:name=>events.push(['navigate',name])};
  const state={routes:['index','transactions','fab','reports','notes','more'].map(name=>({name,key:name})),index:4};
  const menuSlots=slots; slots=[]; cursor=0; const tree=context.exports.CustomTabBar({state,navigation,dismissMenu:ref.close});
  slots=menuSlots; effects=[];
  const press=()=>walk(tree).find(n=>n.props?.routeName===route).props.onPress();
  const before=events.length;
  outsideTap(press); assert.equal(events.length,before,'First outside tap dismisses only');
  outsideTap(press); assert.equal(events.length,before,'Touches stay blocked throughout closing');
  complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
  outsideTap(press);assert.deepEqual(events.at(-1),['navigate',route],'Second tap after closing activates');
}
for(const route of ['/settings','/accounts/synthetic-card',null]) {
  open();const before=events.length;
  const press=()=>{if(route)router.push(route);};
  outsideTap(press);assert.equal(events.length,before);
  complete();outsideTap(press);
  if(route)assert.deepEqual(events.at(-1),['push',route]);else assert.equal(events.length,before);
}
for(let index=0;index<5;index++) {
  const tree=open();const action=walk(tree).filter(n=>n.props?.item)[index];
  // Render the real RadialAction to exercise its Pressable rather than calling navigation directly.
  const button=walk(action.type(action.props)).find(n=>n.type==='Pressable');
  const before=events.length;
  button.props.onPress();assert.equal(events.length,before);
  // A new touch during closing cannot cancel the selected action or leak through.
  outsideTap(()=>assert.fail('Closing overlay leaked a touch'));complete();render();
  assert.deepEqual(events.at(-1),['push',action.props.item.route]);
}
let tree=open();center(tree).props.onPress();complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
open();assert.equal(backHandler(),true);complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
open();pathname='/settings';render();complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
open();focusCleanup();complete();assert.equal(center(render()).props.accessibilityState.expanded,false);
assert(!source.includes('onTouchStart='), 'No pass-through root touch listener');
assert.match(source,/backdropPress: \{ position: \"absolute\", top: 0, left: 0, right: 0, bottom: 0 \}/);
assert.match(source,/pointerEvents=\{active \? \"auto\" : \"none\"\}/);
assert(source.indexOf('testID=\"fab-dismiss-overlay\"') < source.indexOf('{items.map'), 'Actions are above the full-screen shield');
assert.match(source,/accessibilityLabel=\{label\}/);
assert.match(home,/testID="profile-more-btn"[^\n]*router.push\("\/settings"\)/);
assert.match(source,/duration: Math.max\(1, 420 \* remaining\)/);
assert.match(source,/opacity: 0.368 \* phase/);
console.log('PASS: Tools/Herramientas, grid tab, unchanged first four actions, Notes destination, FIRST OUTSIDE TAP DISMISSES ONLY; SECOND TAP ACTIVATES; all tabs/avatar/card/background, closing shield, five direct actions, center toggle, route/focus cleanup, unchanged animation constants and Home Settings access.');
console.log('LIMIT: native Android touch propagation, hit testing and physical animation require Expo Go verification.');
