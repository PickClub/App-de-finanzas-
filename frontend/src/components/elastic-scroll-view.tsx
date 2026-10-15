import React, { forwardRef, useMemo, useCallback } from "react";
import { ScrollView, PixelRatio, type ScrollViewProps, type FlatListProps } from "react-native";
import { useFocusEffect } from "expo-router";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  cancelAnimation, Easing, ReduceMotion, useAnimatedScrollHandler,
  useAnimatedStyle, useSharedValue, withTiming, useComposedEventHandler, type ScrollHandlerProcessed,
} from "react-native-reanimated";

// One shared edge effect for direct dragging and a native momentum arrival. Native bounce is disabled so it cannot add
// unbounded displacement. Twenty physical pixels, adjusted for device density.
export const MAX_PULL_DISTANCE = 20 / PixelRatio.get();
export function pullDistance(distance: number) {
  "worklet";
  return MAX_PULL_DISTANCE * (1 - Math.exp(-Math.max(0, distance - 12) / 180));
}

// Android emits monotonic native timestamps; other platforms use the UI clock.
function scrollClock(event: unknown) {
  "worklet";
  const timestamp = (event as { timestamp?: number })?.timestamp;
  return typeof timestamp === "number" && Number.isFinite(timestamp) ? timestamp : Date.now();
}

export function momentumPullDistance(speed: number) {
  "worklet";
  // Speed is derived from offsets in points per millisecond, not platform velocity units.
  return Number.isFinite(speed) && speed >= 0.6 ? pullDistance(12 + speed * 180) : 0;
}

function useElasticScroll() {
  const y = useSharedValue(0);
  const pull = useSharedValue(0);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);
  const eligible = useSharedValue(false);
  const dragging = useSharedValue(false);
  const active = useSharedValue(false);
  const touching = useSharedValue(false);
  const releasePending = useSharedValue(false);
  const momentumActive = useSharedValue(false);
  const lastTime = useSharedValue(0);
  const releasedAt = useSharedValue(0);
  const approachSpeed = useSharedValue(0);
  const approachAt = useSharedValue(0);

  useFocusEffect(useCallback(() => {
    active.set(true);
    return () => {
      active.set(false);
      touching.set(false);
      dragging.set(false);
      eligible.set(false);
      releasePending.set(false);
      momentumActive.set(false);
      lastTime.set(0);
      approachSpeed.set(0);
      approachAt.set(0);
      cancelAnimation(pull);
      pull.set(0);
    };
  }, [active, touching, dragging, eligible, releasePending, momentumActive, lastTime, approachSpeed, approachAt, pull]));

  const sampleScroll = (nextY: number, now: number) => {
    "worklet";
    if (!Number.isFinite(nextY) || !Number.isFinite(now)) { momentumActive.set(false); return; }
    const previousY = y.value;
    const elapsed = now - lastTime.value;
    y.set(nextY);
    lastTime.set(now);
    if (!active.value || !momentumActive.value || touching.value || dragging.value) return;
    if (nextY > previousY) { momentumActive.set(false); return; }
    if (previousY <= 0 || elapsed <= 0 || elapsed > 80) return;
    if (nextY > 0) {
      approachSpeed.set((previousY - nextY) / elapsed);
      approachAt.set(now);
      return;
    }
    // Consume this native momentum cycle even if its arrival was too slow.
    momentumActive.set(false);
    // A clamped final pixel must not erase the velocity immediately before impact.
    const age = now - approachAt.value;
    const incoming = age >= 0 && age <= 40 ? approachSpeed.value : 0;
    const peak = momentumPullDistance(Math.max((previousY - nextY) / elapsed, incoming));
    if (peak <= 0) return;
    cancelAnimation(pull);
    // Same shared displacement and same release curve as finger-driven stretching.
    pull.set(withTiming(peak, { duration: 80, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System }, finished => {
      if (finished) pull.set(withTiming(0, { duration: 240, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System }));
    }));
  };
  const scrollHandler = useAnimatedScrollHandler({
    onScroll: event => { sampleScroll(event.contentOffset.y, scrollClock(event)); },
    onBeginDrag: event => {
      touching.set(active.value);
      releasePending.set(false);
      momentumActive.set(false);
      y.set(event.contentOffset.y);
      lastTime.set(scrollClock(event));
    },
    onEndDrag: event => {
      releasePending.set(active.value && touching.value && !dragging.value && event.contentOffset.y > 0);
      touching.set(false);
      releasedAt.set(scrollClock(event));
      lastTime.set(releasedAt.value);
      y.set(event.contentOffset.y);
    },
    onMomentumBegin: event => {
      const now = scrollClock(event), age = now - releasedAt.value;
      momentumActive.set(active.value && releasePending.value && !touching.value && age >= 0 && age <= 120 && event.contentOffset.y > 0);
      releasePending.set(false);
      approachSpeed.set(0);
      approachAt.set(0);
      y.set(event.contentOffset.y);
      lastTime.set(now);
    },
    onMomentumEnd: event => {
      sampleScroll(event.contentOffset.y, scrollClock(event));
      momentumActive.set(false);
      releasePending.set(false);
    },
  });
  const gesture = useMemo(() => Gesture.Simultaneous(
    Gesture.Native(),
    Gesture.Pan().manualActivation(true).maxPointers(1).shouldCancelWhenOutside(false)
      .onTouchesDown((event, manager) => {
        "worklet";
        dragging.set(false);
        momentumActive.set(false);
        releasePending.set(false);
        touching.set(active.value);
        cancelAnimation(pull);
        if (pull.value !== 0) pull.set(withTiming(0, { duration: 240, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System }));
        eligible.set(active.value && y.value <= 0 && event.numberOfTouches === 1 && event.allTouches.length === 1);
        if (!eligible.value) { manager.fail(); return; }
        startX.set(event.allTouches[0].absoluteX);
        startY.set(event.allTouches[0].absoluteY);
      })
      .onTouchesMove((event, manager) => {
        "worklet";
        if (dragging.value) return;
        if (!eligible.value || event.numberOfTouches !== 1 || !event.allTouches[0]) { manager.fail(); return; }
        const dx = event.allTouches[0].absoluteX - startX.value;
        const dy = event.allTouches[0].absoluteY - startY.value;
        if (Math.abs(dx) > 12 || dy < -12 || y.value > 0) { manager.fail(); return; }
        if (dy > 12 && dy > Math.abs(dx) * 1.5) {
          cancelAnimation(pull);
          dragging.set(true);
          manager.activate();
        }
      })
      .onUpdate(event => { "worklet"; if (dragging.value) pull.set(pullDistance(event.translationY)); })
      .onFinalize(() => {
        "worklet";
        eligible.set(false);
        if (dragging.value) {
          dragging.set(false);
          pull.set(withTiming(0, { duration: 240, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System }));
        }
      }),
  ), [y, pull, startX, startY, eligible, dragging, active, momentumActive, releasePending, touching]);
  const movement = useAnimatedStyle(() => ({ transform: [{ translateY: pull.value }] }));
  return { gesture, movement, scrollHandler };
}

type Props = Omit<ScrollViewProps, "onScroll" | "refreshControl"> & {
  // Preserve existing UI-thread scroll tracking (Home), without a JS listener.
  animatedOnScroll?: ScrollHandlerProcessed;
};
export const ElasticScrollView = forwardRef<ScrollView, Props>(function ElasticScrollView(props, ref) {
  const { gesture, movement, scrollHandler } = useElasticScroll();
  const { animatedOnScroll, ...scrollProps } = props;
  const composedScroll = useComposedEventHandler([scrollHandler, animatedOnScroll ?? null]);
  return (
    <Animated.View style={[{ flex: 1 }, movement]}>
      <GestureDetector gesture={gesture}>
        <Animated.ScrollView {...scrollProps} ref={ref} onScroll={composedScroll} scrollEventThrottle={16}
          overScrollMode="never" bounces={false} alwaysBounceVertical={false}>
          {props.children}
        </Animated.ScrollView>
      </GestureDetector>
    </Animated.View>
  );
});

// Keep virtualized lists virtualized: no ScrollView or copied rows around them.
export function ElasticFlatList<T>(props: Omit<FlatListProps<T>, "onScroll" | "refreshControl" | "onRefresh" | "refreshing" | "CellRendererComponent">) {
  const { gesture, movement, scrollHandler } = useElasticScroll();
  return (
    <Animated.View style={[{ flex: 1 }, movement]}>
      <GestureDetector gesture={gesture}>
        <Animated.FlatList {...props} onScroll={scrollHandler} scrollEventThrottle={16}
          overScrollMode="never" bounces={false} alwaysBounceVertical={false} />
      </GestureDetector>
    </Animated.View>
  );
}
