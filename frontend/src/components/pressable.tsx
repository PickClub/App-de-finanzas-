/**
 * Drop-in <Pressable> that keeps touch areas >= 44 after the UI scale.
 *
 * If the element's (already scaled) style has a numeric width and/or height
 * below 44, the MINIMUM hitSlop needed to reach 44 is added on that axis only.
 * An explicit `hitSlop` prop always wins. Nothing visual changes.
 */
import React from "react";
import { Pressable as RNPressable, StyleSheet, type PressableProps, type ViewStyle } from "react-native";

const MIN_TOUCH = 44;

function autoSlop(style: PressableProps["style"]) {
  const resolved = typeof style === "function" ? style({ pressed: false, hovered: false } as any) : style;
  const flat = (StyleSheet.flatten(resolved as any) || {}) as ViewStyle;
  const w = typeof flat.width === "number" ? flat.width : null;
  const h = typeof flat.height === "number" ? flat.height : null;
  const x = w !== null && w < MIN_TOUCH ? Math.ceil((MIN_TOUCH - w) / 2) : 0;
  const y = h !== null && h < MIN_TOUCH ? Math.ceil((MIN_TOUCH - h) / 2) : 0;
  return x || y ? { top: y, bottom: y, left: x, right: x } : undefined;
}

export const Pressable = React.forwardRef<any, PressableProps>(function Pressable(props, ref) {
  const hitSlop = props.hitSlop ?? autoSlop(props.style);
  return <RNPressable ref={ref} {...props} hitSlop={hitSlop} />;
});
