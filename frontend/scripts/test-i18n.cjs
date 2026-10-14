// Real i18next resources with simulated React lifecycle and preference storage.
// No application API, database, device storage, or financial writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const {createInstance}=require('i18next');
const en=require('../src/i18n/locales/en.json'),es=require('../src/i18n/locales/es.json');
const compile=(file)=>ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(saved='',web=null,intl=Intl){
 const engine=createInstance(),slots=[],effects=[],warnings=[],writes=[];let index=0,readResolve,writeOk=true;
 const react={createElement:(type,props,...children)=>({type,props,children}),createContext:v=>({Provider:'Provider',value:v}),useContext:c=>c.value,
  useState:v=>{const i=index++;if(!(i in slots))slots[i]=typeof v==='function'?v():v;return [slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},
  useRef:v=>{const i=index++;return slots[i]??(slots[i]={current:v});},useMemo:f=>f(),useCallback:f=>f,
  useEffect:f=>{const i=index++;if(!(i in slots)){slots[i]=true;effects.push(f);}}};react.default=react;
 const storage={getItem:async()=>saved==='pending'?new Promise(r=>readResolve=r):saved,setItem:async(k,v)=>{writes.push([k,v]);return writeOk;}};
 const mocks={i18next:{createInstance:()=>engine},'react-i18next':{initReactI18next:{type:'3rdParty',init:()=>{}},useTranslation:()=>({t:engine.t.bind(engine),i18n:engine})},react,'@/src/utils/storage':{storage},'./locales/en.json':en,'./locales/es.json':es};
 const exports={},context={exports,require:n=>{assert(n in mocks,n);return mocks[n];},__DEV__:true,Intl:intl,console:{warn:m=>warnings.push(m)}};
 if(web!==null)context.localStorage={getItem:()=>web,setItem:(_k,v)=>web=v};
 vm.runInNewContext(compile('frontend/src/i18n/index.tsx'),context);
 const render=()=>{index=0;const tree=exports.LanguageProvider({children:'App'});effects.splice(0).forEach(f=>f());return tree.props.value;};
 return {engine,exports,render,writes,warnings,resolve:v=>readResolve(v),failWrite:()=>writeOk=false};
}
function moduleFile(file,f){const exports={};vm.runInNewContext(compile(file),{exports,require:name=>{
 if(name.includes('locales/en'))return en;if(name.includes('locales/es'))return es;
 if(name==='@/src/category-labels')return moduleFile('frontend/src/category-labels.ts',f);
 if(name==='@/src/i18n'||name==='./index')return {__esModule:true,default:f.engine,...f.exports};throw Error(name);
 }});return exports;}
(async()=>{
 for(const value of ['',null,'invalid','fr']){const f=fixture(value);f.render();await flush();assert.equal(f.engine.language,'en-US');assert.equal(f.render().lang,'en-US');}
 for(const [saved,expected]of [['es','es'],['en','en-US'],['en-US','en-US']]){const f=fixture(saved);f.render();await flush();assert.equal(f.render().lang,expected);assert.equal(f.writes.length,0);}
 for(const [raw,expected]of [['es','es'],['"es"','es'],['en','en-US'],['"en-US"','en-US'],['junk','en-US']]){const f=fixture('',raw);assert.equal(f.engine.language,expected);}
 console.log('PASS: en-US default without device detection; valid native/web explicit and legacy preferences preserved.');
 const f=fixture();let api=f.render();await flush();let changes=0;f.engine.on('languageChanged',()=>changes++);
 await api.setLang('es');assert.equal(f.render().lang,'es');assert.equal(f.engine.t('common.save'),'Guardar');
 await f.render().setLang('en-US');assert.equal(f.render().lang,'en-US');assert.equal(f.engine.t('common.save'),'Save');assert.equal(changes,2);
 assert.deepEqual(f.writes.map(x=>x[1]),['es','en-US']);
 await assert.rejects(f.render().setLang('fr'));f.failWrite();await assert.rejects(f.render().setLang('es'));assert.equal(f.engine.language,'en-US');
 console.log('PASS: bidirectional switching, ordered persistence, languageChanged updates and safe rejection of invalid/failed preferences.');
 const race=fixture('pending');race.render();await race.render().setLang('en-US');race.resolve('es');await flush();assert.equal(race.engine.language,'en-US');
 const queued=fixture();const q=queued.render();await Promise.all([q.setLang('es'),q.setLang('en-US')]);assert.equal(queued.engine.language,'en-US');
 console.log('PASS: delayed hydration cannot overwrite a fresh choice; rapid selections preserve last choice.');
 assert.equal(f.engine.t('ui.transactions_found',{count:1}),'1 transaction found');assert.equal(f.engine.t('ui.transactions_found',{count:2}),'2 transactions found');
 await f.engine.changeLanguage('es');assert.equal(f.engine.t('ui.transactions_found',{count:2}),'2 transacciones encontradas');assert.equal(f.engine.t('ui.transactions_found',{count:1000000}),'1000000 transacciones encontradas');assert.equal(f.engine.t('home.debtCountShare',{count:2,percent:50}),'2 deudas · 50% del total');
 const format=moduleFile('frontend/src/format.ts',f),categories=moduleFile('frontend/src/category-labels.ts',f);
 for(const language of ['en-US','es']){await f.engine.changeLanguage(language);assert.equal(format.formatCurrencyInt(2679),'$2,679');assert.equal(format.formatCurrencyInt(-2504),'-$2,504');assert.equal(categories.catLabel('Groceries',language),'Groceries');assert.equal(categories.catLabel('Alimentación',language),'Alimentación');assert.equal(categories.catLabel('Mi café personal',language),'Mi café personal');}
 assert.equal(categories.catLabel('Groceries','es',true),'Supermercado');assert.equal(categories.catLabel('Groceries','en-US',true),'Groceries');
 await f.engine.changeLanguage('en-US');const date='2026-01-15T12:00:00';assert.match(format.formatDateLong(date),/January/);await f.engine.changeLanguage('es');assert.match(format.formatDateLong(date),/enero/);
 console.log('PASS: pluralization/interpolation, American/Spanish-US dates, unchanged USD integer currency, explicit catalog mapping and untouched custom content.');
 const domains=[
  ['accounts.types.', ['cash','checking','savings','credit_card','wallet','other']],
  ['bills.s_', ['pending','paid','overdue']], ['bills.r_', ['once','weekly','monthly','quarterly','yearly']], ['bills.rem_', ['none','1','3','7']],
  ['budgets.', ['weekly','monthly','custom']], ['budgets.status_', ['normal','warning','reached','exceeded']],
  ['rp.st_', ['active','paused','ended','paid','pending','overdue','upcoming','partial']],
  ['rp.f_', ['daily','weekly','biweekly','monthly','bimonthly','quarterly','semiannual','annual']], ['rp.r_', ['none','0','1','3','7']],
  ['rp.', ['mark','expense','link']], ['calendar.kinds.', Object.keys(en.calendar.kinds)], ['calendar.sub.', Object.keys(en.calendar.sub)],
  ['calendar.', ['month','week','list','pending','overdue','partial','completed','planned','upcoming','done']],
 ];
 for(const language of ['en-US','es'])for(const[prefix,values]of domains)for(const value of values)assert(f.engine.exists(prefix+value,{lng:language,fallbackLng:false}),`${language}: ${prefix+value}`);
 const pickerSource=fs.readFileSync('frontend/src/components/date-range-sheet.tsx','utf8'),pickerTree=ts.createSourceFile('picker.tsx',pickerSource,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 const dateHelpers=pickerTree.statements.filter(n=>ts.isFunctionDeclaration(n)&&['monthNames','weekdayNames'].includes(n.name?.text)).map(n=>n.getText(pickerTree)).join('\n');
 const dates={i18n:f.engine,localeTag:f.exports.localeTag};vm.createContext(dates);vm.runInContext(ts.transpileModule(dateHelpers+'\nglobalThis.months=monthNames;globalThis.days=weekdayNames;',{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,dates);
 await f.engine.changeLanguage('en-US');assert.equal(dates.months()[0],'January');assert.equal(dates.days()[0],'M');await f.engine.changeLanguage('es');assert.equal(dates.months()[0],'Enero');assert.equal(dates.days()[0],'L');
 console.log('PASS: supported dynamic account/bill/budget/recurring/calendar enum labels exist in both languages; actual date-picker helpers switch without changing weekday order.');
 const errors=moduleFile('frontend/src/i18n/errors.ts',f);for(const language of ['en-US','es']){await f.engine.changeLanguage(language);for(const status of [400,404,409,422,503]){const message=errors.localizedError({status,detail:'private URI and unknown backend detail'});assert(!message.includes('private'));assert(!message.includes('URI'));assert(message.length>10);}}
 await f.engine.changeLanguage('en-US');assert.equal(errors.localizedError('API 403: '+JSON.stringify({detail:es.errors.demoDisabled})),en.errors.demoDisabled);
 const fallback=fixture();await fallback.engine.changeLanguage('es');fallback.engine.removeResourceBundle('es','translation');fallback.engine.addResourceBundle('es','translation',{common:{save:'Guardar'}});assert.equal(fallback.engine.t('common.cancel'),en.common.cancel);assert(fallback.warnings.some(w=>w.includes('es:translation:common.cancel')));fallback.engine.t('missing.test.key');assert(fallback.warnings.some(w=>w.includes('missing.test.key')));
 console.log('PASS: safe localized HTTP errors, English fallback and development missing-key reporting.');
 const settings=fs.readFileSync('frontend/app/settings.tsx','utf8');assert(settings.includes('id: "en-US"'));assert(settings.includes('await setLang(l.id)'));assert(!fs.readFileSync('frontend/src/i18n/index.tsx','utf8').includes('getLocales'));
 console.log('PASS: existing Settings selector keeps its structure, persists explicit choices and never derives language from the device.');
 const support=require('./i18n-test-support.cjs'),home=require('./test-summary-totals.cjs');
 // Remove the constructor in both the application VM and i18next's own realm.
 const originalPluralRules=Intl.PluralRules;
 const originalMocks=support.localeMocks,originalGlobals=support.localeGlobals;
 let unavailableHome;
 try{
  Intl.PluralRules=undefined;
  const unavailable=fixture('',null,Intl);
  for(const language of ['en-US','es']){
   await unavailable.engine.changeLanguage(language);
   const dictionary=language==='es'?es:en;
   for(const count of [0,1,2,1234,1000000]){
    const suffix=count===1?'one':'other';
    assert.equal(unavailable.exports.tr('ui.transactions_found',{count}),dictionary.ui['transactions_found_'+suffix].replace('{{count}}',String(count)));
    assert.equal(unavailable.exports.tr('home.debtCountShare',{count,percent:50}),dictionary.home['debtCountShare_'+suffix].replace('{{count}}',String(count)).replace('{{percent}}','50'));
   }
  }
  // The actual Home fixture uses the repaired module, including its postprocessor.
  support.localeMocks=mocks=>{
   const result=originalMocks(mocks);
   result['@/src/i18n']={__esModule:true,default:unavailable.engine,...unavailable.exports,useTranslation:()=>({t:unavailable.exports.tr,i18n:unavailable.engine})};
   return result;
  };
  support.localeGlobals=context=>Object.assign(originalGlobals(context),{tr:unavailable.exports.tr});
  delete require.cache[require.resolve('./test-summary-totals.cjs')];
  const affectedHome=require('./test-summary-totals.cjs');
  unavailableHome=affectedHome.fixture(async()=>affectedHome.positive,[{id:'synthetic',direction:'i_owe'}]);
  for(const language of ['en-US','es']){
   await unavailable.engine.changeLanguage(language);
   unavailableHome.render();const tree=await unavailableHome.settle();
   assert(affectedHome.text(tree).includes(language==='es'?'1 deuda':'1 debt'));
  }
  console.log('PASS: missing Intl.PluralRules does not crash translations or actual Home debt labels; counts 0, 1, 2, 1234 and 1000000 in English/Spanish.');
 }finally{
  unavailableHome?.close();
  Intl.PluralRules=originalPluralRules;
  support.localeMocks=originalMocks;support.localeGlobals=originalGlobals;
  delete require.cache[require.resolve('./test-summary-totals.cjs')];
 }

 await support.setTestLocale('en-US');
 const account={id:'custom',name:'Mi cuenta personal ñ',current_balance:100,color:'#126046',icon:'wallet'};
 const screen=home.fixture(async()=>home.positive,[],[account]);screen.render();let rendered=await screen.settle();
 assert.deepEqual(home.styled(rendered,'statTitle').map(home.text),[en.ui.total_income,en.ui.total_spent,en.ui.month_balance]);
 const originalAmounts=home.styled(rendered,'statAmount').map(home.text),readCount=screen.calls();
 assert(home.text(home.find(rendered,'wallet-custom')).includes(account.name));
 await support.setTestLocale('es');rendered=screen.render();
 assert.deepEqual(home.styled(rendered,'statTitle').map(home.text),[es.ui.total_income,es.ui.total_spent,es.ui.month_balance]);
 assert.deepEqual(home.styled(rendered,'statAmount').map(home.text),originalAmounts);assert.equal(screen.calls(),readCount);
 assert(home.text(home.find(rendered,'wallet-custom')).includes(account.name));
 await support.setTestLocale('en-US');rendered=screen.render();assert.deepEqual(home.styled(rendered,'statTitle').map(home.text),[en.ui.total_income,en.ui.total_spent,en.ui.month_balance]);assert.equal(screen.calls(),readCount);screen.close();
 console.log('PASS: actual Home rerenders English/Spanish/English with cached queries, unchanged financial amounts and verbatim custom account name.');
})().catch(error=>{console.error(error);process.exitCode=1;});
