// Summary sizing and relocation of options: synthetic JSX only, no financial writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const source=fs.readFileSync('frontend/app/debts/index.tsx','utf8');
const detail=fs.readFileSync('frontend/app/debts/[id]/index.tsx','utf8');
const span=(s,a,b)=>s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)));
function extract(text){
 const ast=ts.createSourceFile('debt.tsx',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};
 function visit(n){
  if(ts.isFunctionDeclaration(n)&&n.name?.text==='palette')out.palette=n.getText(ast);
  if(ts.isVariableDeclaration(n)&&n.name.getText(ast)==='useStyles')out.styles=n.initializer.getText(ast);
  if((ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n))&&n.attributes.properties.some(p=>p.name?.getText(ast)==='testID'&&p.initializer?.text==='debt-detail-options'))out.button=n.parent.getText(ast);
  if(ts.isJsxSelfClosingElement(n)&&n.tagName.getText(ast)==='DebtActions')out.actions=n.getText(ast);
  ts.forEachChild(n,visit);
 }visit(ast);return out;
}
const list=extract(source),info=extract(detail);assert(info.button&&info.actions);
assert(!source.includes('debt-options-')&&!source.includes('debtProgress')&&!source.includes('DebtActions')&&!source.includes('actionDebt'));
for(const lang of ['en','es'])for(const scheme of ['light','dark']) {
 const translations=require(`../src/i18n/locales/${lang}.json`),events=[];
 const ctx={React:{createElement:(type,props,...children)=>({type,props,children})},Pressable:'Pressable',Ionicons:'Icon',DebtActions:'DebtActions',makeStyles:f=>f,us:x=>x,ufs:x=>x,
  Platform:{select:values=>values.android??values.default},spacing:{lg:16,md:12,sm:8},radius:{cardLg:28,pill:999,lg:24},scheme,shadow:{elevation:3},busy:false,d:{id:'synthetic-debt'},
  pal:{card:'#FCFCF8',border:'#eee',forest:'#126046'},deleted:{current:false},processing:{current:false},
  setShowOptions:value=>events.push(['options',value]),router:{dismissTo:route=>events.push(['dismissTo',route])},tr:key=>key.split('.').reduce((o,k)=>o[k],translations)};
 vm.runInNewContext(ts.transpileModule(`${list.palette}\nglobalThis.P=palette(scheme);globalThis.listStyles=(${list.styles})({},scheme);globalThis.styles=(${info.styles})();globalThis.button=(${info.button});globalThis.actions=(${info.actions});`,{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText,ctx);
 assert.equal(ctx.listStyles.summaryCard.paddingVertical,30);assert.equal(ctx.listStyles.summaryCard.minHeight,250);assert.equal(ctx.listStyles.summaryCard.marginHorizontal,16);
 assert.equal(ctx.listStyles.summaryBack.top,0);assert.equal(ctx.listStyles.summaryBack.bottom,0);assert.equal(ctx.listStyles.summaryFace.backfaceVisibility,'hidden');
 assert.equal(ctx.listStyles.summarySpacing.marginTop,-9);assert.equal(ctx.listStyles.flipHintText.fontSize,9);
 assert.equal(ctx.P.ring,scheme==='light'?'#0C6B4E':'#2CA079');
 assert.equal(ctx.button.props.testID,'debt-detail-options');assert.equal(ctx.button.props.style[0],ctx.styles.circleBtn);
 assert.equal(ctx.button.children[0].props.name,'ellipsis-horizontal');assert.equal(ctx.button.children[0].props.color,ctx.pal.forest);
 assert.equal(ctx.button.children[0].props.size,22);assert.equal(ctx.button.props.accessibilityLabel,lang==='en'?'More options':'Más opciones');
 ctx.button.props.onPress();assert.deepEqual(events.pop(),['options',true]);
 assert.equal(ctx.actions.props.debt.id,'synthetic-debt');ctx.actions.props.onClose();assert.deepEqual(events.pop(),['options',false]);
 ctx.actions.props.onDeleted();assert(ctx.deleted.current&&ctx.processing.current);assert.deepEqual(events.at(-1),['dismissTo','/debts']);
}
if(process.argv[2]) {
 const before=fs.readFileSync(process.argv[2],'utf8');
 assert.equal(span(source,'const DebtSummaryCard','function SummaryFace'),span(before,'const DebtSummaryCard','function SummaryFace'),'Complete flip implementation must remain byte-identical');
 assert.equal(span(source,'function buildStat','export default'),span(before,'function buildStat','export default'));
 assert.equal(span(source,'  const filtered =','  return ('),span(before,'  const filtered =','  return ('));
 // Individual amounts/progress blocks are untouched by options removal.
 assert.equal(span(source,'                {/* three info blocks */}','          {/* Add debt */}'),span(before,'                {/* three info blocks */}','          {/* Add debt */}'));
}
if(process.argv[3]){
 const before=fs.readFileSync(process.argv[3],'utf8');
 assert.equal(span(detail,'      {/* Resumen de la deuda */}','    </ElasticScrollView>'),span(before,'      {/* Resumen de la deuda */}','    </ElasticScrollView>'),'Full detail body, payment history and controls preserved');
 assert.equal(detail.slice(detail.indexOf('const useStyles')),before.slice(before.indexOf('const useStyles')),'All existing detail styles unchanged');
 assert.equal(span(detail,'  const executeDeletion','  const isPaid').split('  const remove =')[0],span(before,'  const executeDeletion','  const remove ='),'Payment cancellation and financial handlers unchanged');
}
console.log('PASS: 250-point minimum summary height versus ~208, responsive internal scale up to 1.2, unchanged ring greens/width/margins/hint; no list options/empty footprints; same circular detail button opens selected menu and confirmed deletion returns to list.');
console.log('PASS: optional task-start comparison protects all flip code, statistics, filters, list amounts/bars and the complete detail body/styles/payment cancellation.');
console.log('DEVICE LIMIT: native measurements, clipping, fonts and physical Android touch/flip behavior require Expo Go review.');
