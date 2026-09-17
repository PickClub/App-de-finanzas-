export function formatCurrency(amount: number, currency = "USD"): string {
  // Display whole numbers only (no decimals) with thousands separators.
  // The stored numeric value is never modified — this is display formatting only.
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(Math.round(amount));
  const formatted = abs.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "€" : currency === "MXN" ? "$" : "$";
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
  const symbol = currency === "USD" ? "$" : currency === "EUR" ? "€" : currency === "MXN" ? "$" : "$";
  return `${sign}${symbol}${formatted}`;
}

export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "short" });
  } catch {
    return "";
  }
}

export function formatDateLong(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-ES", { day: "2-digit", month: "long", year: "numeric" });
  } catch {
    return "";
  }
}
