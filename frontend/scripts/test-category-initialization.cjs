const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// C5: inspect/execute actual bootstrap effects and explicit restore with fake API.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),cp=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const files=['frontend/app/categories/index.tsx','frontend/app/transactions/new.tsx'];
const read=f=>process.env.C5_TEST_REF?cp.execFileSync('git',['show',`${process.env.C5_TEST_REF}:${f}`],{cwd:root,encoding:'utf8'}):fs.readFileSync(path.join(root,f),'utf8');
function inspect(text,file){const tree=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),effects=[],calls=[];let restore;
  function visit(node,owner){
    if(ts.isVariableDeclaration(node)&&node.name.getText(tree)==='restore')restore=node.initializer.getText(tree);
    if(ts.isArrowFunction(node)||ts.isFunctionExpression(node))owner=ts.isVariableDeclaration(node.parent)?node.parent.name.getText(tree):'callback';
    if(ts.isCallExpression(node)){
      if(node.expression.getText(tree)==='useEffect'&&node.arguments[0]?.getText(tree).includes('api.initDefaultCategories'))effects.push(node.arguments[0].getText(tree));
      if(node.expression.getText(tree)==='api.initDefaultCategories')calls.push(owner);
    }ts.forEachChild(node,n=>visit(n,owner));
  }visit(tree,'render');return {effects,calls,restore};}
const compile=code=>ts.transpileModule(code,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText;
async function main(){
  const fixtures=[[],[{id:'custom',name:'My custom category',type:'expense',parent_id:null}],
    [{id:'g',is_group:true,type:'expense'},{id:'leaf',parent_id:'g',type:'expense'}]];
  for(const file of files){
    const text=read(file),parsed=inspect(text,file);
    for(const cats of fixtures)for(const success of [true,false]){
      let writes=0;const original=JSON.stringify(cats);
      const mount=async()=>{
        const context={q:{isSuccess:success,data:cats},catQ:{isSuccess:success,data:cats},cats,ensuredRef:{current:false},
          api:{initDefaultCategories:async()=>{writes++;}},qc:{invalidateQueries:async()=>{}}};
        for(const effect of parsed.effects){vm.runInNewContext(compile('globalThis.run='+effect),localeGlobals(context));context.run();context.run();}
      };
      await Promise.all([mount(),mount(),mount(),mount()]);await mount();
      assert.equal(writes,0,`${file}: empty/legacy/query error/remount must not bootstrap`);
      assert.equal(JSON.stringify(cats),original);
    }
    assert.deepEqual(parsed.calls,file.includes('categories/index')?['restore']:[],'All initialization calls must be explicit');
    const base=cp.execFileSync('git',['show',`HEAD:${file}`],{cwd:root,encoding:'utf8'}),marker='const useStyles =';
    assert.equal(text.slice(text.indexOf(marker)),base.slice(base.indexOf(marker)));
    if(file.includes('transactions/new')){
      function protectedHandlers(source){const tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out=[];
        function visit(n){if(ts.isVariableDeclaration(n)&&['save','remove'].includes(n.name.getText(tree)))out.push(n.initializer.getText(tree));ts.forEachChild(n,visit);}visit(tree);return out;}
      const approvedStart=text.indexOf('    if (params.id && sourceQ.data?.id === sourceId\n');
      const approvedEnd=text.indexOf('    savingRef.current = true;',approvedStart);
      const approved=approvedStart>=0?text.slice(approvedStart,approvedEnd):'';
      if(approved)assert(approved.includes('delete payload[field]')&&approved.includes('original.amount'));
      const normalized=text.replace(approved,'').replace('params.id ? name : name.trim() || "Sin descripción"','name.trim() || "Sin descripción"');
      assert.deepEqual(protectedHandlers(normalized).map(normalizeUI),protectedHandlers(base).map(normalizeUI));
    }
    const out=ts.transpileModule(text,{fileName:file,reportDiagnostics:true,compilerOptions:{jsx:ts.JsxEmit.React,target:ts.ScriptTarget.ES2020}});
    assert.equal((out.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error).length,0);
  }
  console.log('PASS: existing/custom, empty and ungrouped catalogs; query errors; repeated/concurrent mounts produce zero category writes.');
  const text=read(files[0]),parsed=inspect(text,files[0]);
  assert(text.includes('testID="restore-categories"'));assert(text.includes('onPress={restore}'));
  const old=cp.execFileSync('git',['show',`HEAD:${files[0]}`],{cwd:root,encoding:'utf8'});
  assert.equal(parsed.restore,inspect(old,files[0]).restore);
  let writes=0,refreshes=0;
  const catalog=[];
  const context={api:{initDefaultCategories:async()=>{writes++;catalog.push({id:'synthetic-default',is_group:true});}},qc:{invalidateQueries:({queryKey})=>{assert.equal(queryKey[0],'categories');refreshes++;}}};
  vm.runInNewContext(compile('globalThis.restore='+parsed.restore),localeGlobals(context));
  assert.equal(writes,0);await context.restore();assert.equal(writes,1);assert.equal(refreshes,1);assert.equal(catalog.length,1);
  console.log('PASS: defaults remain available via existing explicit restore for an empty catalog; no automatic first-user provisioning or API contract change.');
  console.log('PASS: styles, transaction save/remove and manual restore handler unchanged; manual create/edit covered by category-save regression.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
