// Shared helpers for the Budgets feature (screen-scoped; global theme/typography untouched).
import { useFonts } from "expo-font";
import i18n, { localeTag } from "@/src/i18n";
import { catLabel } from "@/src/category-labels";

// Existing MoneyFlow dark green (already used by Accounts / Más / Debts screens).
export const FOREST = "#126046";

export function useMontserrat() {
  const [loaded] = useFonts({
    "Montserrat-Bold": require("../../assets/fonts/Montserrat-Bold.ttf"),
    "Montserrat-ExtraBold": require("../../assets/fonts/Montserrat-ExtraBold.ttf"),
  });
  // Explicit fontFamily is honoured by the global Text layer; fontWeight is cleared
  // so web does not synthesise an extra bold on top of the bold file.
  return (extra = false) =>
    loaded ? ({ fontFamily: extra ? "Montserrat-ExtraBold" : "Montserrat-Bold", fontWeight: undefined } as const) : null;
}

export function monthName(year: number, month: number, lang?: string) {
  const s = new Date(year, month - 1, 1).toLocaleDateString(localeTag(lang || i18n.language), { month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function shortDate(iso?: string | null, lang?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(localeTag(lang || i18n.language), { day: "2-digit", month: "short", year: "numeric" }).replace(".", "");
}

export type BudgetStatus = "normal" | "warning" | "reached" | "exceeded";

export function statusColor(status: BudgetStatus, base: string, colors: any) {
  if (status === "exceeded" || status === "reached") return colors.expenseRed;
  if (status === "warning") return colors.warning;
  return base;
}

export function budgetLabel(b: any, cat: any, lang?: string) {
  return cat ? catLabel(cat.name, lang || i18n.language) : b?.name || "";
}

// Pastel diagonal gradient: strongest at top-right, lighter toward bottom-left.
export function pastel(color: string, dark: boolean): [string, string] {
  return dark ? [color + "2E", color + "0A"] : [color + "33", color + "0D"];
}

export type SortKey = "recent" | "highPct" | "lowPct" | "highLimit" | "name";
export const SORT_KEYS: SortKey[] = ["recent", "highPct", "lowPct", "highLimit", "name"];
export const SORT_LABEL: Record<SortKey, string> = {
  recent: "budgets.sortRecent",
  highPct: "budgets.sortHighPct",
  lowPct: "budgets.sortLowPct",
  highLimit: "budgets.sortHighLimit",
  name: "budgets.sortName",
};

export function sortBudgets(list: any[], key: SortKey, labelOf: (b: any) => string) {
  const arr = [...list];
  const created = (b: any) => b.created_at || b.start_date || "";
  switch (key) {
    case "highPct":
      return arr.sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1));
    case "lowPct":
      return arr.sort((a, b) => (a.pct ?? 1e9) - (b.pct ?? 1e9));
    case "highLimit":
      return arr.sort((a, b) => b.amount_limit - a.amount_limit);
    case "name":
      return arr.sort((a, b) => labelOf(a).localeCompare(labelOf(b), localeTag(i18n.language)));
    default:
      return arr.sort((a, b) => created(b).localeCompare(created(a)));
  }
}

export function newIdempotencyKey() {
  return `bud-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
