import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "../api";
import { authEnabled, authGeneration } from "../auth-session";
import { privateJournal } from "../private-journal";
import { createPaymentCoordinator, pendingDebtPayments } from "./pending";
import { createV2PaymentFlow } from "./flow-v2";

// Opt-in development configuration only. No deployment identity is shared in code.
// Missing/invalid identity with the gate enabled fails closed in the v2 flow.
export const LOCAL_V2_ENABLED: boolean = __DEV__ && process.env.EXPO_PUBLIC_R6_LOCAL_V2 === "1";
const APPROVED_LOCAL_CONTEXT = {
  environment_id: process.env.EXPO_PUBLIC_R6_EXPECTED_ENVIRONMENT_ID ?? "",
  user_id: process.env.EXPO_PUBLIC_R6_EXPECTED_USER_ID ?? "",
};
export const localPaymentFlow = LOCAL_V2_ENABLED ? createV2PaymentFlow({
  storage: AsyncStorage,
  expected: APPROVED_LOCAL_CONTEXT,
  readContext: api.getFinancialContext,
  reconcile: api.reconcileDebtPayment,
  send: api.createContextProtectedDebtPayment,
  newKey: () => `debt-${Date.now()}-${Array.from({ length: 4 }, () => Math.random().toString(36).slice(2)).join("-")}`,
}) : { ...pendingDebtPayments, supportsReconciliation: false };

let cached: { epoch: number; flow: ReturnType<typeof authenticatedPaymentFlow> } | undefined;
export function paymentFlowForSession() {
  if (!authEnabled) return localPaymentFlow;
  const epoch = authGeneration();
  if (cached?.epoch !== epoch) cached = { epoch, flow: authenticatedPaymentFlow() };
  return cached.flow;
}

function authenticatedPaymentFlow() {
  const { storage, assertCurrent } = privateJournal();
  return {
    ...createPaymentCoordinator({
      storage,
      backend: () => { assertCurrent(); return "http://127.0.0.1:8013"; },
      send: (data, key) => { assertCurrent(); return api.createDebtPayment(data, key); },
      reconcile: (data, key) => { assertCurrent(); return api.reconcileDebtPayment(data, key); },
      newKey: () => `debt-${Date.now()}-${Array.from({ length: 4 }, () => Math.random().toString(36).slice(2)).join("-")}`,
    }),
    supportsReconciliation: true,
  };
}
