import type { PaymentDisplay } from "./flow-v2";

export function paymentView(operation: PaymentDisplay | null, debtId: string, ready: boolean) {
  if (!ready) return { title: "Pago pendiente de verificar", action: "Verificar registro", editable: false, preview: false };
  if (!operation) return { title: "Registrar nuevo pago", action: "Confirmar pago", editable: true, preview: true };
  if (operation.debtId !== debtId) return { title: "Pago anterior de otra deuda", action: "Resolver pago anterior", editable: false, preview: false };
  if (operation.state === "confirmed") return { title: "Pago confirmado", action: "Registrar nuevo pago", editable: false, preview: false };
  if (operation.state === "conflict") return { title: "Pago con discrepancia", action: "Requiere conciliación", editable: false, preview: false };
  return { title: "Pago pendiente de verificar", action: "Reintentar pago anterior", editable: false, preview: false };
}
