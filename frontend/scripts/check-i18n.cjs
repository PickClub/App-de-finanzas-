// Static UI/catalog checks. Technical identifiers and persisted content are not translations.
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const root = path.resolve(__dirname, '..');
function flatten(object, prefix = '', result = {}) {
  for (const [key, value] of Object.entries(object)) {
    if (typeof value === 'string') result[prefix + key] = value;
    else flatten(value, prefix + key + '.', result);
  }
  return result;
}
const en = flatten(JSON.parse(fs.readFileSync(path.join(root, 'src/i18n/locales/en.json'))));
const es = flatten(JSON.parse(fs.readFileSync(path.join(root, 'src/i18n/locales/es.json'))));
const failures = [], dynamic = [], files = [];
for (const key of new Set([...Object.keys(en), ...Object.keys(es)])) {
  if (!(key in en) || !(key in es)) failures.push(`Missing locale entry: ${key}`);
  const variables = text => [...(text || '').matchAll(/{{\s*([^}]+)\s*}}/g)].map(m => m[1]).sort().join(',');
  if (variables(en[key]) !== variables(es[key])) failures.push(`Interpolation mismatch: ${key}`);
}
function walk(directory) {
  for (const entry of fs.readdirSync(directory)) {
    const file = path.join(directory, entry);
    if (fs.statSync(file).isDirectory()) walk(file);
    else if (/\.tsx?$/.test(file)) files.push(file);
  }
}
walk(path.join(root, 'app')); walk(path.join(root, 'src'));
const displayAttributes = new Set(['placeholder', 'accessibilityLabel', 'title', 'subtitle', 'confirmLabel', 'cancelLabel']);
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8');
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const location = node => `${path.relative(root, file)}:${tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1}`;
  function visit(node) {
    if (ts.isCallExpression(node) && ['t', 'tr'].includes(node.expression.getText(tree)) && node.arguments.length) {
      const argument = node.arguments[0];
      if (ts.isStringLiteral(argument)) {
        const key = argument.text;
        if (!(key in en) && !(key + '_one' in en) && !(key + '_other' in en)) failures.push(`${location(node)} missing key ${key}`);
      } else dynamic.push(location(node));
    }
    if (!file.endsWith('+html.tsx') && ts.isJsxText(node) && /[A-Za-zÀ-ÿ]/.test(node.text)) {
      failures.push(`${location(node)} hardcoded UI text: ${node.text.trim()}`);
    }
    if (ts.isStringLiteral(node) && ts.isJsxAttribute(node.parent) && displayAttributes.has(node.parent.name.getText(tree))
      && /[A-Za-zÀ-ÿ]/.test(node.text)) failures.push(`${location(node)} hardcoded ${node.parent.name.getText(tree)}: ${node.text}`);
    ts.forEachChild(node, visit);
  }
  visit(tree);
}
if (failures.length) {
  failures.forEach(failure => console.error(failure)); process.exitCode = 1;
} else console.log(`PASS: ${Object.keys(en).length} matching English/Spanish keys; interpolation parity; ${files.length} source files; no literal JSX text/display attributes.`);
console.log(`REVIEW: ${dynamic.length} dynamic key calls require explicit enum/interpolation tests. Stored content, computed labels and runtime responses are outside this static proof.`);
module.exports = { flatten };
