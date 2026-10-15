// Actual localized component + simulated UI-thread touch/scroll events.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const file='frontend/src/components/elastic-scroll-view.tsx',source=fs.readFileSync(file,'utf8');
function fixture(kind='scroll',count=20,density=1){
 let pan,native,scroll,animation,handlers,focus,unfocus;let clock=0;const values=[],animations=[];
 class Builder{manualActivation(v){this.manual=v;return this;}maxPointers(v){this.pointers=v;return this;}shouldCancelWhenOutside(v){return this;}
  onTouchesDown(f){this.down=f;return this;}onTouchesMove(f){this.move=f;return this;}onUpdate(f){this.update=f;return this;}onFinalize(f){this.finalize=f;return this;}}
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),forwardRef:f=>f,useMemo:f=>f(),useCallback:f=>f};React.default=React;
 const mocks={react:React,'expo-router':{useFocusEffect:f=>{focus=f;unfocus=f();}},'react-native':{PixelRatio:{get:()=>density}},'react-native-gesture-handler':{GestureDetector:'Detector',Gesture:{Native:()=>native={native:true},Pan:()=>pan=new Builder(),Simultaneous:(...gestures)=>({gestures})}},
  'react-native-reanimated':{__esModule:true,default:{View:'AnimatedView',ScrollView:'AnimatedScrollView',FlatList:'AnimatedFlatList'},useSharedValue:value=>{const v={value,set(next){this.value=typeof next==='function'?next(this.value):next;}};values.push(v);return v;},useAnimatedStyle:f=>f(),useComposedEventHandler:handlers=>e=>handlers.forEach(h=>h&&h(e)),
   useAnimatedScrollHandler:f=>{handlers=typeof f==='function'?{onScroll:f}:f;scroll=e=>handlers.onScroll?.(e);return scroll;},cancelAnimation:()=>{if(animation&&!animation.finished){animation.finished=true;animation.callback?.(false);}},withTiming:(target,config,callback)=>{animation={target,config,callback,finished:false};animations.push(animation);return target;},Easing:{cubic:'cubic',out:x=>x},ReduceMotion:{System:'system'}}};
 const exports={};vm.runInNewContext(ts.transpileModule(source,{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,{exports,require:n=>mocks[n]});
 const tracked=[];
 const draft={description:'Unsaved\ntext',amount:'70.25'};
 const rows=Array.from({length:count},(_,i)=>({id:String(i)}));let rendered=0;
 const renderItem=()=>rendered++;
 const tree=kind==='scroll'?exports.ElasticScrollView({children:draft,animatedOnScroll:e=>tracked.push(e.contentOffset.y),keyboardShouldPersistTaps:'handled',contentContainerStyle:{paddingBottom:16},overScrollMode:'always'},null)
  :exports.ElasticFlatList({data:rows,renderItem,initialNumToRender:12,windowSize:7,contentContainerStyle:{paddingBottom:16}});
 let active=0,failed=0;const manager={activate:()=>active++,fail:()=>failed++};
 const touch=(x,y,n=1)=>({numberOfTouches:n,allTouches:n===1?[{absoluteX:x,absoluteY:y}]:[]});
 return {exports,pan,tree,values,draft,rows,tracked,renderItem,rendered:()=>rendered,manager,touch,scroll,setY:(y,time)=>tree.children[0].children[0].props.onScroll({contentOffset:{y},timestamp:time??(clock+=16)}),active:()=>active,failed:()=>failed,animation:()=>animation,animations:()=>animations,event:(kind,y,time)=>handlers[kind]?.({contentOffset:{y},timestamp:time??(clock+=16)}),finish:()=>{const a=animation;if(a&&!a.finished){a.finished=true;a.callback?.(true);}},blur:()=>unfocus(),focus:()=>{unfocus=focus();}};
}
const f=fixture();assert.equal(f.values[1].value,0);assert.equal(f.animation(),undefined);assert.equal(f.pan.manual,true);assert.equal(f.pan.pointers,1);
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
assert(!source.includes('Keyboard.dismiss'));const focusBody=source.slice(source.indexOf('useFocusEffect(useCallback'),source.indexOf('  const sampleScroll'));assert(!focusBody.includes('withTiming'));assert(focusBody.includes('pull.set(0)')); assert(!source.includes('scale:'));assert(!source.includes('opacity:'));assert(!source.includes('api.'));
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

// Native inertia is armed only by a real drag/release/momentum sequence.
function fling(g,kind='onScroll',time=0){
 g.event('onBeginDrag',500,time);g.event('onScroll',400,time+16);g.event('onEndDrag',400,time+17);g.event('onMomentumBegin',400,time+18);
 g.event('onScroll',40,time+34);g.event(kind,0,time+50);
}
for(const kind of ['scroll','list'])for(const density of [1,2,3.5]){
 const g=fixture(kind,10001,density);fling(g);
 assert(g.values[1].value>0&&g.values[1].value*density<=20);
 assert.equal(g.animations().length,1);assert.equal(g.animation().config.duration,80);assert.equal(g.animation().config.reduceMotion,'system');
 const peak=g.values[1].value;
 g.event('onScroll',0,66);g.event('onScroll',0,82);g.event('onMomentumEnd',0,98);assert.equal(g.animations().length,1);
 g.finish();assert.equal(g.values[1].value,0);assert.equal(g.animations().length,2);assert.equal(g.animation().config.duration,240);assert.equal(g.animation().config.easing,'cubic');
 assert(peak<=g.exports.MAX_PULL_DISTANCE);
 fling(g,'onScroll',200);assert.equal(g.animations().length,3);g.finish();assert.equal(g.values[1].value,0);
}
const clamped=fixture();clamped.event('onBeginDrag',400,0);clamped.event('onEndDrag',400,1);clamped.event('onMomentumBegin',400,2);clamped.setY(1,18);clamped.setY(0,34);assert(clamped.values[1].value>0,'Final-pixel clamping retains the recent approach velocity');
const endOnly=fixture();fling(endOnly,'onMomentumEnd');assert(endOnly.values[1].value>0);endOnly.finish();assert.equal(endOnly.values[1].value,0);
for(const variant of ['programmatic','slow','touching','stale','reverse','oldSample','invalid','alreadyTop']){
 const g=fixture();
 if(variant==='programmatic'){g.event('onMomentumBegin',500,0);g.setY(40,16);g.setY(0,32);}
 else if(variant==='touching'){g.event('onBeginDrag',40,0);g.event('onScroll',0,16);}
 else if(variant==='alreadyTop'){g.event('onBeginDrag',0,0);g.event('onEndDrag',0,1);g.event('onMomentumBegin',0,2);g.setY(0,18);}
 else{
  g.event('onBeginDrag',500,0);g.event('onEndDrag',40,10);g.event('onMomentumBegin',40,variant==='stale'?1000:11);
  if(variant==='slow'){g.setY(8,27);g.setY(6,43);g.setY(4,59);g.setY(2,75);g.setY(0,91);}
  else if(variant==='reverse'){g.setY(80,27);g.setY(0,43);}
  else if(variant==='oldSample')g.setY(0,300);
  else if(variant==='invalid'){g.setY(NaN,27);g.setY(0,43);}
  else g.setY(0,1016);
 }
 assert.equal(g.values[1].value,0,variant);assert.equal(g.animations().length,0,variant);
}
const blurred=fixture();blurred.event('onBeginDrag',400,0);blurred.event('onEndDrag',400,1);blurred.event('onMomentumBegin',400,2);blurred.blur();blurred.focus();blurred.setY(0,18);assert.equal(blurred.animation(),undefined);
fling(blurred,'onScroll',100);assert(blurred.values[1].value>0);blurred.blur();assert.equal(blurred.values[1].value,0);const beforeFocus=blurred.animations().length;blurred.focus();blurred.finish();assert.equal(blurred.animations().length,beforeFocus);
const interrupted=fixture();fling(interrupted);interrupted.pan.down(interrupted.touch(20,20),interrupted.manager);assert.equal(interrupted.values[1].value,0);const interruptedCount=interrupted.animations().length;interrupted.finish();assert.equal(interrupted.animations().length,interruptedCount);
for(const speed of [0,0.1,0.59,NaN,Infinity])assert.equal(f.exports.momentumPullDistance(speed),0);
for(const speed of [0.6,1,3,1000])assert.equal(f.exports.momentumPullDistance(speed),f.exports.pullDistance(12+speed*180));
console.log('PASS: one capped inertia reaction per native fling for ScrollView/FlatList, momentum-end fallback, unchanged 240ms return, slow/programmatic/reversed/stale/invalid arrivals ignored, focus cleanup and touch interruption without queued rebounds.');
