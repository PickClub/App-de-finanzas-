const { approvedHomeBalanceBaseline } = require('./i18n-test-support.cjs');
// Isolated calculator and Home visual regressions.
const assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process');
const home=require('./test-summary-totals.cjs'),direct=require('./test-transaction-direct-read.cjs');
const form=fs.readFileSync('frontend/app/transactions/new.tsx','utf8');
assert.doesNotMatch(form,/\bautoFocus\b/);
(async()=>{
 for(const type of ['expense','income','transfer']){
  const f=direct.fixture('form',{type});
  let tree=f.render();
  const checkAmount=expected=>{
    const display=direct.find(tree,'amount-display');
    assert.equal(display.type,'Text');
    assert.equal(direct.text(display),expected);
    assert(!display.children.flat(Infinity).some(n=>n?.type==='TextInput'));
  };
  checkAmount('0.00');
  direct.find(tree,'calc-0').props.onPress();tree=f.render();
  checkAmount('0');
  direct.find(tree,'calc-backspace').props.onPress();tree=f.render();
  checkAmount('0.00');
 }
 console.log('PASS: expense/income/transfer amount display follows 0.00 → 0 → 0.00 with the calculator keypad.');
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
 for(const marker of markers){
  assert(source.includes(marker)&&base.includes(marker),marker);
  assert.equal(card(source,marker),card(base,marker));
 }
 const current=approvedHomeBalanceBaseline(source,true),reference=approvedHomeBalanceBaseline(base);
 assert.equal(current.slice(current.indexOf('const useStyles =')),reference.slice(reference.indexOf('const useStyles =')));
 console.log('PASS: all three stat cards moved intact; colors, values, internal styles and donut styles unchanged.');
})().catch(e=>{console.error(e);process.exitCode=1;});
