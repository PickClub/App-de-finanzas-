import React, { forwardRef, useMemo } from "react";
import { ScrollView, PixelRatio, type ScrollViewProps, type FlatListProps } from "react-native";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import Animated, {
  cancelAnimation, Easing, ReduceMotion, useAnimatedScrollHandler,
  useAnimatedStyle, useSharedValue, withTiming, useComposedEventHandler, type ScrollHandlerProcessed,
} from "react-native-reanimated";

// One gesture-driven edge effect. Native bounce is disabled so it cannot add
// unbounded displacement. Twenty physical pixels, adjusted for device density.
export const MAX_PULL_DISTANCE = 20 / PixelRatio.get();
export function pullDistance(distance: number) {
  "worklet";
  return MAX_PULL_DISTANCE * (1 - Math.exp(-Math.max(0, distance - 12) / 180));
}

function useElasticScroll() {
  const y = useSharedValue(0);
  const pull = useSharedValue(0);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);
  const eligible = useSharedValue(false);
  const dragging = useSharedValue(false);
  const scrollHandler = useAnimatedScrollHandler(event => { "worklet"; y.value = event.contentOffset.y; });
  const gesture = useMemo(() => Gesture.Simultaneous(
    Gesture.Native(),
    Gesture.Pan().manualActivation(true).maxPointers(1).shouldCancelWhenOutside(false)
      .onTouchesDown((event, manager) => {
        "worklet";
        dragging.value = false;
        eligible.value = y.value <= 0 && event.numberOfTouches === 1 && event.allTouches.length === 1;
        if (!eligible.value) { manager.fail(); return; }
        startX.value = event.allTouches[0].absoluteX;
        startY.value = event.allTouches[0].absoluteY;
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
          dragging.value = true;
          manager.activate();
        }
      })
      .onUpdate(event => { "worklet"; if (dragging.value) pull.value = pullDistance(event.translationY); })
      .onFinalize(() => {
        "worklet";
        eligible.value = false;
        if (dragging.value) {
          dragging.value = false;
          pull.value = withTiming(0, { duration: 240, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System });
        }
      }),
  ), [y, pull, startX, startY, eligible, dragging]);
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
