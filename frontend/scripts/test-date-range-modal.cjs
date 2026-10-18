// Exercise the shared picker with synthetic hooks; no API, storage or device writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const cp = require('node:child_process');
const ts = require('typescript');
const { createInstance } = require('i18next');
const file = 'frontend/src/components/date-range-sheet.tsx';
const source = fs.readFileSync(file, 'utf8');
const old = cp.execFileSync('git',['show',`HEAD:${file}`],{encoding:'utf8'});
const declarations = text => {
  const tree=ts.createSourceFile('picker.tsx',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};
  function visit(n){if(ts.isVariableDeclaration(n)&&n.initializer)out[n.name.getText(tree)]=n.initializer;ts.forEachChild(n,visit);}visit(tree);return {tree,out};
};
const before=declarations(old),after=declarations(source);
const initializer=(decl,name)=>{const n=decl.out[name];return ts.isCallExpression(n)&&['useMemo','useCallback'].includes(n.expression.getText(decl.tree))?n.arguments[0].getText(decl.tree):n.getText(decl.tree);};
for(const name of ['cells','onDayPress','dayState','handleApply'])assert.equal(initializer(after,name),initializer(before,name),`${name}: date/selection/Apply rules must remain unchanged`);
for(const start of ['function startOfDay(', 'function endOfDay(', 'function sameDay(']) {
  const end=text=>{const a=text.indexOf(start);return text.slice(a,text.indexOf('\n}',a)+2);};assert.equal(end(source),end(old));
}
assert.equal(source.slice(source.indexOf('const st =')),old.slice(old.indexOf('const st =')),'All dimensions, fonts, colors, spacing and shadows remain byte-identical');
const engine = createInstance();
engine.init({lng:'en-US',fallbackLng:'en-US',resources:{'en-US':{translation:require('../src/i18n/locales/en.json')},es:{translation:require('../src/i18n/locales/es.json')}},initImmediate:false});
const all = tree => !tree || typeof tree !== 'object' ? [] : [tree,...[tree.props?.children].flat(Infinity).flatMap(all)];
const flat = value => Array.isArray(value) ? Object.assign({},...value.map(flat)) : value || {};
const text = tree => typeof tree==='string'||typeof tree==='number'?String(tree):[tree?.props?.children].flat(Infinity).map(n=>n==null?'':text(n)).join('');
function fixture({width=360,height=800,dark=false,insets={top:24,bottom:24,left:0,right:0},language='en-US',sourceText=source,reducedMotion=false}={}) {
  engine.changeLanguage(language);
  const slots=[];let cursor=0;const changes=[];const ref={};
  const useRef=value=>{const i=cursor++;return slots[i]??(slots[i]={current:value});};
  const useState=value=>{const cell=useRef(value);return [cell.current,value=>{cell.current=typeof value==='function'?value(cell.current):value;}];};
  const useMemo=(fn,values)=>{const cell=useRef(null);if(!cell.current||values.some((v,i)=>!Object.is(v,cell.current.values[i]))){cell.current={values,value:fn()};}return cell.current.value;};
  const timings=[],cleanups=[];
  const useEffect=(fn,values)=>useMemo(()=>{const cleanup=fn();if(cleanup)cleanups.push(cleanup);},values);
  const useSharedValue=initial=>{
    const holder=useRef(null);
    if(!holder.current){
      let value=initial,pending;
      holder.current={get value(){return value;},set value(next){
        if(pending&&!pending.settled){pending.settled=true;pending.done?.(false);}
        if(next?.timing){
          const from=value;
          pending={...next,settled:false,step:f=>{value=from+(next.to-from)*f;},finish:()=>{
            if(pending.settled)return;pending.settled=true;value=next.to;next.done?.(true);
          }};
          timings.push(pending);if(reducedMotion)pending.finish();
        }else{value=next;pending=null;}
      },cancel(){if(pending&&!pending.settled){pending.settled=true;pending.done?.(false);}}};
    }
    return holder.current;
  };
  const react={forwardRef:fn=>fn,memo:fn=>fn,useState,useRef,useEffect,useCallback:(fn,values)=>useMemo(()=>fn,values),useMemo,useImperativeHandle:(ref,fn)=>Object.assign(ref,fn())};react.default=react;
  const jsx=(type,props)=>({type,props});
  const mocks={react,'react/jsx-runtime':{jsx,jsxs:jsx},
    'react-native':{Modal:'Modal',ScrollView:'ScrollView',View:'View',StyleSheet:{create:x=>x,absoluteFill:{position:'absolute',top:0,left:0,right:0,bottom:0}},useWindowDimensions:()=>({width,height})},
    '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},'@react-native-vector-icons/ionicons':{default:'Icon'},
    '@/src/i18n':{__esModule:true,default:engine,localeTag:language=>language==='es'?'es-US':'en-US',tr:engine.t.bind(engine),useTranslation:()=>({})},
    'react-native-safe-area-context':{useSafeAreaInsets:()=>insets},
    '@/src/theme':{useTheme:()=>({colors:{surface:dark?'#141210':'#FDF9F4',border:'#777',onSurface:'#111',muted:'#555',surfaceTertiary:'#eee'},scheme:dark?'dark':'light'}),radius:{cardLg:28,pill:999},spacing:{lg:16}},
    '@/src/ui-scale':{us:x=>x,scaleStyles:x=>x},
    'react-native-reanimated':{__esModule:true,default:{View:'AnimatedView'},useSharedValue,useAnimatedStyle:fn=>fn(),
      withTiming:(to,config,done)=>({timing:true,to,config,done}),runOnJS:fn=>fn,cancelAnimation:value=>value.cancel(),
      Easing:{cubic:'cubic',in:value=>'in-'+value,out:value=>'out-'+value},ReduceMotion:{System:'system'}},
  };
  let formatCalls=0;class CountedDate extends Date {toLocaleDateString(...args){formatCalls++;return super.toLocaleDateString(...args);}}
  const context={exports:{},require:name=>{assert(name in mocks,`Unexpected dependency: ${name}`);return mocks[name];},Date:CountedDate,Math};
  vm.runInNewContext(ts.transpileModule(sourceText,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText,context);
  function render(){cursor=0;return context.exports.DateRangeSheet({onApply:range=>changes.push(range),allowClear:true},ref);}
  function find(id){return all(render()).find(node=>node.props?.testID===id);}
  render();return {ref,render,find,changes,insets,width,height,timings,unmount:()=>cleanups.forEach(fn=>fn()),formatCalls:()=>formatCalls};
}
const range = {start:new Date(2024,1,15).setHours(0,0,0,0),end:new Date(2024,1,17).setHours(23,59,59,999)};
let cases=0;
for(const language of ['en-US','es'])for(const dark of [false,true])for(const size of [{width:360,height:800},{width:320,height:480},{width:800,height:360,insets:{top:0,bottom:24,left:24,right:24}}]) {
  const f=fixture({...size,language,dark});assert.equal(f.render().props.visible,false);f.ref.open(range);
  let tree=f.render();
  const baseline=fixture({...size,language,dark,sourceText:old});baseline.ref.open(range);
  const visualTree=node=>JSON.stringify(node,(key,value)=>key==='hardwareAccelerated'?undefined:value);
  assert.equal(visualTree(tree),visualTree(baseline.render()),'Rendered calendar content, controls and visual props must match the original');
  assert.equal(tree.props.hardwareAccelerated,true);assert.equal(tree.type,'Modal');assert.equal(tree.props.visible,true);assert.equal(tree.props.animationType,'none');
  assert(tree.props.transparent&&tree.props.statusBarTranslucent&&tree.props.navigationBarTranslucent);
  const root=f.find('date-modal-root'),card=f.find('date-modal-card'),scroll=f.find('date-range-sheet');
  assert.equal(flat(root.props.style).justifyContent,'center');assert.equal(flat(root.props.style).alignItems,'center');
  assert.equal(flat(card.props.style).width,'92%');assert.equal(flat(card.props.style).maxHeight,f.height-f.insets.top-f.insets.bottom-32);
  // Actual modal layout can differ from window dimensions (system bars/rotation).
  root.props.onLayout({nativeEvent:{layout:{height:f.height-10}}});
  assert.equal(flat(f.find('date-modal-card').props.style).maxHeight,f.height-10-f.insets.top-f.insets.bottom-32);
  assert.equal(flat(scroll.props.style).flexGrow,0);assert.equal(flat(scroll.props.style).flexShrink,1);
  assert.equal(flat(card.props.style).borderTopLeftRadius,28);assert.equal(flat(card.props.style).borderBottomLeftRadius,28);
  assert.equal(flat(card.props.style).shadowOpacity,.18);assert.equal(flat(f.find('date-modal-backdrop').props.style).opacity,.45);
  assert(!card.props.onTouchStart&&!card.props.onPress,'Inside taps have no dismiss handler');
  assert.equal(all(tree).find(n=>n.type==='ScrollView').props.keyboardShouldPersistTaps,'handled');
  assert(text(tree).includes(language==='es'?'Selecciona un período':'Choose a period'));
  // New draft + each non-Apply exit leaves the externally applied filter unchanged.
  for(const dismiss of [()=>f.find('date-modal-backdrop').props.onPress(),()=>f.find('date-sheet-close').props.onPress(),()=>f.render().props.onRequestClose(),()=>f.ref.close()]) {
    f.find('date-day-2024-2-20').props.onPress();dismiss();assert.equal(f.render().props.visible,false);assert.equal(f.changes.length,0);
    f.ref.open(range);assert(text(f.render()).includes(new Date(range.start).toLocaleDateString(language==='es'?'es-US':'en-US',{day:'numeric',month:'long',year:'numeric'})), text(f.render()));
  }
  f.find('date-next-month').props.onPress();assert(f.find('date-day-2024-3-31'));f.find('date-prev-month').props.onPress();assert(f.find('date-day-2024-2-29'));
  f.find('date-day-2024-2-20').props.onPress();f.find('date-day-2024-2-22').props.onPress();f.find('date-apply').props.onPress();
  assert.equal(f.changes.length,1);assert.equal(f.changes[0].start,new Date(2024,1,20).setHours(0,0,0,0));assert.equal(f.changes[0].end,new Date(2024,1,22).setHours(23,59,59,999));assert.equal(f.render().props.visible,false);
  f.ref.open(null);assert.equal(f.find('date-apply').props.disabled,true);assert(!f.find('date-clear'));f.ref.close();f.ref.open(range);f.find('date-clear').props.onPress();assert.equal(f.changes.at(-1),null);
  cases++;
}
assert(!source.includes('BottomSheet')&&!source.includes('st.grip'));
console.log(`PASS: ${cases} language/theme/portrait/landscape configurations; centered safe-area bounds, measured modal height, internal scrolling, unchanged calendar content/logic, outside/X/Android-back dismissal without applying, month navigation, leap day, range Apply and explicit clear.`);
console.log('DEVICE LIMIT: physical Android hit testing, content measurement, clipping and appearance require Samsung Expo Go review.');

// Count real formatting work rather than inferring performance from props alone.
const performanceFixture=fixture();const initialFormats=performanceFixture.formatCalls();
performanceFixture.ref.open(range);performanceFixture.render();
assert(performanceFixture.formatCalls()-initialFormats<=2,'Opening should format only the selected range, not all 19 calendar labels');
const beforeLayout=performanceFixture.formatCalls();
performanceFixture.find('date-modal-root').props.onLayout({nativeEvent:{layout:{height:790}}});performanceFixture.render();
assert.equal(performanceFixture.formatCalls(),beforeLayout,'Modal layout must not repeat locale formatting');
console.log('PASS: formatting-call regression checks for opening and modal layout. No FPS claim.');

const cachedDay=performanceFixture.find('date-day-2024-2-15');
performanceFixture.find('date-modal-root').props.onLayout({nativeEvent:{layout:{height:780}}});
assert.equal(performanceFixture.find('date-day-2024-2-15'),cachedDay,'Layout changes reuse the actual grid subtree');
const beforeClose=performanceFixture.formatCalls();performanceFixture.ref.close();performanceFixture.render();
assert.equal(performanceFixture.formatCalls(),beforeClose,'Closing does not repeat date formatting');
performanceFixture.ref.open(range);performanceFixture.render();const afterOpen=performanceFixture.formatCalls();
for(let i=0;i<10;i++){performanceFixture.ref.open(range);performanceFixture.render();}
assert.equal(performanceFixture.formatCalls(),afterOpen,'Rapid repeated open taps do no extra formatting');
engine.changeLanguage('es');assert(text(performanceFixture.render()).includes('Febrero'),'Visible month labels update with the language');
const originalPerformance=fixture({sourceText:old});const oldInitial=originalPerformance.formatCalls();originalPerformance.ref.open(range);originalPerformance.render();const oldOpen=originalPerformance.formatCalls()-oldInitial;
console.log(`Measured synthetic date-format calls: open ${oldOpen} before / ${afterOpen-beforeClose} after; layout/close 0 after. Grid element identity retained on layout. These are JS-work counts, not device FPS.`);

// Home opts into an anchored transition; callers without an origin stay immediate.
function layoutAnchored(f, rootY=0) {
  const root=f.find('date-modal-root'),card=f.find('date-modal-card');
  const bounds={x:f.width*.04,y:70,width:f.width*.92,height:Math.min(600,f.height-100)};
  root.props.ref.current={measureInWindow:cb=>cb(0,rootY,f.width,f.height)};
  root.props.onLayout({nativeEvent:{layout:{height:f.height}}});
  card.props.onLayout({nativeEvent:{layout:bounds}});
  return bounds;
}
for(const size of [{width:320,height:480},{width:360,height:800},{width:800,height:360}]) {
  const f=fixture(size),origin={x:45,y:size.height-60};
  f.ref.open(range,origin);
  assert.equal(flat(f.find('date-modal-card').props.style).opacity,0,'No full-size first-frame flash');
  const bounds=layoutAnchored(f,24);
  assert.equal(f.timings.length,0,'Wait for native Modal onShow and valid layout');
  f.render().props.onShow();assert.equal(f.timings.length,1);
  const enter=f.timings[0];assert.equal(enter.config.duration,280);assert.equal(enter.config.easing,'out-cubic');assert.equal(enter.config.reduceMotion,'system');
  let style=flat(f.find('date-modal-card').props.style);
  assert(Math.abs(bounds.x+bounds.width/2+style.transform[0].translateX-origin.x)<1e-8);
  assert(Math.abs(24+bounds.y+bounds.height/2+style.transform[1].translateY-origin.y)<1e-8);
  assert.equal(style.transform[2].scale,.08);
  for(let i=0;i<8;i++)f.ref.open(null,{x:200,y:200});
  assert.equal(f.timings.length,1,'Rapid open never restarts or resets selection');
  enter.finish();style=flat(f.find('date-modal-card').props.style);
  assert.equal(style.opacity,1);assert.equal(style.transform[2].scale,1);
  assert.equal(Math.abs(style.transform[0].translateX),0);assert.equal(Math.abs(style.transform[1].translateY),0);
  const cached=f.find('date-day-2024-2-20');
  f.find('date-day-2024-2-20').props.onPress();f.find('date-day-2024-2-22').props.onPress();
  f.find('date-apply').props.onPress();f.find('date-apply').props.onPress();
  assert.equal(f.changes.length,1);assert.equal(f.changes[0].start,new Date(2024,1,20).setHours(0,0,0,0));
  assert.equal(f.changes[0].end,new Date(2024,1,22).setHours(23,59,59,999));
  assert.equal(f.render().props.visible,true,'Keep native modal mounted throughout exit');
  const exit=f.timings.at(-1);assert.equal(exit.config.duration,220);assert.equal(exit.config.easing,'in-cubic');
  assert.equal(f.find('date-modal-card').props.onStartShouldSetResponderCapture(),true,'Shield closing content from a second gesture');
  f.ref.close();f.ref.open(null,origin);assert.equal(f.timings.length,2);
  exit.step(.5);style=flat(f.find('date-modal-card').props.style);assert(style.opacity>0&&style.opacity<1);assert(style.transform[2].scale>0&&style.transform[2].scale<1);
  exit.finish();assert.equal(f.render().props.visible,false);
  f.ref.open(range,origin);exit.done(true);assert.equal(f.render().props.visible,true,'Stale close cannot hide a new presentation');
  f.ref.close();assert.equal(f.render().props.visible,false,'Close before measurement does not wait for an absent animation');
  assert(cached);
}
for(const exitKind of ['outside','close','back','imperative']) {
  const f=fixture();f.ref.open(range,{x:40,y:500});layoutAnchored(f);f.render().props.onShow();f.timings[0].finish();
  if(exitKind==='outside')f.find('date-modal-backdrop').props.onPress();
  else if(exitKind==='close')f.find('date-sheet-close').props.onPress();
  else if(exitKind==='back')f.render().props.onRequestClose();else f.ref.close();
  assert.equal(f.changes.length,0);assert.equal(f.render().props.visible,true);f.timings.at(-1).finish();assert.equal(f.render().props.visible,false);
}
const reduced=fixture({reducedMotion:true});reduced.ref.open(range,{x:40,y:500});layoutAnchored(reduced);reduced.render().props.onShow();
assert.equal(flat(reduced.find('date-modal-card').props.style).opacity,1);reduced.ref.close();assert.equal(reduced.render().props.visible,false);
const invalid=fixture();invalid.ref.open(range,{x:NaN,y:10});assert.equal(invalid.render().props.onShow,undefined);invalid.ref.close();assert.equal(invalid.render().props.visible,false);
const delayed=fixture();delayed.ref.open(range,{x:40,y:500});let lateMeasurement;
let root=delayed.find('date-modal-root');root.props.ref.current={measureInWindow:cb=>{lateMeasurement=cb;}};
root.props.onLayout({nativeEvent:{layout:{height:800}}});delayed.ref.close();delayed.ref.open(range,{x:90,y:600});
lateMeasurement(0,0,360,800);assert.equal(delayed.timings.length,0,'Ignore measurements from an old presentation');
layoutAnchored(delayed);delayed.render().props.onShow();const pendingEnter=delayed.timings[0];delayed.unmount();assert(pendingEnter.settled,'Cancel UI animation on unmount');
console.log('PASS: Home anchored geometry, 280/220ms timing, hidden layout preparation, repeated taps, all dismissal paths, exact date Apply, stale callbacks, Reduced Motion and unmount cleanup. Physical Samsung animation still requires visual review.');
