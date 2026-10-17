const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync('frontend/src/components/header-actions.tsx', 'utf8');
const output = ts.transpileModule(source, { fileName: 'header-actions.tsx', compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const mocks = {
  react: { default: {} },
  'react/jsx-runtime': { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) },
  'react-native': { ActivityIndicator: 'ActivityIndicator', StyleSheet: { create: value => value }, View: 'View' },
  '@react-native-vector-icons/ionicons': { default: 'Ionicons' },
  '@/src/i18n': { useTranslation: () => ({ t: key => key }) },
  '@/src/theme': { useTheme: () => ({ colors: { surfaceSecondary: 'surface', border: 'border', onSurface: 'text', primaryAction: 'green' } }) },
  './pressable': { Pressable: 'Pressable' },
};
const moduleExports = {};
vm.runInNewContext(output, { exports: moduleExports, require: name => { assert(name in mocks, name); return mocks[name]; } });
const { MoneyFlowHeaderActions } = moduleExports;
const back = () => {};
const save = () => {};
const tree = MoneyFlowHeaderActions({ onBack: back, onSave: save, saveTestID: 'save', backTestID: 'back' });
const controls = tree.props.children.filter(Boolean);
assert.equal(controls[0].props.testID, 'back');
assert.equal(controls[0].props.onPress, back);
assert.equal(controls[0].props.children.props.name, 'arrow-back');
assert.equal(controls[1].props.testID, 'save');
assert.equal(controls[1].props.onPress(), undefined);
assert.equal(controls[1].props.children.props.name, 'arrow-forward');
assert.equal(controls[0].props.accessibilityRole, 'button');
assert.equal(controls[1].props.accessibilityLabel, 'headerActions.saveChanges');

const busy = MoneyFlowHeaderActions({ onBack: back, onSave: save, saving: true, saveDisabled: true, beforeActions: 'options' });
const busyControls = busy.props.children.filter(Boolean);
assert.equal(busyControls[0], 'options');
assert.equal(busyControls[1].props.testID, undefined);
assert.equal(busyControls[2].props.disabled, true);
assert.equal(busyControls[2].props.accessibilityState.busy, true);
assert.equal(busyControls[2].props.children.type, 'ActivityIndicator');

console.log('PASS: shared header orders Back before Save, preserves callback ownership, accessibility, before-actions and saving/disabled states.');
