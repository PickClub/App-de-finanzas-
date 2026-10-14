const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const file='frontend/src/components/home-amount.tsx',source=fs.readFileSync(file,'utf8');
function fixture(){
 let index=0,context={active:true,entry:1,reduced:false},focus,reduceListener,removed=0;
 let renderedTree,reaction,previousVisibility=null;const layouts=[{value:null},{value:null},{value:null}],scroll={value:0},viewport={value:400};
 let pendingEffects=[],nextId=0;const slots=[],frames=new Map();
 const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
 const react={createElement:(type,props,...children)=>({type,props,children}),createContext:()=>({Provider:'Provider'}),
  useContext:()=>context,useMemo:(f)=>f(),useCallback:f=>f,
  useRef:v=>{const i=index++;return slots[i]??(slots[i]={current:v});},
  useState:v=>{const i=index++;if(!(i in slots))slots[i]=v;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},
  useEffect:(fn,deps)=>{const i=index++,old=slots[i];if(!old||!equal(old.deps,deps)){old?.clean?.();slots[i]={deps};pendingEffects.push(()=>slots[i].clean=fn());}}
 };react.default=react;
 const mocks={react,'react-native':{Text:'NativeText',AccessibilityInfo:{isReduceMotionEnabled:async()=>false,addEventListener:(event,fn)=>{assert.equal(event,'reduceMotionChanged');reduceListener=fn;return {remove:()=>removed++};}}},'expo-router':{useFocusEffect:f=>focus=f},'react-native-reanimated':{__esModule:true,default:{Text:'NativeText'},useAnimatedRef:()=>react.useRef(null),useSharedValue:v=>react.useRef({value:v}).current,useAnimatedReaction:(prepare,respond)=>reaction={prepare,respond},measure:()=>{throw Error('Native measurement must not be queried');},runOnJS:f=>f}};
 const exports={};vm.runInNewContext(ts.transpileModule(source,{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText,{exports,require:n=>mocks[n],requestAnimationFrame:fn=>{frames.set(++nextId,fn);return nextId;},cancelAnimationFrame:id=>frames.delete(id)});
 function render(text,ready=true,tracked=false){index=0;pendingEffects=[];const tree=exports.HomeAmount({children:text,ready,...(tracked?{layouts,scrollY:scroll,viewportH:viewport}:{})});pendingEffects.forEach(f=>f());renderedTree=tree;return tree.children[0];}
 return {exports,render,tree:()=>renderedTree,scrollTo:y=>{scroll.value=y;const next=reaction.prepare();reaction.respond(next,previousVisibility);previousVisibility=next;},observe:(top,height=20)=>{layouts[0].value={y:5,height:40};layouts[1].value={y:7,height:40};layouts[2].value={y:top-12,height};const next=reaction.prepare();reaction.respond(next,previousVisibility);previousVisibility=next;},setContext:c=>context={...context,...c},advance:t=>{const work=[...frames.values()];frames.clear();work.forEach(f=>f(t));},pending:()=>frames.size,
  scope:()=>{index=0;pendingEffects=[];const tree=exports.HomeAmountScope({children:'Home'});pendingEffects.forEach(f=>f());return tree.props.value;},focus:()=>focus(),reduce:v=>reduceListener(v),removed:()=>removed,dispose:()=>slots.forEach(s=>s?.clean?.())};
}
for(const [final,start] of [['$1,000','$750'],['$2,000','$1,500'],['$5,000','$3,750'],['$2,679','$2,009'],['$14,545','$10,909'],['$451','$338'],['-$2,504','-$1,878'],['-$451','-$338'],['$0','$0'],['$123,456,789,012,345,678','$92,592,591,759,259,259'],['€1,234','€926']]){
 const f=fixture();assert.equal(f.exports.amountFrame(final,0),start);assert.equal(f.exports.amountFrame(final,1),final);
 for(const p of [0,.1,.5,.9,1]){const result=f.exports.amountFrame(final,p);assert.equal(result.startsWith('-'),final.startsWith('-'));assert(result.includes(final.includes('€')?'€':'$'));}
 assert.equal(f.render(final),start);f.advance(0);f.advance(325);f.render(final);f.advance(650);assert.equal(f.render(final),final);assert.equal(f.pending(),0);f.dispose();
}
console.log('PASS: positive/negative, below/above 1000, zero tails and huge exact strings; 75% start, sign/separators and final text preserved; 650ms completion.');
const formatter={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/format.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,{exports:formatter,require:()=>({default:{language:'en'},localeTag:()=> 'en-US'})});
for(const value of [2679,14545,451,-2504,2000,0,451.5,-451.5,Number.MAX_SAFE_INTEGER,1e22]){
 const final=formatter.formatCurrencyInt(value),g=fixture();assert.equal(g.exports.amountFrame(final,1),final);g.dispose();
}
console.log('PASS: final strings exactly match the unchanged canonical formatter, including existing rounding and large numbers.');
for(const final of ['$1,000','-$1,000','$2,679','$5,000','$123,456,789,012,345,678']){
 const g=fixture();let previous=0n;
 for(const progress of [0,.1,.25,.5,.75,.9,1]){
  const value=BigInt(g.exports.amountFrame(final,progress).replace(/[^0-9]/g,''));assert(value>=previous);previous=value;
 }
 g.dispose();
}
const layout=fixture(),rendered=layout.render('$1,000');assert.equal(rendered,'$750');const reserved=layout.tree().children[1];assert.equal(reserved.props.style.color,'transparent');assert.equal(reserved.props.accessible,false);assert.equal(reserved.children[0],'0,');layout.dispose();
console.log('PASS: full-balance monotonic 75%-100% interpolation, negative signs, and reserved width across thousand boundaries.');


const f=fixture();assert.equal(f.render('…',false),'…');assert.equal(f.pending(),0);assert.equal(f.render('$2,679'),'$2,009');
f.advance(0);f.advance(325);assert.equal(f.render('$2,679'),'$2,512');assert.equal(f.pending(),1);
assert.equal(f.render('$2,679'),'$2,512');assert.equal(f.pending(),1);
assert.equal(f.render('$2,680'),'$2,680');assert.equal(f.pending(),0); // current data replaces stale animation, never replays this visit
f.setContext({active:false});f.render('$2,680');assert.equal(f.pending(),0);
f.setContext({active:true,entry:2});assert.equal(f.render('$2,680'),'$2,010');assert.equal(f.pending(),1);
f.setContext({reduced:true});assert.equal(f.render('$2,680'),'$2,680');assert.equal(f.pending(),0);
f.setContext({reduced:false});assert.equal(f.render('$2,680'),'$2,680');assert.equal(f.pending(),0);
f.setContext({entry:3});f.render('$2,680');assert.equal(f.pending(),1);assert.equal(f.render('••••'),'••••');assert.equal(f.pending(),0);f.dispose();
console.log('PASS: delayed valid data, repeated responses/renders, fresh data, blur/reentry, Reduce Motion and hidden amounts cancel correctly without restart.');
const visible=fixture();
assert.equal(visible.render('$2,679',true,true),'$2,679');assert.equal(visible.pending(),0);
visible.observe(20);assert.equal(visible.render('$2,679',true,true),'$2,009');visible.advance(0);visible.advance(650);assert.equal(visible.render('$2,679',true,true),'$2,679');
for(const top of [30,25,40]){visible.observe(top);assert.equal(visible.render('$2,679',true,true),'$2,679');assert.equal(visible.pending(),0);}
visible.setContext({active:false});assert.equal(visible.render('$2,679',true,true),'$2,679');visible.setContext({active:true,entry:2});assert.equal(visible.render('$2,679',true,true),'$2,009');visible.advance(0);visible.advance(650);assert.equal(visible.render('$2,679',true,true),'$2,679');visible.observe(40);assert.equal(visible.pending(),0);
visible.observe(-30);visible.render('$2,679',true,true);assert.equal(visible.pending(),0);
visible.observe(20);assert.equal(visible.render('$2,679',true,true),'$2,009');assert.equal(visible.pending(),1);
visible.observe(401);assert.equal(visible.render('$2,679',true,true),'$2,679');assert.equal(visible.pending(),0);
visible.observe(390);assert.equal(visible.render('$2,679',true,true),'$2,009');visible.dispose();assert.equal(visible.pending(),0);
for(const [top,height,expected] of [[-20,20,false],[-19,20,true],[399,20,true],[400,20,false],[20,0,false]])assert.equal(visible.exports.amountVisible(top,height,0,400),expected);
console.log('PASS: measured top/bottom viewport exits, reentry replay, no repeated count while visible, offscreen cancellation and cleanup.');
const scrolling=fixture();scrolling.render('$2,679',true,true);scrolling.observe(200);assert.equal(scrolling.render('$2,679',true,true),'$2,009');scrolling.advance(0);scrolling.advance(650);scrolling.render('$2,679',true,true);
scrolling.scrollTo(300);assert.equal(scrolling.render('$2,679',true,true),'$2,679');assert.equal(scrolling.pending(),0);
scrolling.scrollTo(0);assert.equal(scrolling.render('$2,679',true,true),'$2,009');assert.equal(scrolling.pending(),1);
scrolling.observe(NaN);assert.equal(scrolling.render('$2,679',true,true),'$2,679');assert.equal(scrolling.pending(),0);
scrolling.setContext({active:false});scrolling.observe(200);assert.equal(scrolling.render('$2,679',true,true),'$2,679');assert.equal(scrolling.pending(),0);scrolling.dispose();
console.log('PASS: normal scrolling uses stored layouts, replays on upward return, rejects invalid updates and stops while Home is inactive.');

const invalid=fixture();assert.equal(invalid.render('$0',false),'$0');assert.equal(invalid.pending(),0);assert.equal(invalid.render('$451',true),'$338');invalid.dispose();
(async()=>{
 const s=fixture();assert.equal(s.scope().active,false);await Promise.resolve();const blur=s.focus();let visit=s.scope();assert.equal(visit.active,true);assert.equal(visit.entry,1);assert.equal(visit.reduced,false);
 blur();assert.equal(s.scope().active,false);s.focus();assert.equal(s.scope().entry,2);s.reduce(true);assert.equal(s.scope().reduced,true);s.dispose();assert.equal(s.removed(),1);
 console.log('PASS: single focus/accessibility owner, new visit identity, listener cleanup; no full Home renders on animation frames.');
 const home=fs.readFileSync('frontend/app/(tabs)/index.tsx','utf8');assert.equal((home.match(/<HomeAmount(?:\s|>)/g)||[]).length,2);assert.equal((home.match(/<HomeAmountScope>/g)||[]).length,1);
 const start=home.indexOf('        {/* Balance del mes (net'),end=home.indexOf('\n      </View>',start),card=home.slice(start,end);
 for(const color of ['#7C3AED','#EDE9FE','#A78BFA'])assert(card.includes(color));assert(card.includes('money(monthNet)'));assert(!card.includes('monthNet >'));
 assert(home.includes('color: colors.incomeGreen'));assert(home.includes('lighten(colors.expenseRed, 0.16)'));
 assert(!/\bmeasure\s*\(/.test(source));assert(!source.includes('useAnimatedRef'));
 for(const value of [NaN,Infinity,-Infinity]){assert.equal(s.exports.validAmountLayout({y:value,height:20}),null);assert.equal(s.exports.validAmountLayout({y:0,height:value}),null);assert.equal(s.exports.amountVisible(value,20,0,400),false);}
 assert.equal(s.exports.validAmountLayout({y:0,height:0}),null);
 console.log('PASS: no native measure/ref polling; missing/zero/nonfinite layouts rejected, valid parent-relative layout chain drives visibility.');
 assert(!source.includes('setInterval'));assert(!source.includes('withSpring'));assert(!source.includes('api.'));
 console.log('PASS: only the two requested balance locations, purple net identity in either sign, green/red unchanged; no financial calls or spring.');
 console.log('DEVICE LIMIT: Samsung visual smoothness, font fitting and touch behavior remain pending review.');
})().catch(e=>{console.error(e);process.exitCode=1;});
