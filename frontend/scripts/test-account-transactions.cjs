// C1: actual navigation handlers and read-only filter/pagination expressions.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const cp=require('node:child_process'),ts=require('typescript');
const root=path.resolve(__dirname,'../..');
const detailFile='frontend/app/accounts/[id].tsx',listFile='frontend/app/transactions/all.tsx';
const read=file=>process.env.C1_TEST_REF?cp.execFileSync('git',['show',`${process.env.C1_TEST_REF}:${file}`],{cwd:root,encoding:'utf8'}):fs.readFileSync(path.join(root,file),'utf8');
const detail=read(detailFile),list=read(listFile);
function inspect(source,file){
  const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),variables={},press={},effects=[];
  function visit(n){
    if(ts.isVariableDeclaration(n)&&n.initializer)variables[n.name.getText(tree)]=n.initializer.getText(tree);
    if(ts.isCallExpression(n)&&n.expression.getText(tree)==='useEffect')effects.push(n.getText(tree));
    if(ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n)){
      const attrs=n.attributes.properties,id=attrs.find(a=>a.name?.getText(tree)==='testID'),action=attrs.find(a=>a.name?.getText(tree)==='onPress');
      if(id?.initializer&&ts.isStringLiteral(id.initializer)&&action?.initializer&&ts.isJsxExpression(action.initializer))press[id.initializer.text]=action.initializer.expression.getText(tree);
    }
    ts.forEachChild(n,visit);
  }visit(tree);return {variables,press,effects};
}
const d=inspect(detail,detailFile),l=inspect(list,listFile);
function execute(code,context){vm.runInNewContext(ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,context);}
const plain=v=>JSON.parse(JSON.stringify(v));
const allRange={start:Date.parse('2026-10-01T00:00:00Z'),end:Date.parse('2026-10-31T23:59:59.999Z')};
const transaction=(id,type,account_id,to_account_id,date='2026-10-15T12:00:00Z',amount=100)=>({id,type,account_id,to_account_id,date,amount});
const data=[
  ...['income','expense','debt_payment','loan_given','loan_received'].map((type,n)=>transaction('a-'+n,type,'A',null)),
  transaction('incoming','transfer','B','A'),transaction('outgoing','transfer','A','B'),
  transaction('unrelated-transfer','transfer','B','C'),transaction('unrelated-expense','expense','B',null),
  transaction('bad-destination','expense','B','A'), // Destination participation applies only to transfers.
  transaction('old','expense','A',null,'2026-09-01T12:00:00Z'),
  transaction('same-ends-legacy','transfer','A','A'),
];
function pipeline(sourceInfo,accountId,transactions=data,type='all',sort='recent',range=allRange,page=1){
  const ctx={accountId,txQ:{data:transactions},type,sort,range,page,useMemo:f=>f(),Math,Date};
  const variables=['filtered','total','pages','safePage','pageItems','from','to'];
  execute(`const PAGE_SIZE=${sourceInfo.variables.PAGE_SIZE};\n`+variables.map(n=>`const ${n}=${sourceInfo.variables[n]};`).join('\n')+`\nglobalThis.result={${variables.join(',')}};`,ctx);
  return plain(ctx.result);
}
function run(){
  let pushes=[],backs=0;
  const router={push:r=>pushes.push(r),back:()=>backs++};
  execute(`const run=${d.press['acc-see-all']};run();`,{router,account:{id:'A / special?'}});
  assert.deepEqual(plain(pushes),[{pathname:'/transactions/all',params:{accountId:'A / special?'}}]);
  execute(`const run=${l.press['all-tx-back']};run();`,{router});assert.equal(backs,1);
  console.log('PASS: account detail navigates to existing list with exact account ID; Back preserves existing navigation.');

  const before=JSON.stringify(data),result=pipeline(l,'A');
  assert.deepEqual(result.filtered.map(t=>t.id).sort(),['a-0','a-1','a-2','a-3','a-4','incoming','outgoing','same-ends-legacy'].sort());
  assert.equal(result.filtered.filter(t=>t.id==='same-ends-legacy').length,1);
  assert.deepEqual(pipeline(l,'B',data,'transfer').filtered.map(t=>t.id).sort(),['incoming','outgoing','unrelated-transfer'].sort());
  assert.deepEqual(pipeline(l,'A',data,'income').filtered.map(t=>t.id).sort(),['a-0','a-4']);
  assert.deepEqual(pipeline(l,'A',data,'expense').filtered.map(t=>t.id).sort(),['a-1','a-2']);
  assert.equal(JSON.stringify(data),before);
  console.log('PASS: six types, incoming/outgoing transfers, unrelated accounts and legacy self-transfer; no financial data mutation.');

  assert.equal(pipeline(l,'A',data,'all','recent',{start:Date.parse('2026-09-01T00:00:00Z'),end:Date.parse('2026-09-30T23:59:59Z')}).total,1);
  const equalPayments=[transaction('first','expense','A',null),transaction('second','expense','A',null)];
  assert.equal(pipeline(l,'A',equalPayments).total,2);
  const many=Array.from({length:45},(_,n)=>transaction('row-'+n,'expense','A',null,'2026-10-15T12:00:00Z',n+1));
  many.push(transaction('other','expense','B',null));
  const second=pipeline(l,'A',many,'all','high',allRange,2);
  assert.equal(second.total,45);assert.equal(second.pages,3);assert.equal(second.from,21);assert.equal(second.to,40);
  assert.equal(second.pageItems.length,20);assert.equal(second.pageItems[0].amount,25);
  assert.equal(pipeline(l,'A',many,'all','high',allRange,3).pageItems.length,5);
  const empty=pipeline(l,'missing',many,'all','recent',allRange,3);
  assert.equal(empty.total,0);assert.equal(empty.safePage,1);assert.equal(empty.pageItems.length,0);assert.equal(empty.from,0);assert.equal(empty.to,0);
  assert(list.includes('testID="all-tx-empty"'));
  console.log('PASS: date range intersection, equal legitimate movements, sorting, page counts/rows and existing empty state.');

  let page=3;
  const reset=l.effects.find(e=>e.includes('[accountId]'));
  assert(reset);execute(reset,{useEffect:f=>f(),accountId:'B',setPage:p=>page=p});assert.equal(page,1);
  const previous=cp.execFileSync('git',['show',`HEAD:${listFile}`],{cwd:root,encoding:'utf8'}),old=inspect(previous,listFile);
  for(const type of ['all','income','expense','transfer'])for(const sort of ['recent','oldest','high','low']){
    assert.deepEqual(pipeline(l,undefined,data,type,sort),pipeline(old,undefined,data,type,sort));
  }
  console.log('PASS: account changes reset page; absent account preserves original filters, sorting, pagination and results exactly.');

  for(const [file,text] of [[detailFile,detail],[listFile,list]]){
    const base=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),marker='const useStyles =';
    assert.equal(text.slice(text.indexOf(marker)),base.slice(base.indexOf(marker)));
    const out=ts.transpileModule(text,{fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}});
    assert.equal((out.diagnostics||[]).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0);
  }
  assert(list.includes('queryKey: ["transactions"], queryFn: api.listTransactions'));
  console.log('PASS: identical styles, TSX syntax and unchanged read-only API/query cache; no journal/backend changes.');
}
try{run();}catch(error){console.error(error);process.exitCode=1;}
