// Shared validation for v2 recovery and the conservative v1 fallback guard.
import type AsyncStorage from "@react-native-async-storage/async-storage";
import type { PaymentPayload } from "./pending";

export type FinancialContext = {
  version: 1;
  environment_id: string;
  user_id: string;
  mode: "single_user";
  capabilities: { expected_context_headers: boolean; debt_payment_reconciliation: boolean; cross_device_recovery: boolean };
};
export type PaymentRecordV2 = {
  version: 2;
  environment_id: string;
  user_id: string;
  key: string;
  payload: PaymentPayload;
  state: "pending" | "conflict" | "confirmed";
  receipt?: { id: string; transaction_id: string };
};
type Store = Pick<typeof AsyncStorage, "getItem" | "setItem" | "removeItem" | "getAllKeys">;
const prefix = "moneyflow:debt-payment:v2:";
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const locks = new WeakMap<Store, Promise<void>>();

export function validateFinancialContext(value: FinancialContext): FinancialContext {
  if (!value || value.version !== 1 || !uuid.test(value.environment_id) ||
      typeof value.user_id !== "string" || !value.user_id || value.mode !== "single_user" ||
      !value.capabilities || value.capabilities.expected_context_headers !== true ||
      typeof value.capabilities.debt_payment_reconciliation !== "boolean" ||
      typeof value.capabilities.cross_device_recovery !== "boolean") {
    throw new Error("No se puede verificar el contexto financiero.");
  }
  return value;
}
function slot(record: Pick<PaymentRecordV2, "environment_id" | "user_id">) {
  return `${prefix}${record.environment_id}:${encodeURIComponent(record.user_id)}`;
}
function decode(raw: string): PaymentRecordV2 {
  const record = JSON.parse(raw) as PaymentRecordV2;
  const p = record?.payload;
  if (!record || record.version !== 2 || !uuid.test(record.environment_id) ||
      typeof record.user_id !== "string" || !record.user_id || typeof record.key !== "string" ||
      !record.key || record.key.length > 128 || !["pending", "conflict", "confirmed"].includes(record.state) ||
      Object.keys(record).some(k => !["version", "environment_id", "user_id", "key", "payload", "state", "receipt"].includes(k)) ||
      !p || typeof p.debt_id !== "string" || !p.debt_id || !Number.isFinite(p.amount) || p.amount <= 0 ||
      !(p.account_id === null || (typeof p.account_id === "string" && p.account_id.length > 0)) ||
      !(p.notes === null || typeof p.notes === "string") || !(p.date === null || typeof p.date === "string") ||
      Object.keys(p).sort().join() !== "account_id,amount,date,debt_id,notes") {
    throw new Error("El registro v2 requiere revisión; no se reasignará ni eliminará.");
  }
  if (record.state === "confirmed") {
    if (!record.receipt || typeof record.receipt.id !== "string" || !record.receipt.id ||
        typeof record.receipt.transaction_id !== "string" || !record.receipt.transaction_id) throw new Error("Confirmación inválida.");
  } else if (record.receipt !== undefined) throw new Error("Estado de confirmación inválido.");
  return record;
}
function samePayload(a: PaymentPayload, b: PaymentPayload) {
  return ["debt_id", "amount", "account_id", "notes", "date"].every(k => a[k as keyof PaymentPayload] === b[k as keyof PaymentPayload]);
}

export async function assertNoUnresolvedV2(storage: Pick<Store, "getAllKeys" | "getItem">) {
  const keys = await storage.getAllKeys();
  if (!Array.isArray(keys) || keys.some(k => typeof k !== "string")) throw new Error("No se pudo verificar el journal v2.");
  for (const key of keys) {
    if (!key.startsWith(prefix)) continue;
    const raw = await storage.getItem(key);
    if (raw === null) throw new Error("El journal v2 cambió durante la lectura; no se enviará un pago v1.");
    const record = decode(raw);
    if (slot(record) !== key) throw new Error("La identidad del journal v2 no coincide con su ubicación.");
    // v1 cannot establish stable environment identity from its URL. Never guess
    // that a different URL/debt means an unresolved v2 intention is unrelated.
    if (record.state !== "confirmed") throw new Error("Existe un pago v2 sin resolver. Recupera su contexto original; no se enviará un pago v1 ni se creará otra clave.");
  }
}

export function createV2Journal(storage: Store, readContext: () => Promise<FinancialContext>) {
  function exclusive<T>(work: () => Promise<T>): Promise<T> {
    const run = (locks.get(storage) ?? Promise.resolve()).then(work);
    locks.set(storage, run.then(() => undefined, () => undefined));
    return run;
  }
  async function scope() {
    const context = validateFinancialContext(await readContext());
    const keys = await storage.getAllKeys();
    const records: PaymentRecordV2[] = [];
    for (const key of keys) {
      if (key.startsWith("moneyflow:debt-payment:v1:")) {
        if (await storage.getItem(key) !== null) throw new Error("Existe un registro v1 sin identidad verificable. Requiere conciliación; no se migrará automáticamente.");
      } else if (key.startsWith(prefix)) {
        const raw = await storage.getItem(key);
        if (raw === null) throw new Error("El registro cambió durante la lectura.");
        const record = decode(raw);
        if (slot(record) !== key) throw new Error("La identidad del registro no coincide con su ubicación.");
        records.push(record);
        if (record.state !== "confirmed" &&
            (record.environment_id !== context.environment_id || record.user_id !== context.user_id)) {
          throw new Error("Existe una operación sin resolver de otro contexto. No se reasignará.");
        }
      }
    }
    return { context, record: records.find(r => r.environment_id === context.environment_id && r.user_id === context.user_id) ?? null };
  }
  function recover() { return exclusive(async () => (await scope()).record); }
  function save(input: PaymentRecordV2) {
    const record = decode(JSON.stringify(input)); // Freeze caller-owned input before async work.
    return exclusive(async () => {
      const previous = await scope();
      if (record.environment_id !== previous.context.environment_id || record.user_id !== previous.context.user_id) {
        throw new Error("El registro no pertenece al contexto efectivo.");
      }
      if (previous.record && (previous.record.key !== record.key || !samePayload(previous.record.payload, record.payload) ||
          (previous.record.state === "confirmed" && JSON.stringify(previous.record) !== JSON.stringify(record)))) {
        throw new Error("La intención anterior debe conservar su clave, datos y confirmación.");
      }
      const raw = JSON.stringify(record);
      await storage.setItem(slot(record), raw);
      if (await storage.getItem(slot(record)) !== raw) throw new Error("No se pudo verificar la persistencia v2.");
      return decode(raw);
    });
  }
  function clearConfirmed(key: string) {
    return exclusive(async () => {
      const { record } = await scope();
      if (!record || record.key !== key || record.state !== "confirmed") throw new Error("Solo se limpia una confirmación verificada y seleccionada explícitamente.");
      await storage.removeItem(slot(record));
      if (await storage.getItem(slot(record)) !== null) throw new Error("No se pudo verificar la limpieza.");
    });
  }
  return { recover, save, clearConfirmed };
}
