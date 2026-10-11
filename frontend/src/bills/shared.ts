// Shared helpers for the Bills (Facturas) feature (screen-scoped; global theme untouched).
import type { QueryClient } from "@tanstack/react-query";
export { FOREST, useMontserrat } from "@/src/budgets/shared";
export { deepen, safeHex, longDate, toYmd, parseAmount, newGoalKey as newKey } from "@/src/goals/shared";
export { RP_ICONS as BILL_ICONS, RP_COLORS as BILL_COLORS } from "@/src/recurring/shared";

export const BILL_FREQS = ["once", "weekly", "monthly", "quarterly", "yearly"] as const;
export const BILL_REMINDERS: (number | null)[] = [null, 1, 3, 7];
export type BillFilter = "all" | "pending" | "paid" | "overdue";
export const BILL_FILTERS: BillFilter[] = ["all", "pending", "paid", "overdue"];

export function statusColor(status: string, colors: any) {
  if (status === "paid") return colors.incomeGreen;
  if (status === "overdue") return colors.expenseRed;
  return colors.brandSecondary;
}

/** "15 oct 2026" from YYYY-MM-DD without timezone shift. */
export function shortDate(ymd: string | null | undefined, lang: string) {
  if (!ymd) return "";
  const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
  const tag = lang === "en" ? "en-US" : "es-ES";
  return new Date(y, m - 1, d).toLocaleDateString(tag, { day: "2-digit", month: "short", year: "numeric" }).replace(/\./g, "").replace(/ de /g, " ");
}

/** Refresh every view that depends on bills (lists, balances, movements, calendar, recurring). */
export function invalidateBills(qc: QueryClient, money = false) {
  const keys: string[][] = [["bills"], ["bills-summary"], ["bill"], ["calendar-events"], ["calendar-summary"], ["calendar-upcoming"]];
  if (money) keys.push(["accounts"], ["transactions"], ["summary"], ["rp-overview"], ["rp-detail"], ["rp-occ"]);
  return Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
}
