import React, { useState, useEffect, useRef, useCallback } from "react";
import { Tabs, useRouter } from "expo-router";
import { Pressable, View, Text, BackHandler } from "react-native";
import Animated, {
  useSharedValue,
  runOnJS,
  type SharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withSequence,
  interpolate,
  Extrapolation,
  Easing as ReEasing,
} from "react-native-reanimated";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, makeStyles } from "@/src/theme";
import { useTranslation } from "@/src/i18n";

// Bottom-bar tab definitions (icons keep the app's existing solid Ionicons
// language). Order is fixed: Cuentas · IA · (centro) · Informes · Más.
// `labelKey` points at the i18n key; the visible label is translated at render.
const TAB_CONFIG: Record<string, { labelKey: string; icon: string }> = {
  index: { labelKey: "tabs.accounts", icon: "home" },
  transactions: { labelKey: "tabs.ai", icon: "mic" },
  reports: { labelKey: "tabs.reports", icon: "stats-chart" },
  notes: { labelKey: "tabs.notes", icon: "document-text" },
};

// Custom bottom navigation bar. Keeps every existing route/action; only the
// visual presentation is redefined (rounded top, cream surface, compact
// height, integrated wallet+ center button, discreet coral selection dot).
// A single bottom-navigation tab. Owns a subtle icon scale micro-interaction
// that fires ONLY when the tab becomes active (runs on the UI thread). Column
// layout (icon, label, dot slot), colors, labels and testIDs are unchanged.
function TabButton({
  routeName,
  icon,
  label,
  isFocused,
  activeCol,
  inactiveCol,
  onPress,
  onLayout,
  styles,
}: {
  routeName: string;
  icon: string;
  label: string;
  isFocused: boolean;
  activeCol: string;
  inactiveCol: string;
  onPress: () => void;
  onLayout: (e: any) => void;
  styles: any;
}) {
  const scale = useSharedValue(1);
  const wasFocused = useRef(isFocused);

  useEffect(() => {
    if (isFocused && !wasFocused.current) {
      // Subtle pop: 1.00 → 1.07 → 1.00 (spring settle, minimal overshoot).
      scale.value = withSequence(
        withTiming(1.07, { duration: 130, easing: ReEasing.out(ReEasing.quad) }),
        withSpring(1, { stiffness: 240, damping: 18, mass: 1 }),
      );
    }
    wasFocused.current = isFocused;
  }, [isFocused, scale]);

  const iconStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const tint = isFocused ? activeCol : inactiveCol;

  return (
    <Pressable
      testID={`tab-${routeName}`}
      accessibilityRole="button"
      accessibilityState={isFocused ? { selected: true } : {}}
      onPress={onPress}
      onLayout={onLayout}
      style={styles.item}
    >
      <Animated.View style={iconStyle}>
        <Ionicons name={icon as any} size={22} color={tint} />
      </Animated.View>
      <Text style={[styles.label, { color: tint }]} numberOfLines={1}>{label}</Text>
      {/* Transparent placeholder preserves the exact column height; the visible
          active dot is the single shared sliding indicator (rendered below). */}
      <View style={[styles.dot, { backgroundColor: "transparent" }]} />
    </Pressable>
  );
}

function CustomTabBar({ state, navigation, centerSlot, barRef, measureCenter }: any) {
  const { colors, scheme } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const barBg = scheme === "dark" ? colors.surfaceSecondary : "#0B513C";
  // Light mode: dark-green anchored bar with light icons/labels.
  const activeCol = scheme === "dark" ? colors.brandPrimary : "#FFFFFF";
  const inactiveCol = scheme === "dark" ? colors.muted : "#DCE5DF";

  // --- Shared sliding active indicator ------------------------------------
  // One continuous dot that springs from the previous tab to the new one,
  // instead of five independent dots flashing on/off. Position is measured
  // from the real item layouts so it always lands exactly where the original
  // per-item dot used to sit.
  const indicatorX = useSharedValue(0); // center-x of the active tab
  const indicatorY = useSharedValue(0); // constant y of the dot row
  const indicatorOpacity = useSharedValue(0);
  const centers = useRef<Record<string, number>>({});
  const dotY = useRef(0);
  const didInit = useRef(false);

  const activeName = state.routes[state.index]?.name;

  const moveIndicator = useCallback(
    (animated: boolean) => {
      const cx = centers.current[activeName];
      // No dot for routes without a bottom-bar button (e.g. "more").
      if (cx == null || !TAB_CONFIG[activeName]) {
        indicatorOpacity.value = withTiming(0, { duration: 140 });
        return;
      }
      indicatorY.value = dotY.current;
      if (animated && didInit.current) {
        // Quick, controlled, minimal overshoot — appropriate for a finance app.
        indicatorX.value = withSpring(cx, { stiffness: 200, damping: 24, mass: 1 });
      } else {
        indicatorX.value = cx; // initial placement — no travel
      }
      indicatorOpacity.value = withTiming(1, { duration: 140 });
      didInit.current = true;
    },
    [activeName, indicatorX, indicatorY, indicatorOpacity],
  );

  useEffect(() => {
    moveIndicator(true);
  }, [activeName, moveIndicator]);

  const handleItemLayout = useCallback(
    (name: string, e: any) => {
      const { x, width, y, height } = e.nativeEvent.layout;
      centers.current[name] = x + width / 2;
      dotY.current = y + height - 5; // dot sits at the very bottom of the column
      if (name === activeName) moveIndicator(false);
    },
    [activeName, moveIndicator],
  );

  const indicatorStyle = useAnimatedStyle(() => ({
    opacity: indicatorOpacity.value,
    transform: [
      { translateX: indicatorX.value - 2.5 },
      { translateY: indicatorY.value },
    ],
  }));

  return (
    <View ref={barRef} collapsable={false} onLayout={measureCenter} style={[styles.bar, { backgroundColor: barBg, paddingBottom: Math.max(insets.bottom, 6) }]}>
      {state.routes.map((route: any, index: number) => {
        const isFocused = state.index === index;

        // Keep the original circle's layout without a second visible button.
        // The real Pressable stays in one full-screen parent for elevated taps.
        if (route.name === "fab") {
          return (
            <View key={route.key} style={styles.item}>
              <View ref={centerSlot} collapsable={false} onLayout={measureCenter}
                style={[styles.centerCircle, { opacity: 0 }]} />
            </View>
          );
        }

        const cfg = TAB_CONFIG[route.name];
        // `more` is intentionally NOT in TAB_CONFIG: it stays a registered
        // route but is hidden from the bottom bar (returns null → no button).
        if (!cfg) return null;

        const onPress = () => {
          // Single, strong yet DRY impact (existing haptic — not duplicated).
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Rigid).catch(() => {});
          const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
          if (!isFocused && !event.defaultPrevented) {
            navigation.navigate(route.name);
          }
        };

        return (
          <TabButton
            key={route.key}
            routeName={route.name}
            icon={cfg.icon}
            label={t(cfg.labelKey)}
            isFocused={isFocused}
            activeCol={activeCol}
            inactiveCol={inactiveCol}
            onPress={onPress}
            onLayout={(e: any) => handleItemLayout(route.name, e)}
            styles={styles}
          />
        );
      })}

      {/* Single shared active indicator — slides between tabs on the UI thread. */}
      <Animated.View
        pointerEvents="none"
        style={[styles.dotIndicator, { backgroundColor: activeCol }, indicatorStyle]}
      />
    </View>
  );
}

type CenterGeometry = { x: number; y: number; barTop: number; width: number };
type QuickAction = { icon: string; label: string; color: string; route: string };

// Smooth local curves on a linear master clock follow identical paths in reverse.
function phase(value: number, start: number, end: number) {
  "worklet";
  const t = interpolate(value, [start, end], [0, 1], Extrapolation.CLAMP);
  return t * t * (3 - 2 * t);
}

const RadialAction = React.memo(function RadialAction({
  item, index, progress, geometry, enabled, onSelect,
}: {
  item: QuickAction;
  index: number;
  progress: SharedValue<number>;
  geometry: CenterGeometry | null;
  enabled: boolean;
  onSelect: (route: string) => void;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  const angle = (155 - index * 32.5) * Math.PI / 180;
  const available = geometry ? Math.min(geometry.x, geometry.width - geometry.x) : 0;
  const fanRadius = Math.max(0, Math.min(160, (available - 45) / Math.cos(25 * Math.PI / 180)));
  const dx = Math.cos(angle) * fanRadius;
  const dy = -Math.sin(angle) * fanRadius;
  const actionStyle = useAnimatedStyle(() => {
    const spread = phase(progress.value, 0.52, 1);
    const rise = phase(progress.value, 0, 0.65);
    return {
      opacity: spread,
      transform: [
        { translateX: dx * spread },
        { translateY: -50 * rise + dy * spread },
        { scale: 0.75 + 0.25 * spread },
      ],
    };
  });
  return (
    <Animated.View
      style={[styles.actionAnchor, { left: (geometry?.x ?? 0) - 26, top: (geometry?.y ?? 0) - 26 }, actionStyle]}
      pointerEvents={enabled ? "auto" : "none"}
      accessibilityElementsHidden={!enabled}
      importantForAccessibility={enabled ? "auto" : "no-hide-descendants"}
    >
      <Pressable testID={`quick-${item.label}`} accessibilityRole="button"
        accessibilityLabel={item.label} disabled={!enabled}
        onPress={() => onSelect(item.route)} style={styles.actionTouch}>
        <View style={[styles.actionCircle, { backgroundColor: colors.surface }]}>
          <View style={[styles.actionTint, { backgroundColor: item.color + "22" }]}>
            <Ionicons name={item.icon as any} size={23} color={item.color} />
          </View>
        </View>
        <Text style={styles.actionLabel} numberOfLines={2}>{item.label}</Text>
      </Pressable>
    </Animated.View>
  );
});

function QuickMenu({ geometry }: { geometry: CenterGeometry | null }) {
  const { colors, scheme } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const router = useRouter();
  const progress = useSharedValue(0);
  const [active, setActive] = useState(false);
  const [actionsEnabled, setActionsEnabled] = useState(false);
  const targetOpen = useRef(false);
  const pendingRoute = useRef<string | null>(null);
  const transition = useRef(0);
  const mounted = useRef(true);
  const centerIconCol = scheme === "dark" ? colors.brandPrimary : "#0D5A43";

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const finishTransition = useCallback((id: number, open: boolean) => {
    if (!mounted.current || id !== transition.current) return;
    setActionsEnabled(open);
    if (!open) {
      setActive(false);
      const route = pendingRoute.current;
      pendingRoute.current = null;
      if (route) router.push(route as any);
    }
  }, [router]);

  const animateTo = useCallback((open: boolean) => {
    targetOpen.current = open;
    const id = ++transition.current;
    setActionsEnabled(false);
    if (open) setActive(true);
    // Retarget the current value. Remaining distance controls duration, so
    // interruptions never reset position or linger at a nearly closed endpoint.
    const remaining = Math.abs((open ? 1 : 0) - progress.get());
    progress.set(withTiming(open ? 1 : 0, {
      duration: Math.max(1, 420 * remaining), easing: ReEasing.linear,
    }, (finished) => {
      if (finished) runOnJS(finishTransition)(id, open);
    }));
  }, [progress, finishTransition]);

  const close = useCallback(() => {
    if (targetOpen.current) animateTo(false);
  }, [animateTo]);

  const toggle = useCallback(() => {
    if (!geometry || pendingRoute.current) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Soft).catch(() => {});
    animateTo(!targetOpen.current);
  }, [animateTo, geometry]);

  const select = useCallback((route: string) => {
    if (!targetOpen.current || pendingRoute.current || !actionsEnabled) return;
    pendingRoute.current = route;
    animateTo(false);
  }, [animateTo, actionsEnabled]);

  useEffect(() => {
    if (!active) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      close();
      return true;
    });
    return () => sub.remove();
  }, [active, close]);

  const backdropStyle = useAnimatedStyle(() => ({ opacity: 0.368 * phase(progress.value, 0, 1) }));
  const centerStyle = useAnimatedStyle(() => ({ transform: [{ translateY: -50 * phase(progress.value, 0, 0.65) }] }));
  const walletStyle = useAnimatedStyle(() => ({ opacity: 1 - phase(progress.value, 0.1, 0.6) }));
  const closeStyle = useAnimatedStyle(() => ({
    opacity: phase(progress.value, 0.1, 0.6),
    transform: [{ rotate: `${45 * phase(progress.value, 0.1, 0.6)}deg` }],
  }));

  const items: QuickAction[] = [
    { icon: "trending-down-outline", label: t("quickAdd.expense"), color: colors.expenseRed, route: "/transactions/new?type=expense" },
    { icon: "trending-up-outline", label: t("quickAdd.income"), color: colors.incomeGreen, route: "/transactions/new?type=income" },
    { icon: "swap-horizontal-outline", label: t("quickAdd.transfer"), color: colors.accountsBlue, route: "/transactions/new?type=transfer" },
    { icon: "card-outline", label: t("quickAdd.createDebt"), color: colors.statsPurple, route: "/debts/new?direction=i_owe" },
    { icon: "hand-left-outline", label: t("quickAdd.registerLoan"), color: colors.loansYellow, route: "/debts/new?direction=they_owe" },
  ];

  return (
    <View style={styles.overlay} pointerEvents="box-none">
      <Animated.View style={[styles.backdrop, { height: geometry?.barTop ?? 0 }, backdropStyle]}
        pointerEvents={active ? "auto" : "none"} accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants">
        <Pressable style={styles.backdropPress} onPress={close} />
      </Animated.View>
      {items.map((item, index) => (
        <RadialAction key={item.route} item={item} index={index} progress={progress}
          geometry={geometry} enabled={actionsEnabled} onSelect={select} />
      ))}
      {/* One real center Pressable, always in the same parent and above the fan.
          Its closed coordinates come from the original bottom-bar slot. */}
      <Animated.View pointerEvents={geometry ? "box-none" : "none"}
        style={[styles.centerAnchor, {
          left: (geometry?.x ?? 0) - 26, top: (geometry?.y ?? 0) - 26,
          opacity: geometry ? 1 : 0,
        }, centerStyle]}>
        <Pressable testID="fab-add-btn" accessibilityRole="button"
          accessibilityLabel={active ? t("common.close") : t("common.add")}
          accessibilityState={{ expanded: active }}
          hitSlop={5} onPress={toggle} style={styles.centerBtn}>
          <View style={[styles.centerCircle, { marginTop: 0 }]}>
            <Animated.View pointerEvents="none" style={[styles.centerVisual, walletStyle]}>
              <Ionicons name="wallet" size={22} color={centerIconCol} />
              <View style={styles.plusBadge}>
                <Ionicons name="add" size={11} color="#FFFFFF" />
              </View>
            </Animated.View>
            <Animated.View pointerEvents="none" style={[styles.centerVisual, closeStyle]}>
              <Ionicons name="add" size={26} color={centerIconCol} />
            </Animated.View>
          </View>
        </Pressable>
      </Animated.View>
    </View>
  );
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const rootRef = useRef<View>(null);
  const centerSlot = useRef<View>(null);
  const barRef = useRef<View>(null);
  const [geometry, setGeometry] = useState<CenterGeometry | null>(null);

  const measureCenter = useCallback(() => {
    // All measurements share native window coordinates; no assumed bar height.
    rootRef.current?.measureInWindow((rootX, rootY, width) => {
      if (width <= 0) return;
      barRef.current?.measureInWindow((_x, barY) => {
        centerSlot.current?.measureInWindow((x, y, slotWidth, slotHeight) => {
          if (slotWidth <= 0 || slotHeight <= 0) return;
          const next = { x: x - rootX + slotWidth / 2, y: y - rootY + slotHeight / 2, barTop: barY - rootY, width };
          setGeometry((previous) => previous && previous.x === next.x && previous.y === next.y
            && previous.barTop === next.barTop && previous.width === width ? previous : next);
        });
      });
    });
  }, []);

  const renderTabBar = useCallback((props: React.ComponentProps<typeof CustomTabBar>) => (
    <CustomTabBar {...props} centerSlot={centerSlot} barRef={barRef} measureCenter={measureCenter} />
  ), [measureCenter]);

  return (
    <View ref={rootRef} collapsable={false} onLayout={measureCenter} style={{ flex: 1, backgroundColor: colors.surface }}>
      <Tabs tabBar={renderTabBar} screenOptions={{ headerShown: false }}>
        <Tabs.Screen name="index" options={{ title: "Cuentas" }} />
        <Tabs.Screen name="transactions" options={{ title: "IA" }} />
        <Tabs.Screen name="fab" options={{ title: "" }} />
        <Tabs.Screen name="reports" options={{ title: "Informes" }} />
        <Tabs.Screen name="notes" options={{ title: "Notas", lazy: false }} />
        <Tabs.Screen name="more" options={{ title: "Más" }} />
      </Tabs>
      <QuickMenu geometry={geometry} />
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  // --- Bottom navigation bar ---
  bar: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingTop: 8,
    paddingHorizontal: 6,
    borderTopLeftRadius: 26,
    borderTopRightRadius: 26,
    // Extremely soft top shadow to lift the bar off the content.
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: -2 },
    elevation: 6,
  },
  item: { flex: 1, alignItems: "center", justifyContent: "flex-start" },
  label: { fontSize: 11, fontWeight: "600", marginTop: 3 },
  dot: { width: 5, height: 5, borderRadius: 2.5, marginTop: 3 },
  // Single shared active indicator — identical 5×5 dot, absolutely positioned
  // so it can slide between tabs without affecting the row layout.
  dotIndicator: { position: "absolute", top: 0, left: 0, width: 5, height: 5, borderRadius: 2.5 },
  // Center wallet+ button — integrated, slightly emphasized, not a big FAB.
  centerBtn: { width: 52, height: 52, alignItems: "center", justifyContent: "center" },
  centerCircle: {
    width: 42,
    height: 42,
    borderRadius: 21,
    marginTop: -2,
    backgroundColor: scheme === "dark" ? colors.brandPrimary + "1F" : "#F6F8F2",
    borderWidth: scheme === "dark" ? 0 : 2,
    borderColor: "#77B76D",
    alignItems: "center",
    justifyContent: "center",
  },
  plusBadge: {
    position: "absolute",
    right: 4,
    bottom: 4,
    width: 15,
    height: 15,
    borderRadius: 7.5,
    backgroundColor: scheme === "dark" ? colors.brandPrimary : "#0D5A43",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1.5,
    borderColor: scheme === "dark" ? colors.surfaceSecondary : "#0B513C",
  },
  // A stable full-screen parent permits elevated Android hit testing.
  overlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, zIndex: 10, elevation: 10 },
  backdrop: { position: "absolute", top: 0, left: 0, right: 0, backgroundColor: "#000" },
  backdropPress: { flex: 1 },
  centerAnchor: { position: "absolute", width: 52, height: 52, zIndex: 2 },
  centerVisual: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, alignItems: "center", justifyContent: "center" },
  actionAnchor: { position: "absolute", width: 52, height: 52, zIndex: 1 },
  actionTouch: { width: 52, height: 52, alignItems: "center" },
  actionCircle: {
    width: 52, height: 52, borderRadius: 26,
    shadowColor: "#000", shadowOpacity: 0.08, shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 }, elevation: 2,
  },
  actionTint: { flex: 1, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  actionLabel: {
    position: "absolute", top: 58, width: 80, textAlign: "center",
    fontSize: 12, lineHeight: 14, fontWeight: "600", color: "#FFFFFF",
    textShadowColor: "rgba(0,0,0,0.55)",
    textShadowOffset: { width: 0, height: 1.5 },
    textShadowRadius: 2.5,
  },
}));
