// Real form, presentation and legacy coordinator; synthetic storage/server only.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), ts = require('typescript');
const { createInstance } = require('i18next');
const { headerActionNodes } = require('./i18n-test-support.cjs');
const { QueryClient } = require('@tanstack/react-query');
const engine = createInstance();
engine.init({ lng: 'en-US', fallbackLng: 'en-US', initImmediate: false, resources: { 'en-US': { translation: require('../src/i18n/locales/en.json') }, es: { translation: require('../src/i18n/locales/es.json') } } });
const compile = file => ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const load = (file, mocks) => { const exports = {}; vm.runInNewContext(compile(file), { exports, require: name => { assert(name in mocks, name); return mocks[name]; } }); return exports; };
class ApiError extends Error { constructor(status) { super('HTTP ' + status); this.status = status; } }
const journal = load('frontend/src/debt-payments/journal-v2.ts', {});
const pending = load('frontend/src/debt-payments/pending.ts', { '@react-native-async-storage/async-storage': {}, '../api': { ApiError }, './journal-v2': journal });
const v2 = load('frontend/src/debt-payments/flow-v2.ts', { '../api': { ApiError }, './journal-v2': journal });
const presentation = load('frontend/src/debt-payments/view.ts', { '@/src/i18n': { tr: engine.t.bind(engine) } });
const tick = () => new Promise(setImmediate);
const all = n => !n || typeof n !== 'object' ? [] : [n, ...[n.props?.children, ...headerActionNodes(n)].flat(Infinity).flatMap(all)];
function fixture(version = 1) {
  let id = 'A', key = 0, cursor = 0, mountedKey;
  let cells = [], effects = [], deps = [], cleanups = [];
  const disk = new Map(), ledger = new Map(), calls = [], routes = [], alerts = [], invalidations = [];
  const flags = {};
  const storage = { getAllKeys: async () => [...disk.keys()], getItem: async k => disk.get(k) ?? null, setItem: async (k, v) => { disk.set(k, v); }, removeItem: async k => { if (flags.remove) throw Error('Storage unavailable'); disk.delete(k); } };
  const send = async (payload, intent) => {
    calls.push({ payload: JSON.parse(JSON.stringify(payload)), intent });
    if (flags.conflict) throw new ApiError(409);
    if (flags.reject) throw new ApiError(422);
    if (!ledger.has(intent)) ledger.set(intent, { ...payload, id: 'payment-' + intent, transaction_id: 'tx-' + intent });
    if (flags.lost) throw Error('Lost response');
    return ledger.get(intent);
  };
  const context = { version: 1, environment_id: '11111111-1111-4111-8111-111111111111', user_id: 'synthetic-user', mode: 'single_user', capabilities: { expected_context_headers: true, debt_payment_reconciliation: true, cross_device_recovery: false } };
  const flow = version === 1 ? pending.createPaymentCoordinator({ storage, backend: () => 'http://synthetic.invalid', newKey: () => 'key-' + ++key, send }) : v2.createV2PaymentFlow({
    storage, expected: context, readContext: async () => context, newKey: () => 'key-' + ++key, send,
    reconcile: async (payload, intent) => {
      const payment = ledger.get(intent);
      return payment ? { status: 'matched', original_request_matches: true, current_payment: payment } : { status: 'not_found' };
    },
  });
  const react = { useRef: value => { const i = cursor++; return cells[i] ??= { current: value }; }, useState: value => { const i = cursor++; if (!(i in cells)) cells[i] = value; return [cells[i], next => { cells[i] = next; }]; }, useEffect: (fn, values) => { const i = cursor++; if (!deps[i] || values.some((v, j) => v !== deps[i][j])) { deps[i] = values; effects.push(() => { cleanups[i]?.(); cleanups[i] = fn(); }); } } };
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  for (const debt of ['A', 'B']) {
    const history = () => [...ledger.values()].filter(payment => payment.debt_id === debt);
    const currentDebt = () => ({ id: debt, name: 'Debt ' + debt, direction: 'i_owe', color: '#126046', original_amount: 500, total_paid: history().reduce((sum, payment) => sum + payment.amount, 0), remaining_amount: 500 - history().reduce((sum, payment) => sum + payment.amount, 0) });
    cache.setQueryDefaults(['debt', debt], { queryFn: async () => currentDebt() });
    cache.setQueryDefaults(['debt-payments', debt], { queryFn: async () => history() });
    cache.setQueryData(['debt', debt], currentDebt()); cache.setQueryData(['debt-payments', debt], []);
  }
  const colors = new Proxy({}, { get: () => '#126046' });
  const mocks = {
    react, 'react/jsx-runtime': { jsx: (type, props, key) => ({ type, props, key }), jsxs: (type, props, key) => ({ type, props, key }) },
    'react-native': { View: 'View', ScrollView: 'Scroll', KeyboardAvoidingView: 'Keyboard', ActivityIndicator: 'Loading', Platform: { OS: 'android', select: v => v.default }, Alert: { alert: (...v) => alerts.push(v) } },
    '@/src/i18n': { tr: engine.t.bind(engine), useTranslation: () => ({ t: engine.t.bind(engine) }) }, '@/src/i18n/errors': { localizedError: e => e },
    '@/src/components/elastic-scroll-view': { ElasticScrollView: 'Scroll' }, '@/src/native-scroll': { NATIVE_VERTICAL_SCROLL: {} },
    '@/src/components/interaction-system': { Alert: { alert: (...values) => alerts.push(values) } },
    '@/src/components/header-actions': { MoneyFlowHeaderActions: 'MoneyFlowHeaderActions' },
    '@/src/components/pressable': { Pressable: 'Pressable' }, '@/src/components/typography': { Text: 'Text', TextInput: 'Input' },
    '@react-native-vector-icons/ionicons': { default: 'Icon' }, 'expo-router': { useLocalSearchParams: () => ({ id }), useRouter: () => ({ back() {}, push: route => routes.push(route), dismissTo: route => routes.push(route) }) },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    '@tanstack/react-query': { useQuery: ({ queryKey }) => ({ data: queryKey[0] === 'debt' ? cache.getQueryData(['debt', id]) : [{ id: 'source', name: 'Source', current_balance: 1000 }] }), useQueryClient: () => ({ invalidateQueries(options) { invalidations.push(options); return flags.refresh ? Promise.reject(Error('Refresh unavailable')) : cache.invalidateQueries(options, { throwOnError: true }); } }) },
    '@/src/api': { ApiError, api: { listAccounts() {}, getDebt() {} } }, '@/src/debt-payments/local-flow': { localPaymentFlow: flow }, '@/src/debt-payments/view': presentation,
    '@/src/theme': { useTheme: () => ({ colors, scheme: 'light' }), makeStyles: f => () => f(colors), radius: { pill: 999 }, spacing: { lg: 16 } },
    '@/src/format': { formatCurrency: String, formatCurrencyInt: String }, '@/src/components/ui': { IconTile: 'Icon' }, '@/src/components/sheets': { AppSheet: 'Sheet' }, '@/src/ui-scale': { us: x => x },
  };
  const component = load('frontend/app/debts/[id]/pay.tsx', mocks).default;
  const render = () => {
    cursor = 0;
    let tree = component();
    if (typeof tree.type === 'function') {
      if (mountedKey !== tree.key) { cleanups.filter(Boolean).forEach(fn => fn()); cells = []; deps = []; cleanups = []; effects = []; mountedKey = tree.key; }
      tree = tree.type(tree.props);
    }
    effects.splice(0).forEach(fn => fn());
    return tree;
  };
  const find = testID => all(render()).find(n => n.props?.testID === testID);
  return { flow, flags, calls, ledger, disk, routes, alerts, invalidations, cache, render, find, async open(next) { cleanups.filter(Boolean).forEach(fn => fn()); cells = []; deps = []; cleanups = []; effects = []; mountedKey = undefined; id = next; render(); await tick(); render(); } };
}
async function main() {
  for (const version of [1, 2]) for (const lang of ['en-US', 'es']) {
    await engine.changeLanguage(lang);
    let f = fixture(version); await f.open('A'); assert.equal(f.find('pay-amount').props.editable, true);
    f.find('pay-amount').props.onChangeText('100'); f.find('pay-account-select').props.onPress(); f.find('pay-acc-source').props.onPress();
    await f.open('B'); assert.equal(f.find('pay-amount').props.value, '', 'A draft amount must not leak to B');
    assert.equal(f.calls.length, 0); assert(!f.find('pay-account-sheet').props.visible);
    f.find('pay-amount').props.onChangeText('50'); f.find('pay-account-select').props.onPress(); f.find('pay-acc-source').props.onPress();
    const click = f.find('confirm-pay').props.onPress; await Promise.all([click(), click()]);
    assert.equal(f.ledger.size, 1); assert.equal(f.calls[0].payload.debt_id, 'B'); assert.equal(f.calls[0].payload.account_id, 'source');
    await tick(); assert.equal(f.cache.getQueryData(['debt', 'B']).remaining_amount, 450); assert.equal(f.cache.getQueryData(['debt', 'B']).total_paid, 50); assert.equal(f.cache.getQueryData(['debt-payments', 'B']).length, 1); await click(); assert.equal(f.calls.length, 1);
    assert.equal(f.routes.at(-1), '/debts/B', 'Successful payment must dismiss to the same debt');
    assert(f.invalidations.some(q => q.queryKey[0] === 'debt' && q.queryKey[1] === 'B' && q.refetchType === 'all'));
    assert(f.invalidations.some(q => q.queryKey[0] === 'debt-payments' && q.queryKey[1] === 'B'));
    const receiptBytes = JSON.stringify([...f.ledger]); const localBytes = JSON.stringify([...f.disk]); await assert.rejects(f.flow.startNew('wrong-key')); assert.equal(JSON.stringify([...f.disk]), localBytes);
    await f.open('B'); assert.equal(f.find('pay-amount').props.value, ''); assert.equal(f.find('pay-amount').props.editable, true);
    await f.open('A'); assert.equal(f.find('pay-amount').props.editable, true); assert.equal(f.find('pay-amount').props.value, ''); assert.equal(f.calls.length, 1); assert.equal(JSON.stringify([...f.ledger]), receiptBytes);
    for (const invalid of ['', '0', '-1', '501', 'abc', '12oops', 'Infinity']) { f.find('pay-amount').props.onChangeText(invalid); await f.find('confirm-pay').props.onPress(); assert.equal(f.calls.length, 1, invalid); assert.equal(await f.flow.recover(), null); }
    f.find('pay-amount').props.onChangeText('20'); await f.find('confirm-pay').props.onPress(); assert.equal(f.calls.at(-1).payload.debt_id, 'A'); assert.equal(f.calls.at(-1).payload.account_id, null, 'B account must not leak to A');
    f = fixture(version); f.flags.reject = true; await f.open('A'); f.find('pay-amount').props.onChangeText('30'); f.find('pay-account-select').props.onPress(); f.find('pay-acc-source').props.onPress();
    all(f.render()).find(n => n.type === 'Input' && !n.props.testID).props.onChangeText('Keep these notes');
    await f.find('confirm-pay').props.onPress(); assert.equal(f.routes.length, 0); assert.equal(f.find('pay-amount').props.value, '30'); assert.equal((await f.flow.recover()).payload.account_id, 'source'); assert.equal((await f.flow.recover()).payload.notes, 'Keep these notes'); assert.equal(f.ledger.size, 0);
    f = fixture(version); f.flags.refresh = true; await f.open('A'); f.find('pay-amount').props.onChangeText('15'); await f.find('confirm-pay').props.onPress(); await tick(); assert.equal(f.routes.at(-1), '/debts/A'); assert.equal(f.ledger.size, 1); assert(f.alerts.length); await f.find('confirm-pay').props.onPress(); assert.equal(f.calls.length, 1);
    f = fixture(version); f.flags.lost = true; await f.open('A'); f.find('pay-amount').props.onChangeText('25'); await f.find('confirm-pay').props.onPress();
    assert.equal(f.routes.length, 0); const pendingBytes = JSON.stringify([...f.disk]); await f.open('B'); assert.equal(f.find('pay-amount').props.editable, false); await f.find('confirm-pay').props.onPress();
    assert.equal(JSON.stringify([...f.disk]), pendingBytes); assert.equal(f.calls.length, 1); assert(f.alerts.at(-1)[2]?.some(button => button.onPress), 'Unresolved foreign debt must offer a non-writing review action');
    const review = f.alerts.at(-1)[2].find(button => button.onPress); review.onPress(); assert(f.routes.at(-1).includes('/A/pay')); assert.equal(f.calls.length, 1);
    f = fixture(version); f.flags.conflict = true; await f.open('A'); f.find('pay-amount').props.onChangeText('20'); await f.find('confirm-pay').props.onPress(); await f.open('B'); assert.equal(f.find('pay-amount').props.editable, false); assert.equal((await f.flow.recover()).state, 'conflict');
    f = fixture(version); await f.open('A'); f.find('pay-amount').props.onChangeText('10'); await f.find('confirm-pay').props.onPress(); f.flags.remove = true; await f.open('B'); assert.equal(f.find('pay-amount').props.editable, false); assert.equal((await f.flow.recover()).state, 'confirmed'); assert.equal(f.calls.length, 1);
  }
  console.log('PASS: actual payment form EN/ES with legacy and v2 flows; draft isolation A/B, blank form on entry and same-debt dismissal after success, original-debt review for unresolved/conflicting payments, amount validation, correct source account, double-tap protection, unchanged ledger and cleanup failure. Synthetic data only.');
}
module.exports = { run: main };
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
