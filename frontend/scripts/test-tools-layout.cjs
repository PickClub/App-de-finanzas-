// Render the actual Tools screen with isolated navigation and no network/data writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const root = `${__dirname}/..`;
const compile = text => ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const scale = { exports: {} };
vm.runInNewContext(compile(fs.readFileSync(`${root}/src/ui-scale.ts`, 'utf8')), { exports: scale.exports });
const walk = n => !n || typeof n !== 'object' ? [] : [n, ...[n.props?.children].flat(Infinity).flatMap(walk)];
const flatten = styles => Object.assign({}, ...[styles].flat(Infinity).filter(Boolean));
for (const language of ['en', 'es']) for (const scheme of ['light', 'dark']) {
  const catalog = require(`${root}/src/i18n/locales/${language}.json`);
  const t = key => key.split('.').reduce((v, k) => v?.[k], catalog);
  const calls = [];
  const colors = { pageBackground: '#E8EFE7', surfaceSecondary: '#FFFFFF', border: '#DCE5DE', onSurface: '#13201A', muted: '#7A847E', incomeGreen: '#2FA47C' };
  const mocks = {
    react: {}, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-native': { View: 'View' }, 'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 24 }) },
    'expo-router': { useRouter: () => ({ push: route => calls.push(route) }) },
    '@/src/theme': { useTheme: () => ({ colors, scheme }), makeStyles: factory => () => scale.exports.scaleStyles(factory(colors, scheme)) },
    '@/src/i18n': { useTranslation: () => ({ t }) }, '@/src/ui-scale': scale.exports,
    '@/src/components/elastic-scroll-view': { ElasticScrollView: 'Scroll' }, '@/src/native-scroll': { NATIVE_VERTICAL_SCROLL: {} },
    '@/src/components/pressable': { Pressable: 'Pressable' }, '@/src/components/typography': { Text: 'Text' },
    '@react-native-vector-icons/ionicons': { default: 'Icon' }, 'expo-linear-gradient': { LinearGradient: 'Gradient' },
    'react-native-svg': { default: 'Svg', Circle: 'Circle', Path: 'Path' }, 'expo-font': { useFonts: () => [true] },
  };
  const loaded = { exports: {} };
  vm.runInNewContext(compile(fs.readFileSync(`${root}/app/(tabs)/more.tsx`, 'utf8')), {
    exports: loaded.exports, require: name => { if (name.endsWith('.ttf')) return 1; assert(name in mocks, name); return mocks[name]; },
  });
  const tree = loaded.exports.default(), nodes = walk(tree), find = id => nodes.find(n => n.props?.testID === id);
  assert(!find('more-profile')); assert(!find('tools-banner'));
  for (const [id, count] of [['money', 4], ['obligations', 3], ['planning', 2]]) {
    const section = find(`tools-section-${id}`);
    assert(section);
    const rows = section.props.children[1].props.children;
    assert.equal(rows.length, count);
    assert.equal(walk(section).filter(n => n.props?.style === rows[0].props.children.at(-1)?.props?.style && n.props?.pointerEvents === 'none').length, Math.max(0, count - 1));
    assert.equal(section.props.onPress, undefined);
    assert.equal(section.props.accessibilityState?.expanded, undefined);
  }
  assert(!nodes.some(n => n.type === 'Icon' && /chevron|arrow/.test(n.props.name)));
  const tools = ['accounts', 'categories', 'budgets', 'savingsGoals', 'debtsAndLoans', 'recurringPayments', 'invoices', 'financialCalendar'];
  const expected = ['/accounts', '/categories', '/budgets', '/goals', '/debts', '/recurring', '/bills', '/calendar'];
  for (const key of tools) { const card = find(`more-${t(`more.${key}`)}`); assert(card); card.props.onPress(); }
  assert.deepEqual(calls, expected);
  const planningRows = find('tools-section-planning').props.children[1].props.children;
  assert.equal(planningRows[0].props.testID, `more-${t('more.financialCalendar')}`);
  const notes = planningRows[1];
  assert.equal(notes.props.testID, `more-${t('tabs.notes')}`);
  assert.equal(notes.props.children[1].props.children[1].props.children, t('more.subNotes'));
  notes.props.onPress(); assert.equal(calls.at(-1), '/(tabs)/notes');
  find('more-settings-btn').props.onPress(); assert.equal(calls.at(-1), '/settings');
  for (const key of ['moneyManagement', 'paymentsObligations', 'planning']) assert(nodes.some(n => n.props?.children === t(`more.${key}`)));
  // Rows wrap naturally; fixed icon plus flexible copy fits narrow Android widths.
  const scroll = nodes.find(n => n.type === 'Scroll'), padding = flatten(scroll.props.contentContainerStyle).paddingHorizontal;
  for (const width of [320, 360, 393, 430]) {
    for (const key of tools) {
      const row = find(`more-${t(`more.${key}`)}`), style = flatten(row.props.style({ pressed: false }));
      const icon = flatten(row.props.children[0].props.style), copy = flatten(row.props.children[1].props.style);
      const available = width - 2 * padding - 2 * style.paddingHorizontal - icon.width - copy.marginLeft;
      assert(available > 140, `${width}: description retains usable width`);
      assert.equal(copy.flex, 1); assert.equal(copy.minWidth, 0); assert.equal(style.height, undefined);
      const [title, description] = row.props.children[1].props.children;
      assert.equal(flatten(title.props.style).fontFamily, 'Montserrat-Bold');
      assert.equal(flatten(description.props.style).fontWeight, '400');
      assert.equal(title.props.numberOfLines, undefined); assert.equal(description.props.numberOfLines, undefined);
      const divider = row.props.children[2];
      if (divider) assert(flatten(divider.props.style).left >= style.paddingHorizontal + icon.width);
    }
  }
}

console.log('PASS: Tools EN/ES light/dark rendering; 3 permanently visible groups with 4/3/2 rows; eight unchanged tool routes, existing Notes route and Settings; no arrows, greeting, banner or expandable controls; bold titles and regular descriptions; wrapping constraints at 320/360/393/430. Native appearance requires Expo Go review.');
