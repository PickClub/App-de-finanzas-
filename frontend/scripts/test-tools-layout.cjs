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
  notes.props.onPress(); assert.equal(calls.at(-1), '/tools-notes');
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

// Exercise the actual Notes Back handlers with and without navigation history.
const layoutSource = fs.readFileSync(`${root}/app/_layout.tsx`, 'utf8');
assert.match(layoutSource, /animationDuration: 100/);
assert(!layoutSource.includes('name="tools-notes"'), 'Notes inherits the same native transition as other tools');
assert.match(fs.readFileSync(`${root}/app/tools-notes.tsx`, 'utf8'), /export \{ default \} from "\.\/\(tabs\)\/notes"/);
const notesSource = fs.readFileSync(`${root}/app/(tabs)/notes.tsx`, 'utf8');
const tree = ts.createSourceFile('notes.tsx', notesSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler, focus;
function visit(node) {
  if (ts.isVariableStatement(node) && node.declarationList.declarations.some(d => d.name.getText(tree) === 'handleBack')) handler = node.getText(tree);
  if (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression) && node.expression.expression.getText(tree) === 'useFocusEffect') focus = node.getText(tree);
  ts.forEachChild(node, visit);
}
visit(tree);
assert(handler && focus);
for (const initialHistory of [false, true]) {
  let history = initialHistory, hardwareBack, cleanup, removed = 0;
  const calls = [];
  const context = {
    exports: {}, useCallback: fn => fn, useFocusEffect: fn => { cleanup = fn(); },
    router: {
      canGoBack: () => history,
      back: () => { assert(history, 'Never dispatch an unhandled GO_BACK'); calls.push('back'); history = false; },
      replace: route => calls.push(route),
    },
    BackHandler: { addEventListener: (event, fn) => {
      assert.equal(event, 'hardwareBackPress'); hardwareBack = fn;
      return { remove: () => removed++ };
    } },
  };
  vm.runInNewContext(compile(`${handler}\n${focus}\nexport { handleBack };`), context);
  assert.equal(calls.length, 0, 'Mount/focus must not navigate');
  if (history) {
    assert.equal(hardwareBack(), false, 'Native stack handles Android Back when history exists');
    assert.equal(calls.length, 0);
  }
  context.exports.handleBack();
  assert.equal(calls[0], initialHistory ? 'back' : '/(tabs)/more');
  assert.equal(hardwareBack(), true, 'Cold entry falls back safely to Tools');
  assert.equal(calls.at(-1), '/(tabs)/more');
  context.exports.handleBack();
  assert.equal(calls.at(-1), '/(tabs)/more', 'Repeated taps cannot dispatch GO_BACK without history');
  cleanup(); assert.equal(removed, 1);
}
assert.match(notesSource, /onBack=\{handleBack\}/);
console.log('PASS: Tools EN/ES light/dark; unchanged layout and other destinations; root-stack Notes inherits native transitions. Actual Notes header/Android Back handlers preserve valid history, fall back to Tools without history, never navigate on mount and clean up on blur. Device animation requires Expo Go review.');
