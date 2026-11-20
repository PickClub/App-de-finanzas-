// Execute the real AuthGate and account forms with isolated hooks; no network or device writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('../node_modules/typescript');
const { createInstance } = require('../node_modules/i18next');
const i18n = createInstance();
i18n.init({ lng: 'en-US', fallbackLng: 'en-US', initImmediate: false, resources: {
  'en-US': { translation: require('../src/i18n/locales/en.json') }, es: { translation: require('../src/i18n/locales/es.json') },
} });
const links = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/account-links.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: links });
const source = fs.readFileSync('frontend/src/components/auth-gate.tsx', 'utf8');
const nodes = node => !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)];
function fixture(status = 'signed-out', initialURL = null) {
  const states = new Map(), pending = [], calls = [];
  let owner, cursor, linked;
  const colors = new Proxy({}, { get: () => '#126046' });
  const react = {
    useState(initial) {
      const cells = states.get(owner), index = cursor++;
      if (!(index in cells)) cells[index] = initial;
      return [cells[index], value => { cells[index] = value; }];
    },
    useEffect(effect, dependencies) {
      const cells = states.get(owner), index = cursor++;
      if (!cells[index] || JSON.stringify(cells[index]) !== JSON.stringify(dependencies)) {
        cells[index] = dependencies; pending.push(effect);
      }
    },
    useSyncExternalStore: () => ({ status, identity: { user_id: 'synthetic' } }),
  };
  class AuthSessionError extends Error {}
  const mocks = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-native': Object.fromEntries(['ActivityIndicator', 'KeyboardAvoidingView', 'ScrollView', 'Text', 'TextInput', 'View'].map(name => [name, name])),
    'expo-linking': { getInitialURL: async () => initialURL, addEventListener: (_, listener) => { linked = listener; return { remove() {} }; } },
    '@/src/account-links': links,
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '@/src/components/pressable': { Pressable: 'Pressable' },
    '@/src/i18n': { useTranslation: () => ({ t: i18n.t.bind(i18n) }) },
    '@/src/theme': { useTheme: () => ({ colors }) },
    '@/src/private-journal': { resumeDeletedJournals: async () => {} },
    '@/src/auth-session': { AuthSessionError, authState() {}, subscribeAuth() {}, restoreAuth: async () => {},
      signIn: async (...args) => { calls.push(['signin', ...args]); },
      redeemAccountCode: async (...args) => { calls.push(['redeem', ...args]); } },
  };
  mocks['react-native'].StyleSheet = { create: value => value };
  const exported = {};
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText,
    { exports: exported, require: name => { assert(name in mocks, name); return mocks[name]; } });
  function execute(component, props) {
    owner = component; cursor = 0;
    if (!states.has(owner)) states.set(owner, []);
    return component(props);
  }
  function render() {
    let tree = execute(exported.AuthGate, { children: { type: 'PRIVATE', props: {} } });
    if (typeof tree.type === 'function') tree = execute(tree.type, tree.props);
    return tree;
  }
  const flushEffects = () => { while (pending.length) pending.shift()(); };
  const all = () => { render(); flushEffects(); return nodes(render()); };
  const input = label => all().find(node => node.type === 'TextInput' && node.props.accessibilityLabel === i18n.t(label));
  const button = label => all().find(node => node.type === 'Pressable' && nodes(node).some(child => child.props?.children === i18n.t(label)));
  return { all, input, button, calls, link(url) { all(); linked({ url }); }, setStatus(value) { status = value; } };
}
(async () => {
  for (const locale of ['en-US', 'es']) {
    await i18n.changeLanguage(locale);
    let f = fixture('loading'); assert(!f.all().some(node => node.type === 'PRIVATE' || node.type === 'TextInput'));
    f = fixture(); assert(!f.all().some(node => node.type === 'PRIVATE'));
    f.button('auth.useInvitation').props.onPress();
    assert(f.input('auth.accountCode'));
    f.input('auth.accountCode').props.onChangeText('invite.' + 'i'.repeat(43));
    f.input('auth.password').props.onChangeText('synthetic password A');
    f.input('auth.confirmPassword').props.onChangeText('does not match');
    f.button('auth.setPassword').props.onPress(); await new Promise(setImmediate);
    assert.equal(f.calls.length, 0);
    assert(f.all().some(node => node.props?.children === i18n.t('auth.codeInvalid')));
    f.input('auth.password').props.onChangeText('synthetic password A');
    f.input('auth.confirmPassword').props.onChangeText('synthetic password A');
    f.button('auth.setPassword').props.onPress(); await new Promise(setImmediate);
    assert.deepEqual(f.calls[0], ['redeem', 'invite', 'invite.' + 'i'.repeat(43), 'synthetic password A']);
    assert.equal(f.input('auth.password').props.value, '');
    assert(f.all().some(node => node.props?.children === i18n.t('auth.accountReady')));
    assert(!f.all().some(node => node.type === 'PRIVATE'));
    f.link('pickwallet://account/recover');
    assert(f.input('auth.accountCode'));
    f.input('auth.accountCode').props.onChangeText('recover.' + 'r'.repeat(43));
    f.input('auth.password').props.onChangeText('synthetic password B');
    f.input('auth.confirmPassword').props.onChangeText('synthetic password B');
    f.button('auth.setPassword').props.onPress(); await new Promise(setImmediate);
    assert.equal(f.calls[1][1], 'recover');
    f = fixture('signed-out', 'pickwallet://account/invite'); f.all(); await new Promise(setImmediate);
    assert(f.input('auth.accountCode'));
    f = fixture(); f.link('pickwallet://account/invite?token=secret');
    assert(!f.input('auth.accountCode'));
    f.link('pickwallet://accounts'); assert(!f.all().some(node => node.type === 'PRIVATE'));
    f.setStatus('signed-in'); assert(f.all().some(node => node.type === 'PRIVATE'));
    f.setStatus('signed-out'); assert(!f.all().some(node => node.type === 'PRIVATE'));
  }
  const layout = fs.readFileSync('frontend/app/_layout.tsx', 'utf8');
  assert.equal((layout.match(/<Stack\b/g) || []).length, 1);
  assert(layout.indexOf('<Gate>') < layout.indexOf('<Stack') && layout.indexOf('</Gate>') > layout.indexOf('<Stack'));
  console.log('PASS: English/Spanish account forms, confirmation, redemption contracts, credential clearing, external form selection and private-navigation gate');
})().catch(error => { console.error(error); process.exitCode = 1; });
