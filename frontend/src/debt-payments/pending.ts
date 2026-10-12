import AsyncStorage from "@react-native-async-storage/async-storage";
import { api, ApiError, debtPaymentBackend } from "../api";
import { assertNoUnresolvedV2 } from "./journal-v2";

export type PaymentPayload = {
  debt_id: string;
  amount: number;
  account_id: string | null;
  notes: string | null;
  date: string | null;
};
type Receipt = { id: string; transaction_id: string };
export type PendingPayment = {
  version: 1;
  backend: string;
  debtId: string;
  key: string;
  payload: PaymentPayload;
  state: "pending" | "conflict" | "confirmed";
  receipt?: Receipt;
};
type Store = Pick<typeof AsyncStorage, "getItem" | "setItem" | "removeItem" | "getAllKeys">;
type Dependencies = {
  storage: Store;
  backend: () => string;
  send: (payload: PaymentPayload, key: string) => Promise<any>;
  newKey: () => string;
  reconcile?: (payload: PaymentPayload, key: string) => ReturnType<typeof api.reconcileDebtPayment>;
};

function payload(input: PaymentPayload): PaymentPayload {
  if (!input || typeof input.debt_id !== "string" || !input.debt_id ||
      !Number.isFinite(input.amount) || input.amount <= 0 ||
      !(input.account_id === null || (typeof input.account_id === "string" && input.account_id.length > 0)) ||
      !(input.notes === null || typeof input.notes === "string") ||
      !(input.date === null || typeof input.date === "string") ||
      Object.keys(input).sort().join() !== "account_id,amount,date,debt_id,notes") {
    throw new Error("Los datos del pago pendiente no son válidos. No se enviará ningún pago.");
  }
  return { debt_id: input.debt_id, amount: input.amount, account_id: input.account_id, notes: input.notes, date: input.date };
}
function same(a: PaymentPayload, b: PaymentPayload) {
  return JSON.stringify(payload(a)) === JSON.stringify(payload(b));
}
function parse(raw: string, backend: string): PendingPayment {
  const record = JSON.parse(raw) as PendingPayment;
  if (!record || record.version !== 1 || record.backend !== backend ||
      typeof record.key !== "string" || !record.key || record.key.length > 128 ||
      !["pending", "conflict", "confirmed"].includes(record.state) ||
      record.debtId !== record.payload?.debt_id ||
      Object.keys(record).some(k => !["version", "backend", "debtId", "key", "payload", "state", "receipt"].includes(k))) {
    throw new Error("El registro del pago requiere revisión. No se enviará ningún pago.");
  }
  payload(record.payload);
  if (record.state === "confirmed") {
    if (!record.receipt || typeof record.receipt.id !== "string" || !record.receipt.id ||
        typeof record.receipt.transaction_id !== "string" || !record.receipt.transaction_id) {
      throw new Error("La confirmación del pago requiere revisión.");
    }
  } else if (record.receipt !== undefined) {
    throw new Error("El estado del pago requiere revisión.");
  }
  return record;
}

// One pending intention per backend, shared by every debt screen in this runtime.
// No storage error is interpreted as an empty journal. Nothing sends on recovery.
export function createPaymentCoordinator(deps: Dependencies) {
  const active = new Map<string, { data: PaymentPayload; promise: Promise<PendingPayment> }>();
  const resetting = new Set<string>();
  function destination() {
    const backend = deps.backend().trim().replace(/\/+$/, "");
    if (!/^https?:\/\//.test(backend)) throw new Error("El backend del pago no está configurado.");
    return { backend, slot: `moneyflow:debt-payment:v1:${encodeURIComponent(backend)}` };
  }
  async function read(slot: string, backend: string) {
    const raw = await deps.storage.getItem(slot);
    return raw === null ? null : parse(raw, backend);
  }
  async function persist(slot: string, record: PendingPayment) {
    const raw = JSON.stringify(record);
    await deps.storage.setItem(slot, raw);
    if (await deps.storage.getItem(slot) !== raw) {
      throw new Error("No se pudo verificar el guardado del pago. No se enviará otro pago.");
    }
    parse(raw, record.backend);
  }
  async function clear(slot: string) {
    await deps.storage.removeItem(slot);
    if (await deps.storage.getItem(slot) !== null) throw new Error("No se pudo limpiar la confirmación del pago.");
  }
  async function recover(): Promise<PendingPayment | null> {
    await assertNoUnresolvedV2(deps.storage);
    const { backend, slot } = destination();
    return read(slot, backend);
  }
  async function perform(data: PaymentPayload, backend: string, slot: string): Promise<PendingPayment> {
    await assertNoUnresolvedV2(deps.storage);
    let record = await read(slot, backend);
    if (record && !same(record.payload, data)) {
      throw new Error("Existe otro pago pendiente. Recupera y resuelve sus datos originales antes de registrar uno diferente.");
    }
    if (record?.state === "conflict") {
      throw new Error("El pago tiene una discrepancia HTTP 409 y requiere conciliación. No se enviará otro pago.");
    }
    if (record?.state === "confirmed") {
      throw new Error("El pago anterior ya está confirmado. Inicia explícitamente un pago nuevo; no se reutilizará su clave.");
    }
    if (!record) {
      record = { version: 1, backend, debtId: data.debt_id, key: deps.newKey(), payload: data, state: "pending" };
    }
    // Re-verify the existing intention too; a retry cannot skip durable storage.
    await persist(slot, record);
    await assertNoUnresolvedV2(deps.storage);
    if (destination().backend !== backend) throw new Error("El destino del pago cambió. No se enviará el pago.");
    let result: any;
    try {
      result = await deps.send({ ...record.payload }, record.key);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await persist(slot, { ...record, state: "conflict" });
      }
      throw error; // Other errors retain the original pending intention and exact data.
    }
    if (!result || typeof result.id !== "string" || !result.id ||
        typeof result.transaction_id !== "string" || !result.transaction_id ||
        result.debt_id !== record.payload.debt_id || result.amount !== record.payload.amount ||
        (result.account_id ?? null) !== record.payload.account_id ||
        (result.notes ?? null) !== record.payload.notes ||
        (record.payload.date !== null && result.date !== record.payload.date)) {
      throw new Error("La respuesta del pago requiere revisión; se conserva la operación pendiente.");
    }
    const receipt = { id: result.id, transaction_id: result.transaction_id };
    const confirmed: PendingPayment = { ...record, state: "confirmed", receipt };
    await persist(slot, confirmed);
    return confirmed;
  }
  function submit(input: PaymentPayload): Promise<PendingPayment> {
    const data = payload(input);
    const { backend, slot } = destination();
    if (resetting.has(backend)) return Promise.reject(new Error("Se está preparando un pago nuevo. Espera."));
    const running = active.get(backend);
    if (running) {
      if (!same(running.data, data)) return Promise.reject(new Error("Otro pago está en curso. Espera a que se resuelva."));
      return running.promise;
    }
    const promise = perform(data, backend, slot).finally(() => { active.delete(backend); });
    active.set(backend, { data, promise });
    return promise;
  }
  async function startNew(): Promise<void> {
    await assertNoUnresolvedV2(deps.storage);
    const { backend, slot } = destination();
    if (active.has(backend) || resetting.has(backend)) throw new Error("Otro pago está en curso.");
    resetting.add(backend);
    try {
      const record = await read(slot, backend);
      if (!record || record.state !== "confirmed") {
        throw new Error("Solo se puede iniciar un pago nuevo después de confirmar el anterior.");
      }
      await clear(slot);
    } finally {
      resetting.delete(backend);
    }
  }
  async function verify(): Promise<PendingPayment | null> {
    const { backend, slot } = destination();
    if (active.has(backend) || resetting.has(backend)) throw new Error("Otro pago está en curso. Espera antes de verificarlo.");
    const record = await recover();
    if (!record || record.state === "confirmed") return record;
    if (!deps.reconcile) throw new Error("La conciliación no está disponible. Se conserva el pago anterior.");
    const result = await deps.reconcile({ ...record.payload }, record.key);
    await assertNoUnresolvedV2(deps.storage);
    if (active.has(backend) || resetting.has(backend) || destination().backend !== backend || JSON.stringify(await read(slot, backend)) !== JSON.stringify(record)) {
      throw new Error("El registro o destino cambió durante la conciliación.");
    }
    if (result.status === "matched" && result.original_request_matches === true &&
        result.current_payment?.id && result.current_payment?.transaction_id) {
      const confirmed: PendingPayment = { ...record, state: "confirmed", receipt: {
        id: result.current_payment.id, transaction_id: result.current_payment.transaction_id,
      } };
      parse(JSON.stringify(confirmed), backend);
      await persist(slot, confirmed);
      return confirmed;
    }
    if (result.status === "discrepancy" || result.status === "cancelled") {
      await persist(slot, { ...record, state: "conflict" });
      throw new Error("El pago tiene una discrepancia o fue anulado; no se enviará ningún pago.");
    }
    return record; // Not found/unverifiable preserves the original intention.
  }
  return { recover, submit, startNew, verify };
}

export const pendingDebtPayments = createPaymentCoordinator({
  storage: AsyncStorage,
  backend: debtPaymentBackend,
  send: (data, key) => api.createDebtPayment(data, key),
  reconcile: (data, key) => api.reconcileDebtPayment(data, key),
  newKey: () => `debt-${Date.now().toString(36)}-${Array.from({ length: 4 }, () => Math.random().toString(36).slice(2)).join("")}`,
});
