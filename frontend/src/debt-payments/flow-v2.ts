import { ApiError } from "../api";
import { createV2Journal, validateFinancialContext, FinancialContext, PaymentRecordV2 } from "./journal-v2";
import type { PaymentPayload } from "./pending";

export type PaymentDisplay = Pick<PaymentRecordV2, "key" | "payload" | "state" | "receipt"> & { debtId: string };
type JournalStore = Parameters<typeof createV2Journal>[0];
type Reconciliation = {
  status: "matched" | "discrepancy" | "cancelled" | "not_found" | "unverifiable";
  original_request_matches?: boolean;
  current_payment?: { id: string; transaction_id: string };
};
const locks = new WeakMap<JournalStore, Promise<void>>();
const display = (r: PaymentRecordV2 | null): PaymentDisplay | null => r ? { ...r, debtId: r.payload.debt_id } : null;

// No production activation here. Each caller must supply an explicitly approved identity.
export function createV2PaymentFlow(deps: {
  storage: JournalStore;
  expected: { environment_id: string; user_id: string };
  readContext: () => Promise<FinancialContext>;
  reconcile: (payload: PaymentPayload, key: string, context: FinancialContext) => Promise<Reconciliation>;
  send: (payload: PaymentPayload, key: string, context: FinancialContext) => Promise<any>;
  newKey: () => string;
}) {
  const expected = { ...deps.expected };
  async function context() {
    const value = validateFinancialContext(await deps.readContext());
    if (value.environment_id !== expected.environment_id || value.user_id !== expected.user_id ||
        !value.capabilities.debt_payment_reconciliation) throw new Error("El contexto local no está verificado. No se enviará ningún pago.");
    return value;
  }
  const journal = createV2Journal(deps.storage, context);
  function exclusive<T>(work: () => Promise<T>): Promise<T> {
    const run = (locks.get(deps.storage) ?? Promise.resolve()).then(work);
    locks.set(deps.storage, run.then(() => undefined, () => undefined));
    return run;
  }
  async function confirm(record: PaymentRecordV2, receipt: { id: string; transaction_id: string }) {
    if (!receipt || typeof receipt.id !== "string" || !receipt.id ||
        typeof receipt.transaction_id !== "string" || !receipt.transaction_id) throw new Error("La confirmación no es verificable; se conserva la intención.");
    return display(await journal.save({ ...record, state: "confirmed", receipt: { id: receipt.id, transaction_id: receipt.transaction_id } }))!;
  }
  function recover() { return exclusive(async () => display(await journal.recover())); }
  function verify() {
    return exclusive(async () => {
      const record = await journal.recover();
      if (!record || record.state === "confirmed") return display(record);
      const result = await deps.reconcile({ ...record.payload }, record.key, await context());
      if (result.status === "matched" && result.original_request_matches === true && result.current_payment) {
        return confirm(record, result.current_payment);
      }
      if (result.status === "discrepancy" || result.status === "cancelled") {
        await journal.save({ ...record, state: "conflict" });
        throw new Error("El pago tiene una discrepancia o fue anulado. Se conserva el registro.");
      }
      return display(record); // No creation, key generation or retry from verification.
    });
  }
  function submit(input: PaymentPayload) {
    const frozen = { ...input };
    return exclusive(async () => {
      let record = await journal.recover();
      if (record) {
        if (Object.keys(record.payload).some(k => record!.payload[k as keyof PaymentPayload] !== frozen[k as keyof PaymentPayload]) ||
            Object.keys(frozen).sort().join() !== Object.keys(record.payload).sort().join()) throw new Error("Se deben conservar los datos exactos del pago anterior.");
        if (record.state === "confirmed") throw new Error("El pago ya está confirmado. Inicia explícitamente una nueva intención.");
        // Recovery is read-only until the user clicks. Always reconcile before a retry.
        const result = await deps.reconcile({ ...record.payload }, record.key, await context());
        if (result.status === "matched" && result.original_request_matches === true && result.current_payment) {
          return confirm(record, result.current_payment);
        }
        if (result.status === "discrepancy" || result.status === "cancelled") {
          await journal.save({ ...record, state: "conflict" });
          throw new Error("El pago tiene una discrepancia o fue anulado. Se conserva el registro y no se reenviará.");
        }
        if (result.status !== "not_found" || record.state === "conflict") {
          throw new Error("El resultado no permite un reintento seguro. Se conserva la intención para conciliación.");
        }
      } else {
        const effective = await context();
        record = { version: 2, environment_id: effective.environment_id, user_id: effective.user_id,
          key: deps.newKey(), payload: frozen, state: "pending" };
      }
      // Persist and verify the exact original payload before any financial request.
      record = await journal.save(record);
      const effective = await context();
      let payment;
      try {
        payment = await deps.send({ ...record.payload }, record.key, effective);
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) await journal.save({ ...record, state: "conflict" });
        throw error;
      }
      if (!payment || ["debt_id", "amount", "account_id", "notes"].some(k => payment[k] !== record!.payload[k as keyof PaymentPayload]) ||
          (record.payload.date !== null && payment.date !== record.payload.date)) throw new Error("Respuesta de pago no verificable. Se conserva la intención.");
      return confirm(record, payment);
    });
  }
  function startNew() {
    return exclusive(async () => {
      const record = await journal.recover();
      if (!record || record.state !== "confirmed") throw new Error("Primero debe confirmarse la intención anterior.");
      await journal.clearConfirmed(record.key);
    });
  }
  return { recover, verify, submit, startNew, supportsReconciliation: true };
}
