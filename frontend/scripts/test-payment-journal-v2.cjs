const {localeGlobals,localeMocks,normalizeUI}=require('./i18n-test-support.cjs');
// Prepared v2 journal only; no activation, native storage, HTTP or database.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ts = require('typescript'), root = path.resolve(__dirname, '..');
const compile = file => ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsV2 = {};
vm.runInNewContext(compile('src/debt-payments/journal-v2.ts'), localeGlobals({ exports: exportsV2, Map, WeakMap, Error, Promise }));
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const context = (environment_id = A, user_id = 'default-user') => ({ version: 1, environment_id, user_id, mode: 'single_user',
  capabilities: { expected_context_headers: true, debt_payment_reconciliation: false, cross_device_recovery: false } });
const record = (changes = {}) => ({ version: 2, environment_id: A, user_id: 'default-user', key: 'original-key',
  payload: { debt_id: 'd', amount: 100, account_id: 'a', notes: '', date: null }, state: 'pending', ...changes });
const plain = data => JSON.parse(JSON.stringify(data));
function fixture() {
  const disk = new Map(), flags = { read: false, write: false, remove: false, network: false };
  let effective = context(), url = 'http://first.invalid';
  const storage = {
    async getAllKeys() { if (flags.read) throw Error('storage read failure'); return [...disk.keys()]; },
    async getItem(k) { if (flags.read) throw Error('storage read failure'); return disk.get(k) ?? null; },
    async setItem(k,v) { if (flags.write) throw Error('storage write failure'); disk.set(k,v); },
    async removeItem(k) { if (flags.remove) throw Error('storage cleanup failure'); disk.delete(k); },
  };
  const read = async () => { if (flags.network) throw Error('context network failure'); return effective; };
  return { disk, flags, storage, fresh: () => exportsV2.createV2Journal(storage, read),
    setContext: value => effective = value, changeUrl: value => url = value };
}
async function main() {
  let f = fixture(), j = f.fresh();
  await j.save(record()); const before = [...f.disk];
  f.changeUrl('http://second-alias.invalid'); j = f.fresh();
  assert.deepEqual(plain(await j.recover()), record()); assert.deepEqual([...f.disk], before);
  await j.save(record()); assert.deepEqual([...f.disk], before);
  console.log('PASS v2: serialization, restart and URL alias retain identity, key and exact payload');

  for (const value of [context(B), context(A, 'other-effective-user')]) {
    f.setContext(value); await assert.rejects(j.recover()); await assert.rejects(j.save(record({ environment_id: value.environment_id, user_id: value.user_id, key: 'new-key' })));
    assert.deepEqual([...f.disk], before);
  }
  f.setContext(context());
  for (const replacement of [record({ key: 'new-key' }), record({ payload: { ...record().payload, amount: 200 } }), record({ environment_id: B })]) {
    await assert.rejects(j.save(replacement)); assert.deepEqual([...f.disk], before);
  }
  console.log('PASS v2: context/user changes and reassignment blocked; pending key/payload cannot change');

  const confirmed = record({ state: 'confirmed', receipt: { id: 'p', transaction_id: 't' } });
  await j.save(confirmed); await assert.rejects(j.save(record()));
  f.setContext(context(B)); await j.save(record({ environment_id: B, key: 'environment-b' }));
  assert.equal((await j.recover()).environment_id, B); assert.equal(f.disk.size, 2);
  console.log('PASS v2: independent environment journals coexist without overwriting old confirmation');

  f = fixture(); j = f.fresh(); f.disk.set('moneyflow:debt-payment:v1:old-url', JSON.stringify({ version: 1, key: 'legacy' }));
  const legacy = [...f.disk]; await assert.rejects(j.recover()); await assert.rejects(j.save(record()));
  assert.deepEqual([...f.disk], legacy);
  console.log('PASS v2: v1 data remains byte-for-byte intact; no automatic migration/deletion');

  for (const flag of ['read','write','network']) {
    f = fixture(); j = f.fresh(); f.flags[flag] = true;
    await assert.rejects(j.save(record())); assert.equal(f.disk.size, 0);
  }
  f = fixture(); j = f.fresh(); await j.save(record());
  const key = [...f.disk.keys()][0]; f.disk.set(key, '{}');
  await assert.rejects(j.recover()); assert.equal(f.disk.get(key), '{}');
  for (const badContext of [{}, { ...context(), environment_id: 'not-a-uuid' }, { ...context(), mode: 'authenticated' }, { ...context(), capabilities: {} }]) {
    f = fixture(); f.setContext(badContext); await assert.rejects(f.fresh().save(record())); assert.equal(f.disk.size, 0);
  }
  console.log('PASS v2: invalid context, corrupt storage and network/write failures fail closed');

  f = fixture(); j = f.fresh(); await j.save(record());
  await assert.rejects(j.clearConfirmed('original-key'));
  await j.save(confirmed); f.flags.remove = true; await assert.rejects(j.clearConfirmed('original-key'));
  assert.equal((await j.recover()).state, 'confirmed');
  f.flags.remove = false; await j.clearConfirmed('original-key');
  await j.save(record({ key: 'explicit-new-intention' })); assert.equal((await j.recover()).key,'explicit-new-intention');
  console.log('PASS v2: only explicit matched confirmation can clear; failed cleanup retains evidence');

  f = fixture(); const results = await Promise.allSettled([f.fresh().save(record()), f.fresh().save(record({ key: 'competing-key' }))]);
  assert.equal(results.filter(r=>r.status==='fulfilled').length, 1);
  assert.equal((await f.fresh().recover()).key, 'original-key');
  console.log('PASS v2: simultaneous journals cannot replace a pending intention');

  const api = {}, requests = [];
  vm.runInNewContext(compile('src/api.ts'), localeGlobals({ exports: api, process: { env: { EXPO_PUBLIC_BACKEND_URL: 'http://synthetic.invalid' } },
    fetch: async (url, options) => { requests.push({ url, options }); return { ok: true, json: async()=>context() }; } }));
  await api.api.createDebtPayment({}, 'legacy-r6-key');
  assert(!('MoneyFlow-Environment-ID' in requests[0].options.headers));
  await api.api.createContextProtectedDebtPayment({}, 'protected-key', context());
  assert.equal(requests[1].options.headers['MoneyFlow-Environment-ID'], A);
  assert.equal(requests[1].options.headers['MoneyFlow-User-ID'],'default-user');
  await api.api.getFinancialContext(); assert(requests[2].url.endsWith('/api/financial-context'));
  await api.api.reconcileDebtPayment(record().payload, 'original-key', context());
  assert(requests[3].url.endsWith('/api/debt-payments/reconcile'));
  assert.equal(requests[3].options.method,'POST');
  assert.equal(requests[3].options.headers['Idempotency-Key'],'original-key');
  assert.equal(requests[3].options.headers['MoneyFlow-Environment-ID'],A);
  assert.deepEqual(JSON.parse(requests[3].options.body),record().payload);
  await api.api.reconcileDebtPayment(record().payload, 'original-key');
  assert(!('MoneyFlow-Environment-ID' in requests[4].options.headers));
  const screen = fs.readFileSync(path.join(root,'app/debts/[id]/pay.tsx'),'utf8');
  assert(screen.includes('local-flow') && !screen.includes('getFinancialContext'));
  console.log('PASS v2: API helpers available; screen uses the separately tested local activation gate');
}
main().catch(e=>{console.error(e);process.exitCode=1});
