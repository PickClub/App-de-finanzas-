// Centralized bilingual (es/en) i18n system for the app.
//
// - i18next + react-i18next, locally bundled JSON resources (no network).
// - Spanish is the fallback language.
// - On first launch we detect the device language (expo-localization); once the
//   user picks a language manually, the saved preference wins.
// - Persistence uses the app's existing `storage` abstraction (AsyncStorage on
//   native, localStorage on web). On web we also read localStorage synchronously
//   so the first paint is already in the correct language (no flash), mirroring
//   the ThemeProvider pattern.
import i18n from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";
import * as Localization from "expo-localization";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { storage } from "@/src/utils/storage";

import en from "./locales/en.json";
import es from "./locales/es.json";

export type Lang = "es" | "en";
export const SUPPORTED_LANGS: Lang[] = ["es", "en"];
const LANG_KEY = "app-language";

function detectDeviceLang(): Lang {
  try {
    const locales = Localization.getLocales?.() || [];
    const code = (locales[0]?.languageCode || "").toLowerCase();
    if (code === "en") return "en";
    if (code === "es") return "es";
  } catch {
    /* noop */
  }
  return "es"; // fallback
}

// Synchronous best-effort initial language (web reads localStorage; native falls
// back to device detection and hydrates the saved value asynchronously).
function readInitialLang(): Lang {
  try {
    const g: any = globalThis as any;
    if (typeof g.localStorage !== "undefined") {
      const v = g.localStorage.getItem(LANG_KEY);
      if (v === "es" || v === "en") return v;
    }
  } catch {
    /* noop */
  }
  return detectDeviceLang();
}

if (!i18n.isInitialized) {
  i18n
    .use(initReactI18next)
    .init({
      resources: { es: { translation: es }, en: { translation: en } },
      lng: readInitialLang(),
      fallbackLng: "es",
      supportedLngs: SUPPORTED_LANGS,
      interpolation: { escapeValue: false },
      returnNull: false,
      returnEmptyString: false,
    });
}

export default i18n;

/** Locale string for Intl/date formatting derived from the active language. */
export function localeTag(lang?: string): string {
  return (lang || i18n.language) === "en" ? "en-US" : "es-ES";
}

type LangContextValue = {
  lang: Lang;
  setLang: (l: Lang) => void;
};

const LangContext = createContext<LangContextValue>({
  lang: "es",
  setLang: () => {},
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (i18n.language as Lang) || readInitialLang());

  // Hydrate the persisted preference once (covers native cold starts). On web
  // the synchronous localStorage read above is already authoritative.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const g: any = globalThis as any;
        if (typeof g.localStorage !== "undefined" && g.localStorage.getItem(LANG_KEY)) {
          return; // web already resolved synchronously
        }
      } catch {
        /* noop */
      }
      const saved = await storage.getItem<Lang | "">(LANG_KEY, "" as Lang);
      if (active && (saved === "es" || saved === "en")) {
        if (i18n.language !== saved) i18n.changeLanguage(saved);
        setLangState(saved);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    i18n.changeLanguage(l);
    storage.setItem(LANG_KEY, l);
    try {
      const g: any = globalThis as any;
      if (typeof g.localStorage !== "undefined") g.localStorage.setItem(LANG_KEY, l);
    } catch {
      /* noop */
    }
  }, []);

  const value = useMemo<LangContextValue>(() => ({ lang, setLang }), [lang, setLang]);

  return React.createElement(LangContext.Provider, { value }, children);
}

export function useLang(): LangContextValue {
  return useContext(LangContext);
}

// Convenience re-export so screens can `import { useTranslation } from "@/src/i18n"`.
export { useTranslation };
