const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// Actual UI + isolated animation lifecycle. No servers or financial writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),cp=require('node:child_process'),ts=require('typescript');
const home=require('./test-summary-totals.cjs'),direct=require('./test-transaction-direct-read.cjs');
const form=fs.readFileSync('frontend/app/transactions/new.tsx','utf8');
const ast=ts.createSourceFile('form.tsx',form,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
const cursor=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name.text==='AmountCursor').getText(ast);
let effect,clean,tick,visible=true,stops=0;
const ctx={Text:'Text',useState:()=>[visible,fn=>{visible=fn(visible);}],useEffect:f=>effect=f,
 setInterval:(fn,ms)=>{assert.equal(ms,500);tick=fn;return 123;},clearInterval:id=>{assert.equal(id,123);stops++;},
 React:{createElement:(type,props,...children)=>({type,props,children})}};
vm.createContext(localeGlobals(ctx));vm.runInContext(ts.transpileModule(cursor+'\nglobalThis.renderCursor=()=>AmountCursor({color:"#126046"});',{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText,ctx);
let result=ctx.renderCursor();clean=effect();assert.equal(result.props.style.color,'#126046');
tick();result=ctx.renderCursor();assert.equal(result.props.style.color,'transparent');
tick();result=ctx.renderCursor();assert.equal(result.props.style.color,'#126046');
assert.equal(result.children[0],'│');assert.equal(result.props.accessible,false);clean();assert.equal(stops,1);
assert(!cursor.includes('Keyboard'));assert(!form.includes('autoFocus'));
console.log('PASS: visible/transparent/visible blink every 500 ms, child-only state and timer cleanup.');
(async()=>{
 for(const type of ['expense','income','transfer']){
  const f=direct.fixture('form',{type});let tree=f.render(),display=direct.find(tree,'amount-display');
  const hasCursor=node=>node.children.flat(Infinity).some(n=>n?.type?.name==='AmountCursor');
  assert(hasCursor(display));
  assert(!display.children.flat(Infinity).some(n=>n?.type==='TextInput'));
  direct.find(tree,'calc-0').props.onPress();tree=f.render();display=direct.find(tree,'amount-display');assert(!hasCursor(display));
  direct.find(tree,'calc-backspace').props.onPress();tree=f.render();assert(!hasCursor(direct.find(tree,'amount-display')));
 }
 console.log('PASS: initial cursor in expense/income/transfer disappears on first zero and stays hidden after backspace; no keyboard input.');
 for(const count of [1,5,6]){
  const accounts=Array.from({length:count},(_,i)=>({id:String(i),name:'Synthetic '+i,current_balance:100,color:'#126046',icon:'wallet'}));
  const f=home.fixture(async()=>home.positive,[],accounts);f.render();let tree=await f.settle();
  const check=expected=>{
    const actual=home.findAll(tree,n=>n.props?.testID?.startsWith('dist-row-'));
    const empty=home.findAll(tree,n=>n.props?.testID==='dist-empty-row');
    assert.equal(actual.length,expected);assert.equal(actual.length+empty.length,5);
    assert(empty.every(n=>n.props.pointerEvents==='none'&&n.props.importantForAccessibility==='no-hide-descendants'));
    assert.deepEqual(home.styled(tree,'statAmount').map(home.text),['$100.00','$20.00','$80.00']);
    assert.deepEqual(home.styled(tree,'statTitle').map(home.text),['Total ingresado','Total gastado','Balance del mes']);
    assert(home.text(home.styled(tree,'distCenterVal')[0]).includes(String(expected*100)));
  };
  check(Math.min(5,count));
  if(count===6){home.find(tree,'accounts-carousel').props.onMomentumScrollEnd({nativeEvent:{layoutMeasurement:{width:400},contentOffset:{x:400}}});tree=f.render();check(1);}
  f.close();
 }
 console.log('PASS: one/five/six accounts retain five row slots across pages; totals and approved stat order preserved.');
 const source=fs.readFileSync('frontend/app/(tabs)/index.tsx','utf8'),base=cp.execFileSync('git',['show','HEAD:frontend/app/(tabs)/index.tsx'],{encoding:'utf8'});
 const markers=['        {/* Balance del mes (net','        {/* Total gastado','        {/* Total ingresado'];
 function card(s,m){const a=s.indexOf(m),end=s.indexOf('\n        {/*',a+1),fallback=s.indexOf('\n      </View>',a);return s.slice(a,end<0?fallback:Math.min(end,fallback));}
 const normalized=source.replace(/ onLayout=\{e => \{ (?:balanceCardLayout|monthAmountLayout)\.value = validAmountLayout\(e\.nativeEvent\.layout\); \}\}/g,'').replace(/<HomeAmount[^>]*>/g,'').replaceAll('</HomeAmount>','').replace('— purple identity','— number in dark/black').replace('backgroundColor: "#EDE9FE"','backgroundColor: scheme === "dark" ? colors.brandPrimary + "26" : "#DCE9DD"').replaceAll('color={"#A78BFA"}','color={scheme === "dark" ? colors.brandPrimary : "#126046"}').replace('color: "#7C3AED"','color: colors.onSurface');
 for(const m of markers)assert.equal(normalizeUI(card(normalized,m)),normalizeUI(card(base,m)));
 assert.equal(source.slice(source.indexOf('const useStyles =')),base.slice(base.indexOf('const useStyles =')));
 console.log('PASS: all three stat cards moved intact; colors, values, internal styles and donut styles unchanged.');
})().catch(e=>{console.error(e);process.exitCode=1;});
