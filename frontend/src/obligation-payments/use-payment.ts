import { useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { authEnabled } from "../auth-session";
import { privateJournal } from "../private-journal";
import { api } from "../api";
import { newKey } from "../recurring/shared";
import { createObligationPayments, type Record, type Target, type Context } from "./journal";

function paymentJournal() {
  const scope = authEnabled ? privateJournal() : undefined;
  const assertCurrent = () => scope?.assertCurrent();
  return createObligationPayments({
  storage: scope?.storage ?? AsyncStorage,
  readContext: () => { assertCurrent(); return api.getFinancialContext(); },
  newKey: () => newKey("obligation"),
  send: (target,payload,key,context) => { assertCurrent(); return target.kind === "bill" ? api.contextBillPay(target.id,payload,key,context) : api.contextRecurringPay(target.id,payload,key,context); },
  reconcile: (target,payload,key,context) => { assertCurrent(); return target.kind === "bill" ? api.reconcileBillPayment(target.id,payload,key,context) : api.reconcileRecurringPayment(target.id,payload,key,context); },
  });
}
export function useObligationPayment(target: Target) {
  const obligationPayments = useMemo(paymentJournal, []);
  const [record,setRecord] = useState<Record | null>(null);
  const [ready,setReady] = useState(false);
  const [problem,setProblem] = useState<string | null>(null);
  const generation = useRef(0);
  const expected = useRef<Context | null>(null);
  async function recover() {
    const current = generation.current;
    setReady(false);
    try {
      const prepared = await obligationPayments.prepare(target);
      const value = prepared.record;
      if (expected.current && (expected.current.environment_id !== prepared.context.environment_id || expected.current.user_id !== prepared.context.user_id)) {
        throw Error("El contexto cambió. Vuelve a abrir la pantalla; no se enviará el pago.");
      }
      if (current === generation.current) { expected.current = prepared.context; setRecord(value); setReady(true); setProblem(null); }
      return value;
    } catch (error: any) {
      if (current === generation.current) { setReady(false); setProblem(error.message); }
      throw error;
    }
  }
  useEffect(() => {
    generation.current++; expected.current = null; setReady(false); setRecord(null); setProblem(null);
    if (target.id && target.due) void recover().catch(() => {});
    return () => { generation.current++; };
  },[target.kind,target.id,target.due]);
  async function submit(payload: Record["payload"]) {
    const current = generation.current;
    if (!expected.current) throw Error("No se ha verificado el contexto de esta pantalla.");
    try { const value = await obligationPayments.submit(target,payload,expected.current); if (current === generation.current) setRecord(value); return value; }
    catch (error) { if (current === generation.current) await recover().catch(() => {}); throw error; }
  }
  async function retry() {
    const current = generation.current;
    const existing = await recover();
    if (!existing) throw Error("No existe un pago pendiente para recuperar.");
    try { const value = await obligationPayments.retry(target,existing.key); if (current === generation.current) setRecord(value); return value; }
    catch (error) { if (current === generation.current) await recover().catch(() => {}); throw error; }
  }
  async function reconcile() {
    const current = generation.current;
    const existing = await recover();
    if (!existing) throw Error("No existe una intención para conciliar.");
    try { const value = await obligationPayments.reconcile(target,existing.key); if (current === generation.current) setRecord(value); return value; }
    catch (error) { if (current === generation.current) await recover().catch(() => {}); throw error; }
  }
  return { record, ready, problem, locked: !!record || !ready, recover, submit, retry, reconcile,
    acknowledge: (key: string) => obligationPayments.acknowledge(target,key) };
}
