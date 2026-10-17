// Static coverage for shared contextual triggers and app-owned dialog routing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const expected = {
  'frontend/app/accounts/[id].tsx': [['acc-detail-options', ['edit']]],
  'frontend/app/accounts/new.tsx': [['account-form-options', ['delete']]],
  'frontend/app/transactions/[id].tsx': [['more-btn', ['edit', 'dup', 'recur', 'category', 'delete']]],
  'frontend/app/debts/[id]/index.tsx': [['debt-detail-options', ['edit', 'delete']], ['cancel-payment-${p.id}', ['cancel-payment']]],
  'frontend/app/(tabs)/notes.tsx': [['note-menu-${note.id}', ['edit', 'pin', 'delete']], ['notes-preview-actions', ['edit', 'pin', 'delete']]],
  'frontend/app/bills/[id].tsx': [['bill-actions', ['edit', 'delete']], ['bill-pay-actions-${p.id}', ['delete']]],
  'frontend/app/recurring/[id].tsx': [['rp-actions', ['edit', 'pause', 'resume', 'end', 'delete']], ['rp-record-actions-${rec.id}', ['undo']]],
  'frontend/app/budgets/[id].tsx': [['budget-actions', ['edit', 'delete']]],
  'frontend/app/goals/[id].tsx': [['goal-actions', ['edit', 'delete']]],
  'frontend/app/categories/new.tsx': [['category-actions', ['delete']]],
};
const read = file => fs.readFileSync(file, 'utf8');
const parse = (file, source) => ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
for (const [file, records] of Object.entries(expected)) {
  const source = read(file), ast = parse(file, source), found = new Map();
  const declarations = new Map();
  function visit(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name)) declarations.set(node.name.text, node.initializer?.getText(ast) || '');
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && node.tagName.getText(ast) === 'ContextActionsTrigger') {
      const props = node.attributes.properties;
      const testID = props.find(prop => prop.name?.getText(ast) === 'testID')?.initializer?.getText(ast).replace(/^\{|\}$/g, '').replace(/^[`'"]|[`'"]$/g, '');
      let actions = props.find(prop => prop.name?.getText(ast) === 'actions')?.initializer?.getText(ast) || '';
      actions = actions.replace(/^\{|\}$/g, '');
      if (/^[A-Za-z_$][\w$]*$/.test(actions) && declarations.has(actions)) actions = declarations.get(actions);
      const ids = [...actions.matchAll(/\bid\s*:\s*["']([^"']+)["']/g)].map(match => match[1]);
      assert(testID && actions, `${file} trigger must expose a stable test/accessibility context and declarative actions`);
      assert(actions.includes('label:') && actions.includes('icon:') && actions.includes('onPress:'), `${file}:${testID} needs localized labels, icons, and handlers`);
      found.set(testID, ids);
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
  for (const [testID, actions] of records) {
    const actual = found.get(testID);
    assert(actual, `Missing shared trigger ${testID} in ${file}`);
    for (const action of actions) assert(actual.includes(action), `Missing ${action} in ${testID}`);
  }
  if (file.endsWith('transactions/[id].tsx')) assert(!found.get('more-btn').includes('receipt'), 'Do not expose the unsupported receipt placeholder');
}
for (const file of Object.keys(expected)) {
  const source = read(file);
  if (!source.includes('Alert.alert(')) continue;
  const ast = parse(file, source);
  const ownsSharedAlert = ast.statements.some(statement => ts.isImportDeclaration(statement)
    && statement.moduleSpecifier.text === '@/src/components/interaction-system'
    && statement.importClause?.namedBindings && ts.isNamedImports(statement.importClause.namedBindings)
    && statement.importClause.namedBindings.elements.some(element => element.name.text === 'Alert'));
  assert(ownsSharedAlert, `${file} still routes an app alert outside the shared system`);
}
const sheets = read('frontend/src/components/sheets.tsx');
assert(sheets.includes('return <MoneyFlowConfirmDialog {...props} />'), 'Existing confirmation callers must use the shared visual dialog');
console.log(`PASS: ${Object.keys(expected).length} feature areas expose context-specific shared action triggers; all app alerts and legacy ConfirmSheet callers route through the shared system.`);
