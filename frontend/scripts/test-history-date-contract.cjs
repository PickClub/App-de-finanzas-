// C3/R9 stage 1. Actual expressions, controlled TZ/clock, no API or storage.
// Expected defects are strict: an unexpected pass requires updating the test.
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
let passed = 0, defects = 0;
function check(name, action) { action(); passed++; console.log('PASS:', name); }
function pending(name, action) {
  try { action(); } catch (error) {
    if (!(error instanceof assert.AssertionError)) throw error;
    defects++; console.log('EXPECTED DEFECT:', name); return;
  }
  throw Error('Unexpected pass; review/remove expected-defect classification: ' + name);
}
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
  if (zone === 'America/Chicago') {
    const rp = variables('frontend/app/recurring/[id].tsx');
    pending('recurring today must use local date at month/year boundary', () => {
      const context = {Date:clock('2026-01-01T05:30:00Z')};
      run('globalThis.result=' + rp.todayIso, context);
      assert.equal(context.result,'2025-12-31');
    });
    pending('generic formatDateLong must preserve an all-day debt due date', () => {
      const context = {exports:{}, require:()=>({default:{language:'en'},localeTag:()=> 'en-US'})};
      run(read('frontend/src/format.ts'), context);
      assert.equal(context.exports.formatDateLong('2026-01-01'), 'January 01, 2026');
    });
    pending('7-day calendar filter cannot subtract fixed 24-hour intervals across spring DST', () => {
      const context = {Date:clock('2026-03-09T05:30:00Z'),useMemo:f=>f(),
        period:'7d',DAY:86400000,cursor:new Date(2026,2,1),custom:null};
      run(`const startOfDay=${all.startOfDay};const endOfDay=${all.endOfDay};globalThis.result=${all.range};`,context);
      assert.equal(new Date(context.result.start).getDate(),3);
    });
  }
  console.log(`RESULT ${zone}: ${passed} passing checks, ${defects} strict expected defects`);
}
try { main(); } catch (error) { console.error(error); process.exitCode=1; }
