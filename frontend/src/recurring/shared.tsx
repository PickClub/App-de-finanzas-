// Shared helpers for the Recurring payments feature (screen-scoped).
export { FOREST, useMontserrat, pastel, monthName } from "@/src/budgets/shared";
export { deepen, safeHex, longDate, toYmd, parseAmount, newGoalKey as newKey } from "@/src/goals/shared";

// Generic icons only (never brand logos).
export const RP_ICONS = [
  "tv-outline", "wifi-outline", "musical-notes-outline", "cloud-outline", "barbell-outline", "phone-portrait-outline",
  "home-outline", "shield-checkmark-outline", "car-outline", "flash-outline", "water-outline", "flame-outline",
  "school-outline", "medkit-outline", "game-controller-outline", "newspaper-outline", "card-outline", "receipt-outline",
];
// Existing MoneyFlow palette tones: green, pink, orange, blue, lavender...
export const RP_COLORS = ["#2FA47C", "#E88DAA", "#FF8A3D", "#4C83EA", "#8267B7", "#29C4A9", "#F5B83B", "#FF654A"];
export const RP_FREQS = ["daily", "weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "annual"] as const;
export const MONTH_BASED = new Set(["monthly", "bimonthly", "quarterly", "semiannual", "annual"]);
export const RP_REMINDERS: (number | null)[] = [null, 0, 1, 3, 7];

export type RpSortKey = "due" | "recent" | "high" | "low" | "name";
export const RP_SORT_KEYS: RpSortKey[] = ["due", "recent", "high", "low", "name"];
export const RP_SORT_LABEL: Record<RpSortKey, string> = {
  due: "rp.sortDue", recent: "rp.sortRecent", high: "rp.sortHigh", low: "rp.sortLow", name: "rp.sortName",
};

export function sortRp(list: any[], key: RpSortKey) {
  const arr = [...list];
  switch (key) {
    case "recent":
      return arr.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    case "high":
      return arr.sort((a, b) => (b.due_expected ?? b.amount) - (a.due_expected ?? a.amount));
    case "low":
      return arr.sort((a, b) => (a.due_expected ?? a.amount) - (b.due_expected ?? b.amount));
    case "name":
      return arr.sort((a, b) => a.name.localeCompare(b.name));
    default: {
      // Unpaid first by date, then paid, then items without a date.
      const rank = (x: any) => (x.card_status === "paid" ? 1 : x.due_date ? 0 : 2);
      return arr.sort((a, b) => rank(a) - rank(b) || (a.due_date || "9999").localeCompare(b.due_date || "9999"));
    }
  }
}

export function statusTint(status: string, colors: any) {
  switch (status) {
    case "paid": return colors.incomeGreen;
    case "overdue": return colors.expenseRed;
    case "pending": return colors.brandSecondary;
    case "upcoming": return colors.info;
    default: return colors.muted;
  }
}

/** "5 oct" style short day label from YYYY-MM-DD without timezone shift. */
export function dayLabel(ymd: string | null | undefined, lang: string) {
  if (!ymd) return "";
  const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
  const tag = lang === "en" ? "en-US" : "es-ES";
  return new Date(y, m - 1, d).toLocaleDateString(tag, { day: "numeric", month: "short" }).replace(".", "");
}
