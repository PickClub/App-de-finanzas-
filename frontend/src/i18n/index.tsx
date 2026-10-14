// English-first bundled localization. Only an explicit saved preference overrides en-US.
import { createInstance, type PostProcessorModule } from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useRef,
} from "react";
import { storage } from "@/src/utils/storage";

import en from "./locales/en.json";
import es from "./locales/es.json";

const i18n = createInstance();
const reportedMissing = new Set<string>();
const developmentCoverage: PostProcessorModule = {
  type: "postProcessor",
  name: "developmentCoverage",
  process(value, keys, options) {
    if (typeof __DEV__ === "undefined" || !__DEV__) return value;
    const language = options.lng || i18n.language;
    const namespace = Array.isArray(options.ns) ? options.ns[0] : options.ns || "translation";
    const requested = Array.isArray(keys) ? keys[0] : keys;
    // Share i18next's plural resolver and its fallback for runtimes without Intl.PluralRules.
    const suffix = typeof options.count === "number"
      ? i18n.services.pluralResolver.getSuffix(language, options.count, options) : "";
    const pluralKey = `${requested}${suffix}`;
    if (i18n.getResource(language, namespace, pluralKey) === undefined
      && i18n.getResource(language, namespace, requested) === undefined) {
      const identity = `${language}:${namespace}:${pluralKey}`;
      if (!reportedMissing.has(identity)) {
        reportedMissing.add(identity);
        console.warn(`[i18n] Missing ${identity}; using English fallback`);
      }
    }
    return value;
  },
};

export type Lang = "en-US" | "es";
export const SUPPORTED_LANGS: Lang[] = ["en-US", "es"];
const LANG_KEY = "app-language";

export function normalizeLanguage(value: unknown): Lang | null {
  return value === "en" || value === "en-US" ? "en-US" : value === "es" ? "es" : null;
}

// Synchronous best-effort initial language (web reads localStorage; native falls
// back to English and hydrates the saved value asynchronously).
function readInitialLang(): Lang {
  try {
    const g: any = globalThis as any;
    if (typeof g.localStorage !== "undefined") {
      const v = g.localStorage.getItem(LANG_KEY);
      const saved = normalizeLanguage(v) || (() => { try { return normalizeLanguage(JSON.parse(v || "null")); } catch { return null; } })();
      if (saved) return saved;
    }
  } catch {
    /* noop */
  }
  return "en-US";
}

if (!i18n.isInitialized) {
  i18n
    .use(initReactI18next)
    .use(developmentCoverage)
    .init({
      resources: { "en-US": { translation: en }, es: { translation: es } },
      lng: readInitialLang(),
      fallbackLng: "en-US",
      supportedLngs: SUPPORTED_LANGS,
      load: "currentOnly",
      saveMissing: true,
      postProcess: ["developmentCoverage"],
      missingKeyHandler: (_languages, namespace, key) => {
        if (typeof __DEV__ !== "undefined" && __DEV__) console.warn(`[i18n] Missing ${namespace}:${key}`);
      },
      interpolation: { escapeValue: false },
      returnNull: false,
      returnEmptyString: false,
    });
}

export default i18n;

/** Reactive components subscribe with useTranslation; display helpers read the current locale. */
export function tr(key: string, values?: Record<string, unknown>): string {
  return String(i18n.t(key, values));
}

/** Locale string for Intl/date formatting derived from the active language. */
export function localeTag(lang?: string): string {
  return (lang || i18n.language).startsWith("es") ? "es-US" : "en-US";
}

type LangContextValue = {
  lang: Lang;
  setLang: (l: Lang) => Promise<void>;
};

const LangContext = createContext<LangContextValue>({
  lang: "en-US",
  setLang: async () => {},
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const selectionRevision = useRef(0);
  const writes = useRef(Promise.resolve());
  const [lang, setLangState] = useState<Lang>(() => (i18n.language as Lang) || readInitialLang());

  // Hydrate the persisted preference once (covers native cold starts). On web
  // the synchronous localStorage read above is already authoritative.
  useEffect(() => {
    let active = true;
    const revision = selectionRevision.current;
    (async () => {
      try {
        const g: any = globalThis as any;
        if (typeof g.localStorage !== "undefined" && g.localStorage.getItem(LANG_KEY)) {
          return; // web already resolved synchronously
        }
      } catch {
        /* noop */
      }
      const saved = normalizeLanguage(await storage.getItem<string>(LANG_KEY, ""));
      if (active && revision === selectionRevision.current && saved) {
        if (i18n.language !== saved) i18n.changeLanguage(saved);
        setLangState(saved);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const setLang = useCallback((l: Lang) => {
    const selected = normalizeLanguage(l);
    if (!selected) return Promise.reject(new Error("Unsupported language"));
    selectionRevision.current += 1;
    const save = async () => {
      if (!await storage.setItem(LANG_KEY, selected)) throw new Error("Language preference could not be saved");
      await i18n.changeLanguage(selected);
      setLangState(selected);
      try {
        const g: any = globalThis;
        if (typeof g.localStorage !== "undefined") g.localStorage.setItem(LANG_KEY, JSON.stringify(selected));
      } catch { /* Native storage remains authoritative. */ }
    };
    const pending = writes.current.then(save);
    writes.current = pending.catch(() => {});
    return pending;
  }, []);

  const value = useMemo<LangContextValue>(() => ({ lang, setLang }), [lang, setLang]);

  return React.createElement(LangContext.Provider, { value }, children);
}

export function useLang(): LangContextValue {
  return useContext(LangContext);
}

// Convenience re-export so screens can `import { useTranslation } from "@/src/i18n"`.
export { useTranslation };
