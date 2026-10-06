/**
 * Central UI scale.
 *
 * One nominal factor (UI_SCALE) shrinks the app's visual dimensions. Every
 * dimension is scaled EXACTLY ONCE:
 *   - theme `makeStyles` sheets and the two raw StyleSheet sheets pass through
 *     `scaleStyles` (spacing / radius tokens stay BASE values, so a style like
 *     `padding: spacing.lg` is scaled here and nowhere else);
 *   - inline JSX sizes / icon sizes use `us()` / `ufs()` at the call site;
 *   - values measured at runtime (onLayout, measureInWindow, Dimensions,
 *     safe-area insets) are NEVER scaled.
 *
 * Preserved as-is: strings/percentages, flex*, aspectRatio, opacity, zIndex,
 * elevation, durations, angles, progress, hairline borders (<= 2) and
 * pill radii (>= 999).
 *
 * Text legibility: small text is reduced less (see `ufs`). System font
 * scaling (allowFontScaling) is untouched.
 */
import type { ImageStyle, TextStyle, ViewStyle } from "react-native";

/** Base factor (the 80% look). */
export const BASE_SCALE = 0.8;
/** Single additional boost applied on top of the 80% look (+10%). */
export const SCALE_BOOST = 1.1;
/** Effective dimension factor: 0.8 × 1.10 = 0.88. */
export const UI_SCALE = BASE_SCALE * SCALE_BOOST;

const round2 = (v: number) => Math.round(v * 100) / 100;

/** Scale a dimension (width, padding, icon size…): v × 0.88. */
export const us = (v: number): number => round2(v * UI_SCALE);

/**
 * Font size = (80% result WITH its legibility floor) × SCALE_BOOST.
 *   at80 = max(v * 0.8, min(v, 9 + (v - 9) / 2))
 * The boost multiplies the 80% result, so every text grows by exactly the same
 * 10% and the current proportions between texts and elements are kept.
 * Examples (80% → now): 9→9→9.9 · 12→10.5→11.55 · 12.5→10.75→11.83 ·
 *   13→11→12.1 · 17→13.6→14.96 · 18→14.4→15.84 · 28→22.4→24.64
 */
export const ufs = (v: number): number => {
  if (v <= 0) return v;
  const floor = Math.min(v, 9 + (v - 9) / 2);
  const at80 = Math.max(v * BASE_SCALE, floor);
  return round2(at80 * SCALE_BOOST);
};

/** hitSlop that grows an element of the given effective size to `min` (44). */
export const touchSlop = (w: number, h: number = w, min = 44) => {
  const x = Math.max(0, Math.ceil((min - w) / 2));
  const y = Math.max(0, Math.ceil((min - h) / 2));
  return { top: y, bottom: y, left: x, right: x };
};

const DIMENSION_KEYS = new Set([
  "width", "height", "minWidth", "maxWidth", "minHeight", "maxHeight",
  "margin", "marginTop", "marginBottom", "marginLeft", "marginRight",
  "marginHorizontal", "marginVertical", "marginStart", "marginEnd",
  "padding", "paddingTop", "paddingBottom", "paddingLeft", "paddingRight",
  "paddingHorizontal", "paddingVertical", "paddingStart", "paddingEnd",
  "gap", "rowGap", "columnGap",
  "top", "bottom", "left", "right", "start", "end",
  "shadowRadius", "textShadowRadius",
]);
const RADIUS_KEYS = new Set([
  "borderRadius", "borderTopLeftRadius", "borderTopRightRadius",
  "borderBottomLeftRadius", "borderBottomRightRadius",
  "borderTopStartRadius", "borderTopEndRadius", "borderBottomStartRadius", "borderBottomEndRadius",
]);
const BORDER_KEYS = new Set([
  "borderWidth", "borderTopWidth", "borderBottomWidth", "borderLeftWidth", "borderRightWidth",
]);
const PILL = 999;
const HAIRLINE = 2;

type AnyStyle = ViewStyle & TextStyle & ImageStyle & Record<string, any>;

/** Scale one style object (returns a new object; input untouched). */
export function scaleStyle<T extends Record<string, any>>(style: T): T {
  if (!style || typeof style !== "object" || Array.isArray(style)) return style;
  const src = style as AnyStyle;
  const out: Record<string, any> = {};
  // Text metrics follow the effective font ratio so line boxes stay coherent.
  const fsRatio = typeof src.fontSize === "number" && src.fontSize > 0 ? ufs(src.fontSize) / src.fontSize : UI_SCALE;
  for (const k of Object.keys(src)) {
    const v = src[k];
    if (typeof v === "number") {
      if (k === "fontSize") out[k] = ufs(v);
      else if (k === "lineHeight" || k === "letterSpacing") out[k] = Math.round(v * fsRatio * 100) / 100;
      else if (DIMENSION_KEYS.has(k)) out[k] = us(v);
      else if (RADIUS_KEYS.has(k)) out[k] = v >= PILL ? v : us(v);
      else if (BORDER_KEYS.has(k)) out[k] = v <= HAIRLINE ? v : us(v);
      else out[k] = v;
    } else if (k === "shadowOffset" || k === "textShadowOffset") {
      out[k] = v && typeof v === "object" ? { width: us(v.width || 0), height: us(v.height || 0) } : v;
    } else if (k === "transform" && Array.isArray(v)) {
      out[k] = v.map((t: any) => {
        if (t && typeof t === "object") {
          if (typeof t.translateX === "number") return { translateX: us(t.translateX) };
          if (typeof t.translateY === "number") return { translateY: us(t.translateY) };
        }
        return t;
      });
    } else {
      out[k] = v;
    }
  }
  return out as T;
}

/** Scale every entry of a style-sheet factory result. */
export function scaleStyles<T extends Record<string, any>>(sheet: T): T {
  const out: Record<string, any> = {};
  for (const k of Object.keys(sheet)) out[k] = scaleStyle(sheet[k]);
  return out as T;
}
