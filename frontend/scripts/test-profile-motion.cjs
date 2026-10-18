// Synthetic lifecycle checks for Profile-only anchored sheets; no API or storage access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const cp = require('node:child_process');
const source = fs.readFileSync('frontend/src/components/sheets.tsx', 'utf8');
const baseline = cp.execFileSync('git', ['show', 'ede886399c620354ff9b4d34d417ffc842cf68a3:frontend/src/components/sheets.tsx'], { encoding: 'utf8' });
const profile = fs.readFileSync('frontend/app/settings.tsx', 'utf8');
const oldProfile = cp.execFileSync('git', ['show', 'ede886399c620354ff9b4d34d417ffc842cf68a3:frontend/app/settings.tsx'], { encoding: 'utf8' });
assert.equal(profile.slice(profile.indexOf('const useStyles =')), oldProfile.slice(oldProfile.indexOf('const useStyles =')), 'Profile colors and dimensions remain identical');
const saveHandler = text => text.slice(text.indexOf('  const save ='), text.indexOf('  const confirmRestore ='));
assert.equal(saveHandler(profile), saveHandler(oldProfile), 'Name/currency persistence remains identical');
assert.equal(source.slice(source.indexOf('const s =')), baseline.slice(baseline.indexOf('const s =')), 'All final sheet styles remain identical');
assert.equal(source.slice(source.indexOf('function SlidingAppSheet'), source.indexOf('/** Compatibility')),
  baseline.slice(baseline.indexOf('export function AppSheet'), baseline.indexOf('/** Compatibility')).replace('export function AppSheet', 'function SlidingAppSheet'), 'Existing non-Profile sheet animation is unchanged');
const walk = node => !node || typeof node !== 'object' ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(walk)];
const flat = styles => Object.assign({}, ...[styles].flat(Infinity).filter(Boolean));
function fixture(reduced = false) {
  let cursor = 0, effects = [], visible = true;
  const slots = [], timings = [], cleanups = [];
  const useRef = value => slots[cursor++] ??= { current: value };
  const useState = initial => { const ref = useRef(initial); return [ref.current, value => { ref.current = value; }]; };
  const useEffect = (fn, deps) => { const ref = useRef(null); if (!ref.current || deps.some((v, i) => v !== ref.current[i])) { ref.current = deps; effects.push(fn); } };
  const useSharedValue = initial => {
    const ref = useRef(null);
    if (!ref.current) {
      let value = initial, pending;
      ref.current = { get value() { return value; }, set value(next) {
        if (pending) pending.settled = true;
        if (next?.timing) {
          const from = value;
          const entry = { ...next, settled: false, finish() { if (entry.settled) return; entry.settled = true; value = next.to; next.done?.(true); }, step(f) { value = from + (next.to - from) * f; } };
          pending = entry; timings.push(entry); if (reduced) entry.finish();
        } else { value = next; pending = null; }
      }, cancel() { if (pending) pending.settled = true; } };
    }
    return ref.current;
  };
  const jsx = (type, props) => ({ type, props });
  const mocks = {
    react: { useEffect, useRef, useState }, 'react/jsx-runtime': { jsx, jsxs: jsx },
    'react-native': { View: 'View', Modal: 'Modal', Animated: {}, Easing: {}, StyleSheet: { create: v => v, absoluteFill: {} }, Dimensions: { get: () => ({ height: 800 }) } },
    '@/src/components/pressable': { Pressable: 'Pressable' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ bottom: 24 }) },
    '@/src/theme': { useTheme: () => ({ colors: { surface: 'white', border: 'gray', borderStrong: 'gray' } }), radius: { cardLg: 28 }, spacing: { lg: 16 } },
    '@/src/ui-scale': { us: v => v, scaleStyles: v => v }, './interaction-system': { MoneyFlowConfirmDialog: 'Dialog' },
    'react-native-reanimated': { __esModule: true, default: { View: 'AnimatedView' }, useSharedValue, useAnimatedStyle: fn => fn(), cancelAnimation: value => value.cancel(), runOnJS: fn => fn,
      withTiming: (to, config, done) => ({ timing: true, to, config, done }), Easing: { cubic: 'cubic', out: v => `out-${v}`, in: v => `in-${v}` }, ReduceMotion: { System: 'system' } },
  };
  const context = { exports: {}, require: name => { assert(name in mocks, name); return mocks[name]; } };
  vm.runInNewContext(ts.transpileModule(source + '\nexport { AnchoredAppSheet };', { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText, context);
  const render = () => { cursor = 0; const tree = context.exports.AnchoredAppSheet({ visible, onClose: () => { visible = false; }, origin: { x: 180, y: 264 }, testID: 'panel', children: 'Original content' }); const pending = effects; effects = []; pending.forEach(fn => { const cleanup = fn(); if (cleanup) cleanups.push(cleanup); }); return tree; };
  return { render, timings, setVisible: value => { visible = value; }, unmount: () => cleanups.forEach(fn => fn()), wrapper: context.exports.AppSheet };
}
for (const reduced of [false, true]) {
  const f = fixture(reduced);
  assert.equal(f.wrapper({ visible: true }).type.name, 'SlidingAppSheet');
  let tree = f.render();
  const root = tree.props.children;
  const panel = walk(tree).find(node => node.props?.testID === 'panel');
  assert.equal(flat(panel.props.style).opacity, 0, 'Never flash the final panel before layout');
  root.props.ref.current = { measureInWindow: callback => callback(0, 24, 360, 776) };
  panel.props.onLayout({ nativeEvent: { layout: { x: NaN, y: 500, width: 360, height: 276 } } });
  assert.equal(f.timings.length, 0, 'Invalid measurements never start a transition');
  panel.props.onLayout({ nativeEvent: { layout: { x: 0, y: 500, width: 360, height: 276 } } });
  assert.equal(f.timings.length, 0, 'Wait for Modal onShow');
  tree.props.onShow();
  assert.equal(f.timings[0].config.duration, 280); assert.equal(f.timings[0].config.easing, 'out-cubic'); assert.equal(f.timings[0].config.reduceMotion, 'system');
  f.timings[0].finish(); tree = f.render();
  assert.equal(flat(walk(tree).find(n => n.props?.testID === 'panel').props.style).transform[2].scale, 1);
  f.setVisible(false); f.render(); tree = f.render();
  assert.equal(f.timings.at(-1).config.duration, 220); assert.equal(f.timings.at(-1).config.easing, 'in-cubic');
  if (!reduced) {
    assert(tree, 'Keep the panel mounted through exit');
    assert(walk(tree).find(n => n.props?.testID === 'panel').props.onStartShouldSetResponderCapture());
    f.setVisible(true); f.render(); f.timings.at(-1).finish(); assert(f.render(), 'Rapid reopening cancels the old dismissal');
    f.setVisible(false); f.render(); f.timings.at(-1).finish();
  }
  assert.equal(f.render(), null);
  f.setVisible(true); f.render(); tree = f.render(); assert(tree);
  tree.props.onRequestClose(); f.render(); assert.equal(f.render(), null, 'Back before layout closes safely');
  f.unmount();
}
for (const dismiss of ['backdrop', 'android']) {
  const f = fixture();
  for (let cycle = 0; cycle < 5; cycle++) {
    f.setVisible(true); f.render();
    const tree = f.render(), root = tree.props.children;
    root.props.ref.current = { measureInWindow: callback => callback(0, 24, 360, 776) };
    walk(tree).find(n => n.props?.testID === 'panel').props.onLayout({ nativeEvent: { layout: { x: 0, y: 500, width: 360, height: 276 } } });
    tree.props.onShow(); f.timings.at(-1).finish();
    if (dismiss === 'backdrop') walk(tree).find(n => n.props?.testID === 'sheet-backdrop').props.onPress();
    else tree.props.onRequestClose();
    f.render(); f.timings.at(-1).finish(); assert.equal(f.render(), null);
  }
  f.unmount();
}
console.log('PASS: unchanged final styles and legacy sheets; anchored hidden preparation, validated layout, 280/220ms curves, Reduced Motion, rapid reversal, retained exit, Android Back before layout and cleanup. Device animation remains unverified.');
