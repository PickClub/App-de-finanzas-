import React, { createContext, useContext, useState, useRef, useEffect, useCallback, useMemo } from "react";
import { AccessibilityInfo, Text as NativeText } from "react-native";
import { useFocusEffect } from "expo-router";
import { runOnJS, useAnimatedReaction, type SharedValue } from "react-native-reanimated";

const DURATION = 650;
const AmountEntry = createContext({ active: false, entry: 0, reduced: true });

// One focus/accessibility subscription for Home, no per-frame Home renders.
export function HomeAmountScope({ children }: { children: React.ReactNode }) {
  const [visit, setVisit] = useState({ active: false, entry: 0 });
  const [reduced, setReduced] = useState(true);
  useEffect(() => {
    let alive = true;
    let eventReceived = false;
    const subscription = AccessibilityInfo.addEventListener("reduceMotionChanged", value => {
      eventReceived = true;
      if (alive) setReduced(value);
    });
    AccessibilityInfo.isReduceMotionEnabled().then(value => {
      if (alive && !eventReceived) setReduced(value);
    }).catch(() => {}); // Keep the final value if accessibility cannot be read.
    return () => { alive = false; subscription.remove(); };
  }, []);
  useFocusEffect(useCallback(() => {
    setVisit(previous => ({ active: true, entry: previous.entry + 1 }));
    return () => setVisit(previous => ({ ...previous, active: false }));
  }, []));
  const value = useMemo(() => ({ ...visit, reduced }), [visit, reduced]);
  return <AmountEntry.Provider value={value}>{children}</AmountEntry.Provider>;
}

// Work from the existing whole-currency text, never the stored balance.
// Integer arithmetic preserves large amounts without a float conversion.
export function amountFrame(finalText: string, progress: number): string {
  const parts = finalText.match(/^([^\d]*)(\d[\d,]*)([^\d]*)$/);
  if (!parts || progress >= 1) return finalText;
  const amount = BigInt(parts[2].replace(/,/g, ""));
  const eased = 1 - (1 - Math.max(0, progress)) ** 2;
  const fraction = BigInt(750000 + Math.round(250000 * eased));
  const displayed = ((amount * fraction + 500000n) / 1000000n).toString();
  return parts[1] + displayed.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + parts[3];
}

export function amountVisible(top: number, height: number, viewportTop: number, viewportHeight: number) {
  "worklet";
  return [top, height, viewportTop, viewportHeight].every(Number.isFinite)
    && height > 0 && viewportHeight > 0 && top < viewportTop + viewportHeight && top + height > viewportTop;
}

export type AmountLayout = { y: number; height: number };
export function validAmountLayout(layout: AmountLayout): AmountLayout | null {
  return Number.isFinite(layout.y) && Number.isFinite(layout.height) && layout.height > 0
    ? { y: layout.y, height: layout.height } : null;
}

export function HomeAmount({ children, ready = true, scrollY, viewportH, layouts }: {
  children: string; ready?: boolean; scrollY?: SharedValue<number>; viewportH?: SharedValue<number>; layouts?: SharedValue<AmountLayout | null>[];
}) {
  const { active, entry, reduced } = useContext(AmountEntry);
  const [visibility, setVisibility] = useState({ visible: !layouts, cycle: 0 });
  const onVisibility = useCallback((visible: boolean) => {
    setVisibility(previous => previous.visible === visible ? previous
      : { visible, cycle: previous.cycle + (visible ? 1 : 0) });
  }, []);
  useAnimatedReaction(() => {
    // Layout events already provide parent-relative positions. Sum the explicit
    // ancestor chain; never query Fabric metrics for nested/absent text views.
    if (!active) return false;
    if (!layouts) return true;
    const offset = scrollY?.value, height = viewportH?.value;
    if (offset === undefined || height === undefined || !Number.isFinite(offset) || !Number.isFinite(height)) return false;
    let top = 0, amountHeight = 0;
    for (const shared of layouts) {
      const layout = shared.value;
      if (!layout || !Number.isFinite(layout.y) || !Number.isFinite(layout.height) || layout.height <= 0) return false;
      top += layout.y;
      amountHeight = layout.height;
    }
    return amountVisible(top - offset, amountHeight, 0, height);
  }, (visible, previous) => {
    if (visible !== previous) runOnJS(onVisibility)(visible);
  }, [active, layouts, scrollY, viewportH, onVisibility]);
  const visit = `${entry}:${visibility.cycle}`;
  const played = useRef("");
  const [frame, setFrame] = useState<{ target: string; entry: string; text: string } | null>(null);
  const numeric = ready && /\d/.test(children);
  const shouldStart = active && visibility.visible && !reduced && numeric && played.current !== visit;
  useEffect(() => {
    if (!active || !visibility.visible || reduced || !numeric || played.current === visit) {
      setFrame(null);
      return;
    }
    played.current = visit;
    const initial = amountFrame(children, 0);
    if (initial === children) return;
    setFrame({ target: children, entry: visit, text: initial });
    let id: number;
    let start: number | null = null;
    let last = -Infinity;
    const tick = (time: number) => {
      if (start === null) start = time;
      const progress = Math.min(1, (time - start) / DURATION);
      if (time - last >= 32 || progress === 1) {
        last = time;
        setFrame({ target: children, entry: visit, text: amountFrame(children, progress) });
      }
      if (progress < 1) id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [active, visit, visibility.visible, reduced, numeric, children]);
  const displayed = !active || !visibility.visible || reduced || !numeric ? children
    : frame?.target === children && frame.entry === visit ? frame.text
    : shouldStart ? amountFrame(children, 0) : children;
  // Reserve missing digit/separator widths while crossing a thousands boundary.
  // Transparent trailing glyphs keep the existing inline footprint constant.
  const padding = "0".repeat(Math.max(0, (children.match(/\d/g) || []).length - (displayed.match(/\d/g) || []).length))
    + ",".repeat(Math.max(0, (children.match(/,/g) || []).length - (displayed.match(/,/g) || []).length));
  return <NativeText style={{ fontVariant: ["tabular-nums"] }} accessibilityLabel={children}>{displayed}
    {padding ? <NativeText style={{ color: "transparent" }} accessible={false}>{padding}</NativeText> : null}
  </NativeText>;
}
