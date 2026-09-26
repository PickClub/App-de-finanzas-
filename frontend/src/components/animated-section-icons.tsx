import React from "react";
import { Platform } from "react-native";
import Svg, { Rect, G, Circle, Path } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedProps,
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
const ACircle = Animated.createAnimatedComponent(Circle);
const APath = Animated.createAnimatedComponent(Path);

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
  const t = usePlayTimeline(play, 2150);
  const stops = [0, 0.14, 0.3, 0.44, 0.6, 0.76, 1];
  const angles = [0, -58, -58, 0, -40, 0, 0];
  const flapProps = useAnimatedProps(() => {
    const a = interpolate(t.value, stops, angles);
    // Web: SVG transform string attribute. Native: individual svg transform
    // props (Reanimated passes these through; it does NOT parse them as a
    // transform array, so no "invalidTransform" crash).
    if (IS_WEB) {
      return { transform: `rotate(${a} 4.5 10)` } as any;
    }
    return { rotation: a, originX: 4.5, originY: 10 } as any;
  });
  return (
    <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24" fill="none">
      {/* wallet body */}
      <Rect x={3.5} y={8.5} width={17} height={11} rx={3} stroke={color} strokeWidth={SW} fill="none" />
      {/* clasp button */}
      <Circle cx={15.6} cy={14} r={1.15} fill={color} />
      {/* lid / flap — hinged on the left, swings open then closed */}
      <AG animatedProps={flapProps as any}>
        <Rect x={3.5} y={4.6} width={17} height={5.6} rx={2.6} stroke={color} strokeWidth={SW} fill="none" />
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
// 3) DEUDAS — an open (cupped) hand receiving a coin. The coin hovers, drops
//    into the palm, softly settles, lifts and drops once more, then rests.
// ---------------------------------------------------------------------------
export function HandCoinIcon({ color, play }: IconProps) {
  const t = usePlayTimeline(play, 2350);

  // Coin vertical position: resting pose = hovering just above the palm.
  const coinStops = [0, 0.14, 0.2, 0.26, 0.46, 0.52, 0.58, 0.8, 1];
  const coinCy = [7, 11.5, 12.6, 11.5, 7, 11.5, 12.4, 11.5, 7];
  // Subtle palm "receive" dip as the coin lands.
  const handStops = [0, 0.2, 0.26, 0.34, 0.52, 0.58, 0.66, 1];
  const handTy = [0, 0, 0.8, 0, 0, 0.8, 0, 0];

  const coinOuterProps = useAnimatedProps(() => ({ cy: interpolate(t.value, coinStops, coinCy) }));
  const coinInnerProps = useAnimatedProps(() => ({ cy: interpolate(t.value, coinStops, coinCy) }));
  // Web: SVG transform string attribute. Native: individual `translateY` svg
  // prop (avoids the transform-array parsing / "invalidTransform" crash).
  const handProps = useAnimatedProps(() => {
    const ty = interpolate(t.value, handStops, handTy);
    if (IS_WEB) {
      return { transform: `translate(0 ${ty})` } as any;
    }
    return { translateY: ty } as any;
  });

  return (
    <Svg width={SIZE} height={SIZE} viewBox="0 0 24 24" fill="none">
      {/* coin (outline ring + tiny inner mark) */}
      <ACircle animatedProps={coinOuterProps as any} cx={12} r={3} stroke={color} strokeWidth={SW} fill="none" />
      <ACircle animatedProps={coinInnerProps as any} cx={12} r={1.25} stroke={color} strokeWidth={1.1} fill="none" />
      {/* cupped hand receiving */}
      <APath
        animatedProps={handProps as any}
        d="M4.4 12.6 q0 6.6 7.6 6.6 q7.6 0 7.6 -6.6"
        stroke={color}
        strokeWidth={SW}
        strokeLinecap="round"
        fill="none"
      />
      {/* small thumb hint to read clearly as a hand */}
      <APath
        animatedProps={handProps as any}
        d="M4.4 12.6 q-1.4 -1.2 -0.3 -3"
        stroke={color}
        strokeWidth={SW}
        strokeLinecap="round"
        fill="none"
      />
    </Svg>
  );
}
