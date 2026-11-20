"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../privacy_web/delete.js"), "utf8");

function fixture(fetch) {
  let submit;
  const fields = {
    deletion: {
      addEventListener: (_, listener) => { submit = listener; },
      reset() {
        fields.email.value = "";
        fields.password.value = "";
        fields.confirmed.checked = false;
      },
    },
    email: { value: "a@example.com" },
    password: { value: "synthetic password" },
    confirmed: { checked: false },
    submit: { disabled: true },
    status: { dataset: { pending: "pending", complete: "complete", unconfirmed: "unconfirmed" } },
  };
  vm.runInNewContext(source, { document: { querySelector: id => fields[id.slice(1)] }, fetch });
  return { fields, submit: () => submit({ preventDefault() {} }) };
}

(async () => {
  let calls = 0;
  let finish;
  const live = fixture((url, request) => {
    calls += 1;
    assert.equal(url, "/api/auth/account/delete-web");
    assert.equal(request.credentials, "omit");
    assert.equal(request.redirect, "error");
    assert.deepEqual(JSON.parse(request.body), {
      email: "a@example.com", password: "synthetic password", confirmed: true,
    });
    return new Promise(resolve => { finish = resolve; });
  });
  await live.submit();
  assert.equal(calls, 0);
  live.fields.confirmed.checked = true;
  const pending = live.submit();
  assert.equal(live.fields.password.value, "");
  assert.equal(live.fields.submit.disabled, true);
  await live.submit();
  assert.equal(calls, 1);
  finish({ status: 204 });
  await pending;
  assert.equal(live.fields.status.textContent, "complete");
  assert.equal(live.fields.email.value, "");
  live.fields.confirmed.checked = true;
  await live.submit();
  assert.equal(calls, 1);

  for (const result of [200, 401, 503, null]) {
    const failed = fixture(async () => {
      if (result === null) throw Error("synthetic network failure");
      return { status: result };
    });
    failed.fields.confirmed.checked = true;
    await failed.submit();
    assert.equal(failed.fields.status.textContent, "unconfirmed");
    assert.equal(failed.fields.password.value, "");
    assert.equal(failed.fields.submit.disabled, false);
  }
  console.log("PASS: explicit confirmation, one in-flight submission, credential clearing, exact 204, generic failure");
})().catch(error => { console.error(error); process.exitCode = 1; });
