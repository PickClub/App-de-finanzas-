const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const ts = require("typescript");
const exported = {};
vm.runInNewContext(ts.transpileModule(fs.readFileSync("frontend/src/category-onboarding.ts", "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports: exported });
const { ensureCategoryCatalog } = exported;

(async () => {
  const catalogs = new Map([["a", []], ["b", []], ["custom", [{ id: "custom", name: "Unchanged ñ", color: "#123456" }]]]);
  const initializes = [];
  const port = actor => ({
    assertCurrent() {},
    read: async () => catalogs.get(actor),
    initialize: async () => {
      initializes.push(actor);
      catalogs.set(actor, [{ id: actor + "-expense", type: "expense" }, { id: actor + "-income", type: "income" }]);
    },
  });
  await ensureCategoryCatalog(port("a"));
  assert.deepEqual(initializes, ["a"]);
  await ensureCategoryCatalog(port("a"));
  assert.deepEqual(initializes, ["a"]);
  const custom = JSON.stringify(catalogs.get("custom"));
  await ensureCategoryCatalog(port("custom"));
  assert.equal(JSON.stringify(catalogs.get("custom")), custom);
  assert.deepEqual(initializes, ["a"]);
  await ensureCategoryCatalog(port("b"));
  assert.deepEqual(initializes, ["a", "b"]);
  assert.notEqual(catalogs.get("a")[0].id, catalogs.get("b")[0].id);
  await assert.rejects(ensureCategoryCatalog({
    ...port("a"), read: async () => { throw Error("Synthetic outage"); },
  }));
  assert.deepEqual(initializes, ["a", "b"]);
  let current = true;
  await assert.rejects(ensureCategoryCatalog({
    assertCurrent() { assert.equal(current, true); },
    read: async () => { current = false; return []; },
    initialize: async () => assert.fail("Changed session must not initialize"),
  }));
  console.log("PASS: empty catalog initialized, repeat session skipped, custom data preserved, A/B isolated, failures and session changes block setup");
})().catch(error => { console.error(error); process.exitCode = 1; });
