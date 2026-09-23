import i18n, { localeTag } from "@/src/i18n";

export function formatCurrency(amount: number, currency = "USD"): string {
  // Display whole numbers only (no decimals) with thousands separators.
  // The stored numeric value is never modified — this is display formatting only.
  // NOTE: language and currency are independent — the currency symbol never
  // changes with the UI language.
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(Math.round(amount));
  const formatted = abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "\u20ac" : currency === "MXN" ? "$" : "$";
  return `${sign}${symbol}${formatted}`;
}

/**
 * Currency display without decimals — visual-only helper for the debt cards.
 * Rounds to the nearest integer and keeps the comma thousands separator.
 * The stored value in the database is never modified.
 */
export function formatCurrencyInt(amount: number, currency = "USD"): string {
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(Math.round(amount));
  const formatted = abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "\u20ac" : currency === "MXN" ? "$" : "$";
  return `${sign}${symbol}${formatted}`;
}

// Locale-aware interface date formatting. Uses the active UI language
// (es-ES / en-US) so month names follow the selected language.
export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(localeTag(i18n.language), { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

export function formatDateLong(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(localeTag(i18n.language), { day: "2-digit", month: "long", year: "numeric" });
  } catch {
    return "";
  }
}

// Locale-aware "date, time" used by transaction rows (e.g. "23 sept, 4:22 p.m."
// in Spanish or "Sep 23, 4:22 AM" in English).
export function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    const tag = localeTag(i18n.language);
    const date = d.toLocaleDateString(tag, { day: "2-digit", month: "short" }).replace(".", "");
    const time = d.toLocaleTimeString(tag, { hour: "numeric", minute: "2-digit" });
    return `${date}, ${time}`;
  } catch {
    return "";
  }
}

// System/default category display translation. User-created categories are NOT
// translated: we only map the known canonical Spanish default names to the
// active language. Anything not in the map is returned unchanged.
export function translateCategoryName(name?: string | null): string {
  if (!name) return "";
  const key = `categories.system.${name}`;
  const translated = i18n.t(key, { defaultValue: name });
  return translated || name;
}
