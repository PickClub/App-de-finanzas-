// Financial calendar helpers (screen-scoped; global theme/typography untouched).
import i18n, { localeTag } from "@/src/i18n";

export type CalKind = "income" | "expense" | "recurring" | "bill" | "debt" | "goal" | "other";
export const CAL_KINDS: CalKind[] = ["income", "expense", "recurring", "bill", "debt", "goal", "other"];

export type CalEvent = {
  id: string;
  kind: CalKind;
  subtype: string;
  source: "transaction" | "recurring" | "debt" | "goal";
  ref_id: string;
  date: string;
  time: string | null;
  title: string;
  account?: string | null;
  category?: string | null;
  amount: number | null;
  sign: number;
  realized: boolean;
  counts_in_net: boolean;
  status: string;
  partial?: boolean;
  days_left?: number;
};

// Event colour system (pastel cards, strong dots/icons).
export const KIND_COLOR: Record<CalKind, string> = {
  income: "#1C9A68",
  expense: "#E5534B",
  recurring: "#E5534B",
  bill: "#8457E8",
  debt: "#E3A21A",
  goal: "#2C78E4",
  other: "#A39C96",
};

// Generic icons (no commercial logos).
export function eventIcon(e: Pick<CalEvent, "kind" | "subtype">): string {
  if (e.subtype === "transfer") return "swap-horizontal";
  switch (e.kind) {
    case "income": return "wallet";
    case "expense": return "cart";
    case "recurring": return "repeat";
    case "bill": return "document-text";
    case "debt": return "cash";
    case "goal": return "flag";
    default: return "ellipse";
  }
}

// Legend groups (expense + recurring share the coral "Pagos" colour).
export const LEGEND: { key: string; color: string }[] = [
  { key: "income", color: KIND_COLOR.income },
  { key: "payments", color: KIND_COLOR.expense },
  { key: "bills", color: KIND_COLOR.bill },
  { key: "debts", color: KIND_COLOR.debt },
  { key: "goals", color: KIND_COLOR.goal },
  { key: "others", color: KIND_COLOR.other },
];

const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
export const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export function parseYmd(s: string) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}
export function addDays(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}
/** Monday-start week containing d. */
export function weekStart(d: Date) {
  return addDays(d, -((d.getDay() + 6) % 7));
}
/** Full Monday-start weeks covering the month (4, 5 or 6 rows; leap years via Date). */
export function monthGrid(year: number, month: number) {
  const first = new Date(year, month - 1, 1);
  const start = weekStart(first);
  const dim = new Date(year, month, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  const cells = Math.ceil((offset + dim) / 7) * 7;
  const days: Date[] = [];
  for (let i = 0; i < cells; i++) days.push(addDays(start, i));
  return { start: days[0], end: days[days.length - 1], days };
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
export function weekdayShort(lang?: string) {
  const tag = localeTag(lang || i18n.language);
  // 1 Jan 2024 was a Monday.
  return Array.from({ length: 7 }, (_, i) =>
    cap(new Date(2024, 0, 1 + i).toLocaleDateString(tag, { weekday: "short" }).replace(".", "")),
  );
}
export function monthTitle(d: Date, lang?: string) {
  const tag = localeTag(lang || i18n.language);
  return `${cap(d.toLocaleDateString(tag, { month: "long" }))} ${d.getFullYear()}`;
}
export function dayTitle(d: Date, lang?: string) {
  const tag = localeTag(lang || i18n.language);
  return cap(d.toLocaleDateString(tag, { weekday: "long", day: "numeric", month: "long" }));
}
export function monthShort(d: Date, lang?: string) {
  const tag = localeTag(lang || i18n.language);
  return d.toLocaleDateString(tag, { month: "short" }).replace(".", "").toUpperCase();
}
export function rangeTitle(a: Date, b: Date, lang?: string) {
  const tag = localeTag(lang || i18n.language);
  const ms = (d: Date) => d.toLocaleDateString(tag, { month: "short" }).replace(".", "");
  return a.getMonth() === b.getMonth()
    ? `${a.getDate()} – ${b.getDate()} ${ms(b)} ${b.getFullYear()}`
    : `${a.getDate()} ${ms(a)} – ${b.getDate()} ${ms(b)} ${b.getFullYear()}`;
}
