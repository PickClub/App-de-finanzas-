// Isolated UI regressions: no network requests or persisted financial writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const read = file => fs.readFileSync(`${__dirname}/../${file}`, 'utf8');
const compile = text => ts.transpileModule(text, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const nodes = n => !n || typeof n !== 'object' ? [] : [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)];
function accountsFixture(count) {
  let cursor = 0, effects = [], accounts = Array.from({ length: count }, (_, i) => ({ id: String(i), name: `Account ${i}`, current_balance: i + 1 }));
  const cells = [], navigations = [];
  const react = { useState(initial) { const i = cursor++; if (!(i in cells)) cells[i] = initial; return [cells[i], v => { cells[i] = v; }]; }, useEffect(fn) { effects.push(fn); } };
  const colors = new Proxy({}, { get: () => '#126046' });
  const mocks = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-native': { View: 'View', Platform: { select: v => v.default } },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    'expo-router': { useRouter: () => ({ push: p => navigations.push(p), back() {} }) },
    '@tanstack/react-query': { useQuery: () => ({ data: accounts }) },
    '@/src/api': { api: {} }, '@/src/theme': { useTheme: () => ({ colors, scheme: 'light' }), makeStyles: fn => () => fn(colors), spacing: { lg: 16 } },
    '@/src/format': { formatCurrency: v => `money:${v}` }, '@/src/i18n': { useTranslation: () => ({ t: key => key }) },
    '@/src/lock': { useLock: () => ({ guard: fn => fn }) }, '@/src/ui-scale': { us: n => n },
    '@/src/components/elastic-scroll-view': { ElasticScrollView: 'Scroll' }, '@/src/native-scroll': { NATIVE_VERTICAL_SCROLL: {} },
    '@/src/components/pressable': { Pressable: 'Pressable' }, '@/src/components/typography': { Text: 'Text' },
    'react-native-svg': { default: 'Svg', Path: 'Path' }, '@react-native-vector-icons/ionicons': { default: 'Icon' },
  };
  const loaded = { exports: {} };
  vm.runInNewContext(compile(read('app/accounts/index.tsx')), { require: name => { assert(name in mocks, name); return mocks[name]; }, module: loaded, exports: loaded.exports });
  let tree;
  const render = () => { cursor = 0; effects = []; tree = loaded.exports.default(); effects.forEach(fn => fn()); return nodes(tree); };
  return { render, setCount(n) { accounts = Array.from({ length: n }, (_, i) => ({ id: String(i), name: `Account ${i}`, current_balance: i + 1 })); }, navigations };
}
for (const count of [0, 7, 10, 11, 21]) {
  const f = accountsFixture(count), seen = [];
  let tree = f.render();
  for (let page = 0; page < Math.max(1, Math.ceil(count / 10)); page++) {
    const cards = tree.filter(n => /^account-\d+$/.test(n.props?.testID));
    assert(cards.length <= 10); seen.push(...cards.map(n => n.props.testID));
    assert(tree.some(n => n.props?.children === `money:${count * (count + 1) / 2}`));
    const next = tree.find(n => n.props?.testID === 'accounts-next');
    if (page < Math.ceil(count / 10) - 1) { assert(!next.props.disabled); next.props.onPress(); tree = f.render(); }
    else if (next) assert(next.props.disabled);
  }
  assert.deepEqual(seen, Array.from({ length: count }, (_, i) => `account-${i}`));
  if (count > 10) {
    tree.find(n => n.props?.testID === 'accounts-previous').props.onPress(); tree = f.render();
    assert(tree.some(n => n.props?.testID === `account-${Math.max(0, Math.ceil(count / 10) - 2) * 10}`));
    f.setCount(7); tree = f.render(); assert.equal(tree.filter(n => /^account-\d+$/.test(n.props?.testID)).length, 7);
  }
}
const growing = accountsFixture(10);
assert(!growing.render().some(n => n.props?.testID === 'accounts-next'));
growing.setCount(11);
let growingTree = growing.render();
growingTree.find(n => n.props?.testID === 'accounts-next').props.onPress();
growingTree = growing.render();
growingTree.find(n => n.props?.testID === 'account-10').props.onPress();
assert.deepEqual(growing.navigations, ['/accounts/new?id=10']);
const bills = read('app/bills/index.tsx');
const start = bills.indexOf('  const groups ='), end = bills.indexOf('  const s =', start);
const classify = all => vm.runInNewContext(`${bills.slice(start, end)}; ({groups, counts, items})`, { all, filter: 'all', BILL_FILTERS: ['all', 'pending', 'paid', 'overdue'] });
let result = classify([{ id: 'paid', status: 'paid', remaining: 0 }]);
assert.equal(JSON.stringify(result.counts), '{"all":0,"pending":0,"paid":1,"overdue":0}');
const input = [
  { id: 'unpaid', status: 'pending', remaining: 100 }, { id: 'partial', status: 'pending', remaining: 40, partial: true },
  { id: 'late', status: 'overdue', remaining: 20 }, { id: 'paid-period', recurring_id: 'series', status: 'paid', remaining: 0 },
  { id: 'next-period', recurring_id: 'series', status: 'pending', remaining: 100 },
];
const before = JSON.stringify(input); result = classify(input);
assert.equal(JSON.stringify(result.counts), '{"all":4,"pending":3,"paid":1,"overdue":1}');
assert.equal(JSON.stringify(input), before);
for (const key of ['all', 'pending', 'overdue']) assert(!result.groups[key].some(b => b.status === 'paid'));
for (const name of ['budgets', 'recurring']) {
  const text = read(`app/${name}/index.tsx`);
  assert(text.includes('style={[styles.backBtn, { backgroundColor: forest }]}'));
  assert(text.includes('styles.emptyBtn, { backgroundColor: forest }'));
}
for (const file of ['app/accounts/index.tsx', 'app/categories/index.tsx', 'app/debts/index.tsx', 'src/screens/TransactionsScreen.tsx']) assert(!read(file).includes('LockToggle'));
const lock = read('src/lock.tsx');
assert(!/Animated|FlashLayer|storage|lock-closed|lock-open/.test(lock));
const loaded = { exports: {} };
vm.runInNewContext(compile(lock), { require: () => ({}), module: loaded, exports: loaded.exports });
let called = 0; loaded.exports.useLock().guard(() => called++)(); assert.equal(called, 1);
console.log('PASS: account pagination 0/7/10/11/21, full totals, order, previous/next and removal clamp; bill counts/partial/overdue/recurring occurrence isolation; four green buttons; no lock controls/overlays or stale UI lock. No financial writes.');
