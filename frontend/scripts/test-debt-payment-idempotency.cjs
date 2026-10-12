// Actual R6 coordinator/API/save handler; storage and server are synthetic only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const compile = file => ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
}).outputText;
class ApiError extends Error { constructor(status) { super(`HTTP ${status}`); this.status = status; } }
const mod = { exports: {} };
const journal = {};
vm.runInNewContext(compile('src/debt-payments/journal-v2.ts'), { exports: journal });
vm.runInNewContext(compile('src/debt-payments/pending.ts'), { exports: mod.exports, module: mod,
  require: name => name === './journal-v2' ? journal : name.includes('async-storage') ? {} : { ApiError, api: {}, debtPaymentBackend: () => '' },
  Map, Error, JSON, Date, Math, Array, Promise,
});
const create = mod.exports.createPaymentCoordinator;
const data = (changes = {}) => ({ debt_id: 'd', amount: 100, account_id: 'a', notes: '', date: null, ...changes });
const plain = obj => JSON.parse(JSON.stringify(obj));
function fixture() {
  const disk = new Map(), paid = new Map(), events = [], calls = [];
  let backend = 'http://synthetic-a.invalid', serial = 0, lost = false, gate;
  const flags = { read: false, write: false, confirm: false, remove: false, corruptVerify: false, conflict: false, badResponse: false };
  const store = {
    async getAllKeys() { if (flags.read) throw Error('read failed'); return [...disk.keys()]; },
    async getItem(key) { if (flags.read) throw Error('read failed'); return disk.get(key) ?? null; },
    async setItem(key, raw) { const record = JSON.parse(raw); events.push(record.state);
      if (flags.write || (flags.confirm && record.state === 'confirmed')) throw Error('write failed');
      disk.set(key, flags.corruptVerify ? '{}' : raw);
    },
    async removeItem(key) { events.push('remove'); if (flags.remove) throw Error('remove failed'); disk.delete(key); },
  };
  async function send(payload, key) {
    calls.push({ backend, key, payload: plain(payload) }); events.push('send');
    if (gate) await gate;
    if (flags.conflict) throw new ApiError(409);
    const slot = backend + key, fingerprint = JSON.stringify(payload);
    if (paid.has(slot) && paid.get(slot).fingerprint !== fingerprint) throw new ApiError(409);
    if (!paid.has(slot)) paid.set(slot, { fingerprint, receipt: { ...plain(payload), id: `p${paid.size}`, transaction_id: `t${paid.size}` } });
    if (lost) { lost = false; throw Error('response lost after commit'); }
    const result = paid.get(slot).receipt;
    return flags.badResponse ? { ...result, amount: 999 } : result;
  }
  const fresh = () => create({ storage: store, backend: () => backend, newKey: () => `key-${++serial}`, send });
  return { disk, paid, events, calls, flags, store, fresh, lose: () => { lost = true; },
    destination: b => { backend = b; }, hold: () => { let release; gate = new Promise(r => release = r); return () => { gate = null; release(); }; } };
}
async function main() {
  let f = fixture(), c = f.fresh(); f.lose();
  await assert.rejects(c.submit(data()));
  assert.equal(f.paid.size, 1); assert.equal(f.disk.size, 1);
  const pending = plain(await c.recover());
  assert.equal(pending.state, 'pending');
  c = f.fresh(); // New runtime/screen, same durable storage.
  const restored = plain(await c.recover()); assert.deepEqual(restored, pending); assert.equal(f.calls.length, 1);
  await c.submit(restored.payload);
  assert.equal(f.paid.size, 1); assert.equal(f.calls[0].key, f.calls[1].key);
  assert.deepEqual(f.calls[0].payload, f.calls[1].payload); assert.equal(f.disk.size, 1);
  assert.equal(plain(await c.recover()).state, 'confirmed');
  await assert.rejects(c.submit(data()));
  await c.startNew();
  assert.equal(f.disk.size, 0);
  assert(f.events.indexOf('pending') < f.events.indexOf('send'));
  assert(f.events.indexOf('confirmed') < f.events.indexOf('remove'));
  await c.submit(data()); assert.equal(f.paid.size, 2); assert.notEqual(f.calls[1].key, f.calls[2].key);
  console.log('PASS: response loss/restart/exact replay; durable intention before send; confirmation before cleanup; legitimate second payment');

  f = fixture(); c = f.fresh(); const release = f.hold();
  const first = c.submit(data()), second = c.submit(data());
  await assert.rejects(c.submit(data({ amount: 200 })));
  await new Promise(r => setImmediate(r)); assert.equal(f.calls.length, 1);
  release(); await Promise.all([first, second]); assert.equal(f.paid.size, 1);
  console.log('PASS: concurrent double submission coalesces; different concurrent payment blocked');
  // A reset cannot race with a submit and erase a newly persisted intention.
  const originalRemove = f.store.removeItem;
  let finishReset;
  f.store.removeItem = async key => { await new Promise(resolve => finishReset = resolve); return originalRemove(key); };
  const resetting = c.startNew(); await new Promise(r => setImmediate(r));
  await assert.rejects(c.submit(data())); await assert.rejects(c.startNew());
  assert.equal(f.calls.length, 1); finishReset(); await resetting;
  f.store.removeItem = originalRemove;
  await c.submit(data()); assert.equal(f.paid.size, 2);
  console.log('PASS: explicit reset and submission cannot race; reset performs no financial request');


  for (const flag of ['read', 'write', 'corruptVerify']) {
    f = fixture(); c = f.fresh(); f.flags[flag] = true;
    await assert.rejects(c.submit(data())); assert.equal(f.calls.length, 0);
  }
  f = fixture(); c = f.fresh(); f.disk.set('moneyflow:debt-payment:v1:http%3A%2F%2Fsynthetic-a.invalid', 'not json');
  await assert.rejects(c.recover()); await assert.rejects(c.submit(data())); assert.equal(f.calls.length, 0);
  f = fixture(); c = f.fresh(); f.lose(); await assert.rejects(c.submit(data()));
  f.flags.write = true; await assert.rejects(f.fresh().submit(data())); assert.equal(f.calls.length, 1);
  console.log('PASS: read/write/readback/corruption errors block first send and retries');

  f = fixture(); c = f.fresh(); f.flags.confirm = true;
  await assert.rejects(c.submit(data())); assert.equal(f.paid.size, 1); assert.equal(f.disk.size, 1);
  f.flags.confirm = false; await f.fresh().submit(data()); assert.equal(f.paid.size, 1);
  f = fixture(); c = f.fresh(); f.flags.remove = true;
  await c.submit(data()); assert.equal(plain(await f.fresh().recover()).state, 'confirmed');
  await assert.rejects(f.fresh().submit(data({ amount: 200 })));
  await assert.rejects(f.fresh().submit(data()));
  await assert.rejects(f.fresh().startNew());
  assert.equal(f.calls.length, 1); assert.equal(f.paid.size, 1);
  f.flags.remove = false; await f.fresh().startNew(); assert.equal(f.calls.length, 1); assert.equal(f.disk.size, 0);
  await f.fresh().submit(data({ amount: 200 })); assert.equal(f.paid.size, 2);
  console.log('PASS: confirmation persistence failure retries same key; cleanup failure survives restart without another request');

  f = fixture(); c = f.fresh(); f.lose(); await assert.rejects(c.submit(data()));
  for (const change of [{ amount: 200 }, { account_id: 'b' }, { debt_id: 'other' }, { notes: 'changed' }, { date: '2026-10-12' }]) {
    await assert.rejects(f.fresh().submit(data(change)));
  }
  assert.equal(f.calls.length, 1);
  f.destination('http://synthetic-b.invalid'); const other = f.fresh();
  assert.equal(await other.recover(), null); await other.submit(data()); assert.equal(f.paid.size, 2);
  f.destination('http://synthetic-a.invalid'); const recovered = plain(await f.fresh().recover());
  assert.equal(recovered.key, f.calls[0].key); await f.fresh().submit(recovered.payload); assert.equal(f.paid.size, 2);
  console.log('PASS: every payload field frozen; backends have separate pending journals and no cross-environment replay');

  f = fixture(); c = f.fresh(); f.flags.conflict = true;
  await assert.rejects(c.submit(data())); assert.equal(plain(await c.recover()).state, 'conflict');
  f.flags.conflict = false; await assert.rejects(f.fresh().submit(data()));
  await assert.rejects(f.fresh().submit(data({ amount: 200 }))); assert.equal(f.calls.length, 1); assert.equal(f.disk.size, 1);
  f = fixture(); c = f.fresh(); f.flags.badResponse = true;
  await assert.rejects(c.submit(data())); assert.equal(plain(await c.recover()).state, 'pending');
  f.flags.badResponse = false; await f.fresh().submit(data()); assert.equal(f.paid.size, 1);
  console.log('PASS: HTTP 409 remains unresolved and blocks replay; mismatching receipt cannot mark confirmation');

  // Actual API wrapper, using mocked fetch only.
  const apiExports = {}, wire = [];
  vm.runInNewContext(compile('src/api.ts'), { exports: apiExports, process: { env: { EXPO_PUBLIC_BACKEND_URL: 'http://synthetic.invalid' } },
    fetch: async (url, options) => { wire.push({ url, options }); return { ok: true, json: async () => ({}) }; } });
  await apiExports.api.createDebtPayment(data(), 'stable-key');
  assert.equal(wire[0].options.headers['Idempotency-Key'], 'stable-key');
  assert.deepEqual(JSON.parse(wire[0].options.body), data());

  // Execute the actual screen handler and recovery effect with synthetic hooks.
  const src = fs.readFileSync(path.join(root, 'app/debts/[id]/pay.tsx'), 'utf8');
  const tree = ts.createSourceFile('pay.tsx', src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let handler, effect;
  const visit = n => {
    if (ts.isVariableDeclaration(n) && n.name.getText(tree) === 'save') handler = n.initializer.getText(tree);
    if (ts.isCallExpression(n) && n.expression.getText(tree) === 'useEffect') effect = n.arguments[0].getText(tree);
    ts.forEachChild(n, visit);
  }; visit(tree);
  f = fixture(); c = f.fresh();
  let operation = null, navigation = 0;
  const ctx = { Error, operation: null, amt: 100, d: { id: 'd' }, params: { id: 'd' }, accountId: 'a', notes: '',
    recoveryReady: { current: false }, recoveryError: { current: null }, savingRef: { current: false },
    setSaving: () => {}, setReady: () => {}, Alert: { alert: () => {} }, qc: { invalidateQueries: () => {} },
    router: { back: () => navigation++ }, pendingDebtPayments: c,
    setOperation: record => { operation = record; ctx.operation = record; }, setAmount: value => ctx.amt = parseFloat(value) || 0,
    setAccountId: value => ctx.accountId = value, setNotes: value => ctx.notes = value };
  vm.createContext(ctx); vm.runInContext(ts.transpileModule('globalThis.save = '+handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, ctx);
  vm.runInContext('globalThis.effect = '+effect, ctx);
  await ctx.save(); assert.equal(f.calls.length, 0);
  ctx.effect(); await new Promise(r => setImmediate(r)); assert.equal(ctx.recoveryReady.current, true);
  const finish = f.hold(); const waiting = ctx.save(); await new Promise(r => setImmediate(r));
  await ctx.save(); assert.equal(f.calls.length, 1); finish(); await waiting;
  assert.equal(operation.state, 'confirmed'); assert.equal(navigation, 0);
  await ctx.save(); // Explicit new-payment action; does not submit the old values.
  assert.equal(operation, null); assert.equal(ctx.amt, 0); assert.equal(f.calls.length, 1);
  await ctx.save(); assert.equal(f.calls.length, 1); // Empty new form cannot pay.
  ctx.amt = 100; ctx.accountId = 'a'; await ctx.save();
  assert.equal(f.paid.size, 2); assert.notEqual(f.calls[0].key, f.calls[1].key);
  console.log('PASS: screen separates confirmed result from explicit empty new form; identical legitimate second payment uses new key');

  // Restore exact payload while ignoring mutable/stale form values on retries.
  f = fixture(); c = f.fresh(); const original = data({ amount: 100.25, account_id: null, notes: null, date: '2026-10-12T00:00:00Z' });
  f.lose(); await assert.rejects(c.submit(original));
  ctx.pendingDebtPayments = f.fresh(); ctx.effect(); await new Promise(r => setImmediate(r));
  assert.equal(ctx.amt, 100.25); assert.equal(ctx.accountId, undefined); assert.equal(ctx.notes, '');
  ctx.amt = 999; ctx.notes = 'stale edits'; await ctx.save();
  assert.deepEqual(f.calls[1].payload, original); assert.equal(f.calls[0].key, f.calls[1].key);
  assert.equal(operation.state, 'confirmed');
  f.flags.remove = true; await ctx.save(); assert.equal(operation.state, 'confirmed'); assert.equal(f.calls.length, 2);
  assert.equal(ctx.amt, 100.25); // Failed cleanup restores the old confirmed display, not a new payment.
  console.log('PASS: recovery retries only original data; cleanup failure cannot report a new payment as successful');

  f = fixture(); c = f.fresh(); f.flags.conflict = true; await assert.rejects(c.submit(data()));
  ctx.pendingDebtPayments = f.fresh(); ctx.effect(); await new Promise(r => setImmediate(r));
  await ctx.save(); assert.equal(operation.state, 'conflict'); assert.equal(f.calls.length, 1);
  let finishRecovery;
  ctx.pendingDebtPayments = { recover: () => new Promise(resolve => finishRecovery = resolve) };
  const cleanup = ctx.effect(); cleanup(); finishRecovery({ debtId: 'd', payload: original });
  await new Promise(r => setImmediate(r)); assert.equal(ctx.recoveryReady.current, false);
  ctx.pendingDebtPayments.recover = async () => { throw Error('synthetic read failure'); };
  ctx.effect(); await new Promise(r => setImmediate(r)); assert.equal(ctx.recoveryReady.current, false);
  console.log('PASS: discrepant payments stay blocked; unmounted/failed recovery cannot enable sending');

  const viewExports = {};
  vm.runInNewContext(compile('src/debt-payments/view.ts'), { exports: viewExports });
  const view = viewExports.paymentView;
  assert.equal(view(null, 'd', true).preview, true);
  for (const state of ['pending', 'conflict', 'confirmed']) {
    const display = view({ state, debtId: 'd' }, 'd', true);
    assert.equal(display.preview, false); assert.equal(display.editable, false);
  }
  assert.equal(view({ state: 'pending', debtId: 'd' }, 'd', true).action, 'Reintentar pago anterior');
  assert.equal(view({ state: 'confirmed', debtId: 'd' }, 'd', true).action, 'Registrar nuevo pago');
  assert.equal(view({ state: 'conflict', debtId: 'd' }, 'd', true).action, 'Requiere conciliación');
  assert.equal(view({ state: 'pending', debtId: 'other' }, 'd', true).preview, false);
  assert.equal(view(null, 'd', false).editable, false);
  // The actual JSX uses the tested view state rather than only testing a label helper.
  assert(src.includes('view.preview && amt > 0'));
  assert(src.includes('editable={view.editable && !saving}'));
  console.log('PASS: recovered/confirmed/discrepant states have distinct actions, locked fields and no fictitious additional-discount preview');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
