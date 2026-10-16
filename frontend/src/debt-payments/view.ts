import { tr } from "@/src/i18n";
import type { PaymentDisplay } from "./flow-v2";

export function paymentView(operation: PaymentDisplay | null, debtId: string, ready: boolean) {
  if (!ready) return { get title() { return tr("ui.payment_awaiting_verification"); }, action: tr("ui.verify_record"), editable: false, preview: false };
  if (!operation) return { get title() { return tr("ui.record_new_payment"); }, action: tr("ui.confirm_payment"), editable: true, preview: true };
  if (operation.state === "confirmed") return { get title() { return tr("ui.payment_confirmed"); }, action: tr("ui.record_new_payment"), editable: false, preview: false };
  if (operation.debtId !== debtId) return { get title() { return tr("ui.previous_payment_belongs_to_another_debt"); }, action: tr("ui.resolve_previous_payment"), editable: false, preview: false };
  if (operation.state === "conflict") return { get title() { return tr("ui.payment_mismatch"); }, action: tr("ui.reconciliation_required"), editable: false, preview: false };
  return { get title() { return tr("ui.payment_awaiting_verification"); }, action: tr("ui.retry_previous_payment"), editable: false, preview: false };
}
