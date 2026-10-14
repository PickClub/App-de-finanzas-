import i18n from "./index";
import en from "./locales/en.json";
import es from "./locales/es.json";

// Match existing public messages without changing ApiError, status codes, or
// financial guards. No unknown driver message or response body reaches the UI.
const labels = new Map<string, string>();
function collect(tree: Record<string, unknown>, prefix = "") {
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix + key;
    if (typeof value === "string" && !value.includes("{{")) labels.set(value, path);
    else if (value && typeof value === "object") collect(value as Record<string, unknown>, path + ".");
  }
}
collect(en); collect(es);

export function localizedError(error: unknown): string {
  let value = typeof error === "string" ? error
    : error && typeof error === "object" ? String((error as { detail?: unknown; message?: unknown }).detail
      ?? (error as { message?: unknown }).message ?? "") : "";
  const status = error && typeof error === "object" ? (error as { status?: unknown }).status
    : Number(value.match(/^API (\d{3}):/)?.[1]);
  const envelope = value.match(/^API \d{3}: (.*)$/s);
  if (envelope) {
    try {
      const detail = JSON.parse(envelope[1]).detail;
      if (typeof detail === "string") value = detail;
    } catch { /* Unknown response bodies never become display text. */ }
  }
  const key = labels.get(value);
  if (key) return String(i18n.t(key));
  const fallback = status === 404 ? "notFound" : status === 409 ? "conflict"
    : status === 422 || status === 400 ? "invalidInput" : status === 503 ? "unavailable" : "requestFailed";
  return String(i18n.t(`errors.${fallback}`));
}
