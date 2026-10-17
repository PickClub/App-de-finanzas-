// Execute the existing obligation handlers through contextual actions with synthetic APIs only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { createInstance } = require('i18next');
const { headerActionNodes } = require('./i18n-test-support.cjs');
const engine = createInstance();
engine.init({ lng: 'en-US', fallbackLng: 'en-US', initImmediate: false, resources: {
  'en-US': { translation: require('../src/i18n/locales/en.json') },
  es: { translation: require('../src/i18n/locales/es.json') },
} });
const nodes = node => !node || typeof node !== 'object' ? []
  : [node, ...[node.props?.children, ...headerActionNodes(node)].flat(Infinity).flatMap(nodes)];
class ApiError extends Error { constructor(status, detail) { super(detail); this.status = status; this.detail = detail; } }

function fixture(kind, options = {}) {
  let cursor = 0;
  const cells = [], events = [], writes = [], alerts = [], reads = [];
  const resource = kind === 'bill'
    ? { id: 'bill-selected', name: 'User-authored bill', amount: 500, remaining: 400, paid_amount: 100,
      status: 'pending', due_date: '2026-10-20', days_left: 3, color: '#126046', progress: .2,
      payments: [{ id: 'payment-a', amount: 40 }, { id: 'payment-b', amount: 60 }] }
    : { id: 'recurring-selected', name: 'User-authored recurring', state: options.lifecycle || 'active',
      amount: 500, paid_total: 100, frequency: 'monthly', color: '#126046',
      next_due: { due_date: '2026-10-20', expected: 500, remaining: 400 } };
  const state = { contextValid: true, ...options };
  const financialContext = { environment_id: 'synthetic-environment', generation: 1 };
  const react = {
    useState(initial) { const index = cursor++; if (!(index in cells)) cells[index] = initial;
      return [cells[index], value => { cells[index] = typeof value === 'function' ? value(cells[index]) : value; }]; },
    useRef(value) { const index = cursor++; return cells[index] ??= { current: value }; },
    useCallback: callback => callback,
  };
  react.default = react;
  const recordWrite = async (operation, ...args) => {
    writes.push([operation, ...args]);
    if (state.hold) await state.hold;
    if (state.failure) throw state.failure;
  };
  const api = {
    billGet: async id => { reads.push(['bill', id]); return resource; },
    rpGet: async id => { reads.push(['recurring', id]); return resource; },
    rpOccurrences: async () => ({ items: [], has_more: false }),
    getFinancialContext: async () => { reads.push(['context']); return financialContext; },
    billDelete: id => recordWrite('billDelete', id),
    billDeletePayment: (id, context) => recordWrite('billDeletePayment', id, context),
    rpDelete: id => recordWrite('rpDelete', id),
    rpDeletePayment: (id, context) => recordWrite('rpDeletePayment', id, context),
    rpAction: (id, action) => recordWrite('rpAction', id, action),
  };
  const invalidate = async (_client, all) => events.push(['invalidate', all]);
  const qc = { removeQueries: config => events.push(['remove', config.queryKey]) };
  const router = { back: () => events.push(['back']), push: route => events.push(['push', route]) };
  let resourceQuery;
  const colors = new Proxy({}, { get: () => '#126046' });
  const mocks = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-native': { View: 'View', ScrollView: 'Scroll', ActivityIndicator: 'Loading' },
    '@/src/components/interaction-system': { ContextActionsTrigger: 'ContextActionsTrigger', Alert: { alert: (...args) => alerts.push(args) } },
    '@/src/components/header-actions': { MoneyFlowHeaderActions: 'MoneyFlowHeaderActions' },
    '@/src/components/pressable': { Pressable: 'Pressable' },
    '@/src/components/typography': { Text: 'Text' },
    '@/src/components/elastic-scroll-view': { ElasticScrollView: 'Scroll' },
    '@/src/native-scroll': { NATIVE_VERTICAL_SCROLL: {} },
    '@/src/components/sheets': { ConfirmSheet: 'ConfirmSheet' },
    '@/src/components/ProgressBar': { ProgressBar: 'ProgressBar' },
    '@react-native-vector-icons/ionicons': { default: 'Icon' },
    'expo-linear-gradient': { LinearGradient: 'Gradient' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 16 }) },
    'expo-router': { useLocalSearchParams: () => ({ id: resource.id }), useRouter: () => router, useFocusEffect: () => {} },
    '@tanstack/react-query': {
      useQuery: config => { resourceQuery = config; return { data: resource, isLoading: false, refetch: async () => config.queryFn() }; },
      useQueryClient: () => qc,
      useInfiniteQuery: () => ({ data: { pages: [{ items: [{ due_date: '2026-10-01', status: 'partial', paid: 100, expected: 500,
        records: [{ id: 'record-a', amount: 40, mode: 'expense' }, { id: 'record-b', amount: 60, mode: 'link' }] }] }] },
        refetch: async () => {}, hasNextPage: false }),
    },
    '@/src/api': { api, ApiError },
    '@/src/i18n': { tr: engine.t.bind(engine), useTranslation: () => ({ t: engine.t.bind(engine), i18n: engine }) },
    '@/src/i18n/errors': { localizedError: value => value?.message || String(value) },
    '@/src/theme': { useTheme: () => ({ colors, scheme: options.dark ? 'dark' : 'light' }),
      makeStyles: factory => () => factory(colors, options.dark ? 'dark' : 'light'), radius: {}, spacing: { lg: 16 } },
    '@/src/format': { formatCurrencyInt: value => String(value), formatDateTime: () => 'Synthetic date' },
    '@/src/category-labels': { catLabel: value => value },
    '@/src/bills/shared': { FOREST: '#126046', useMontserrat: () => () => ({}), safeHex: value => value,
      deepen: value => value, longDate: value => value, statusColor: () => '#126046', invalidateBills: invalidate },
    '@/src/recurring/shared': { FOREST: '#126046', useMontserrat: () => () => ({}), safeHex: value => value,
      deepen: value => value, longDate: value => value, pastel: value => [value, value], statusTint: () => '#126046' },
    '@/src/obligation-payments/journal': { invalidateObligationPayments: invalidate,
      verifiedDeletionContext(value, _kind, pinned) {
        if (!state.contextValid || pinned && value.environment_id !== pinned.environment_id) throw Error('Context mismatch');
        return value;
      } },
    '@/src/ui-scale': { us: value => value },
  };
  const file = `frontend/app/${kind === 'bill' ? 'bills' : 'recurring'}/[id].tsx`;
  const context = { exports: {}, require: name => { assert(name in mocks, name); return mocks[name]; } };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, context);
  const render = () => { cursor = 0; return context.exports.default(); };
  const find = id => nodes(render()).find(node => node.props?.testID === id);
  const confirmation = () => nodes(render()).find(node => node.type === 'ConfirmSheet');
  const action = (trigger, actionId) => {
    const button = find(trigger); assert(button && button.type === 'ContextActionsTrigger', trigger);
    const found = button.props.actions.find(value => value.id === actionId); assert(found, actionId); return found;
  };
  render();
  return { render, find, confirmation, action, writes, reads, alerts, events, state, resource,
    load: () => resourceQuery.queryFn() };
}

async function main() {
  for (const language of ['en-US', 'es']) for (const dark of [false, true]) {
    await engine.changeLanguage(language);
    let f = fixture('bill', { dark });
    assert.equal(JSON.stringify(f.find('bill-actions').props.actions.map(action => action.id)), JSON.stringify(['edit', 'delete']));
    f.action('bill-actions', 'edit').onPress();
    assert.equal(f.events[0][1].pathname, '/bills/new'); assert.equal(f.events[0][1].params.id, f.resource.id);
    assert.equal(f.writes.length, 0);
    assert(f.find('bill-register-pay')); assert.equal(f.find('bill-pay-actions-payment-a').props.actions.length, 1);
    f.action('bill-actions', 'delete').onPress(); assert.equal(f.writes.length, 0);
    f.confirmation().props.onClose(); assert.equal(f.confirmation().props.visible, false); assert.equal(f.writes.length, 0);
    f.action('bill-actions', 'delete').onPress(); await f.confirmation().props.onConfirm();
    assert.deepEqual(f.writes, [['billDelete', 'bill-selected']]); assert(f.events.some(event => event[0] === 'back'));

    f = fixture('bill', { dark }); await f.load();
    f.action('bill-pay-actions-payment-b', 'delete').onPress(); assert.equal(f.writes.length, 0);
    await f.confirmation().props.onConfirm();
    assert.equal(f.writes[0][0], 'billDeletePayment'); assert.equal(f.writes[0][1], 'payment-b');
    assert.equal(f.writes[0][2].environment_id, 'synthetic-environment');
    assert(!f.events.some(event => event[0] === 'back'));
    f = fixture('bill', { dark, failure: new ApiError(409, 'Linked records') });
    f.action('bill-actions', 'delete').onPress(); await f.confirmation().props.onConfirm();
    assert(f.find('bill-error')); assert(!f.events.some(event => event[0] === 'back'));
    f = fixture('bill', { dark }); await f.load(); f.state.contextValid = false;
    f.action('bill-pay-actions-payment-a', 'delete').onPress(); await f.confirmation().props.onConfirm();
    assert.equal(f.writes.length, 0); assert(f.find('bill-error'));

    for (const lifecycle of ['active', 'paused', 'ended']) {
      f = fixture('recurring', { lifecycle, dark });
      assert.equal(JSON.stringify(f.find('rp-actions').props.actions.map(action => action.id)),
        JSON.stringify(['edit', ...(lifecycle === 'active' ? ['pause', 'end'] : lifecycle === 'paused' ? ['resume', 'end'] : []), 'delete']));
      assert.equal(!!f.find('rp-register-pay'), lifecycle !== 'ended');
      f.action('rp-actions', 'edit').onPress(); assert.equal(f.events[0][1], '/recurring/new?id=recurring-selected');
      assert.equal(f.writes.length, 0);
      if (lifecycle !== 'ended') {
        const operation = lifecycle === 'active' ? 'pause' : 'resume';
        await f.action('rp-actions', operation).onPress(); assert.deepEqual(f.writes[0], ['rpAction', 'recurring-selected', operation]);
      }
      f.action('rp-actions', 'delete').onPress(); const before = f.writes.length;
      f.confirmation().props.onClose(); assert.equal(f.writes.length, before); assert.equal(f.confirmation().props.visible, false);
    }
    f = fixture('recurring', { dark }); f.action('rp-actions', 'end').onPress(); assert.equal(f.writes.length, 0);
    await f.confirmation().props.onConfirm(); assert.deepEqual(f.writes, [['rpAction', 'recurring-selected', 'end']]);
    f = fixture('recurring', { dark }); f.action('rp-actions', 'delete').onPress(); await f.confirmation().props.onConfirm();
    assert.deepEqual(f.writes, [['rpDelete', 'recurring-selected']]); assert(f.events.some(event => event[0] === 'back'));
    f = fixture('recurring', { dark }); await f.load(); f.action('rp-record-actions-record-b', 'undo').onPress();
    assert.equal(f.writes.length, 0); await f.confirmation().props.onConfirm();
    assert.equal(f.writes[0][0], 'rpDeletePayment'); assert.equal(f.writes[0][1], 'record-b');
    assert.equal(f.writes[0][2].environment_id, 'synthetic-environment');
    f = fixture('recurring', { dark, failure: new ApiError(409, 'Linked records') });
    f.action('rp-actions', 'delete').onPress(); await f.confirmation().props.onConfirm();
    assert.equal(f.alerts.length, 1); assert(!f.events.some(event => event[0] === 'back'));
    f = fixture('recurring', { dark }); await f.load(); f.state.contextValid = false;
    f.action('rp-record-actions-record-a', 'undo').onPress(); await f.confirmation().props.onConfirm();
    assert.equal(f.writes.length, 0); assert.equal(f.alerts.length, 1);

    for (const kind of ['bill', 'recurring']) {
      let release; const hold = new Promise(resolve => { release = resolve; });
      f = fixture(kind, { dark, hold }); f.action(kind === 'bill' ? 'bill-actions' : 'rp-actions', 'delete').onPress();
      const pending = f.confirmation().props.onConfirm();
      assert.equal(f.confirmation().props.busy, true);
      assert.equal(f.find(kind === 'bill' ? 'bill-actions' : 'rp-actions').props.disabled, true);
      await f.confirmation().props.onConfirm(); assert.equal(f.writes.length, 1);
      release(); await pending; assert.equal(f.writes.length, 1);
    }
  }
  console.log('PASS: Bill and Recurring actual contextual action handlers in EN/ES and light/dark; selected resource/payment IDs, lifecycle availability, unchanged primary pay flow, cancel without writes, guarded confirmation, one request while busy, verified payment-cancellation context, server errors and success-only navigation. Synthetic APIs only.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
