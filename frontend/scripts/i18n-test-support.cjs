// Existing financial tests isolate presentation. Localization behavior itself
// is covered by test-i18n.cjs using the real engine, resources and preference lifecycle.
const fs=require('node:fs'),ts=require('typescript'),{createInstance}=require('i18next');
const es=require('../src/i18n/locales/es.json');
const en=require('../src/i18n/locales/en.json');
const engine=createInstance();engine.init({lng:'es',fallbackLng:'en-US',resources:{es:{translation:es},'en-US':{translation:en}},initImmediate:false});
let integration=false;
async function setTestLocale(language){integration=true;await engine.changeLanguage(language);}
const tr=(key,options)=>String(engine.t(key,options));
const localizedError=value=>typeof value==='string'?value:value?.detail||value?.message||'';
function localeGlobals(context){
  Object.assign(context,{tr,localizedError});
  context.require??=name=>{
    if(name==='@/src/i18n')return {tr,useTranslation:()=>({t:tr,i18n:engine})};
    if(name==='@/src/i18n/errors')return {localizedError};
    throw Error(`Unexpected isolated import: ${name}`);
  };
  return context;
}
function localeMocks(mocks){
  mocks['@/src/i18n']={default:{language:'es'},tr,localeTag:()=> 'es-US',useTranslation:()=>({t:key=>key,i18n:{language:'es'}}),...mocks['@/src/i18n']};
  if(integration)Object.assign(mocks['@/src/i18n'],{default:engine,tr,localeTag:()=>engine.language==='es'?'es-US':'en-US',useTranslation:()=>({t:tr,i18n:engine})});
  mocks['@/src/i18n/errors']={localizedError};
  mocks['@/src/components/header-actions']={MoneyFlowHeaderActions:'MoneyFlowHeaderActions',...mocks['@/src/components/header-actions']};
  const nativeAlert=mocks['react-native']?.Alert;
  mocks['@/src/components/interaction-system']={Alert:nativeAlert||{alert(){}},ContextActionsTrigger:'ContextActionsTrigger',MoneyFlowConfirmDialog:'MoneyFlowConfirmDialog',...mocks['@/src/components/interaction-system']};
  return mocks;
}
function headerActionNodes(node){
  if(!node||typeof node!=='object'||node.type!=='MoneyFlowHeaderActions')return [];
  const p=node.props||{},nodes=[];
  if(p.beforeActions)nodes.push(p.beforeActions);
  if(p.onBack)nodes.push({type:'Pressable',props:{testID:p.backTestID,onPress:p.onBack}});
  if(p.onSave)nodes.push({type:'Pressable',props:{testID:p.saveTestID,onPress:p.onSave,disabled:!!(p.saveDisabled||p.saving)}});
  return nodes;
}
// Exact financial-handler comparisons allow only translated presentation calls.
// Source/payload conditions, request methods and field assignments stay intact.
function normalizeUI(source){
 const tree=ts.createSourceFile('ui.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 function visit(node){
  if(ts.isGetAccessorDeclaration(node)&&node.body?.statements.length===1&&ts.isReturnStatement(node.body.statements[0])){
   const expression=node.body.statements[0].expression;
   if(expression&&ts.isCallExpression(expression)&&expression.expression.getText(tree)==='tr'){
    edits.push([node.getStart(tree),node.end,node.name.getText(tree)+': '+normalizeUI(expression.getText(tree))]);return;
   }
  }
  if(ts.isCallExpression(node)&&node.expression.getText(tree)==='tr'&&node.arguments.length===1&&ts.isStringLiteral(node.arguments[0])){
   const value=tr(node.arguments[0].text);edits.push([node.getStart(tree),node.end,JSON.stringify(value)]);return;
  }
  if(ts.isCallExpression(node)&&node.expression.getText(tree)==='l10n'&&node.arguments.length===2&&node.arguments.every(ts.isStringLiteral)){
   edits.push([node.getStart(tree),node.end,JSON.stringify(node.arguments[0].text)]);return;
  }
  if(ts.isCallExpression(node)&&node.expression.getText(tree)==='localizedError'&&node.arguments.length===1){
   edits.push([node.getStart(tree),node.end,normalizeUI(node.arguments[0].getText(tree))]);return;
  }
  ts.forEachChild(node,visit);
 }visit(tree);let result=source;for(const[a,b,text]of edits.sort((a,b)=>b[0]-a[0]))result=result.slice(0,a)+text+result.slice(b);return result;
}
function visualContract(source){
 const tree=ts.createSourceFile('screen.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),result=[];
 const attributes=new Set(['style','size','color','contentContainerStyle','horizontal','numberOfLines','adjustsFontSizeToFit','minimumFontScale','scrollEventThrottle']);
 function visit(node){if(ts.isJsxOpeningElement(node)||ts.isJsxSelfClosingElement(node))for(const prop of node.attributes.properties)if(prop.name&&attributes.has(prop.name.getText(tree)))result.push(prop.getText(tree));ts.forEachChild(node,visit);}
 visit(tree);const marker='const useStyles =';if(source.includes(marker))result.push(source.slice(source.indexOf(marker)));return result.sort();
}
// Permit only the reviewed Home token aliases in presentation-style comparisons.
// Financial colors, handler bodies, dimensions and arbitrary colors remain exact.
function normalizeHomeColors(source){
 return source.replace(/\bcolors\.pageBackground\b/g,'colors.surface')
  .replace(/\bcolors\.primaryAction\b/g,'colors.brandPrimary')
  .replace(/\bcolors\.identityAccent\b/g,'colors.brandPrimary');
}
module.exports={localeGlobals,localeMocks,normalizeUI,visualContract,normalizeHomeColors,setTestLocale,tr,localizedError,headerActionNodes};
