// Shared helpers for the Savings Goals feature (screen-scoped; global theme untouched).
import React from "react";
import Svg, { Circle, Path, Ellipse } from "react-native-svg";
import i18n, { localeTag } from "@/src/i18n";
import { FOREST } from "@/src/budgets/shared";

export { FOREST, useMontserrat, pastel } from "@/src/budgets/shared";

// Existing MoneyFlow palette tones (all from COLOR_PALETTE): mint, purple, orange, pink...
export const GOAL_COLORS = ["#2FA47C", "#8F5BE8", "#FF8A3D", "#E88DAA", "#4C83EA", "#29C4A9", "#F5B83B", "#FF654A"];
export const DEFAULT_GOAL_COLOR = GOAL_COLORS[0];
export const GOAL_ICONS = [
  "car", "airplane", "home", "school", "flag", "gift", "laptop", "heart",
  "shield-checkmark", "cash", "bicycle", "medkit", "paw", "diamond", "briefcase", "phone-portrait",
];

/** Darker shade of a hex color for amounts/icons on pastel backgrounds (light mode). */
export function deepen(hex: string, dark: boolean, amount = 0.28): string {
  if (dark) return hex;
  if (hex.toUpperCase() === "#2FA47C") return FOREST;
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const ch = (s: number) => Math.round(((n >> s) & 255) * (1 - amount)).toString(16).padStart(2, "0");
  return `#${ch(16)}${ch(8)}${ch(0)}`;
}

/** 6-digit hex guard so alpha suffixes ("29", "33"...) always produce valid colors. */
export function safeHex(hex?: string | null): string {
  return hex && /^#[0-9a-f]{6}$/i.test(hex) ? hex : DEFAULT_GOAL_COLOR;
}

/** "diciembre de 2027" / "December 2027" from a YYYY-MM-DD date (no timezone shift). */
export function monthYear(ymd?: string | null, lang?: string) {
  if (!ymd) return "";
  const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
  const tag = localeTag(lang || i18n.language);
  const s = new Date(y, (m || 1) - 1, d || 1).toLocaleDateString(tag, { month: "long", year: "numeric" });
  return s;
}

export function longDate(ymd?: string | null, lang?: string) {
  if (!ymd) return "";
  const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1).toLocaleDateString(localeTag(lang || i18n.language), { day: "numeric", month: "long", year: "numeric" });
}

export function toYmd(ms: number) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function parseAmount(v: string) {
  const n = Number((v || "").replace(/,/g, "."));
  return Number.isFinite(n) ? n : NaN;
}

export type GoalSortKey = "recent" | "oldest" | "highPct" | "lowPct" | "nearest" | "highTarget";
export const GOAL_SORT_KEYS: GoalSortKey[] = ["recent", "oldest", "highPct", "lowPct", "nearest", "highTarget"];
export const GOAL_SORT_LABEL: Record<GoalSortKey, string> = {
  recent: "goals.sortRecent",
  oldest: "goals.sortOldest",
  highPct: "goals.sortHighPct",
  lowPct: "goals.sortLowPct",
  nearest: "goals.sortNearest",
  highTarget: "goals.sortHighTarget",
};

export function sortGoals(list: any[], key: GoalSortKey) {
  const arr = [...list];
  const created = (g: any) => g.created_at || "";
  switch (key) {
    case "oldest":
      return arr.sort((a, b) => created(a).localeCompare(created(b)));
    case "highPct":
      return arr.sort((a, b) => (b.pct ?? -1) - (a.pct ?? -1));
    case "lowPct":
      return arr.sort((a, b) => (a.pct ?? 1e9) - (b.pct ?? 1e9));
    case "nearest":
      // Goals without a target date go last.
      return arr.sort((a, b) => (a.target_date || "9999").localeCompare(b.target_date || "9999"));
    case "highTarget":
      return arr.sort((a, b) => b.target_amount - a.target_amount);
    default:
      return arr.sort((a, b) => created(b).localeCompare(created(a)));
  }
}

export function newGoalKey(prefix = "goal") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Lightweight line piggy-bank icon (Ionicons has no piggy bank). */
export function PiggyIcon({ size = 26, color }: { size?: number; color: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <Circle cx="17" cy="5.5" r="2.6" stroke={color} strokeWidth={2} />
      <Path
        d="M6 15.5c0-4.4 4.3-7.5 9.5-7.5 3.2 0 6 1.1 7.7 2.9l2.8-1.1-.6 3.6c.9 1 1.5 2 1.8 3.1H29v4h-2c-.6 1.6-1.7 3-3.2 4v3h-3.5v-1.8c-1.5.4-3.5.4-5 0V28h-3.5v-3.2C8 23.3 6 19.6 6 15.5Z"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      <Circle cx="21.5" cy="14" r="1.3" fill={color} />
      <Path d="M6 15.5c-1.6 0-3-1-3-2.6" stroke={color} strokeWidth={2} strokeLinecap="round" />
      <Ellipse cx="14" cy="11.6" rx="2.4" ry="0.9" fill={color} opacity={0.5} />
    </Svg>
  );
}

/** Target / bullseye with arrow (Ionicons has no bullseye). */
export function TargetIcon({ size = 24, color }: { size?: number; color: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="11" cy="13" r="8.5" stroke={color} strokeWidth={2.2} />
      <Circle cx="11" cy="13" r="4.6" stroke={color} strokeWidth={2.2} />
      <Circle cx="11" cy="13" r="1.4" fill={color} />
      <Path d="M11 13 19.5 4.5" stroke={color} strokeWidth={2.2} strokeLinecap="round" />
      <Path d="M17 3.2v3.8h3.8" stroke={color} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
