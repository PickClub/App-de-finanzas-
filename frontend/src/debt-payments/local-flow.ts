import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "../api";
import { pendingDebtPayments } from "./pending";
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
