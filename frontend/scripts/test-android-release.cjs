const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../node_modules/typescript');
const { resolveTarget } = require('../src/release-policy.cjs');
const id = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const origin = 'https://api.example.com';
const production = { environment: 'production', origin, auth: true, release: true, environmentId: id };
assert.equal(resolveTarget(production).origin, origin);
for (const changes of [ { origin: '' }, { origin: 'http://api.example.com' }, { origin: 'http://127.0.0.1:8013' },
  { origin: 'https://127.0.0.1' }, { origin: 'https://localhost' }, { origin: 'https://api.internal' },
  { origin: 'https://api.example.com/path' }, { origin: 'https://user:pass@api.example.com' },
  { origin: 'https://api.example.com?fallback=1' }, { origin: 'https://api.example.com/' },
  { auth: false }, { environment: 'development' }, { environmentId: '' } ]) {
  assert.throws(() => resolveTarget({ ...production, ...changes }));
}
assert.notEqual(resolveTarget(production).storageKey, resolveTarget({ ...production, environment: 'test' }).storageKey);
const code = fs.readFileSync(path.join(__dirname, '../src/account-links.ts'), 'utf8');
const links = {};
vm.runInNewContext(ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: links });
for (const action of ['invite', 'recover']) {
  assert.equal(links.accountFormFromLink(`pickwallet://account/${action}`), action);
  assert.equal(links.accountFormFromLink(`pickwallet:///account/${action}`), action);
}
for (const url of [null, 'frontend://account/invite', 'frontend://account/recover', 'https://evil.example/account/recover', 'pickwallet://accounts', 'pickwallet://account/invite?token=secret',
  'pickwallet://account/recover#token=secret', 'pickwallet://account/recover/../../accounts', 'pickwallet://account/signin']) {
  assert.equal(links.accountFormFromLink(url), undefined);
}
const configFactory = require('../app.config.js');
const original = { ...process.env };
try {
  Object.assign(process.env, { EAS_BUILD_PROFILE: 'production', EXPO_PUBLIC_APP_ENV: 'production',
    EXPO_PUBLIC_R3_AUTH: '1', EXPO_PUBLIC_BACKEND_URL: origin, EXPO_PUBLIC_API_ENVIRONMENT_ID: id, PW_EAS_PROJECT_ID: id });
  const base = require('../app.json').expo;
  const config = configFactory({ config: base });
  assert.equal(config.name, 'PickWallet');
  assert.equal(config.android.package, 'com.pickclub.pickwallet');
  assert.equal(config.scheme, 'pickwallet');
  assert.equal(config.android.allowBackup, false);
  assert.equal(config.updates.enabled, false);
  assert(config.android.blockedPermissions.includes('android.permission.RECORD_AUDIO'));
  delete process.env.PW_EAS_PROJECT_ID;
  assert.throws(() => configFactory({ config: base }));
} finally {
  for (const key of Object.keys(process.env)) if (!(key in original)) delete process.env[key];
  Object.assign(process.env, original);
}
const pkg = require('../package.json'), lock = require('../package-lock.json');
assert.equal(pkg.packageManager, 'npm@10.9.7');
for (const section of ['dependencies', 'devDependencies']) {
  assert.deepEqual(lock.packages[''][section], pkg[section]);
  for (const name of Object.keys(pkg[section])) assert(lock.packages['node_modules/' + name], name);
}
const eas = require('../eas.json');
assert.equal(eas.build.production.android.buildType, 'app-bundle');
assert.equal(eas.build.production.distribution, 'store');
assert.equal(eas.build.production.autoIncrement, true);
const ignore = fs.readFileSync(path.join(__dirname, '../../.easignore'), 'utf8');
const ignores = require('../node_modules/ignore')().add(ignore);
for (const name of ['backend/.env', 'backend/server.py', 'docs/validation/R3_DELIVERY_3.md',
  '.git/config', 'frontend/android/app/debug.keystore', 'frontend/android/app/build.gradle',
  'frontend/.env', 'frontend/src/.env.local', 'frontend/src/credentials.json', 'frontend/node_modules/x/index.js']) {
  assert(ignores.ignores(name), name);
}
for (const name of ['frontend/package.json', 'frontend/package-lock.json', 'frontend/eas.json', 'frontend/app.json',
  'frontend/app.config.js', 'frontend/app/account/[action].tsx', 'frontend/src/auth-session.ts',
  'frontend/src/release-policy.cjs', 'frontend/plugins/with-release-security.js', 'frontend/assets/images/icon.png',
  'frontend/scripts/cmd-guard.js', 'frontend/constants/testIds/auth.js']) assert(!ignores.ignores(name), name);
const manifest = fs.readFileSync(path.join(__dirname, '../android/app/src/main/AndroidManifest.xml'), 'utf8');
assert(manifest.includes('android:usesCleartextTraffic="false"'));
assert(manifest.includes('android:allowBackup="false"'));
for (const permission of ['READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE', 'SYSTEM_ALERT_WINDOW']) assert(!manifest.includes(permission));
const gradle = fs.readFileSync(path.join(__dirname, '../android/app/build.gradle'), 'utf8');
assert(!gradle.slice(gradle.indexOf('        release {')).includes('signingConfig signingConfigs.debug'));
console.log('PASS: release target rejection matrix, storage isolation, account link allowlist, EAS identity/AAB profile and native signing/permission guards');
