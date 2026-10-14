import type { ScrollViewProps } from "react-native";

// Native edge effects have no pixel cap. The shared elastic containers provide
// the bounded gesture instead; never combine it with a second native bounce.
export const NATIVE_VERTICAL_SCROLL = Object.freeze({
  overScrollMode: "never",
  bounces: false,
  alwaysBounceVertical: false,
} satisfies Pick<ScrollViewProps, "overScrollMode" | "bounces" | "alwaysBounceVertical">);
