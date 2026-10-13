// Financial context consistency only: default-user/single_user is NOT authentication.
export type Target = { kind: "bill" | "recurring"; id: string; due: string };
export type Context = { environment_id: string; user_id: "default-user"; mode: "single_user" };
export type Resolution = { status: "matched" | "cancelled" | "tracking_removed"; financial_state: "active" | "annulled" | "none" };
export type Record = { version: 1; key: string; target: Target; context: Context;
  payload: { [field: string]: any }; state: "pending" | "conflict" | "confirmed" | "reconciled"; receipt?: any; resolution?: Resolution };
type Storage = { getItem(key: string): Promise<string | null>; setItem(key: string, value: string): Promise<void>; removeItem(key: string): Promise<void> };
type Deps = { storage: Storage; readContext(): Promise<unknown>; newKey(): string;
  reconcile?(target: Target, payload: Record["payload"], key: string, context: Context): Promise<any>;
  send(target: Target, payload: Record["payload"], key: string, context: Context): Promise<any> };
const slot = "moneyflow:obligation-payment:v1";
const locks = new WeakMap<Storage, Promise<unknown>>();
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const same = (a: any, b: any) => JSON.stringify(a) === JSON.stringify(b);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const id = (value: any) => typeof value === "string" && value.length > 0 && value.trim() === value;
const nullable = (value: any) => value === null || id(value);
const positive = (value: any) => typeof value === "number" && Number.isFinite(value) && value > 0;
const keys = (value: any, allowed: string[]) => value && typeof value === "object" && !Array.isArray(value) &&
  Object.keys(value).sort().join() === allowed.sort().join();
const fail = (): never => { throw Error("No se puede verificar el registro de pago; no se enviará ni eliminará."); };
export function verifiedContext(value: any): Context {
  if (!value || value.version !== 1 || !uuid.test(value.environment_id) || value.user_id !== "default-user" ||
      value.mode !== "single_user" || value.capabilities?.bill_payment_context_headers !== true ||
      value.capabilities?.recurring_payment_context_headers !== true) {
    throw Error("El backend no ofrece un contexto verificable para estos pagos. No se enviará el pago.");
  }
  return { environment_id: value.environment_id, user_id: value.user_id, mode: value.mode };
}
export function verifiedDeletionContext(value: any, kind: Target["kind"], expected?: Context): Context {
  const context = verifiedContext(value);
  const capability = kind === "bill" ? "bill_payment_delete_context_headers" : "recurring_payment_delete_context_headers";
  if (value.capabilities?.[capability] !== true) throw Error("El backend no garantiza el contexto de la anulación. No se enviará la solicitud.");
  if (expected && !same(context, expected)) throw Error("El contexto financiero cambió. No se enviará la anulación.");
  return context;
}
function validate(record: Record): Record {
  if (!record || record.version !== 1 || !id(record.key) || record.key.length > 128 ||
      !keys(record, record.state === "reconciled" ? ["version","key","target","context","payload","state","receipt","resolution"] : record.state === "confirmed" ? ["version","key","target","context","payload","state","receipt"] : ["version","key","target","context","payload","state"]) ||
      !keys(record.context,["environment_id","user_id","mode"]) || !uuid.test(record.context.environment_id) || record.context.user_id !== "default-user" || record.context.mode !== "single_user" ||
      !keys(record.target,["kind","id","due"]) || !["bill","recurring"].includes(record.target.kind) || !id(record.target.id) || !/^\d{4}-\d{2}-\d{2}$/.test(record.target.due) || !Number.isFinite(Date.parse(record.target.due + "T00:00:00Z")) || new Date(record.target.due + "T00:00:00Z").toISOString().slice(0,10) !== record.target.due ||
      !["pending","conflict","confirmed","reconciled"].includes(record.state)) return fail();
  const p = record.payload;
  const fields = record.target.kind === "bill" ? ["amount","account_id","date","notes"] :
    ["due_date","mode","amount","account_id","category_id","date","notes","transaction_id","settles","allow_overpay"];
  if (!keys(p,fields) || typeof p.date !== "string" || !Number.isFinite(Date.parse(p.date)) ||
      !(p.notes === null || typeof p.notes === "string") || !nullable(p.account_id)) return fail();
  if (record.target.kind === "bill") {
    if (!positive(p.amount) || !id(p.account_id)) return fail();
  } else if (p.due_date !== record.target.due || !["expense","link","mark"].includes(p.mode) ||
      !nullable(p.category_id) || !nullable(p.transaction_id) || typeof p.allow_overpay !== "boolean" ||
      !(p.settles === null || typeof p.settles === "boolean") || (p.mode === "link" ? !id(p.transaction_id) || p.amount !== null : !positive(p.amount)) ||
      (p.mode === "expense" && !id(p.account_id))) return fail();
  if (record.state === "confirmed" || record.state === "reconciled") {
    verifyReceipt(record, record.receipt);
    if (!keys(record.receipt, record.target.kind === "bill" ?
      ["id","user_id","amount","account_id","date","transaction_id","bill_id"] :
      ["id","user_id","amount","account_id","date","transaction_id","recurring_id","due_date","mode"])) return fail();
  }
  if (record.state === "reconciled") {
    const r = record.resolution;
    if (!keys(r,["status","financial_state"]) || !r || !["matched","cancelled","tracking_removed"].includes(r.status) ||
        (r.status === "cancelled" ? r.financial_state !== "annulled" || p.mode === "mark" :
          r.financial_state !== (p.mode === "mark" ? "none" : "active"))) return fail();
  }
  return clone(record);
}
function verifyReceipt(record: Record, receipt: any) {
  const p = record.payload;
  if (!receipt || typeof receipt.date !== "string" || !Number.isFinite(Date.parse(receipt.date)) || !positive(receipt.amount) || !nullable(receipt.account_id) || !id(receipt.id) || receipt.user_id !== record.context.user_id || receipt.deleted ||
      (record.target.kind === "bill" ? receipt.bill_id !== record.target.id : receipt.recurring_id !== record.target.id || receipt.due_date !== record.target.due || receipt.mode !== p.mode) ||
      (p.amount !== null && receipt.amount !== p.amount) || (p.mode !== "link" && p.account_id !== null && receipt.account_id !== p.account_id) ||
      (p.transaction_id && receipt.transaction_id !== p.transaction_id) ||
      (p.mode === "mark" ? receipt.transaction_id !== null : !id(receipt.transaction_id))) return fail();
  // link uses the original movement date; other modes use the frozen request date.
  if (p.mode !== "link" && Date.parse(receipt.date) !== Date.parse(p.date)) return fail();
}
export function createObligationPayments(deps: Deps) {
  async function locked<T>(fn: () => Promise<T>): Promise<T> {
    const next = (locks.get(deps.storage) ?? Promise.resolve()).catch(() => {}).then(fn);
    locks.set(deps.storage,next); return next;
  }
  async function read() {
    try {
      const raw = await deps.storage.getItem(slot);
      return raw === null ? null : validate(JSON.parse(raw));
    } catch {
      throw Error("No se puede leer o verificar la intención pendiente. No se enviará ni eliminará el pago.");
    }
  }
  async function write(record: Record) {
    validate(record); const raw = JSON.stringify(record);
    await deps.storage.setItem(slot,raw);
    if (await deps.storage.getItem(slot) !== raw) return fail();
  }
  async function scope(target: Target, record: Record | null) {
    const context = verifiedContext(await deps.readContext());
    if (record && (!same(context,record.context) || !same(target,record.target))) {
      throw Error("Existe un pago anterior en otro contexto, entidad o período. Conserva su registro y recupera la operación original.");
    }
    return context;
  }
  async function send(record: Record) {
    try {
      const receipt = await deps.send(clone(record.target),clone(record.payload),record.key,clone(record.context));
      try { verifyReceipt(record,receipt); } catch (error) {
        await write({ ...record,state:"conflict" }); throw error;
      }
      const fields = record.target.kind === "bill" ?
        ["id","user_id","amount","account_id","date","transaction_id","bill_id"] :
        ["id","user_id","amount","account_id","date","transaction_id","recurring_id","due_date","mode"];
      const minimal = Object.fromEntries(fields.map(field => [field,receipt[field]]));
      const confirmed: Record = { ...record,state:"confirmed",receipt:minimal };
      await write(confirmed); return clone(confirmed);
    } catch (error: any) {
      // 503/network/storage failures can follow a commit. Never create a new key.
      if (error?.status === 409) await write({ ...record,state:"conflict" });
      throw error;
    }
  }
  return {
    prepare: (target: Target) => locked(async () => { const record = await read(); const context = await scope(target,record); return { record:clone(record),context }; }),
    recover: (target: Target) => locked(async () => { const record = await read(); await scope(target,record); return clone(record); }),
    submit: (target: Target, payload: Record["payload"], expected: Context) => locked(async () => {
      const existing = await read(); const context = await scope(target,existing);
      if (!same(context,expected)) throw Error("El contexto cambió desde que se abrió la pantalla. Vuelve a abrirla antes de registrar el pago.");
      if (existing) throw Error("Hay una intención anterior. Recupera su resultado antes de registrar otro pago.");
      const declared: any = await deps.readContext();
      const capability = target.kind === "bill" ? "bill_payment_reconciliation" : "recurring_payment_reconciliation";
      if (!same(verifiedContext(declared),context) || declared.capabilities?.[capability] !== true || !deps.reconcile) {
        throw Error("El backend no garantiza la recuperación verificable de esta intención. No se enviará el pago.");
      }
      const record = validate({ version:1,key:deps.newKey(),target:clone(target),context,payload:clone(payload),state:"pending" });
      await write(record); return send(record);
    }),
    retry: (target: Target, key: string) => locked(async () => {
      const record = await read(); await scope(target,record);
      if (!record || record.key !== key) return fail();
      if (record.state === "confirmed" || record.state === "reconciled") return record;
      if (record.state === "conflict") throw Error("El pago tiene una discrepancia pendiente de verificar. No se reenviará ni se eliminará su registro.");
      return send(record);
    }),
    reconcile: (target: Target, key: string) => locked(async () => {
      const record = await read(); await scope(target,record);
      if (!record || record.key !== key || !deps.reconcile) return fail();
      const value: any = await deps.readContext();
      const context = verifiedContext(value);
      const capability = target.kind === "bill" ? "bill_payment_reconciliation" : "recurring_payment_reconciliation";
      if (!same(context,record.context) || value.capabilities?.[capability] !== true) {
        throw Error("No se puede verificar la conciliación en el contexto original. Se conserva la intención.");
      }
      const result = await deps.reconcile(clone(record.target),clone(record.payload),record.key,clone(record.context));
      if (!result || result.version !== 1 || result.environment_id !== record.context.environment_id || result.user_id !== record.context.user_id ||
          result.origin !== target.kind || result.parent_id !== target.id ||
          (result.original_due_date !== null && result.original_due_date !== target.due)) return fail();
      if (!["matched","cancelled","tracking_removed"].includes(result.status)) {
        if (!["not_found","discrepancy","unverifiable"].includes(result.status) || result.receipt !== null || result.financial_state !== "unknown" ||
            result.original_request_matches !== (result.status === "discrepancy" ? false : null)) return fail();
        throw Error(result.status === "not_found" ? "Intención no encontrada en la consulta. No demuestra un fallo: se conserva bloqueada, con su clave original." :
          result.status === "discrepancy" ? "La intención presenta una discrepancia. Se conserva el registro sin reenviar dinero." :
          "El historial no permite verificar el resultado. Se conserva la intención bloqueada.");
      }
      if (result.original_request_matches !== true || (target.kind === "recurring" && result.original_due_date !== target.due)) return fail();
      verifyReceipt(record,result.receipt);
      const fields = target.kind === "bill" ? ["id","user_id","amount","account_id","date","transaction_id","bill_id"] :
        ["id","user_id","amount","account_id","date","transaction_id","recurring_id","due_date","mode"];
      const resolved: Record = { ...record,state:"reconciled",receipt:Object.fromEntries(fields.map(field => [field,result.receipt[field]])),
        resolution:{status:result.status,financial_state:result.financial_state} };
      await write(resolved); return clone(resolved);
    }),
    acknowledge: (target: Target, key: string) => locked(async () => {
      const record = await read(); await scope(target,record);
      if (!record) return;
      if (record.key !== key || !["confirmed","reconciled"].includes(record.state)) return fail();
      await deps.storage.removeItem(slot);
      if (await deps.storage.getItem(slot) !== null) return fail();
    }),
  };
}
export const OBLIGATION_QUERY_KEYS = ["bills","bill","bills-summary","rp-list","rp-overview","rp-detail","rp-occ","rp-cand",
  "accounts","transactions","summary","calendar-events","calendar-summary","calendar-upcoming"];
export async function invalidateObligationPayments(client: { invalidateQueries(options: { queryKey: string[] }): Promise<unknown> }) {
  await Promise.all(OBLIGATION_QUERY_KEYS.map(key => client.invalidateQueries({queryKey:[key]})));
}
export function reconciliationMessage(record: Record): string {
  if (record.state !== "reconciled") return record.state === "conflict" ? "Intención con discrepancia pendiente de verificar." :
    record.state === "confirmed" ? "Operación confirmada. Verifica su estado actual para continuar." : "Intención pendiente de verificar. Se conserva su clave y payload originales.";
  if (record.resolution?.status === "cancelled") return "Operación confirmada y posteriormente anulada. No se repetirá.";
  if (record.resolution?.status === "tracking_removed") return record.resolution.financial_state === "none" ?
    "Marca administrativa retirada. No hubo gasto financiero." : "Seguimiento retirado. El gasto financiero sigue vigente; no se repetirá.";
  return record.payload.mode === "mark" ? "Marca administrativa confirmada. Sin gasto financiero." :
    record.payload.mode === "link" ? "Seguimiento confirmado. No se registró otro gasto." : "Pago confirmado por conciliación. No se repetirá.";
}
