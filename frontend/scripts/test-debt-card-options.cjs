// Protect the existing debt summary flip while checking the shared debt detail menu.
const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
const source=fs.readFileSync('frontend/app/debts/index.tsx','utf8');
const detail=fs.readFileSync('frontend/app/debts/[id]/index.tsx','utf8');
const span=(s,a,b)=>s.slice(s.indexOf(a),s.indexOf(b,s.indexOf(a)));
function extract(text){
 const ast=ts.createSourceFile('debt.tsx',text,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};
 function visit(n){
  if(ts.isFunctionDeclaration(n)&&n.name?.text==='palette')out.palette=n.getText(ast);
  if(ts.isVariableDeclaration(n)&&n.name.getText(ast)==='useStyles')out.styles=n.initializer.getText(ast);
  if((ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n))&&n.attributes.properties.some(p=>p.name?.getText(ast)==='testID'&&p.initializer?.text==='debt-detail-options'))out.button=n.getText(ast);
  if(ts.isJsxSelfClosingElement(n)&&n.tagName.getText(ast)==='DebtActions')out.confirmation=n.getText(ast);
  ts.forEachChild(n,visit);
 }visit(ast);return out;
}
const list=extract(source),detailBits=extract(detail);assert(detailBits.button&&detailBits.confirmation);
assert(!source.includes('debt-options-')&&!source.includes('DebtActions')&&!source.includes('actionDebt'));
for(const lang of ['en','es'])for(const scheme of ['light','dark']){
 const translations=require(`../src/i18n/locales/${lang}.json`),events=[];
 const ctx={React:{createElement:(type,props,...children)=>({type,props,children})},ContextActionsTrigger:'ContextActionsTrigger',DebtActions:'DebtActions',makeStyles:f=>f,us:x=>x,Platform:{select:values=>values.android??values.default},spacing:{lg:16,md:12,sm:8},radius:{cardLg:28,pill:999,lg:24},scheme,
  shadow:{elevation:3},deleted:{current:false},processing:{current:false},busy:false,d:{id:'synthetic-debt'},pal:{card:'#FCFCF8',border:'#eee',forest:'#126046'},
  confirmDelete:false,router:{push:route=>events.push(['push',route]),dismissTo:route=>events.push(['dismissTo',route])},
  setConfirmDelete:value=>events.push(['confirmDelete',value]),tr:key=>key.split('.').reduce((o,k)=>o[k],translations)};
 const js=ts.transpileModule(`${list.palette}\nglobalThis.P=palette(scheme);globalThis.listStyles=(${list.styles})({},scheme);globalThis.styles=(${detailBits.styles})();globalThis.button=(${detailBits.button});globalThis.confirmation=(${detailBits.confirmation});`,{compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
 const vm=require('node:vm');vm.runInNewContext(js,ctx);
 assert.equal(ctx.listStyles.summaryCard.paddingVertical,30);assert.equal(ctx.listStyles.summaryCard.minHeight,250);assert.equal(ctx.listStyles.summaryCard.marginHorizontal,16);
 assert.equal(ctx.listStyles.summaryBack.top,0);assert.equal(ctx.listStyles.summaryBack.bottom,0);assert.equal(ctx.listStyles.summaryFace.backfaceVisibility,'hidden');
 assert.equal(ctx.listStyles.summarySpacing.marginTop,-9);assert.equal(ctx.listStyles.flipHintText.fontSize,9);
 assert.equal(ctx.P.ring,scheme==='light'?'#0C6B4E':'#2CA079');
 assert.equal(ctx.button.type,'ContextActionsTrigger');
 const props=ctx.button.props;
 assert.equal(props.testID,'debt-detail-options');assert.equal(props.style[0],ctx.styles.circleBtn);
 assert.equal(props.iconColor,ctx.pal.forest);assert.equal(props.iconSize,22);
 assert.equal(props.accessibilityLabel,lang==='en'?'More options':'Más opciones');
 const actions=props.actions;
 assert.equal(JSON.stringify(actions.map(a=>a.id)),JSON.stringify(['edit','delete']));
 actions[0].onPress();
 assert.equal(events.pop()[1].params.id,'synthetic-debt');
 actions[1].onPress();
 assert.deepEqual(events.pop(),['confirmDelete',true]);
 assert.equal(ctx.confirmation.type,'DebtActions');assert.equal(ctx.confirmation.props.visible,false);assert.equal(ctx.confirmation.props.debt.id,'synthetic-debt');
}
if(process.argv[2]){
 const before=fs.readFileSync(process.argv[2],'utf8');
 assert.equal(span(source,'const DebtSummaryCard','function SummaryFace'),span(before,'const DebtSummaryCard','function SummaryFace'),'The complete flip implementation must remain byte-identical');
 assert.equal(span(source,'function buildStat','export default'),span(before,'function buildStat','export default'));
 assert.equal(span(source,'  const filtered =','  return ('),span(before,'  const filtered =','  return ('));
 assert.equal(span(source,'                {/* three info blocks */}','          {/* Add debt */}'),span(before,'                {/* three info blocks */}','          {/* Add debt */}'));
}
if(process.argv[3]){
 const before=fs.readFileSync(process.argv[3],'utf8');
 for(const token of ['styles.hero','styles.amountCard','styles.infoCard','styles.payBtn','styles.historyCard','styles.histRow'])assert(detail.includes(token));
 for(const token of ['circleBtn: { width: 46, height: 46','hero: { flexDirection: "row"','amountCard: { flexDirection: "row"','payBtn: { flexDirection: "row"'])assert(detail.includes(token));
 assert.equal(span(detail,'  const executeDeletion','  const isPaid').split('  const remove =')[0],span(before,'  const executeDeletion','  const remove ='),'Debt and payment deletion handlers remain unchanged');
}
console.log('PASS: debt summary flip, ring colors, sizing, filters and metric blocks remain intact; debt detail retains its circular ellipsis, exactly Edit/Delete, the existing edit route and named deletion confirmation.');
console.log('DEVICE LIMIT: native measurements, menu animation, touch targets and flip behavior still need Expo Go review.');
