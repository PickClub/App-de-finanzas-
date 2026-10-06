import React from "react";
import { View } from "react-native";
import { useTheme } from "@/src/theme";
import { us } from "@/src/ui-scale";

export function ProgressBar({
  progress,
  color,
  height = us(8),
  trackColor,
}: {
  progress: number;
  color?: string;
  height?: number;
  trackColor?: string;
}) {
  const { colors } = useTheme();
  const p = Math.max(0, Math.min(1, progress));
  return (
    <View
      style={{
        width: "100%",
        height,
        borderRadius: height / 2,
        backgroundColor: trackColor || colors.surfaceTertiary,
        overflow: "hidden",
      }}
    >
      <View
        style={{
          width: `${p * 100}%`,
          height: "100%",
          borderRadius: height / 2,
          backgroundColor: color || colors.brandPrimary,
        }}
      />
    </View>
  );
}
