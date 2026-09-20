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
  // Surfaces — soft pale green / near-white botanical canvas
  surface: "#EDF4EC",
  onSurface: "#1B2A20",
  surfaceSecondary: "#FFFFFF",
  onSurfaceSecondary: "#1B2A20",
  surfaceTertiary: "#E1ECDD",
  onSurfaceTertiary: "#1B2A20",
  surfaceInverse: "#14311F",
  onSurfaceInverse: "#F1F7EF",
  muted: "#77857A",

  // Brand — deep forest green
  brand: "#1F5A3D",
  onBrand: "#FFFFFF",
  brandPrimary: "#1F5A3D",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#2E7D52",
  onBrandSecondary: "#FFFFFF",
  brandTertiary: "#CFE3D5",
  onBrandTertiary: "#1F5A3D",

  // Status — deepened & harmonized with the forest palette
  success: "#2E7D52",
  onSuccess: "#FFFFFF",
  warning: "#A9761E",
  onWarning: "#FFFFFF",
  error: "#B24A31",
  onError: "#FFFFFF",
  info: "#2C6E7F",
  onInfo: "#FFFFFF",

  // Lines
  border: "#D6E2D2",
  borderStrong: "#BCCDB6",
  divider: "#D6E2D2",

  // Module accents — deep, slightly muted jewel tones (same family)
  accountsBlue: "#2C6E7F",
  statsPurple: "#5E4B6E",
  savingsTurquoise: "#1F7A6B",
  loansYellow: "#A9761E",
  incomeGreen: "#2E7D52",
  expenseRed: "#B24A31",

  // Bottom navigation bar (solid dark forest green with light icons)
  navBar: "#153D29",
  onNavBar: "#FFFFFF",
  navBarMuted: "rgba(255,255,255,0.6)",
};

const dark: typeof light = {
  // Surfaces — deep forest-tinted near-black, slightly lighter cards
  surface: "#0F1A14",
  onSurface: "#EAF2EC",
  surfaceSecondary: "#16241C",
  onSurfaceSecondary: "#EAF2EC",
  surfaceTertiary: "#1F3227",
  onSurfaceTertiary: "#EAF2EC",
  surfaceInverse: "#EAF2EC",
  onSurfaceInverse: "#0F1A14",
  muted: "#8FA096",

  // Brand — brighter forest green for contrast on dark
  brand: "#4FA97A",
  onBrand: "#08120C",
  brandPrimary: "#4FA97A",
  onBrandPrimary: "#08120C",
  brandSecondary: "#6BC392",
  onBrandSecondary: "#08120C",
  brandTertiary: "#1E3A2A",
  onBrandTertiary: "#8FE3B4",

  // Status — same hues, brightened for dark bg
  success: "#4FBF88",
  onSuccess: "#08120C",
  warning: "#D9A441",
  onWarning: "#0F1A14",
  error: "#DE7256",
  onError: "#0F1A14",
  info: "#5FAFC2",
  onInfo: "#06171B",

  // Lines
  border: "#26372D",
  borderStrong: "#37493D",
  divider: "#1F3227",

  // Module accents — same hues, adjusted for legibility on dark
  accountsBlue: "#5FAFC2",
  statsPurple: "#9C86B0",
  savingsTurquoise: "#43BFA9",
  loansYellow: "#D9A441",
  incomeGreen: "#4FBF88",
  expenseRed: "#DE7256",

  // Bottom navigation bar
  navBar: "#0C2418",
  onNavBar: "#FFFFFF",
  navBarMuted: "rgba(255,255,255,0.55)",
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
