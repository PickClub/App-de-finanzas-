// Exercise real presentation state/geometry and dialog callbacks without native APIs or writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const stateModule = { exports: {} };
vm.runInNewContext(compile(fs.readFileSync(root + '/src/components/interaction-state.ts', 'utf8')), { exports: stateModule.exports });
const { createInteractionStore, placeContextMenu, interactions } = stateModule.exports;
const rect = { x: 140, y: 80, width: 44, height: 44 };
const viewport = { x: 0, y: 0, width: 360, height: 740 };
const insets = { top: 24, bottom: 24, left: 0, right: 0 };
for (const width of [280, 320, 360, 430]) for (const y of [35, 180, 550, 650]) for (const fontScale of [1, 1.5, 2]) {
  for (const keyboard of [null, 400]) {
    const anchor = { x: width - 44, y, width: 44, height: 44 };
    const result = placeContextMenu(anchor, { ...viewport, width }, insets, keyboard, fontScale, 12, 88);
    if (!result) continue;
    assert(result.x >= 8 && result.x + result.width <= width - 8);
    assert(result.y >= insets.top + 8);
    assert(result.y + result.height <= Math.min(740 - 24 - 8 - 88, keyboard === null ? Infinity : keyboard - 8));
    assert(result.height <= 304); // Twelve actions must scroll inside this bounded card.
  }
}
assert.equal(placeContextMenu({ ...rect, x: NaN }, viewport, insets, null, 1, 2), null);
const bottom = placeContextMenu({ ...rect, y: 650 }, viewport, insets, null, 1, 4, 88); assert(bottom.upward);
const top = placeContextMenu(rect, viewport, insets, null, 1, 4, 88); assert(!top.upward);
let calls = [], focused = 0;
const store = createInteractionStore();
const actions = id => [{ id: 'edit', label: 'Edit', icon: 'pencil', onPress: () => calls.push(id) }, { id: 'disabled', label: 'Disabled', icon: 'x', disabled: true, onPress: () => { throw Error('disabled'); } }];
store.openMenu('A', rect, actions('A'), () => focused++);
store.openMenu('B', rect, actions('B'), () => focused++); assert.equal(store.getSnapshot().menu.owner, 'B');
let id = store.getSnapshot().menu.id;
store.selectMenuAction(id, 'disabled'); assert(!store.getSnapshot().menu.closing);
store.selectMenuAction(id, 'edit'); store.selectMenuAction(id, 'edit');
const operation = store.finishMenuClose(id); operation(); assert.equal(store.finishMenuClose(id), undefined); assert.deepEqual(calls, ['B']); assert.equal(focused, 1, 'Restore trigger focus before running a selected action');
store.openMenu('A', rect, actions('A'), () => focused++); id = store.getSnapshot().menu.id;
store.closeMenu(); assert(store.getSnapshot().menu.closing); assert.equal(store.finishMenuClose(id), undefined); assert.equal(focused, 2);
store.openMenu('A', rect, actions('A')); store.clearMenu('wrong'); assert(store.getSnapshot().menu); store.clearMenu('A'); assert.equal(store.getSnapshot().menu, null);
let dismissals = 0;
store.alert('Discard?', 'Keep draft', [{ text: 'Cancel', style: 'cancel' }], { cancelable: true, onDismiss: () => dismissals++ });
id = store.getSnapshot().alert.id; store.dismissAlert(id); assert.equal(dismissals, 1);
store.alert('Protected'); id = store.getSnapshot().alert.id; store.dismissAlert(id); assert(store.getSnapshot().alert);
assert(store.claimAlert(id)); assert(!store.claimAlert(id)); store.alert('Nested error'); assert.equal(store.getSnapshot().queue.length, 1);
store.finishAlert(id); assert.equal(store.getSnapshot().alert.title, 'Nested error');
console.log('PASS: geometry bounds/keyboard/edges/font scales; scroll cap; one menu; correct entity; single selection; dismissal; default-safe alerts; queued error and onDismiss semantics.');

const style = {};
function fixture() {
  let cursor = 0; const cells = [];
  const react = {
    useRef: value => { const i = cursor++; return cells[i] ??= { current: value }; },
    useState: value => { const i = cursor++; if (!(i in cells)) cells[i] = value; return [cells[i], next => { cells[i] = typeof next === 'function' ? next(cells[i]) : next; }]; },
    useEffect() {}, useId: () => 'trigger', useSyncExternalStore: (_subscribe, get) => get(),
  };
  const colors = new Proxy({}, { get: () => '#126046' });
  const jsx = (type, props) => ({ type, props });
  const mocks = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx },
    'react-native': { View: 'View', Modal: 'Modal', ScrollView: 'Scroll', KeyboardAvoidingView: 'KeyboardAvoidingView', Platform: { OS: 'android' }, ActivityIndicator: 'Spinner', StyleSheet: { create: x => x, absoluteFill: style }, AccessibilityInfo: { setAccessibilityFocus() {} }, findNodeHandle: () => 1, useWindowDimensions: () => ({ width: 360, height: 740, fontScale: 1 }), Keyboard: { addListener: () => ({ remove() {} }) } },
    '@react-native-vector-icons/ionicons': { default: 'Icon' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => insets }, 'expo-router': { usePathname: () => '/more' }, 'expo-font': { useFonts: () => [true] },
    'react-native-reanimated': { default: { View: 'AnimatedView' }, Easing: {}, ReduceMotion: { System: 'system' }, useReducedMotion: () => false, useSharedValue: x => ({ value: x }), useAnimatedStyle: fn => fn(), withTiming: x => x, runOnJS: fn => fn },
    '@/src/i18n': { useTranslation: () => ({ t: key => key }) }, '@/src/i18n/errors': { localizedError: e => e.message || String(e) }, '@/src/theme': { useTheme: () => ({ colors }) },
    './pressable': { Pressable: 'Pressable' }, './typography': { Text: 'Text' }, './interaction-state': stateModule.exports,
  };
  const loaded = { exports: {} };
  vm.runInNewContext(compile(fs.readFileSync(root + '/src/components/interaction-system.tsx', 'utf8') + '\nexport { DialogSurface, AlertOverlay };'), { exports: loaded.exports, require: name => name.endsWith('.ttf') ? 1 : (assert(name in mocks, name), mocks[name]) });
  return { components: loaded.exports, render: (name, props) => { cursor = 0; return loaded.exports[name](props); } };
}
(async () => {
  const f = fixture(); let confirmed = 0, canceled = 0, resolve;
  const props = { visible: true, title: 'Delete selected?', icon: 'trash', confirmLabel: 'Delete', onClose: () => canceled++, onConfirm: () => { confirmed++; return new Promise(r => { resolve = r; }); } };
  let dialog = f.render('MoneyFlowConfirmDialog', props);
  const confirm = dialog.props.buttons[0];
  const pending = confirm.onPress(); confirm.onPress(); assert.equal(confirmed, 1);
  dialog = f.render('MoneyFlowConfirmDialog', props); assert(dialog.props.busy);
  dialog.props.onClose(); dialog.props.buttons[1].onPress(); assert.equal(canceled, 0, 'Stale outside/cancel callbacks cannot close while the operation is pending');
  resolve(); await pending;
  dialog = f.render('MoneyFlowConfirmDialog', props); assert(!dialog.props.busy); assert(dialog, 'Owner, not Promise resolution, closes the dialog');
  dialog.props.buttons[1].onPress(); assert.equal(canceled, 1); assert.equal(confirmed, 1);
  const surface = f.render('DialogSurface', { ...dialog.props, busy: true }); surface.props.onRequestClose(); assert.equal(canceled, 1);
  const free = f.render('DialogSurface', { ...dialog.props, busy: false }); free.props.onRequestClose(); assert.equal(canceled, 2);
  while (interactions.getSnapshot().alert) interactions.finishAlert(interactions.getSnapshot().alert.id);
  let alertCount = 0;
  interactions.alert('Confirm', 'selected entity', [{ text: 'Delete', style: 'destructive', onPress: async () => { alertCount++; interactions.alert('Error', 'Existing failure feedback'); } }]);
  let alert = f.render('AlertOverlay'); await Promise.all([alert.props.buttons[0].onPress(), alert.props.buttons[0].onPress()]);
  assert.equal(alertCount, 1); assert.equal(interactions.getSnapshot().alert.title, 'Error');
  const source = fs.readFileSync(root + '/src/components/interaction-system.tsx', 'utf8');
  assert(source.includes('duration: 190') && source.includes('duration: 130') && source.includes('ReduceMotion.System') && source.includes('useReducedMotion'));
  assert(source.includes('showsVerticalScrollIndicator nestedScrollEnabled')); assert(source.includes('measureInWindow')); assert(!source.includes('setInterval'));
  console.log('PASS: real dialog callbacks lock duplicate taps, keep owner-controlled lifecycle, safe Back/cancel, nested error feedback and fonts; menu UI-thread timing/reduced motion/internal scrolling configured. Native gesture/animation profiling pending.');
})().catch(error => { console.error(error); process.exitCode = 1; });
