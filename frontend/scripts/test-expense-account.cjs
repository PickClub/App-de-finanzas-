// Actual transaction save handler, synthetic API only; no financial storage.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), ts = require('typescript');
const { createInstance } = require('i18next');
const engine = createInstance(); engine.init({ lng: 'en-US', fallbackLng: 'en-US', initImmediate: false, resources: { 'en-US': { translation: require('../src/i18n/locales/en.json') }, es: { translation: require('../src/i18n/locales/es.json') } } });
const source = ts.createSourceFile('form.tsx', fs.readFileSync('frontend/app/transactions/new.tsx', 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler; function visit(node) { if (ts.isVariableDeclaration(node) && node.name.getText(source) === 'save') handler = node.initializer.getText(source); ts.forEachChild(node, visit); } visit(source);
function fixture(overrides = {}) {
  const calls = [], alerts = [], routes = [];
  const context = { savingRef: { current: false }, deletion: { locked: { current: false } }, resourceLoaded: true, finalAmount: 56.25, calcError: null,
    type: 'expense', accountId: undefined, accounts: [{ id: 'valid' }, { id: 'deleted', deleted: true }], name: 'Preserve description', notes: 'Preserve notes', categoryId: 'category', toAccountId: undefined, params: {}, sourceQ: {}, sourceId: undefined,
    round2: value => Math.round(value * 100) / 100, setSaving() {}, tr: engine.t.bind(engine), localizedError: value => value,
    Alert: { alert: (...args) => alerts.push(args) }, qc: { invalidateQueries() {} }, router: { back: () => routes.push('back') },
    api: { createTransaction: async payload => { calls.push(payload); if (context.reject) throw Error('Server rejected'); if (context.hold) await context.hold; }, updateTransaction: async (id, payload) => { calls.push({ id, ...payload }); } }, ...overrides };
  vm.createContext(context); vm.runInContext(ts.transpileModule('globalThis.save = ' + handler, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context);
  return { context, calls, alerts, routes };
}
async function main() {
  for (const lang of ['en-US', 'es']) {
    await engine.changeLanguage(lang);
    for (const accountId of [undefined, null, '', 'missing', 'deleted']) for (const params of [{}, { id: 'existing' }]) {
      const f = fixture({ accountId, params }); await f.context.save(); assert.equal(f.calls.length, 0); assert.equal(f.routes.length, 0); assert.equal(f.context.name, 'Preserve description'); assert.equal(f.context.notes, 'Preserve notes'); assert.equal(f.context.finalAmount, 56.25); assert.equal(f.alerts[0][1], engine.t('transactions.expenseSourceRequired'));
    }
    let release; const f = fixture({ accountId: 'valid', hold: new Promise(resolve => { release = resolve; }) });
    const saving = f.context.save(); await f.context.save(); assert.equal(f.calls.length, 1); release(); await saving; assert.equal(f.routes.length, 1); assert.equal(f.calls[0].account_id, 'valid');
    const rejected = fixture({ accountId: 'valid', reject: true }); await rejected.context.save(); assert.equal(rejected.routes.length, 0); assert.equal(rejected.context.name, 'Preserve description'); assert(rejected.alerts.length);
    const income = fixture({ type: 'income' }); await income.context.save(); assert.equal(income.calls.length, 1);
  }
  console.log('PASS: EN/ES actual save handler rejects absent/invalid/deleted accounts on create/edit without losing fields; valid expense, double-tap guard, rejection without navigation, income behavior unchanged.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
