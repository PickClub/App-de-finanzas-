// Actual localized component + simulated UI-thread touch/scroll events.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const file='frontend/src/components/elastic-scroll-view.tsx',source=fs.readFileSync(file,'utf8');
function fixture(kind='scroll',count=20,density=1){
 let pan,native,scroll,animation;const values=[];
 class Builder{manualActivation(v){this.manual=v;return this;}maxPointers(v){this.pointers=v;return this;}shouldCancelWhenOutside(v){return this;}
  onTouchesDown(f){this.down=f;return this;}onTouchesMove(f){this.move=f;return this;}onUpdate(f){this.update=f;return this;}onFinalize(f){this.finalize=f;return this;}}
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),forwardRef:f=>f,useMemo:f=>f()};React.default=React;
 const mocks={react:React,'react-native':{PixelRatio:{get:()=>density}},'react-native-gesture-handler':{GestureDetector:'Detector',Gesture:{Native:()=>native={native:true},Pan:()=>pan=new Builder(),Simultaneous:(...gestures)=>({gestures})}},
  'react-native-reanimated':{__esModule:true,default:{View:'AnimatedView',ScrollView:'AnimatedScrollView',FlatList:'AnimatedFlatList'},useSharedValue:value=>{const v={value};values.push(v);return v;},useAnimatedStyle:f=>f(),useComposedEventHandler:handlers=>e=>handlers.forEach(h=>h&&h(e)),
   useAnimatedScrollHandler:f=>{scroll=f;return f;},cancelAnimation:()=>{},withTiming:(target,config)=>{animation={target,config};return target;},Easing:{cubic:'cubic',out:x=>x},ReduceMotion:{System:'system'}}};
 const exports={};vm.runInNewContext(ts.transpileModule(source,{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,{exports,require:n=>mocks[n]});
 const tracked=[];
 const draft={description:'Unsaved\ntext',amount:'70.25'};
 const rows=Array.from({length:count},(_,i)=>({id:String(i)}));let rendered=0;
 const renderItem=()=>rendered++;
 const tree=kind==='scroll'?exports.ElasticScrollView({children:draft,animatedOnScroll:e=>tracked.push(e.contentOffset.y),keyboardShouldPersistTaps:'handled',contentContainerStyle:{paddingBottom:16},overScrollMode:'always'},null)
  :exports.ElasticFlatList({data:rows,renderItem,initialNumToRender:12,windowSize:7,contentContainerStyle:{paddingBottom:16}});
 let active=0,failed=0;const manager={activate:()=>active++,fail:()=>failed++};
 const touch=(x,y,n=1)=>({numberOfTouches:n,allTouches:n===1?[{absoluteX:x,absoluteY:y}]:[]});
 return {exports,pan,tree,values,draft,rows,tracked,renderItem,rendered:()=>rendered,manager,touch,scroll,setY:y=>tree.children[0].children[0].props.onScroll({contentOffset:{y}}),active:()=>active,failed:()=>failed,animation:()=>animation};
}
const f=fixture();assert(f.values.every(v=>v.value===0||v.value===false));assert.equal(f.pan.manual,true);assert.equal(f.pan.pointers,1);
f.pan.down(f.touch(20,20),f.manager);f.pan.move(f.touch(20,27),f.manager);assert.equal(f.active(),0);
f.pan.move(f.touch(20,80),f.manager);assert.equal(f.active(),1);f.pan.update({translationY:60});
assert(f.values[1].value>0&&f.values[1].value<20);const before=f.values[1].value;
f.pan.update({translationY:200});assert(f.values[1].value>before);f.pan.finalize();assert.equal(f.values[1].value,0);
assert.equal(f.animation().target,0);assert.equal(f.animation().config.duration,240);assert.equal(f.animation().config.reduceMotion,'system');
console.log('PASS: no initial/focus movement; downward top drag moves content with bounded resistance; release returns to exact zero.');
for(const [y,x,dy,n] of [[100,0,80,1],[0,80,80,1],[0,0,-80,1],[0,0,80,2]]){
 const g=fixture();g.setY(y);g.pan.down(g.touch(20,20,n),g.manager);g.pan.move(g.touch(20+x,20+dy,n),g.manager);
 assert.equal(g.active(),0);assert(g.failed()>0);assert.equal(g.values[1].value,0);
}
const composed=fixture();composed.setY(150);assert.equal(composed.values[0].value,150);assert.deepEqual(composed.tracked,[150]);
console.log('PASS: existing Home UI-thread scroll handler remains composed with elastic top detection.');
const tap=fixture();tap.pan.down(tap.touch(20,20),tap.manager);tap.pan.finalize();assert.equal(tap.active(),0);assert.equal(tap.animation(),undefined);
const cancelled=fixture();cancelled.pan.down(cancelled.touch(20,20),cancelled.manager);cancelled.pan.move(cancelled.touch(20,90),cancelled.manager);cancelled.pan.update({translationY:70});cancelled.pan.finalize();assert.equal(cancelled.values[1].value,0);
console.log('PASS: ordinary taps, upward/horizontal/scrolled/multitouch gestures do not activate; cancellation also restores zero.');
const detector=f.tree.children[0],scrollView=detector.children[0];assert.equal(detector.props.gesture.gestures.length,2);
assert.equal(scrollView.children[0],f.draft);assert.equal(scrollView.props.keyboardShouldPersistTaps,'handled');assert.equal(scrollView.props.contentContainerStyle.paddingBottom,16);
assert.equal(scrollView.props.overScrollMode,'never');assert.equal(scrollView.props.bounces,false);assert(!scrollView.props.refreshControl);assert(!scrollView.props.onRefresh);
assert(!source.includes('Keyboard.dismiss'));assert(!source.includes('useFocusEffect'));assert(!source.includes('scale:'));assert(!source.includes('opacity:'));assert(!source.includes('api.'));
console.log('PASS: native scroll remains simultaneous, only one elastic mechanism, draft/layout/keyboard props preserved, no refresh or navigation callbacks.');
for(const count of [0,1,10001]){
 const list=fixture('list',count),view=list.tree.children[0].children[0];
 assert.equal(view.type,'AnimatedFlatList');assert.equal(view.props.data,list.rows);assert.equal(view.props.renderItem,list.renderItem);
 assert.equal(view.props.initialNumToRender,12);assert.equal(view.props.windowSize,7);assert.equal(list.rendered(),0);
 assert(!view.props.onRefresh);assert(!view.props.refreshControl);
 list.pan.down(list.touch(20,20),list.manager);list.pan.move(list.touch(20,90),list.manager);list.pan.update({translationY:70});
 assert(list.values[1].value>0);list.pan.finalize();assert.equal(list.values[1].value,0);
}
console.log('PASS: empty/one/10001-row FlatList keeps data and render callbacks/windows unchanged, with drag/return and no nested ScrollView.');
for(const path of ['frontend/app/settings.tsx','frontend/app/accounts/[id].tsx','frontend/app/transactions/new.tsx','frontend/app/(tabs)/more.tsx']){
 const s=fs.readFileSync(path,'utf8');assert.equal((s.match(/<ElasticScrollView/g)||[]).length,1,path);assert.equal((s.match(/<\/ElasticScrollView>/g)||[]).length,1,path);
}
assert(fs.readFileSync('frontend/app/transactions/new.tsx','utf8').includes('["expense", "income", "transfer"]'));
console.log('PASS: all four mandatory screen containers integrated; the shared calculator form covers expense, income and transfer.');
for(const path of ['frontend/app/budgets/index.tsx','frontend/app/goals/index.tsx','frontend/app/recurring/index.tsx','frontend/app/transactions/[id].tsx']){
 const s=fs.readFileSync(path,'utf8');assert.equal((s.match(/<ElasticScrollView/g)||[]).length,1,path);assert.equal((s.match(/<\/ElasticScrollView>/g)||[]).length,1,path);
}
const bills=fs.readFileSync('frontend/app/bills/index.tsx','utf8');assert.equal((bills.match(/<ElasticFlatList/g)||[]).length,1);
assert(bills.includes('data={items}'));assert(bills.includes('initialNumToRender={12}'));assert(bills.includes('windowSize={7}'));
console.log('PASS: Budgets, Goals, Recurring, Bills and transaction preview each use an explicit elastic container.');
for(const density of [1,2,3,3.5]){
 const g=fixture('scroll',1,density);let previous=0;
 for(const distance of [-100,0,12,13,60,200,1000,100000,Infinity]){
  const displacement=g.exports.pullDistance(distance)*density;
  const prior=10*(1-Math.exp(-Math.max(0,distance-12)/180));
  assert(Math.abs(displacement-prior*2)<1e-10, "Each drag must move exactly twice as far, with unchanged resistance");
  assert(displacement>=previous&&displacement>=0&&displacement<=20);previous=displacement;
 }
 assert.equal(g.exports.pullDistance(100000)*density,20);
}
console.log('PASS: physical displacement capped at 20 pixels for densities 1/2/3/3.5, huge drags and infinity; high resistance and monotonic response.');
console.log('DEVICE LIMIT: Android gesture arbitration/resistance and keyboard taps require Samsung review; these are simulated events, not a real touch test.');
