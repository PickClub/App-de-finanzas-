// Real summary components and worklet styles under synthetic hooks; no financial writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const cp = require('node:child_process');
const vm = require('node:vm');
const ts = require('typescript');
const {createInstance} = require('i18next');
const React = require('react');
const {Trans} = require('react-i18next');
const {renderToStaticMarkup} = require('react-dom/server');
const file='frontend/app/debts/index.tsx', source=fs.readFileSync(file,'utf8');
const old=cp.execFileSync('git',['show',`HEAD:${file}`],{encoding:'utf8'});
const between=(s,a,b)=>s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)));
// Exclude only the separately tested visual options button from the list-preservation check.
const listSource=source
 .replace(/                <Pressable testID=\{`debt-options-\$\{d.id\}`\}[\s\S]*?<\/Pressable>\n\n/,'')
 .replace('                  <View style={styles.debtProgress}>\n','').replace('                  </ProgressRing>\n                  </View>','                  </ProgressRing>')
 .replace('      {actionDebt && <DebtActions key={actionDebt.id} debt={actionDebt} onClose={() => setActionDebt(null)} />}\n','');
assert.equal(between(source,'function buildStat','export default'),between(old,'function buildStat','export default'),'Existing amount arithmetic/percentage rules preserved');
assert.equal(between(listSource,'        {/* Filters','function FilterPill'),between(old,'        {/* Filters','function FilterPill'),'Filters, individual cards, add action and order preserved');
assert.equal(between(source,'function FilterPill','function MetricRow'),between(old,'function FilterPill','function MetricRow'));
assert(source.includes('<MoneyFlowHeaderActions onBack={() => router.back()} backTestID="debts-back" beforeActions='),'Shared Back controls retain the existing list route');
assert.equal(between(source,'        <View style={styles.summarySpacing}>','        {/* Filters'),between(old,'        <View style={styles.summarySpacing}>','        {/* Filters'),'Summary card and its surrounding spacing remain unchanged');
const engine=createInstance();engine.init({lng:'en-US',fallbackLng:'en-US',initImmediate:false,resources:{'en-US':{translation:require('../src/i18n/locales/en.json')},es:{translation:require('../src/i18n/locales/es.json')}}});
let slots=[],index=0,cleanups=[],pending=[],reduced=false,dark=false,stateWrites=0,viewportWidth=460;
const useRef=value=>{const i=index++;return slots[i]??(slots[i]={current:value});};
const useState=value=>{const r=useRef(value);return [r.current,v=>{stateWrites++;r.current=typeof v==='function'?v(r.current):v;}];};
const react={memo:fn=>fn,useRef,useState,useCallback:fn=>fn,useMemo:fn=>fn(),useEffect:(fn,deps)=>{const r=useRef(null);if(!r.current){r.current=deps;cleanups.push(fn());}}};react.default=react;
const jsx=(type,props)=>({type,props});
const reanimated={default:{View:'AnimatedFace'},useReducedMotion:()=>reduced,ReduceMotion:{System:'system'},Easing:{cubic:'cubic',inOut:x=>['inOut',x]},
 useSharedValue:value=>{const r=useRef(null);return r.current??(r.current={value,set(next){if(typeof next==='object'){pending.push({cell:this,from:this.value,...next});}else this.value=next;}});},
 useAnimatedStyle:fn=>fn(),runOnJS:fn=>fn,withTiming:(to,options,done)=>({to,options,done}),cancelAnimation:()=>{},
};
const mocks={react,'react/jsx-runtime':{jsx,jsxs:jsx,Fragment:'Fragment'},'react-i18next':{Trans:'Trans'},
 '@/src/i18n':{tr:engine.t.bind(engine),useTranslation:()=>({})},
 '@/src/components/elastic-scroll-view':{ElasticScrollView:'Elastic'},'@/src/native-scroll':{NATIVE_VERTICAL_SCROLL:{}},
 'react-native':{View:'View',StyleSheet:{absoluteFill:{}},Animated:{},Easing:{},Platform:{OS:'android'},useWindowDimensions:()=>({width:viewportWidth,height:900})},
 'react-native-reanimated':reanimated,'@/src/components/pressable':{Pressable:'Pressable'},'@/src/components/typography':{Text:'Text'},
 '@react-native-vector-icons/ionicons':{default:'Icon'},'expo-linear-gradient':{LinearGradient:'Gradient'},'react-native-safe-area-context':{},'expo-router':{},'@tanstack/react-query':{},'@/src/api':{},'@/src/components/debt-actions':{DebtActions:'DebtActions'},
 '@/src/theme':{useTheme:()=>({scheme:dark?'dark':'light'}),makeStyles:factory=>()=>factory({},dark?'dark':'light'),radius:{cardLg:28,pill:999},spacing:{lg:16,md:12,sm:8}},
 '@/src/format':{formatCurrencyInt:value=>new Intl.NumberFormat(engine.language==='es'?'es-US':'en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(value)},
 '@/src/components/ProgressRing':{ProgressRing:'Ring'},'@/src/components/ui':{IconTile:'IconTile'},'@/src/components/header-actions':{MoneyFlowHeaderActions:'MoneyFlowHeaderActions'},'@/src/lock':{},'@/src/ui-scale':{us:x=>x,ufs:x=>x}};
const context={exports:{},Math,require:name=>{assert(name in mocks,name);return mocks[name];}};
vm.runInNewContext(ts.transpileModule(source+'\nexport {buildStat, DebtSummaryCard, SummaryFace, palette};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText,context);
const {buildStat,DebtSummaryCard,SummaryFace}=context.exports;
const all=t=>!t||typeof t!=='object'?[]:[t,...[t.props?.children].flat(Infinity).flatMap(all)];
const flatten=x=>Array.isArray(x)?Object.assign({},...x.map(flatten)):x||{};
function render(front,back){index=0;return DebtSummaryCard({front,back,entryT:1});}
function sample(fraction){for(const a of pending)a.cell.value=a.from+(a.to-a.from)*fraction;}
function finish(){sample(1);const work=pending;pending=[];work.forEach(a=>a.done(true));}
function reset(){slots=[];index=0;pending=[];cleanups=[];stateWrites=0;}
const row=(direction,original,paid=0)=>Object.freeze({id:'synthetic',name:'User-authored Español',direction,original_amount:original,remaining_amount:original-paid,total_paid:paid});
const example=Object.freeze([row('i_owe',500),row('i_owe',4500),row('they_owe',1500)]);
const front=buildStat(example.filter(d=>d.direction==='i_owe')),back=buildStat(example.filter(d=>d.direction==='they_owe'));
assert.equal(front.original,5000);assert.equal(front.remaining,5000);assert.equal(front.count,2);assert.equal(back.original,1500);assert.equal(back.count,1);
assert.equal(buildStat([]).pct,0);assert.equal(buildStat([row('i_owe',0)]).pct,0);
const paid=buildStat([row('i_owe',500,100),row('i_owe',4500,500)]),collected=buildStat([row('they_owe',1500,300)]);
assert.equal(paid.paid,600);assert.equal(paid.remaining,4400);assert.equal(paid.pct,.12);assert.equal(collected.paid,300);assert.equal(collected.remaining,1200);assert.equal(collected.pct,.2);
assert.equal(buildStat([row('i_owe',100,100)]).pct,1);
assert(Math.abs(buildStat([row('i_owe',10.25,2.15),row('i_owe',20.75,3.85)]).paid-6)<1e-12);
for(const language of ['en-US','es'])for(dark of [false,true]) {
 engine.changeLanguage(language);reset();reduced=false;
 let tree=render(paid,collected);assert.equal(tree.props.accessibilityRole,'button');assert.equal(tree.props.accessibilityLabel,engine.t('debts.flipToReceivables'));
 for(const [isBack,stat] of [[false,paid],[true,collected]]) {
  const face=SummaryFace({summary:stat,back:isBack,entryT:1});const nodes=all(face);
  const metrics=nodes.filter(n=>n.type?.name==='MetricRow');assert.equal(metrics.length,4);
  assert.equal(metrics[0].props.label,engine.t(isBack?'debts.peopleOweYou':'ui.total_debt'));
  assert.equal(metrics[0].props.value,String(stat.count));assert.equal(metrics[3].props.label,engine.t(isBack?'debts.collected':'ui.paid'));
  assert.equal(nodes.find(n=>n.type==='Ring').props.progress,stat.pct);
  assert.equal(nodes.find(n=>n.type==='Ring').props.color,context.exports.palette(dark?'dark':'light').ring);
  assert.equal(nodes.find(n=>n.type==='Text'&&n.props.children===engine.t('debts.tapToFlip')).props.style.fontSize,9);
  assert.equal(metrics[1].props.valueColor,context.exports.palette(dark?'dark':'light').red);
  assert.equal(metrics[3].props.valueColor,context.exports.palette(dark?'dark':'light').incomeGreen);
  const caption=renderToStaticMarkup(React.createElement(Trans,{i18n:engine,i18nKey:'debts.summaryProgress',values:{paid:'$600',total:'$5,000'},components:{paid:React.createElement('strong')}}));
  assert.equal(caption,language==='es'?'<strong>$600</strong> de $5,000':'<strong>$600</strong> of $5,000');
 }
 for(const reverse of [false,true]) {
  tree.props.onPress();const animation=pending[0];assert.equal(pending.length,1);assert.equal(animation.options.duration,440);assert.deepEqual(animation.options.easing,['inOut','cubic']);assert.equal(animation.options.reduceMotion,'system');
  for(let n=0;n<10;n++)tree.props.onPress();assert.equal(pending.length,1,'Rapid taps cannot enqueue flips');
  const before=stateWrites;
  for(const fraction of [0,.25,.5,.75,.99]) {
   sample(fraction);const faces=render(paid,collected).props.children;
   const f=flatten(faces[0].props.style),b=flatten(faces[1].props.style);
   assert.equal(f.backfaceVisibility,'hidden');assert.equal(b.backfaceVisibility,'hidden');assert.equal(b.position,'absolute');
   assert.equal(faces[0].props.pointerEvents,'none');assert.equal(faces[1].props.pointerEvents,'none');
   assert.equal(f.opacity+b.opacity,1);assert.equal(f.transform[0].perspective,1000);
   assert(!f.transform.some(t=>'scaleX'in t||'translateX'in t));
   assert.equal(stateWrites,before,'No React state writes during frames');
  }
  finish();tree=render(paid,collected);assert.equal(stateWrites,before+1);
  const faces=tree.props.children;assert.equal(flatten(faces[reverse?0:1].props.style).transform[1].rotateY,'0deg','Visible face is never mirrored at rest');
 }
 reduced=true;reset();tree=render(paid,collected);tree.props.onPress();assert.equal(pending.length,0);tree=render(paid,collected);assert.equal(tree.props.accessibilityLabel,engine.t('debts.flipToDebts'));
 // Unmount while a flip is pending must not update React state later.
 reduced=false;reset();tree=render(paid,collected);tree.props.onPress();cleanups.filter(Boolean).forEach(fn=>fn());const before=stateWrites;finish();assert.equal(stateWrites,before);
}
for(viewportWidth of [320,360,393,460,800]) {
 const scale=Math.min(1.2,Math.max(1,(viewportWidth-64-2)/300));
 for(const back of [false,true]) {
  const nodes=all(SummaryFace({summary:paid,back,entryT:1}));
  const ring=nodes.find(n=>n.type==='Ring');assert.equal(ring.props.size,116*scale);assert.equal(ring.props.stroke,11*scale);
  assert(ring.props.size<viewportWidth-64-2);assert(scale>=1&&scale<=1.2);
  const metrics=nodes.filter(n=>n.type?.name==='MetricRow');assert(metrics.every(n=>n.props.scale===scale));
  const metric=metrics[0].type(metrics[0].props);
  assert.equal(flatten(metric.props.style).paddingVertical,7*scale);
 }
}
assert(!source.includes('onCardLayout')&&!source.includes('cardScaleX')&&!source.includes('setLockH'));
console.log('PASS: independent directional totals/payments/counts/percentages, zero and decimal amounts; original arithmetic, summary card, filters and list unchanged; English/Spanish light/dark faces, interpolated captions, four metrics and small hint.');
console.log('PASS: real 3D worklet transforms both directions, midpoint face gating, no mirrored resting face, fixed overlay bounds/no layout measurement, 440ms cubic inOut, rapid-tap exclusion, no per-frame React writes, Reduce Motion and unmount cleanup.');
console.log('LIMIT: Samsung frame rate, GPU compositing, text fitting and touch/scroll behavior require Expo Go review.');
