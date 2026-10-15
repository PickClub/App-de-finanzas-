const {localeGlobals,localeMocks,normalizeHomeColors,normalizeUI,visualContract}=require('./i18n-test-support.cjs');
// All primary screen scrolls share the bounded gesture; no focus/entry animation.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),ts=require('typescript'),vm=require('node:vm');
const reports='frontend/app/(tabs)/reports.tsx';
const reportSource=fs.readFileSync(reports,'utf8');
assert.deepEqual(visualContract(reportSource),visualContract(cp.execFileSync('git',['show','HEAD:'+reports],{encoding:'utf8'})));
for(const file of ['frontend/app/_layout.tsx','frontend/app/(tabs)/_layout.tsx']){
 assert.deepEqual(visualContract(normalizeHomeColors(fs.readFileSync(file,'utf8'))),visualContract(normalizeHomeColors(cp.execFileSync('git',['show','HEAD:'+file],{encoding:'utf8'}))));
}
assert(!fs.existsSync('frontend/src/components/screen-entrance.tsx'));
const paths=[];function walk(dir){for(const f of fs.readdirSync(dir)){const p=path.join(dir,f);fs.statSync(p).isDirectory()?walk(p):p.endsWith('.tsx')&&paths.push(p);}}walk('frontend/app');
const moduleSource=fs.readFileSync('frontend/src/native-scroll.ts','utf8'),exportsObject={};
vm.runInNewContext(ts.transpileModule(moduleSource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,localeGlobals({exports:exportsObject}));
assert.deepEqual(JSON.parse(JSON.stringify(exportsObject.NATIVE_VERTICAL_SCROLL)),{overScrollMode:'never',bounces:false,alwaysBounceVertical:false});
assert(Object.isFrozen(exportsObject.NATIVE_VERTICAL_SCROLL));
const covered=new Set(),refresh=new Set(),explicit=new Set();let scrolls=0,configured=0,fallbacks=0;
for(const file of paths){
 const source=fs.readFileSync(file,'utf8'),tree=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 assert(!/screen-entrance|stackScreenEntrance|tabScreenEntrance/.test(source));
 function visit(n){
  if(ts.isJsxOpeningElement(n)||ts.isJsxSelfClosingElement(n)){
   const tag=n.tagName.getText(tree);
   if(['ScrollView','Animated.ScrollView','FlatList','SectionList','ElasticScrollView','ElasticFlatList'].includes(tag)){
    const attrs=n.attributes.properties;
    const horizontal=attrs.find(a=>a.name?.getText(tree)==='horizontal');
    if(!horizontal){
     const preview=file==='frontend/app/(tabs)/notes.tsx'&&attrs.some(a=>a.name?.getText(tree)==='testID'&&a.initializer?.text==='notes-preview-content');
     if(preview){
      assert.equal(attrs.find(a=>a.name?.getText(tree)==='overScrollMode')?.initializer?.text,'never');
      assert.equal(attrs.find(a=>a.name?.getText(tree)==='bounces')?.initializer?.getText(tree),'{false}');
      assert(!attrs.some(a=>a.name?.getText(tree)==='alwaysBounceVertical'||a.name?.getText(tree)==='refreshControl'));
      let insideModal=false;for(let a=n.parent;a;a=a.parent)if(ts.isJsxElement(a)&&a.openingElement.tagName.getText(tree)==='Modal')insideModal=true;
      assert(insideModal,'Read-only note preview must remain a modal body scroll');
     }else for(const key of ['overScrollMode','bounces','alwaysBounceVertical'])
      assert(!attrs.some(a=>a.name?.getText(tree)===key),file+': '+key+' differs from Reports defaults');
     covered.add(file);scrolls++;
     if(tag==='ElasticScrollView'||tag==='ElasticFlatList')fallbacks++;
     const profile=attrs.some(a=>ts.isJsxSpreadAttribute(a)&&a.expression.getText(tree)==='NATIVE_VERTICAL_SCROLL');
     let modal=false;for(let a=n.parent;a;a=a.parent){if(ts.isJsxElement(a)&&['Modal','AppSheet','BottomSheetModal'].includes(a.openingElement.tagName.getText(tree)))modal=true;}
     if(!modal){assert(['ElasticScrollView','ElasticFlatList'].includes(tag),file+' requires bounded elastic displacement');if(file!==reports)assert(profile,file+' requires the shared disabled-native configuration');explicit.add(file);configured++;}
     else assert(!profile,file+': modal scroll must remain original');
     if(attrs.some(a=>a.name?.getText(tree)==='refreshControl'))refresh.add(file);
    }
   }
  }
  ts.forEachChild(n,visit);
 }
 visit(tree);
}
for(const expected of ['frontend/app/(tabs)/index.tsx','frontend/app/accounts/index.tsx','frontend/app/bills/index.tsx','frontend/app/transactions/all.tsx','frontend/app/calendar/index.tsx','frontend/app/settings.tsx','frontend/app/(tabs)/notes.tsx'])assert(covered.has(expected));
console.log('PASS: Reports and navigation layout contracts unchanged, allowing reviewed Home colors; no focus pulse.');
assert.equal(fallbacks,34);
console.log('PASS:',explicit.size,'screens,',configured,'main scroll/list instances use the same bounded gesture.');
console.log('Reports now shares the pixel cap; nested modal lists are unchanged. Total vertical instances inspected:',scrolls);
assert.equal(refresh.size,0,'Pull-to-refresh must not intercept the native vertical edge effect');
console.log('PASS: no pull-to-refresh callbacks or wheels on screen scrolls; drag cannot start a refresh.');
console.log('Non-scrollable routes (no artificial gestures):',paths.filter(p=>!covered.has(p)&&!p.includes('_layout')&&!p.includes('+html')).join(', '));
console.log('LIMIT: offline source checks do not prove Samsung native edge stretching, resistance or scroll/refresh arbitration.');
