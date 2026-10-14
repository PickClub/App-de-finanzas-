const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// Actual components and handlers, synthetic APIs only. No financial storage.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const direct=require('./test-transaction-direct-read.cjs');
const page=require('./test-transaction-history-page.cjs');
const plain=x=>JSON.parse(JSON.stringify(x));
function sheet(tree){if(!tree||typeof tree!=='object')return;return tree.type==='DateRangeSheet'?tree:(tree.children||[]).flat(Infinity).map(sheet).find(Boolean);}
async function main(){
  let cases=0;
  for(const type of ['expense','income','transfer'])for(const [before,after] of [['','Added\nsecond line'],['Existing','Changed\ntext'],['Existing','']]){
    const source={...direct.row('description',type),name:before,amount:70.123456,notes:'Preserved\nnotes'};
    const f=direct.fixture('form',{id:source.id});f.render();f.next(source.id,async()=>source);let tree=await f.settle(source.id);
    assert.equal(direct.find(tree,'name-input').props.value,before);
    direct.find(tree,'name-input').props.onChangeText(after);tree=f.render();await direct.find(tree,'save-tx').props.onPress();
    assert.equal(f.writes.length,1);const saved={...source,...plain(f.writes[0].payload)};
    assert.equal(saved.name,after);for(const k of Object.keys(source).filter(k=>k!=='name'))assert.deepEqual(saved[k],source[k],k);
    assert.equal(f.invalidations.length,1);assert.equal(f.backs(),1);
    const d=direct.fixture('detail',{id:source.id});d.render();d.next(source.id,async()=>saved);tree=await d.settle(source.id);
    if(after)assert(direct.text(tree).includes(after));else assert(!direct.text(tree).includes(before));
    cases++;
  }
  console.log('PASS: 9 description add/edit/clear cases; expense/income/transfer, multiline, exact unchanged fields, invalidation and fresh detail.');
  const records=Array.from({length:65},(_,i)=>page.row(String(i).padStart(3,'0'),{date:i<45?'2026-10-10T12:00:00Z':'2000-01-01T12:00:00Z'}));
  for(const range of [{start:Date.parse('2026-10-10T00:00:00Z'),end:Date.parse('2026-10-10T23:59:59.999Z')},{start:Date.parse('2026-10-01T00:00:00Z'),end:Date.parse('2026-10-15T23:59:59.999Z')}]){
    const f=page.createFixture(page.syntheticBackend(records),{accountId:'A',categoryId:'C'});let tree=f.render();tree=await f.settle();
    page.find(tree,'all-tx-type-expense').props.onPress();page.find(tree,'all-tx-sort-low').props.onPress();f.render();tree=await f.settle();
    assert.equal(sheet(tree).props.allowClear,true);sheet(tree).props.onApply(range);f.render();tree=await f.settle();assert.equal(f.query().data.total,45);
    page.find(tree,'all-tx-page-next').props.onPress();f.render();tree=await f.settle();assert(f.calls.at(-1).cursor);
    page.find(tree,'all-tx-clear-date').props.onPress();f.render();tree=await f.settle();
    const request=f.calls.at(-1);assert.equal(request.cursor,undefined);assert.equal(request.filters.start,undefined);assert.equal(request.filters.end,undefined);
    assert.equal(request.filters.account_id,'A');assert.equal(request.filters.category_id,'C');assert.equal(request.filters.order,'low');assert.deepEqual(request.filters.types,['expense','debt_payment']);
    assert.equal(f.query().data.total,65);assert(!page.find(tree,'all-tx-clear-date'));assert(page.text(page.find(tree,'all-tx-month')).includes('Todas las fechas'));f.close();cases++;
  }
  console.log('PASS: day/range clear removes both date bounds, retains account/category/type/order and resets page/cursor.');
  let finish;const f=page.createFixture(filters=>filters.start?new Promise(resolve=>finish=resolve):Promise.resolve({items:[page.row('unfiltered')],total:65,has_more:false,next_cursor:null}));
  let tree=f.render();await Promise.resolve();page.find(tree,'all-tx-clear-date').props.onPress();f.render();tree=await f.settle();assert(f.calls[0].signal.aborted);
  finish({items:[page.row('obsolete')],total:1,has_more:false,next_cursor:null});await new Promise(setImmediate);tree=f.render();assert(page.find(tree,'all-tx-row-unfiltered'));assert(!page.find(tree,'all-tx-row-obsolete'));f.close();cases++;
  console.log('PASS: obsolete date response cannot restore the cleared filter or replace unfiltered results.');
  const source=fs.readFileSync('frontend/src/components/date-range-sheet.tsx','utf8'),ast=ts.createSourceFile('sheet.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let handler;function visit(n){if(ts.isJsxOpeningElement(n)&&n.attributes.properties.some(p=>p.name?.getText(ast)==='testID'&&p.initializer?.text==='date-clear'))handler=n.attributes.properties.find(p=>p.name?.getText(ast)==='onPress').initializer.expression.getText(ast);ts.forEachChild(n,visit);}visit(ast);
  const actions=[];vm.runInNewContext('('+handler+')()',localeGlobals({setSelStart:v=>actions.push(['start',v]),setSelEnd:v=>actions.push(['end',v]),onApply:v=>actions.push(['apply',v]),close:()=>actions.push(['close'])}));
  assert.deepEqual(actions,[['start',null],['end',null],['apply',null],['close']]);assert(source.includes('allowClear = false'));assert(source.includes('allowClear && selStart'));
  console.log('PASS: shared clear handler removes selection and closes; opt-in keeps payment/date forms unchanged.');
  console.log('RESULT:',cases+1,'scenario groups passed.');
}
let finished=false;
process.on('beforeExit',()=>{if(!finished){console.error('FAIL: scenarios did not complete');process.exitCode=1;}});
main().then(()=>{finished=true;}).catch(e=>{finished=true;console.error(e);process.exitCode=1;});
