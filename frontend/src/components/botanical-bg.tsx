import React from "react";
import { StyleSheet, View } from "react-native";
import Svg, { G, Path, Ellipse, Defs, LinearGradient, Stop } from "react-native-svg";
import { useTheme } from "@/src/theme";

// Purely decorative botanical backdrop.
// Renders large, soft, semi-transparent leaf illustrations that sit BEHIND the
// cards. Contains no text and never intercepts touches (pointerEvents="none").
// Colors follow the current theme so it works in light and dark.

type LeafProps = {
  x: number;
  y: number;
  rotate: number;
  scale: number;
  color: string;
  opacity: number;
};

// A single soft leaf (blade + midrib) drawn in local coordinates and then
// positioned / rotated / scaled by the surrounding <G>.
function Leaf({ x, y, rotate, scale, color, opacity }: LeafProps) {
  return (
    <G x={x} y={y} rotation={rotate} scale={scale} opacity={opacity}>
      <Path
        d="M0 0 C 14 -34, 52 -46, 92 -16 C 54 6, 16 16, 0 0 Z"
        fill={color}
      />
      <Path
        d="M6 -2 C 30 -12, 58 -20, 86 -16"
        stroke={color}
        strokeOpacity={0.5}
        strokeWidth={1.4}
        fill="none"
      />
    </G>
  );
}

export function BotanicalBackground() {
  const { colors, scheme } = useTheme();

  // Leaf tones tuned per scheme so they stay subtle and elegant.
  const c1 = scheme === "dark" ? "#3F8F63" : "#2E7D52";
  const c2 = scheme === "dark" ? "#2E7D52" : "#1F5A3D";
  const c3 = scheme === "dark" ? "#4FA97A" : "#5AA47D";
  const o = scheme === "dark" ? 0.1 : 0.09;

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <Svg width="100%" height="100%" viewBox="0 0 400 860" preserveAspectRatio="xMidYMin slice">
        <Defs>
          <LinearGradient id="botanicalBase" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={colors.surface} />
            <Stop offset="1" stopColor={scheme === "dark" ? colors.surface : "#E4EFE0"} />
          </LinearGradient>
        </Defs>

        {/* pale base wash */}
        <Path d="M0 0 H400 V860 H0 Z" fill="url(#botanicalBase)" />

        {/* Top-right cluster (mirrors the reference's upper foliage) */}
        <Leaf x={330} y={70} rotate={-24} scale={1.5} color={c1} opacity={o} />
        <Leaf x={300} y={40} rotate={18} scale={1.25} color={c2} opacity={o * 0.9} />
        <Leaf x={372} y={150} rotate={62} scale={1.35} color={c3} opacity={o * 0.85} />
        <Leaf x={250} y={120} rotate={-8} scale={1.0} color={c1} opacity={o * 0.7} />

        {/* Mid / lower-left foliage */}
        <Leaf x={20} y={430} rotate={150} scale={1.7} color={c1} opacity={o} />
        <Leaf x={60} y={520} rotate={112} scale={1.2} color={c3} opacity={o * 0.8} />
        <Leaf x={-6} y={610} rotate={190} scale={1.4} color={c2} opacity={o * 0.7} />

        {/* Lower-right foliage */}
        <Leaf x={360} y={690} rotate={210} scale={1.6} color={c1} opacity={o} />
        <Leaf x={320} y={780} rotate={166} scale={1.25} color={c3} opacity={o * 0.8} />

        {/* soft round bokeh accents */}
        <Ellipse cx={120} cy={250} rx={60} ry={50} fill={c3} opacity={o * 0.35} />
        <Ellipse cx={300} cy={470} rx={70} ry={58} fill={c1} opacity={o * 0.3} />
      </Svg>
    </View>
  );
}

export default BotanicalBackground;
