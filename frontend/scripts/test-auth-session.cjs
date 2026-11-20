const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("../node_modules/typescript");

const origin = "http://127.0.0.1:8013";
const actorA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const actorB = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const environment = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const token = (kind, letter) => kind + "." + letter.repeat(43);
const pair = (actor, letter) => ({
  user_id: actor, environment_id: environment,
  access: token("access", letter), refresh: token("refresh", letter),
});
const response = (status, data) => ({
  status, ok: status < 300, json: async () => data, text: async () => JSON.stringify(data),
});
let durable;
let clears = 0;
let fetch;
let secureWrites = [];
let storageFailure = false;
let journalRows = new Map();
let journalFailure = false;
function runtime(configuration = {}) {
  const exports = new Map();
  const mocks = {
    "react-native": { Platform: { OS: "android" } },
    "expo-secure-store": {
      WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
      setItemAsync: async (key, value, options) => {
        if (storageFailure) throw Error("Synthetic secure storage failure");
        secureWrites.push({ key, options }); durable = value;
      },
      getItemAsync: async () => durable,
      deleteItemAsync: async () => { durable = undefined; },
    },
    "@react-native-async-storage/async-storage": {
      __esModule: true,
      default: {
        getAllKeys: async () => Array.from(journalRows.keys()),
        multiRemove: async keys => {
          if (journalFailure) throw Error("Synthetic device storage failure");
          for (const key of keys) journalRows.delete(key);
        },
        removeItem: async key => { journalRows.delete(key); },
        setItem: async (key, value) => { journalRows.set(key, value); },
      },
    },
    "./query-client": { queryClient: { cancelQueries: async () => {}, clear: () => { clears++; } } },
  };
  function load(name) {
    if (name in mocks) return mocks[name];
    if (name.endsWith(".cjs")) return require(path.join(__dirname, "../src", name));
    if (exports.has(name)) return exports.get(name);
    const code = fs.readFileSync(path.join(__dirname, "../src", name + ".ts"), "utf8");
    const js = ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
    const module = { exports: {} };
    vm.runInNewContext(js, {
      exports: module.exports, module, require: load, __DEV__: configuration.dev ?? true,
      process: { env: { EXPO_PUBLIC_R3_AUTH: "1", EXPO_PUBLIC_BACKEND_URL: origin, ...configuration.env } },
      fetch: (...args) => fetch(...args),
    }, { filename: name });
    exports.set(name, module.exports);
    return module.exports;
  }
  return { auth: load("./auth-session"), api: load("./api").api, journal: load("./private-journal") };
}

(async () => {
  let { auth, api } = runtime();
  let refreshes = 0;
  let writes = 0;
  const catalogs = new Set();
  let initializations = 0;
  fetch = async (url, options) => {
    assert.ok(url.startsWith(origin));
    const authorization = options.headers.Authorization;
    if (url.endsWith("/login")) {
      const data = JSON.parse(options.body);
      return data.password === "bad" ? response(401, {}) :
        response(200, data.email === "b" ? pair(actorB, "b") : pair(actorA, "a"));
    }
    if (url.endsWith("/refresh")) {
      refreshes++;
      return response(200, pair(actorA, refreshes === 1 ? "c" : "d"));
    }
    if (url.endsWith("/logout")) return response(204);
    if (url.endsWith("/categories/init-defaults")) {
      initializations++;
      catalogs.add(authorization?.endsWith("b".repeat(43)) ? "b" : "a");
      return response(200, { ok: true });
    }
    if (url.endsWith("/categories")) return response(200, catalogs.has(authorization?.endsWith("b".repeat(43)) ? "b" : "a") ? [{ id: "category" }] : []);
    if (options.method === "POST") { writes++; return response(401, {}); }
    return authorization === "Bearer " + token("access", "a") ? response(401, {}) : response(200, []);
  };
  await assert.rejects(auth.signIn("a", "bad"), error => error.reason === "invalid");
  assert.equal(auth.authState().status, "signed-out");
  await assert.rejects(api.listAccounts(), error => error.status === 401);
  await auth.signIn("a", "synthetic");
  assert.equal(durable, token("refresh", "a"));
  assert.equal(initializations, 1);
  assert.equal(auth.authState().identity.user_id, actorA);
  await Promise.all([api.listAccounts(), api.listAccounts(), api.listAccounts()]);
  assert.equal(refreshes, 1);
  assert.equal(durable, token("refresh", "c"));
  await assert.rejects(api.createAccount({ name: "Synthetic" }), error => error.status === 401);
  assert.equal(writes, 1);
  ({ auth, api } = runtime());
  await auth.restoreAuth();
  assert.equal(auth.authState().identity.user_id, actorA);
  assert.equal(durable, token("refresh", "d"));
  assert.equal(initializations, 1);

  const old = auth.privateSession();
  let release;
  const held = new Promise(resolve => { release = resolve; });
  const originalFetch = fetch;
  fetch = (url, options) => url.endsWith("/accounts") ? held : originalFetch(url, options);
  const previous = api.listAccounts();
  await auth.signOut();
  await auth.signIn("b", "synthetic");
  release(response(200, [{ private: "A" }]));
  await assert.rejects(previous, error => error.reason === "changed");
  assert.throws(old.assertCurrent, error => error.reason === "changed");
  assert.equal(auth.authState().identity.user_id, actorB);
  assert.ok(!auth.privateSession().namespace.includes(actorA));
  await auth.signOut();
  assert.equal(durable, undefined);
  assert.ok(clears > 0);
  await assert.rejects(api.listAccounts(), error => error.status === 401);

  durable = token("refresh", "x");
  ({ auth } = runtime());
  fetch = async () => response(401, {});
  await auth.restoreAuth();
  assert.equal(auth.authState().status, "signed-out");
  assert.equal(durable, undefined);
  const releaseOrigin = "https://api.example.com";
  const releaseEnv = { EXPO_PUBLIC_APP_ENV: "production", EXPO_PUBLIC_R3_AUTH: "1",
    EXPO_PUBLIC_BACKEND_URL: releaseOrigin, EXPO_PUBLIC_API_ENVIRONMENT_ID: environment };
  let calls = [];
  fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/invite/accept") || url.endsWith("/recovery/confirm") || url.endsWith("/logout")) return response(204);
    if (url.endsWith("/login")) return response(200, pair(actorA, "a"));
    if (url.endsWith("/categories")) return response(200, [{ id: "owned" }]);
    return response(200, []);
  };
  ({ auth, api } = runtime({ dev: false, env: releaseEnv }));
  await auth.redeemAccountCode("invite", token("invite", "i"), "synthetic password A");
  assert.equal(auth.authState().status, "signed-out");
  assert.equal(JSON.parse(calls[0].options.body).invitation, token("invite", "i"));
  await auth.redeemAccountCode("recover", token("recover", "r"), "synthetic password B");
  assert.equal(JSON.parse(calls[1].options.body).token, token("recover", "r"));
  assert.equal(durable, undefined);
  const count = calls.length;
  await assert.rejects(auth.redeemAccountCode("invite", "inviteX" + "i".repeat(43), "synthetic password A"));
  await assert.rejects(auth.redeemAccountCode("invite", token("recover", "r"), "synthetic password A"));
  await assert.rejects(auth.redeemAccountCode("recover", token("recover", "r"), "short"));
  assert.equal(calls.length, count);
  await auth.signIn("a@example.com", "synthetic password A");
  await api.listAccounts();
  assert.equal(secureWrites.at(-1).key, `pickwallet.production.${environment}.refresh.v1`);
  assert.equal(secureWrites.at(-1).options.keychainAccessible, 7);
  assert(calls.every(call => call.url.startsWith(releaseOrigin + "/api/") && call.options.redirect === "error"));
  await auth.signOut();
  for (const env of [ { ...releaseEnv, EXPO_PUBLIC_BACKEND_URL: origin },
    { ...releaseEnv, EXPO_PUBLIC_R3_AUTH: "0" }, { EXPO_PUBLIC_R3_AUTH: "0", EXPO_PUBLIC_BACKEND_URL: "http://192.168.1.122:8001" } ]) {
    calls = [];
    ({ auth, api } = runtime({ dev: false, env }));
    assert.equal(auth.authEnabled, true);
    await assert.rejects(auth.signIn("a", "synthetic password A"));
    await assert.rejects(api.listAccounts());
    assert.equal(calls.length, 0);
  }
  ({ auth } = runtime({ dev: false, env: releaseEnv }));
  fetch = async url => url.endsWith("/login") ? response(200, pair(actorB, "b")) : response(204);
  const wrongEnv = { ...pair(actorA, "a"), environment_id: actorB };
  fetch = async url => url.endsWith("/login") ? response(200, wrongEnv) : response(204);
  await assert.rejects(auth.signIn("a", "synthetic password A"));
  assert.equal(auth.authState().status, "signed-out");
  ({ auth } = runtime({ dev: false, env: releaseEnv }));
  fetch = async url => url.endsWith("/login") ? response(200, pair(actorA, "a")) :
    url.endsWith("/categories") ? response(200, [{ id: "owned" }]) : response(204);
  storageFailure = true;
  await assert.rejects(auth.signIn("a", "synthetic password A"));
  assert.equal(auth.authState().status, "signed-out");
  assert.equal(auth.accessToken(), undefined);
  storageFailure = false;
  fetch = async () => response(401, {});
  await assert.rejects(auth.redeemAccountCode("recover", token("recover", "r"), "synthetic password A"), error => error.reason === "invalid");
  assert.equal(auth.authState().status, "signed-out");
  let deletionStatus = 503;
  const deletion = runtime({ dev: false, env: releaseEnv });
  ({ auth, api } = deletion);
  fetch = async (url, options) => {
    if (url.endsWith("/login")) return response(200, pair(actorA, "a"));
    if (url.endsWith("/categories")) return response(200, [{ id: "owned" }]);
    assert.equal(url, releaseOrigin + "/api/auth/account/delete");
    assert.equal(options.headers.Authorization, "Bearer " + token("access", "a"));
    assert.deepEqual(JSON.parse(options.body), { password: "synthetic current password" });
    return response(deletionStatus, {});
  };
  await auth.signIn("a@example.com", "synthetic password A");
  const namespace = auth.privateSession().namespace;
  journalRows = new Map([[namespace + "pending", "a"], ["other:pending", "b"]]);
  for (const status of [401, 503, 200]) {
    deletionStatus = status;
    await assert.rejects(auth.deleteAccount("synthetic current password", deletion.journal.erasePrivateJournal));
    assert.equal(auth.authState().status, "signed-in");
    assert.equal(journalRows.get(namespace + "pending"), "a");
  }
  deletionStatus = 204;
  const staleJournal = deletion.journal.privateJournal();
  await auth.deleteAccount("synthetic current password", deletion.journal.erasePrivateJournal);
  assert.equal(auth.authState().status, "signed-out");
  assert.equal(auth.authState().deletion, "confirmed");
  assert.equal(durable, undefined);
  assert.deepEqual([...journalRows], [["other:pending", "b"]]);
  await assert.rejects(staleJournal.storage.setItem("late", "a"));
  await assert.rejects(api.listAccounts(), error => error.status === 401);

  await auth.signIn("a@example.com", "synthetic password A");
  journalRows.set(namespace + "pending", "a");
  journalFailure = true;
  await auth.deleteAccount("synthetic current password", deletion.journal.erasePrivateJournal);
  assert.equal(auth.authState().status, "signed-out");
  assert.equal(auth.authState().deletion, "device-pending");
  assert.equal(journalRows.get(namespace + "pending"), "a");
  journalFailure = false;
  await runtime({ dev: false, env: releaseEnv }).journal.resumeDeletedJournals();
  assert.deepEqual([...journalRows], [["other:pending", "b"]]);
  console.log("PASS: account deletion confirmation, scoped device purge, stale journal rejection and partial device failure");
  console.log("PASS: production HTTPS/no fallback, account code contracts and validation, environment pinning and no automatic session after redemption");
  console.log("PASS: local session lifecycle, one refresh, no mutation replay, account switch, revocation and private cache clearing");
})().catch(error => { console.error(error); process.exitCode = 1; });
