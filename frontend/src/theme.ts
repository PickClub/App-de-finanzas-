// MoneyFlow global theme system.
//
// SINGLE SOURCE OF TRUTH: a React context holds the user's `mode`
// ("light" | "dark" | "system") and derives the effective `scheme`.
// Every component reads its colors from `useTheme()` (directly or through
// `makeStyles`), so a theme change re-renders the whole tree instantly —
// no JS bundle reload, so the navigation stack is preserved.
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { StyleSheet, useColorScheme } from "react-native";
import { storage } from "@/src/utils/storage";

export type ColorScheme = "light" | "dark";
export type ThemeMode = "light" | "dark" | "system";

const light = {
  // Surfaces
  surface: "#FFF8F2",
  onSurface: "#27221F",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#27221F",
  surfaceTertiary: "#F2EBE5",
  onSurfaceTertiary: "#27221F",
  surfaceInverse: "#27221F",
  onSurfaceInverse: "#FFF8F2",
  muted: "#8E8883",

  // Brand
  brand: "#FF654A",
  onBrand: "#FFFFFF",
  brandPrimary: "#FF654A",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#FF8A3D",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#FFD3C9",
  onBrandTertiary: "#FF654A",

  // Status
  success: "#2FA47C",
  onSuccess: "#FFFFFF",
  warning: "#F5B83B",
  onWarning: "#FFFFFF",
  error: "#D95345",
  onError: "#FFFFFF",
  info: "#4C83EA",
  onInfo: "#FFFFFF",

  // Lines
  border: "#E8DFD8",
  borderStrong: "#D1C6BE",
  divider: "#E8DFD8",

  // Module accents
  accountsBlue: "#4C83EA",
  statsPurple: "#8F5BE8",
  savingsTurquoise: "#29C4A9",
  loansYellow: "#F5B83B",
  incomeGreen: "#2FA47C",
  expenseRed: "#D95345",
};

const dark: typeof light = {
  // Surfaces — warm near-black background, slightly lighter cards
  surface: "#141210",
  onSurface: "#F5F1EC",
  surfaceSecondary: "#1E1B18",
  onSurfaceSecondary: "#F5F1EC",
  surfaceTertiary: "#2A2622",
  onSurfaceTertiary: "#F5F1EC",
  surfaceInverse: "#F5F1EC",
  onSurfaceInverse: "#141210",
  muted: "#9E9791",

  // Brand — slightly brighter coral for contrast on dark
  brand: "#FF7A63",
  onBrand: "#1A1512",
  brandPrimary: "#FF7A63",
  onBrandPrimary: "#1A1512",
  brandSecondary: "#FF9C5A",
  onBrandSecondary: "#1A1512",
  brandTertiary: "#3E2620",
  onBrandTertiary: "#FF9E8A",

  // Status — same hues, brightened for dark bg
  success: "#37C08D",
  onSuccess: "#0F1613",
  warning: "#F5B83B",
  onWarning: "#1A1512",
  error: "#EB6D5F",
  onError: "#1A1512",
  info: "#6D9BFF",
  onInfo: "#0E1424",

  // Lines
  border: "#2C2723",
  borderStrong: "#3B3630",
  divider: "#2A2622",

  // Module accents — same hues, adjusted for legibility on dark
  accountsBlue: "#6D9BFF",
  statsPurple: "#A57DFF",
  savingsTurquoise: "#3ED4B9",
  loansYellow: "#F5C556",
  incomeGreen: "#37C08D",
  expenseRed: "#EB6D5F",
};

export type ThemeColors = typeof light;
export const themes: { light: ThemeColors; dark: ThemeColors } = { light, dark };

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 8, md: 16, lg: 24, cardLg: 28, pill: 999 };

const THEME_KEY = "theme-mode";

/**
 * Synchronous initial read so web avoids a light/dark flash on first paint.
 * Native has no sync storage, so it starts at "system" and hydrates async.
 */
function readInitialMode(): ThemeMode {
  try {
    const g: any = globalThis as any;
    if (typeof g.localStorage !== "undefined") {
      const v = g.localStorage.getItem(THEME_KEY);
      if (v === "light" || v === "dark" || v === "system") return v;
    }
  } catch {
    /* noop */
  }
  return "system";
}

type ThemeContextValue = {
  mode: ThemeMode; // user preference
  scheme: ColorScheme; // effective / resolved theme
  colors: ThemeColors;
  setMode: (m: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  mode: "system",
  scheme: "light",
  colors: light,
  setMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // `useColorScheme` is reactive: it updates when the OS theme changes while
  // the app is open, so "system" mode follows the device live.
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>(readInitialMode);

  // Hydrate the persisted preference once (covers native cold starts).
  // On web the synchronous localStorage read above is already authoritative,
  // so we must NOT override it with the async store (which can be stale and
  // would incorrectly reset the user's choice back to "system").
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const g: any = globalThis as any;
        if (typeof g.localStorage !== "undefined" && g.localStorage.getItem(THEME_KEY)) {
          return; // web already resolved synchronously
        }
      } catch {
        /* noop */
      }
      const saved = await storage.getItem<ThemeMode>(THEME_KEY, "system" as ThemeMode);
      if (active && (saved === "light" || saved === "dark" || saved === "system")) {
        setModeState((prev) => (prev === saved ? prev : saved));
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const setMode = useCallback((m: ThemeMode) => {
    // Only persist + update global state. Never reload the bundle.
    setModeState(m);
    storage.setItem(THEME_KEY, m);
    try {
      const g: any = globalThis as any;
      if (typeof g.localStorage !== "undefined") g.localStorage.setItem(THEME_KEY, m);
    } catch {
      /* noop */
    }
  }, []);

  const scheme: ColorScheme = mode === "system" ? (system === "dark" ? "dark" : "light") : mode;

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, scheme, colors: themes[scheme], setMode }),
    [mode, scheme, setMode],
  );

  return React.createElement(ThemeContext.Provider, { value }, children);
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}

/**
 * Build a StyleSheet from theme colors. The returned hook rebuilds the styles
 * whenever the effective scheme changes, so every screen stays in sync.
 */
export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors, scheme: ColorScheme) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors, scheme } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors, scheme)), [colors, scheme]);
  };
}
