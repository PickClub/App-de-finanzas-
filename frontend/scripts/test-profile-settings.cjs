// Execute the actual Profile screen with isolated hooks and synthetic API responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { createInstance } = require('i18next');
const i18n = createInstance();
i18n.init({ lng: 'en-US', fallbackLng: 'en-US', initImmediate: false, resources: {
  'en-US': { translation: require('../src/i18n/locales/en.json') }, es: { translation: require('../src/i18n/locales/es.json') },
} });
const nodes = n => !n || typeof n !== 'object' ? [] : [n, ...[n.props?.children].flat(Infinity).flatMap(nodes)];
function fixture(options = {}) {
  let cursor = 0;
  const cells = [], calls = [], alerts = [];
  const state = { user: { id: 'same-user', name: 'Custom ñ', currency: 'USD', email: null }, mode: 'system', lang: i18n.language, ...options };
  const react = { useState: initial => { const i = cursor++; if (!(i in cells)) cells[i] = initial; return [cells[i], value => { cells[i] = value; }]; }, useRef: value => { const i = cursor++; return cells[i] ??= { current: value }; } };
  const colors = new Proxy({}, { get: () => '#126046' });
  const mocks = {
    react, 'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
    'react-native': { View: 'View', useWindowDimensions: () => ({ width: state.width ?? 393, fontScale: state.fontScale ?? 1 }), Alert: { alert: (...args) => alerts.push(args) } },
    '@/src/i18n': { useTranslation: () => ({ t: i18n.t.bind(i18n) }), useLang: () => ({ lang: state.lang, setLang: async lang => { calls.push(['language', lang]); state.lang = lang; await i18n.changeLanguage(lang); } }) },
    '@/src/i18n/errors': { localizedError: value => value },
    '@/src/components/elastic-scroll-view': { ElasticScrollView: 'Scroll' }, '@/src/native-scroll': { NATIVE_VERTICAL_SCROLL: {} },
    '@/src/components/pressable': { Pressable: 'Pressable' }, '@/src/components/typography': { Text: 'Text', TextInput: 'Input' },
    '@react-native-vector-icons/ionicons': { default: 'Icon' }, 'expo-font': { useFonts: () => [true, null] },
    '../assets/fonts/Montserrat-Regular.ttf': 1, '../assets/fonts/Montserrat-Bold.ttf': 2,
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 16 }) },
    'expo-router': { useRouter: () => ({ back: () => calls.push(['back']) }) },
    '@tanstack/react-query': { useQuery: () => ({ data: state.user, isError: !!state.loadError, refetch: () => calls.push(['retry']) }), useQueryClient: () => ({ setQueryData: (_, user) => { state.user = user; }, invalidateQueries: () => calls.push(['invalidate']) }) },
    '@/src/api': { api: { updateUser: async payload => { calls.push(['update', payload]); if (state.fail) throw Error('Save failed'); return { ...state.user, ...payload }; }, seed: async () => { calls.push(['seed']); throw Error('Demo disabled'); } } },
    '@/src/theme': { useTheme: () => ({ colors, mode: state.mode, setMode: mode => { state.mode = mode; calls.push(['theme', mode]); } }), makeStyles: fn => () => fn(colors), radius: { lg: 20, md: 12, cardLg: 28, pill: 999 }, spacing: { lg: 16 } },
    '@/src/components/sheets': { AppSheet: 'Sheet' }, '@/src/ui-scale': { us: value => value },
  };
  const context = { exports: {}, require: name => { assert(name in mocks, name); return mocks[name]; } };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/app/settings.tsx', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText, context);
  const render = () => { cursor = 0; return context.exports.default(); };
  const find = id => nodes(render()).find(n => n.props?.testID === id);
  return { state, calls, alerts, find, render };
}
async function main() {
  for (const lang of ['en-US', 'es']) {
    await i18n.changeLanguage(lang);
    for (const width of [320, 360, 393, 412]) for (const fontScale of [1, 1.5]) {
      const responsive = fixture({ width, fontScale });
      const appearance = responsive.find('profile-appearance');
      assert.equal(!!appearance.props.style[1], width >= 380 && fontScale <= 1.15);
      assert(nodes(responsive.render()).some(n => n.props?.testID === 'theme-system'));
    }
    let f = fixture(); assert(!f.find('profile-email')); assert(nodes(f.render()).some(n => n.props?.children === i18n.t('settings.profileTitle')));
    f.find('profile-name').props.onPress(); assert.equal(f.find('profile-name-input').props.value, 'Custom ñ');
    f.find('profile-name-input').props.onChangeText('Edited'); await f.find('save-settings').props.onPress();
    assert.equal(JSON.stringify(f.calls.find(c => c[0] === 'update')[1]), '{"name":"Edited"}'); assert.equal(f.state.user.id, 'same-user'); assert.equal(f.state.user.currency, 'USD'); assert(!f.calls.some(c => c[0] === 'back'));
    f = fixture(); f.find('profile-edit').props.onPress(); f.find('profile-name-input').props.onChangeText('Discard'); f.find('profile-editor-cancel').props.onPress(); assert(!f.calls.length); assert.equal(f.state.user.name, 'Custom ñ');
    f = fixture({ fail: true }); f.find('profile-name').props.onPress(); f.find('profile-name-input').props.onChangeText('Kept draft'); await f.find('save-settings').props.onPress(); assert(f.alerts.length); assert.equal(f.find('profile-editor').props.visible, true); assert.equal(f.find('profile-name-input').props.value, 'Kept draft');
    for (const currency of ['USD', 'EUR', 'MXN', 'COP', 'ARS', 'CLP']) {
      f = fixture(); f.find('currency-row').props.onPress(); f.find(`currency-${currency}`).props.onPress(); await f.find('save-settings').props.onPress(); assert.equal(JSON.stringify(f.calls.find(c => c[0] === 'update')[1]), JSON.stringify({ currency })); assert.equal(f.state.user.name, 'Custom ñ');
    }
    f = fixture(); f.find('theme-dark').props.onPress(); assert.equal(f.state.mode, 'dark'); assert(!f.calls.some(c => c[0] === 'update'));
    f.find('language-row').props.onPress(); const next = lang === 'es' ? 'en-US' : 'es'; await f.find(`language-option-${next}`).props.onPress(); assert.equal(f.state.lang, next); assert.equal(f.find('language-sheet').props.visible, false);
    f = fixture(); f.find('reseed').props.onPress(); assert(!f.calls.length); assert.equal(f.alerts[0][2][0].style, 'cancel'); await f.alerts[0][2][1].onPress(); assert.equal(f.calls.filter(c => c[0] === 'seed').length, 1); assert(!f.calls.some(c => c[0] === 'invalidate')); assert.equal(f.alerts.length, 2);
    f = fixture({ user: { name: 'Custom', currency: 'USD', email: 'real@example.invalid' } }); assert(f.find('profile-email')); assert(f.find('profile-email-row').props.disabled);
    f = fixture({ user: null, loadError: true }); assert(f.find('profile-retry')); assert(!f.find('profile-name')); f.find('profile-retry').props.onPress(); assert.equal(f.calls[0][0], 'retry');
  }
  console.log('PASS: Profile EN/ES rendering, optional email, name save/cancel/error, all six currencies, field-only updates, immediate theme/language, guarded restore rejection, loading retry. Mocked APIs only.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
