import React from "react";
import { Platform } from "react-native";
import Svg, { Rect, G, Circle, Path } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedProps,
  useAnimatedStyle,
  useAnimatedReaction,
  withTiming,
  interpolate,
  Easing,
  type SharedValue,
} from "react-native-reanimated";

// Reanimated's NATIVE runtime special-cases the `transform` key and expects an
// RN transform ARRAY — passing an SVG `transform` STRING there triggers the
// "invalidTransform" Remote-Function crash on Android / Expo Go. On Web the
// opposite is true: the individual `translateY`/`rotation`/`originX` props leak
// to the DOM and warn. So we pick the representation per platform (decided
// OUTSIDE the worklet — a plain captured boolean is worklet-safe).
const IS_WEB = Platform.OS === "web";

// Animated SVG primitives. These custom icons intentionally mirror the existing
// Ionicons outline language (fine line stroke, brand-green color, minimalist
// weight) so they belong to the same icon family — but are built from separate
// parts so their INTERNAL graphics can animate while the surrounding rounded
// tile container stays perfectly static.
const ARect = Animated.createAnimatedComponent(Rect);
const AG = Animated.createAnimatedComponent(G);

const SW = 1.7; // stroke width — matches the outline Ionicons weight
const SIZE = 20; // rendered inside the 38px tile, ~ the old size-18 icon

type IconProps = {
  color: string;
  // Increments once each time the section should play its entrance (per Home
  // visit). Watched on the UI thread — no React re-renders while animating.
  play: SharedValue<number>;
};

// Drives a normalized 0→1 timeline whenever `play` increments. Both t=0 and
// t=1 map to the icon's resting pose, so the icon always finishes exactly where
// it started.
function usePlayTimeline(play: SharedValue<number>, duration: number) {
  const t = useSharedValue(0);
  useAnimatedReaction(
    () => play.value,
    (cur, prev) => {
      if (cur > 0 && cur !== prev) {
        t.value = 0;
        // Linear master timeline so the hand-tuned keyframes play at their
        // intended, evenly-paced moments; smoothness comes from the keyframes.
        t.value = withTiming(1, { duration, easing: Easing.linear });
      }
    },
  );
  return t;
}

// ---------------------------------------------------------------------------
// 1) MIS CUENTAS — wallet whose lid opens & closes twice, then rests closed.
// ---------------------------------------------------------------------------
export function WalletIcon({ color, play }: IconProps) {
  const t = usePlayTimeline(play, 1800);
  // Single, smooth open → close of the fold-over flap. Many keyframes on a
  // linear master give an eased-in / eased-out swing (rest → open → rest); both
  // ends sit at the closed pose so the wallet always finishes shut.
  const stops = [0, 0.1, 0.22, 0.36, 0.5, 0.64, 0.78, 0.9, 1];
  const angles = [0, 0, -26, -46, -52, -46, -26, 0, 0];
  const flapProps = useAnimatedProps(() => {
    const a = interpolate(t.value, stops, angles);
    // Web: SVG transform string attribute. Native: individual svg transform
    // props (Reanimated passes these through; it does NOT parse them as a
    // transform array, so no "invalidTransform" crash). Hinge at the flap's
    // bottom-left so only the flap swings — the wallet body stays anchored.
    if (IS_WEB) {
      return { transform: `rotate(${a} 4.6 11)` } as any;
    }
    return { rotation: a, originX: 4.6, originY: 11 } as any;
  });
  return (
    <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24" fill="none">
      {/* wallet body / billfold — stationary */}
      <Rect x={3.5} y={7.5} width={17} height={12} rx={2.8} stroke={color} strokeWidth={SW} fill="none" />
      {/* card-slot line, gives it a clear billfold read */}
      <Path d="M3.5 11 H20.5" stroke={color} strokeWidth={1.1} strokeLinecap="round" />
      {/* clasp / snap button on the front pocket */}
      <Circle cx={15.7} cy={15.2} r={1.25} fill={color} />
      {/* fold-over flap — hinged bottom-left, opens then closes once */}
      <AG animatedProps={flapProps as any}>
        <Path
          d="M4.6 11 V6.6 a2.4 2.4 0 0 1 2.4 -2.4 H17 a2.4 2.4 0 0 1 2.4 2.4 V11 Z"
          stroke={color}
          strokeWidth={SW}
          strokeLinejoin="round"
          fill="none"
        />
      </AG>
    </Svg>
  );
}

// ---------------------------------------------------------------------------
// 2) RESUMEN DEL MES — four bars ripple in a smooth wave, then settle back to
//    their exact original heights.
// ---------------------------------------------------------------------------
const BAR_STOPS = [0, 0.2, 0.4, 0.6, 0.8, 1];
const BASE_Y = 20; // baseline the bars sit on

function Bar({
  t,
  x,
  width,
  heights,
  color,
}: {
  t: SharedValue<number>;
  x: number;
  width: number;
  heights: number[];
  color: string;
}) {
  const props = useAnimatedProps(() => {
    const h = interpolate(t.value, BAR_STOPS, heights);
    return { y: BASE_Y - h, height: h };
  });
  return <ARect animatedProps={props as any} x={x} width={width} rx={1.2} fill={color} />;
}

export function ChartIcon({ color, play }: IconProps) {
  const t = usePlayTimeline(play, 2300);
  // Each bar starts & ends at its resting height; the middle frames form a
  // travelling wave (short → medium → tall → medium → short).
  const bars = [
    { x: 4.0, heights: [6, 16, 8, 12, 6, 6] },
    { x: 8.2, heights: [10, 6, 16, 8, 12, 10] },
    { x: 12.4, heights: [14, 12, 6, 16, 9, 14] },
    { x: 16.6, heights: [9, 14, 12, 6, 15, 9] },
  ];
  return (
    <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24" fill="none">
      {bars.map((b, i) => (
        <Bar key={i} t={t} x={b.x} width={2.8} heights={b.heights} color={color} />
      ))}
    </Svg>
  );
}

// ---------------------------------------------------------------------------
// 3) DEUDAS — a financial coin that spins once around its VERTICAL axis, then
//    rests full-face. Exported name kept (`HandCoinIcon`) so its call site is
//    untouched. The coin's centre stays perfectly anchored; only its internal
//    graphic scales horizontally (edge-on ↔ full-face), mirroring on the back.
// ---------------------------------------------------------------------------
export function HandCoinIcon({ color, play }: IconProps) {
  const t = usePlayTimeline(play, 1800);
  // One full 360° turn about the vertical axis. scaleX follows cos(angle):
  // 1 → 0 → -1 → 0 → 1 = full-face → edge → opposite (mirrored) face → edge →
  // full-face. Magnitude clamped to 0.12 so the coin never fully vanishes.
  // Applied on an OUTER Animated.View (standard RN transform) so it animates
  // reliably on native/Android — not an SVG-only transform prop. The View
  // scales about its own centre, so the coin's centre stays perfectly fixed.
  const spinStyle = useAnimatedStyle(() => {
    const angle = t.value * Math.PI * 2;
    const c = Math.cos(angle);
    const s = c >= 0 ? Math.max(c, 0.12) : Math.min(c, -0.12);
    return { transform: [{ scaleX: s }] };
  });

  return (
    <Animated.View style={spinStyle}>
      <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24" fill="none">
        {/* coin outline */}
        <Circle cx={12} cy={12} r={6.4} stroke={color} strokeWidth={SW} fill="none" />
        {/* subtle inner ring detail */}
        <Circle cx={12} cy={12} r={4.5} stroke={color} strokeWidth={0.9} fill="none" />
        {/* currency ($) mark */}
        <Path d="M12 8 V16" stroke={color} strokeWidth={1.2} strokeLinecap="round" fill="none" />
        <Path
          d="M13.9 9.5 C13.9 8.5 10.1 8.5 10.1 10.2 C10.1 11.6 13.9 11.6 13.9 13.4 C13.9 15.1 10.1 15.1 10.1 14.1"
          stroke={color}
          strokeWidth={1.2}
          strokeLinecap="round"
          fill="none"
        />
      </Svg>
    </Animated.View>
  );
}
