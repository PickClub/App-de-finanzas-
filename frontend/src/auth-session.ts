import { Platform } from "react-native";
import { apiTarget, authenticationRequired } from "./runtime-config";
import * as SecureStore from "expo-secure-store";
import { ensureCategoryCatalog } from "./category-onboarding";
import { queryClient } from "./query-client";

export const authEnabled = authenticationRequired;
const origin = process.env.EXPO_PUBLIC_BACKEND_URL;
const key = (() => { try { return apiTarget().storageKey; } catch { return "pickwallet.invalid.refresh.v1"; } })();
type Identity = { user_id: string; environment_id: string };
type Tokens = Identity & { access: string; refresh: string };
type State = { status: "loading" | "signed-out" | "signed-in"; identity?: Identity; removalUnconfirmed?: boolean; deletion?: "confirmed" | "device-pending" };
let state: State = { status: "loading" };
let tokens: Tokens | undefined;
let generation = 0;
let storageTail: Promise<unknown> = Promise.resolve();
let refreshing: Promise<string> | undefined;
let restoring: Promise<void> | undefined;
const listeners = new Set<() => void>();
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export const subscribeAuth = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
export const authState = () => state;
export const authGeneration = () => generation;
export const accessToken = () => tokens?.access;
export function assertAuthGeneration(expected: number) {
  if (expected !== generation) throw new AuthSessionError("changed");
}

export class AuthSessionError extends Error {
  constructor(public readonly reason: "invalid" | "unavailable" | "changed") {
    super("Authentication session unavailable");
  }
}

function publish(next: State) {
  state = next;
  listeners.forEach(listener => listener());
}

function store(work: () => Promise<unknown>) {
  const next = storageTail.catch(() => {}).then(work);
  storageTail = next;
  return next;
}

function assertAuthTarget() {
  try {
    const target = apiTarget();
    if (!authEnabled || !target.auth || Platform.OS !== "android") throw Error();
  } catch { throw new AuthSessionError("unavailable"); }
}

async function authRequest(path: string, body: object, access?: string) {
  assertAuthTarget();
  const result = await fetch(`${origin}/api/auth/${path}`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(access ? { Authorization: `Bearer ${access}` } : {}) }, body: JSON.stringify(body),
    redirect: "error",
  });
  if (!result.ok) throw new AuthSessionError(result.status === 401 ? "invalid" : "unavailable");
  if (path === "account/delete" && result.status !== 204) throw new AuthSessionError("unavailable");
  return result.status === 204 ? undefined : result.json();
}

async function catalogRequest(access: string, method: "GET" | "POST") {
  assertAuthTarget();
  const suffix = method === "POST" ? "/init-defaults" : "";
  const result = await fetch(`${origin}/api/categories${suffix}`, {
    method,
    headers: { Authorization: `Bearer ${access}`, "Content-Type": "application/json" },
    redirect: "error",
  });
  if (!result.ok) {
    throw new AuthSessionError(result.status === 401 ? "invalid" : "unavailable");
  }
  return result.json();
}

async function install(value: Tokens, expected: number, previous?: Identity) {
  assertAuthGeneration(expected);
  if (!value || !uuid.test(value.user_id) || !uuid.test(value.environment_id) ||
      (apiTarget().environmentId && apiTarget().environmentId !== value.environment_id) ||
      !/^access\.[A-Za-z0-9_-]{43}$/.test(value.access) ||
      !/^refresh\.[A-Za-z0-9_-]{43}$/.test(value.refresh) ||
      (previous && (previous.user_id !== value.user_id || previous.environment_id !== value.environment_id))) {
    throw new AuthSessionError("invalid");
  }
  try {
    if (!previous) {
      await ensureCategoryCatalog({
        assertCurrent: () => assertAuthGeneration(expected),
        read: () => catalogRequest(value.access, "GET"),
        initialize: () => catalogRequest(value.access, "POST"),
      });
    }
    assertAuthGeneration(expected);
    await store(async () => {
      assertAuthGeneration(expected);
      await SecureStore.setItemAsync(key, value.refresh, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
    });
    assertAuthGeneration(expected);
  } catch (error) {
    void authRequest("logout", { refresh: value.refresh }).catch(() => {});
    throw error;
  }
  tokens = value;
  if (state.status !== "signed-in") {
    publish({ status: "signed-in", identity: { user_id: value.user_id, environment_id: value.environment_id } });
  }
  return value.access;
}

function hidePrivateState() {
  generation += 1;
  tokens = undefined;
  refreshing = undefined;
  void queryClient.cancelQueries();
  queryClient.clear();
  publish({ status: "signed-out" });
}

export async function signOut() {
  const refresh = tokens?.refresh;
  hidePrivateState();
  const expected = generation;
  const removed = store(() => SecureStore.deleteItemAsync(key));
  const revoked = refresh ? authRequest("logout", { refresh }) : Promise.resolve();
  const outcomes = await Promise.allSettled([removed, revoked]);
  const confirmed = outcomes.every(result => result.status === "fulfilled");
  if (!confirmed && state.status === "signed-out" && generation === expected) {
    publish({ status: "signed-out", removalUnconfirmed: true });
  }
  return confirmed;
}

export async function deleteAccount(password: string, eraseJournal: (namespace: string) => Promise<void>) {
  const session = privateSession();
  const expected = generation;
  if (!tokens) throw new AuthSessionError("invalid");
  const access = tokens.access;
  await authRequest("account/delete", { password }, access);

  // The response confirms server commit. Never clear a different session's key.
  const current = generation === expected;
  if (current) hidePrivateState();
  const signedOutGeneration = generation;
  const cleanup = await Promise.allSettled([
    eraseJournal(session.namespace),
    current ? store(() => SecureStore.deleteItemAsync(key)) : Promise.resolve(),
  ]);
  if (current && generation === signedOutGeneration) {
    publish({ status: "signed-out", deletion: cleanup.every(item => item.status === "fulfilled") ? "confirmed" : "device-pending" });
  }
}

export async function signIn(email: string, password: string) {
  assertAuthTarget();
  hidePrivateState();
  const expected = generation;
  await store(() => SecureStore.deleteItemAsync(key));
  await install(await authRequest("login", { email, password }), expected);
}

export function restoreAuth() {
  if (!restoring) restoring = (async () => {
    const expected = generation;
    try {
      assertAuthTarget();
      const refresh = await SecureStore.getItemAsync(key);
      if (!refresh) {
        if (generation === expected) hidePrivateState();
        return;
      }
      await install(await authRequest("refresh", { refresh }), expected);
    } catch {
      if (generation === expected) await signOut();
    }
  })();
  return restoring;
}

export function refreshAccess(expected: number, rejected: string): Promise<string> {
  assertAuthGeneration(expected);
  if (!tokens) return Promise.reject(new AuthSessionError("invalid"));
  if (tokens.access !== rejected) return Promise.resolve(tokens.access);
  if (!refreshing) {
    const current = tokens;
    const pending = (async () => {
      try {
        return await install(await authRequest("refresh", { refresh: current.refresh }), expected, current);
      } catch (error) {
        if (generation === expected) await signOut();
        throw error;
      }
    })();
    refreshing = pending;
    void pending.finally(() => { if (refreshing === pending) refreshing = undefined; }).catch(() => {});
  }
  return refreshing;
}

export function privateSession() {
  const identity = state.identity;
  const epoch = generation;
  if (!identity) throw new AuthSessionError("invalid");
  return {
    namespace: `moneyflow:r3:${identity.environment_id}:${identity.user_id}:`,
    assertCurrent: () => assertAuthGeneration(epoch),
  };
}

// Codes come from operator-issued email, never from route parameters or URL queries.
export async function redeemAccountCode(kind: "invite" | "recover", code: string, password: string) {
  assertAuthTarget();
  const purpose = kind === "invite" ? "invite" : "recover";
  if (!(new RegExp(`^${purpose}\\.[A-Za-z0-9_-]{43}$`)).test(code) ||
      Array.from(password).length < 15 || Array.from(password).length > 128) {
    throw new AuthSessionError("invalid");
  }
  const expected = generation;
  await authRequest(kind === "invite" ? "invite/accept" : "recovery/confirm",
    kind === "invite" ? { invitation: code, password } : { token: code, password });
  assertAuthGeneration(expected);
  await signOut();
}
