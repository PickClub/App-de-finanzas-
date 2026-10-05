/**
 * Global typography layer — Montserrat.
 *
 * Drop-in replacements for React Native's <Text> / <TextInput>. They keep every
 * existing prop/style untouched and ONLY change the typeface:
 *   - the existing fontWeight is mapped to the matching Montserrat static file
 *     (Regular / Medium / SemiBold / Bold / ExtraBold) so the current hierarchy is kept
 *     (custom fonts on Android ignore fontWeight, hence one file per weight);
 *   - numbers use tabular figures (fontVariant tabular-nums) unless a style
 *     already sets fontVariant.
 * An explicit fontFamily in a style (e.g. monospace) is always respected.
 * Nested <Text> without its own fontWeight inherits the parent's weight.
 */
import React, { createContext, useContext } from "react";
import {
  StyleSheet,
  Text as RNText,
  TextInput as RNTextInput,
  type TextStyle,
  type StyleProp,
} from "react-native";

export const FONT_FILES = {
  Montserrat_400Regular: require("../../assets/fonts/Montserrat_400Regular.ttf"),
  Montserrat_500Medium: require("../../assets/fonts/Montserrat_500Medium.ttf"),
  Montserrat_600SemiBold: require("../../assets/fonts/Montserrat_600SemiBold.ttf"),
  Montserrat_700Bold: require("../../assets/fonts/Montserrat_700Bold.ttf"),
  Montserrat_800ExtraBold: require("../../assets/fonts/Montserrat_800ExtraBold.ttf"),
};

const REGULAR = "Montserrat_400Regular";

function familyForWeight(w: TextStyle["fontWeight"] | undefined): string | undefined {
  if (w === undefined || w === null) return undefined;
  if (w === "bold") return "Montserrat_700Bold";
  if (w === "normal") return REGULAR;
  const n = typeof w === "number" ? w : parseInt(String(w), 10);
  if (isNaN(n)) return undefined;
  if (n >= 800) return "Montserrat_800ExtraBold";
  if (n >= 700) return "Montserrat_700Bold";
  if (n >= 600) return "Montserrat_600SemiBold";
  if (n >= 500) return "Montserrat_500Medium";
  return REGULAR;
}

const FamilyContext = createContext<string | null>(null);

// True when the rendered text is a numeric value (amounts, %, numeric dates…):
// it contains digits and no letters. Tabular figures are applied only there so
// mixed text ("7 días", "Pago: Tienda") keeps the font's natural spacing.
function plainText(children: React.ReactNode): string {
  if (typeof children === "number") return String(children);
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(plainText).join("");
  return "";
}
function hasDigits(children: React.ReactNode): boolean {
  const s = plainText(children);
  return /\d/.test(s) && !/[A-Za-zÀ-ÿ]/.test(s);
}

function resolve(style: StyleProp<TextStyle>, inherited: string | null, numeric = true) {
  const flat = (StyleSheet.flatten(style) || {}) as TextStyle;
  if (flat.fontFamily) return { family: flat.fontFamily, extra: null };
  const family = familyForWeight(flat.fontWeight) ?? inherited ?? REGULAR;
  const extra: TextStyle = { fontFamily: family, fontWeight: "normal" };
  if (numeric && flat.fontVariant === undefined) extra.fontVariant = ["tabular-nums"];
  return { family, extra };
}

type TextProps = React.ComponentProps<typeof RNText>;
type TextInputProps = React.ComponentProps<typeof RNTextInput>;

export function Text(props: TextProps) {
  const inherited = useContext(FamilyContext);
  const { family, extra } = resolve(props.style as StyleProp<TextStyle>, inherited, hasDigits(props.children));
  return (
    <FamilyContext.Provider value={family}>
      <RNText {...props} style={extra ? [props.style, extra] : props.style} />
    </FamilyContext.Provider>
  );
}

export function TextInput(props: TextInputProps) {
  const { extra } = resolve(props.style as StyleProp<TextStyle>, null);
  return <RNTextInput {...props} style={extra ? [props.style, extra] : props.style} />;
}
