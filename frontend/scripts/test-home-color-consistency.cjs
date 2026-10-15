// Color-only contracts. Optional task-start baseline proves structural preservation.
const assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process'),vm=require('node:vm'),ts=require('typescript');
const themeSource=fs.readFileSync('frontend/src/theme.ts','utf8');
function ast(file,text){return ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true,file.endsWith('.tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);}
function palettes(text){
 const tree=ast('theme.ts',text),values={};
 function visit(n){if(ts.isVariableDeclaration(n)&&['light','dark'].includes(n.name.getText(tree)))values[n.name.getText(tree)]=vm.runInNewContext('('+n.initializer.getText(tree)+')');ts.forEachChild(n,visit);}visit(tree);return values;
}
const themes=palettes(themeSource),homeFile='frontend/app/(tabs)/index.tsx',home=fs.readFileSync(homeFile,'utf8');
assert(home.includes('backgroundColor: scheme === "dark" ? colors.surface : "#E8EFE7"'));
assert.equal(themes.light.pageBackground,'#E8EFE7');assert.equal(themes.dark.pageBackground,themes.dark.surface);
assert(home.includes('"#146448"'));assert.equal(themes.light.primaryAction,'#146448');assert.equal(themes.light.identityAccent,'#126046');
assert.equal(themes.light.secondaryActionBackground,'#DFEBDD');assert(home.includes('\"#DFEBDD\"'));
assert.equal(themes.dark.primaryAction,themes.dark.brandPrimary);assert.equal(themes.dark.identityAccent,themes.dark.brandPrimary);
const files=cp.execFileSync('rg',['--files','frontend/app','frontend/src/screens','-g','*.tsx'],{encoding:'utf8'}).trim().split('\n');
let pageUses=0;
for(const file of files){const source=fs.readFileSync(file,'utf8'),tree=ast(file,source);
 function visit(n){
  if(ts.isObjectLiteralExpression(n)){
   const full=n.properties.some(p=>p.name?.getText(tree)==='flex'&&p.initializer?.getText(tree)==='1');
   const bg=n.properties.find(p=>p.name?.getText(tree)==='backgroundColor');
   if(full&&bg?.initializer){
    let modal=false;for(let p=n.parent;p;p=p.parent)if(ts.isJsxElement(p)&&p.openingElement.tagName.getText(tree)==='Modal')modal=true;
    if(!modal)assert.notEqual(bg.initializer.getText(tree),'colors.surface',file+': page still uses the warm surface');
   }
  }
  if(ts.isPropertyAccessExpression(n)&&n.getText(tree)==='colors.pageBackground')pageUses++;
  ts.forEachChild(n,visit);
 }visit(tree);
}
assert(pageUses>=25);
const colorKeys=new Set(['color','backgroundColor','borderColor','borderTopColor','borderBottomColor','borderLeftColor','borderRightColor','shadowColor','tintColor','fill','stroke']);
function structure(file,text){
 const tree=ast(file,text);
 const result=ts.transform(tree,[context=>function visit(node){
  if(ts.isObjectLiteralExpression(node)&&file==='frontend/src/theme.ts'){
   node=ts.factory.updateObjectLiteralExpression(node,node.properties.filter(p=>!['pageBackground','primaryAction','identityAccent','secondaryActionBackground'].includes(p.name?.getText(tree))));
  }
  if(ts.isPropertyAccessExpression(node)&&node.getText(tree)==='colors.identityAccent')return ts.factory.createPropertyAccessExpression(ts.factory.createIdentifier('colors'),'brandPrimary');
  if(ts.isPropertyAssignment(node)&&colorKeys.has(node.name.getText(tree)))return ts.factory.updatePropertyAssignment(node,node.name,ts.factory.createStringLiteral('COLOR'));
  if(ts.isJsxAttribute(node)&&colorKeys.has(node.name.getText(tree)))return ts.factory.updateJsxAttribute(node,node.name,ts.factory.createStringLiteral('COLOR'));
  return ts.visitEachChild(node,visit,context);
 }]);
 const printed=ts.createPrinter({removeComments:true}).printFile(result.transformed[0]);result.dispose();return printed;
}
if(process.argv[2]){
 const before=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 for(const[file,source]of Object.entries(before)){const actual=structure(file,fs.readFileSync(file,'utf8')),expected=structure(file,source);assert(actual===expected,file+': a non-color change was introduced');}
 assert.equal(home,before[homeFile]);
 assert.equal(fs.readFileSync('frontend/app/(tabs)/notes.tsx','utf8'),before['frontend/app/(tabs)/notes.tsx']);
 const oldThemes=palettes(before['frontend/src/theme.ts']);
 for(const mode of ['light','dark'])for(const key of Object.keys(oldThemes[mode]))assert.equal(themes[mode][key],oldThemes[mode][key],`Existing ${mode} token changed: ${key}`);
 console.log('PASS: task-start AST comparison preserves all component trees, handlers, dimensions, typography, navigation, animations, user color data and every existing theme token; Home is byte-for-byte unchanged.');
}else console.log('SKIP: task-start structural comparison requires the optional baseline JSON argument.');
console.log('PASS: exact Home background/action/accent tokens, unchanged dark equivalents, '+pageUses+' page-token references; internal card surfaces and semantic theme colors stay separate.');
