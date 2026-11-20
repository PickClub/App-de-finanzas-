// Actual date expressions and helpers, controlled TZ/clock, no API or storage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '../..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
function variables(file) {
  const tree = ts.createSourceFile(file, read(file), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found = {};
  function visit(n) {
    if (ts.isVariableDeclaration(n) && n.initializer) found[n.name.getText(tree)] = n.initializer.getText(tree);
    ts.forEachChild(n, visit);
  }
  visit(tree); return found;
}
function run(source, context) {
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS,
  }}).outputText, context);
}
let passed = 0;
function check(name, action) { action(); passed++; console.log('PASS:', name); }
function clock(iso) {
  const Native = Date;
  return class extends Native {
    constructor(...args) { super(...(args.length ? args : [iso])); }
    static now() { return Native.parse(iso); }
  };
}
function main() {
  // Each zone runs in a fresh process so timezone changes cannot leak/cache.
  if (!process.env.C3_R9_TZ_CASE) {
    for (const zone of ['America/Chicago', 'UTC', 'Pacific/Kiritimati']) {
      cp.execFileSync(process.execPath, [__filename], {
        env: { ...process.env, TZ: zone, C3_R9_TZ_CASE: zone }, stdio: 'inherit',
      });
    }
    return;
  }
  const zone = process.env.C3_R9_TZ_CASE;
  console.log('Zone:', zone);
  check('all-day component construction preserves leap/month/year days', () => {
    for (const [y, m, d] of [[2024,2,29], [2026,1,1], [2026,12,31]]) {
      const local = new Date(y,m-1,d);
      assert.deepEqual([local.getFullYear(),local.getMonth()+1,local.getDate()], [y,m,d]);
    }
  });
  check('UTC instant retains exact value across local rendering', () => {
    const original = '2026-01-01T00:00:00.000Z';
    assert.equal(new Date(original).toISOString(), original);
  });
  const all = variables('frontend/app/transactions/all.tsx');
  check('C1 account filter retains incoming/outgoing and distinct equal payments', () => {
    const rows = [
      {id:'a',type:'transfer',account_id:'A',to_account_id:'B',amount:70,date:'2026-10-01T12:00:00Z'},
      {id:'b',type:'transfer',account_id:'B',to_account_id:'A',amount:70,date:'2026-10-01T12:00:00Z'},
      {id:'c',type:'expense',account_id:'B',to_account_id:'A',amount:70,date:'2026-10-01T12:00:00Z'},
    ];
    const context = { useMemo:f=>f(), accountId:'A', categoryId:undefined, type:'all', sort:'recent',
      range:{start:0,end:Date.parse('2026-10-31T23:59:59.999Z')}, Date };
    run('globalThis.result=' + all.filters, context);
    assert.equal(context.result.account_id,'A');
    assert.equal(context.result.types,undefined);
    assert.equal(context.result.end,'2026-11-01T00:00:00.000Z');
    // Transfer participation is now evaluated by the paged backend. This
    // contract sends the account once, without narrowing to origin-only IDs.
    assert.deepEqual(rows.filter(x=>x.account_id===context.result.account_id || (x.type==='transfer'&&x.to_account_id===context.result.account_id)).map(x=>x.id).sort(), ['a','b']);
    assert.equal(rows.length,3);
  });
  const rp = variables('frontend/app/recurring/[id].tsx');
  const helperFile = 'frontend/src/goals/shared.tsx';
  const helperTree = ts.createSourceFile(helperFile, read(helperFile), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const helper = helperTree.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'toYmd');
  assert(helper, 'Recurring payments must reuse the existing local-day helper');
  assert.match(read('frontend/src/recurring/shared.tsx'), /export \{[^}]*toYmd[^}]*\} from "@\/src\/goals\/shared"/);
  assert.match(read('frontend/app/recurring/[id].tsx'), /import \{[^}]*toYmd[^}]*\} from "@\/src\/recurring\/shared"/);
  const localDay = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const boundaries = [
    {instant:'2026-01-01T05:30:00Z', today:zone==='America/Chicago'?'2025-12-31':'2026-01-01', start:zone==='America/Chicago'?'2025-12-25':'2025-12-26'},
    {instant:'2026-03-09T05:30:00Z', today:'2026-03-09', start:'2026-03-03'},
    {instant:'2026-11-02T06:30:00Z', today:'2026-11-02', start:'2026-10-27'},
    {instant:'2024-03-01T12:00:00Z', today:zone==='Pacific/Kiritimati'?'2024-03-02':'2024-03-01', start:zone==='Pacific/Kiritimati'?'2024-02-25':'2024-02-24'},
    {instant:'2026-12-31T12:30:00Z', today:zone==='Pacific/Kiritimati'?'2027-01-01':'2026-12-31', start:zone==='Pacific/Kiritimati'?'2026-12-26':'2026-12-25'},
  ];
  check('recurring today uses local day at midnight, leap and year boundaries', () => {
    for (const fixture of boundaries) {
      const context = {Date:clock(fixture.instant),exports:{}};
      run(helper.getText(helperTree),context);
      context.toYmd = context.exports.toYmd;
      run('globalThis.result=' + rp.todayIso,context);
      assert.equal(context.result,fixture.today,fixture.instant);
    }
  });
  check('seven-day history preserves exactly seven calendar days across DST and boundaries', () => {
    for (const fixture of boundaries) {
      const context = {Date:clock(fixture.instant),useMemo:f=>f(),period:'7d',DAY:86400000,cursor:new Date(2026,2,1),custom:null};
      run(`const startOfDay=${all.startOfDay};const endOfDay=${all.endOfDay};globalThis.result=${all.range};`,context);
      const start = new Date(context.result.start), end = new Date(context.result.end);
      assert.equal(localDay(start),fixture.start,fixture.instant);
      assert.equal(localDay(end),fixture.today,fixture.instant);
      assert.deepEqual([start.getHours(),start.getMinutes(),start.getSeconds(),start.getMilliseconds()],[0,0,0,0]);
      assert.deepEqual([end.getHours(),end.getMinutes(),end.getSeconds(),end.getMilliseconds()],[23,59,59,999]);
    }
  });
  check('long date preserves all-day values and actual instant semantics in English and Spanish', () => {
    let language = 'en-US';
    const context = {exports:{},require:()=>({default:{get language(){return language;}},localeTag:()=>language==='es'?'es-US':'en-US'})};
    run(read('frontend/src/format.ts'),context);
    for (language of ['en-US','es']) {
      const tag=language==='es'?'es-US':'en-US', options={day:'2-digit',month:'long',year:'numeric'};
      for (const iso of ['2026-01-01','2024-02-29','2026-12-31','0099-01-01']) {
        const [year,month,day]=iso.split('-').map(Number), expected=new Date(0);
        expected.setFullYear(year,month-1,day);expected.setHours(0,0,0,0);
        assert.equal(context.exports.formatDateLong(iso),expected.toLocaleDateString(tag,options),`${tag}:${iso}`);
      }
      for (const iso of ['2026-01-01T00:00:00.000Z','2026-01-01T12:30:45-06:00','2026-01-01T12:30:45']) {
        assert.equal(context.exports.formatDateLong(iso),new Date(iso).toLocaleDateString(tag,options),`${tag}:${iso}`);
      }
      assert.equal(context.exports.formatCurrencyInt(2679),'$2,679');
    }
  });
  console.log(`RESULT ${zone}: ${passed} passing checks, 0 expected defects`);
}
try { main(); } catch (error) { console.error(error); process.exitCode=1; }
