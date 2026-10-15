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
const content = text => text.slice(text.indexOf('      {/* Header */}'), text.indexOf('    </BottomSheetView>') < 0 ? text.indexOf('          </ScrollView>') : text.indexOf('    </BottomSheetView>'));
assert.equal(content(source),content(old),'Calendar JSX, controls, labels and internal styles must remain unchanged');
for(const start of ['function monthNames()', 'function weekdayNames()', 'function startOfDay(', 'function endOfDay(', 'function sameDay(', 'function longEs(']) {
  const end=text=>{const a=text.indexOf(start);return text.slice(a,text.indexOf('\n}',a)+2);};
  assert.equal(end(source),end(old));
}
const calendarLogic = text => text.slice(text.indexOf('  const cells ='), text.indexOf('\n  return (',text.indexOf('  const cells =')));
assert.equal(calendarLogic(source),calendarLogic(old),'Selection, range classification, validation and Apply logic unchanged');
const engine = createInstance();
engine.init({lng:'en-US',fallbackLng:'en-US',resources:{'en-US':{translation:require('../src/i18n/locales/en.json')},es:{translation:require('../src/i18n/locales/es.json')}},initImmediate:false});
const all = tree => !tree || typeof tree !== 'object' ? [] : [tree,...[tree.props?.children].flat(Infinity).flatMap(all)];
const flat = value => Array.isArray(value) ? Object.assign({},...value.map(flat)) : value || {};
const text = tree => typeof tree==='string'||typeof tree==='number'?String(tree):[tree?.props?.children].flat(Infinity).map(n=>n==null?'':text(n)).join('');
function fixture({width=360,height=800,dark=false,insets={top:24,bottom:24,left:0,right:0},language='en-US'}={}) {
  engine.changeLanguage(language);
  const slots=[];let cursor=0;const changes=[];const ref={};
  const useRef=value=>{const i=cursor++;return slots[i]??(slots[i]={current:value});};
  const useState=value=>{const cell=useRef(value);return [cell.current,value=>{cell.current=typeof value==='function'?value(cell.current):value;}];};
  const react={forwardRef:fn=>fn,memo:fn=>fn,useState,useRef,useCallback:fn=>fn,useMemo:fn=>fn(),useImperativeHandle:(ref,fn)=>Object.assign(ref,fn())};react.default=react;
  const jsx=(type,props)=>({type,props});
  const mocks={react,'react/jsx-runtime':{jsx,jsxs:jsx},
    'react-native':{Modal:'Modal',ScrollView:'ScrollView',View:'View',StyleSheet:{create:x=>x,absoluteFill:{position:'absolute',top:0,left:0,right:0,bottom:0}},useWindowDimensions:()=>({width,height})},
    '@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},'@react-native-vector-icons/ionicons':{default:'Icon'},
    '@/src/i18n':{__esModule:true,default:engine,localeTag:language=>language==='es'?'es-US':'en-US',tr:engine.t.bind(engine),useTranslation:()=>({})},
    'react-native-safe-area-context':{useSafeAreaInsets:()=>insets},
    '@/src/theme':{useTheme:()=>({colors:{surface:dark?'#141210':'#FDF9F4',border:'#777',onSurface:'#111',muted:'#555',surfaceTertiary:'#eee'},scheme:dark?'dark':'light'}),radius:{cardLg:28,pill:999},spacing:{lg:16}},
    '@/src/ui-scale':{us:x=>x,scaleStyles:x=>x},
  };
  const context={exports:{},require:name=>{assert(name in mocks,`Unexpected dependency: ${name}`);return mocks[name];},Date,Math};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText,context);
  function render(){cursor=0;return context.exports.DateRangeSheet({onApply:range=>changes.push(range),allowClear:true},ref);}
  function find(id){return all(render()).find(node=>node.props?.testID===id);}
  render();return {ref,render,find,changes,insets,width,height};
}
const range = {start:new Date(2024,1,15).setHours(0,0,0,0),end:new Date(2024,1,17).setHours(23,59,59,999)};
let cases=0;
for(const language of ['en-US','es'])for(const dark of [false,true])for(const size of [{width:360,height:800},{width:320,height:480},{width:800,height:360,insets:{top:0,bottom:24,left:24,right:24}}]) {
  const f=fixture({...size,language,dark});assert.equal(f.render().props.visible,false);f.ref.open(range);
  let tree=f.render();assert.equal(tree.type,'Modal');assert.equal(tree.props.visible,true);assert.equal(tree.props.animationType,'none');
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
