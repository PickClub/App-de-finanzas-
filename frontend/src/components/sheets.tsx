import React, { useEffect, useRef, useState } from "react";
import { View, Modal, Animated, Easing, StyleSheet, Dimensions } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, radius, spacing } from "@/src/theme";

import { us, scaleStyles } from "@/src/ui-scale";
import { MoneyFlowConfirmDialog } from "./interaction-system";
import Reanimated, { cancelAnimation, Easing as UIEasing, ReduceMotion, runOnJS, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";
const { height: SCREEN_H } = Dimensions.get("window");

export type SheetOrigin = { x: number; y: number };
type AppSheetProps = {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  testID?: string;
  origin?: SheetOrigin;
};

export function AppSheet(props: AppSheetProps) {
  return props.origin ? <AnchoredAppSheet {...props} /> : <SlidingAppSheet {...props} />;
}

/** Opt-in Profile transition; all other sheets retain their existing animation. */
function AnchoredAppSheet({ visible, onClose, children, testID, origin }: AppSheetProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  const root = useRef<View>(null);
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const alive = useRef(true);
  const generation = useRef(0);
  const ready = useRef(false);
  const shown = useRef(false);
  const bounds = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const windowOrigin = useRef<SheetOrigin | null>(null);
  const progress = useSharedValue(0);
  const offset = useSharedValue({ x: 0, y: 0 });
  const finishClose = (id: number) => { if (alive.current && generation.current === id && !visibleRef.current) setMounted(false); };
  const reveal = () => {
    const card = bounds.current, position = windowOrigin.current;
    if (!visibleRef.current || !shown.current || !card || !position || !origin) return;
    offset.value = { x: origin.x - position.x - card.x - card.width / 2, y: origin.y - position.y - card.y - card.height / 2 };
    if (ready.current) return;
    ready.current = true;
    progress.value = withTiming(1, { duration: 280, easing: UIEasing.out(UIEasing.cubic), reduceMotion: ReduceMotion.System });
  };
  const measureRoot = () => {
    const id = generation.current;
    root.current?.measureInWindow((x, y, width, height) => {
      if (!alive.current || generation.current !== id || !visibleRef.current || ![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return;
      windowOrigin.current = { x, y };
      reveal();
    });
  };
  useEffect(() => {
    const id = ++generation.current;
    if (visible) {
      if (!mounted) {
        progress.value = 0;
        ready.current = false; shown.current = false;
        bounds.current = null; windowOrigin.current = null;
        setMounted(true);
      } else if (ready.current) {
        progress.value = withTiming(1, { duration: 280, easing: UIEasing.out(UIEasing.cubic), reduceMotion: ReduceMotion.System });
      }
    } else if (mounted) {
      if (!ready.current) { setMounted(false); return; }
      progress.value = withTiming(0, { duration: 220, easing: UIEasing.in(UIEasing.cubic), reduceMotion: ReduceMotion.System }, finished => {
        if (finished) runOnJS(finishClose)(id);
      });
    }
  }, [visible]);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; cancelAnimation(progress); };
  }, [progress]);
  const backdrop = useAnimatedStyle(() => ({ opacity: progress.value }));
  const panel = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [{ translateX: offset.value.x * (1 - progress.value) }, { translateY: offset.value.y * (1 - progress.value) }, { scale: 0.08 + 0.92 * progress.value }],
  }));
  if (!mounted) return null;
  return <Modal transparent visible animationType="none" onRequestClose={onClose} statusBarTranslucent hardwareAccelerated
    onShow={() => { shown.current = true; measureRoot(); reveal(); }}>
    <View ref={root} collapsable={false} style={s.root} onLayout={measureRoot}>
      <Reanimated.View style={[s.backdrop, backdrop]}><Pressable style={StyleSheet.absoluteFill} onPress={onClose} testID="sheet-backdrop" /></Reanimated.View>
      <Reanimated.View testID={testID} onStartShouldSetResponderCapture={() => !visibleRef.current}
        onLayout={({ nativeEvent: { layout } }) => {
          if (![layout.x, layout.y, layout.width, layout.height].every(Number.isFinite) || layout.width <= 0 || layout.height <= 0) return;
          bounds.current = layout; reveal();
        }}
        style={[s.sheet, { backgroundColor: colors.surface, borderColor: colors.border, paddingBottom: insets.bottom + us(spacing.lg) }, panel]}>
        <View style={[s.grip, { backgroundColor: colors.borderStrong }]} />
        {children}
      </Reanimated.View>
    </View>
  </Modal>;
}

/**
 * One consistent bottom-sheet primitive used by every transaction action.
 * Warm cream surface, large rounded top corners, subtle border + soft shadow,
 * gray drag indicator. Animates: slide up + fade in / slide down + fade out.
 * No bouncing (cubic easing).
 */
function SlidingAppSheet({
  visible,
  onClose,
  children,
  testID,
}: {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  const ty = useRef(new Animated.Value(SCREEN_H)).current;
  const op = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      requestAnimationFrame(() => {
        Animated.parallel([
          Animated.timing(op, { toValue: 1, duration: 180, useNativeDriver: true }),
          Animated.timing(ty, { toValue: 0, duration: 260, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        ]).start();
      });
    } else if (mounted) {
      Animated.parallel([
        Animated.timing(op, { toValue: 0, duration: 150, useNativeDriver: true }),
        Animated.timing(ty, { toValue: SCREEN_H, duration: 200, easing: Easing.in(Easing.cubic), useNativeDriver: true }),
      ]).start(() => setMounted(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  if (!mounted) return null;

  return (
    <Modal transparent visible animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <View style={s.root}>
        <Animated.View style={[s.backdrop, { opacity: op }]}>
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} testID="sheet-backdrop" />
        </Animated.View>
        <Animated.View
          testID={testID}
          style={[
            s.sheet,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              paddingBottom: insets.bottom + us(spacing.lg),
              transform: [{ translateY: ty }],
            },
          ]}
        >
          <View style={[s.grip, { backgroundColor: colors.borderStrong }]} />
          {children}
        </Animated.View>
      </View>
    </Modal>
  );
}

/** Compatibility name: existing handlers now use the unified centered dialog. */
export function ConfirmSheet(props: React.ComponentProps<typeof MoneyFlowConfirmDialog>) {
  return <MoneyFlowConfirmDialog {...props} />;
}

const s = StyleSheet.create(scaleStyles({
  root: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFill, backgroundColor: "rgba(20,16,12,0.45)" },
  sheet: {
    borderTopLeftRadius: radius.cardLg,
    borderTopRightRadius: radius.cardLg,
    borderWidth: 1,
    paddingTop: 10,
    paddingHorizontal: spacing.lg,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -8 },
    elevation: 24,
  },
  grip: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, marginBottom: 14 },
}));
