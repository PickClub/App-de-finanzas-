import React, { useState, useEffect, useRef, useCallback } from "react";
import { Tabs, useRouter } from "expo-router";
import { Pressable, View, Text, BackHandler } from "react-native";
import Animated, {
  useSharedValue,
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
import { useTheme, makeStyles, radius } from "@/src/theme";
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

function CustomTabBar({ state, navigation, toggleMenu }: any) {
  const { colors, scheme } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const barBg = scheme === "dark" ? colors.surfaceSecondary : "#0B513C";
  // Light mode: dark-green anchored bar with light icons/labels.
  const activeCol = scheme === "dark" ? colors.brandPrimary : "#FFFFFF";
  const inactiveCol = scheme === "dark" ? colors.muted : "#DCE5DF";
  const centerIconCol = scheme === "dark" ? colors.brandPrimary : "#0D5A43";

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
    <View style={[styles.bar, { backgroundColor: barBg, paddingBottom: Math.max(insets.bottom, 6) }]}>
      {state.routes.map((route: any, index: number) => {
        const isFocused = state.index === index;

        // Center action — visually a compact "wallet+"; runs the SAME action
        // the old floating + button did (opens the quick-add menu).
        if (route.name === "fab") {
          return (
            <View key={route.key} style={styles.item}>
              <Pressable
                testID="fab-add-btn"
                accessibilityRole="button"
                onPress={() => {
                  // Same single Rigid (dry, sharp) impact as the other tabs.
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Rigid).catch(() => {});
                  toggleMenu();
                }}
                style={({ pressed }) => [styles.centerBtn, pressed && { transform: [{ scale: 0.94 }] }]}
              >
                <View style={styles.centerCircle}>
                  <Ionicons name="wallet" size={22} color={centerIconCol} />
                  <View style={styles.plusBadge}>
                    <Ionicons name="add" size={11} color="#FFFFFF" />
                  </View>
                </View>
              </Pressable>
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

// A single option row inside the floating list. Its subtle entrance is derived
// from the shared `panel` value on the UI thread (micro-stagger), so the whole
// list still reads as ONE object rising from the bottom. Memoized + static
// content → no re-render churn while the menu animates.
const MenuRow = React.memo(function MenuRow({
  item,
  index,
  panel,
  onSelect,
  isLast,
  muted,
  styles,
}: {
  item: { icon: string; label: string; color: string; route: string };
  index: number;
  panel: Animated.SharedValue<number>;
  onSelect: (route: string) => void;
  isLast: boolean;
  muted: string;
  styles: any;
}) {
  const rowStyle = useAnimatedStyle(() => {
    // Tiny per-item trail (~50ms-equivalent at these durations) that reverses
    // automatically on close. Runs entirely on the UI thread.
    const start = index * 0.05;
    const local = interpolate(panel.value, [start, start + 0.55], [0, 1], Extrapolation.CLAMP);
    return {
      opacity: local,
      transform: [{ translateY: (1 - local) * 10 }, { scale: 0.985 + local * 0.015 }],
    };
  });

  return (
    <Animated.View style={rowStyle}>
      <Pressable
        testID={`quick-${item.label}`}
        accessibilityRole="button"
        onPress={() => onSelect(item.route)}
        style={({ pressed }) => [styles.row, !isLast && styles.rowDivider, pressed && styles.rowPressed]}
      >
        <View style={[styles.rowIcon, { backgroundColor: item.color + "22" }]}>
          <Ionicons name={item.icon as any} size={22} color={item.color} />
        </View>
        <Text style={styles.rowLabel} numberOfLines={1}>{item.label}</Text>
        <Ionicons name="chevron-forward" size={18} color={muted} />
      </Pressable>
    </Animated.View>
  );
});

// Premium floating quick-add list. Opens by rapidly sliding upward from below
// the bottom navigation and settling just above it; closes by sinking back
// down. All motion is transform/opacity on the UI thread (time-based, no JS
// frame loop, no overshoot). Same actions/labels/icons/routes as before.
function QuickMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  // Approximate height of the existing bottom bar (content + safe-area). Derived
  // synchronously from insets, so there is no async reposition/jump.
  const navH = Math.max(insets.bottom, 6) + 60;

  const items = [
    { icon: "trending-down-outline", label: t("quickAdd.expense"), color: colors.expenseRed, route: "/transactions/new?type=expense" },
    { icon: "trending-up-outline", label: t("quickAdd.income"), color: colors.incomeGreen, route: "/transactions/new?type=income" },
    { icon: "swap-horizontal-outline", label: t("quickAdd.transfer"), color: colors.accountsBlue, route: "/transactions/new?type=transfer" },
    { icon: "card-outline", label: t("quickAdd.createDebt"), color: colors.statsPurple, route: "/debts/new?direction=i_owe" },
    { icon: "hand-left-outline", label: t("quickAdd.registerLoan"), color: colors.loansYellow, route: "/debts/new?direction=they_owe" },
    { icon: "cash-outline", label: t("quickAdd.debtPayment"), color: colors.brandPrimary, route: "/debts" },
  ];

  // Master timeline: 0 = fully hidden below the bar, 1 = open & settled.
  const panel = useSharedValue(0);
  // Exact off-screen travel distance; refined once the panel is measured so the
  // list appears to emerge from just beneath the navigation bar.
  const fromY = useSharedValue(800);

  useEffect(() => {
    if (visible) {
      // Fast, decelerating rise (accelerate away immediately → smooth settle,
      // no bounce/overshoot). Time-based so it honours the native refresh rate.
      panel.value = withTiming(1, { duration: 220, easing: ReEasing.out(ReEasing.cubic) });
    } else {
      // Slightly quicker, accelerating sink back into the bottom of the screen.
      panel.value = withTiming(0, { duration: 170, easing: ReEasing.in(ReEasing.cubic) });
    }
  }, [visible, panel]);

  // Android hardware back closes the menu instead of leaving the screen.
  useEffect(() => {
    if (!visible) return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      onClose();
      return true;
    });
    return () => sub.remove();
  }, [visible, onClose]);

  const onPanelLayout = useCallback(
    (e: any) => {
      const h = e.nativeEvent.layout.height;
      if (h > 0) fromY.value = h + navH + 24; // guarantee fully off-screen when closed
    },
    [navH, fromY],
  );

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: interpolate(panel.value, [0, 1], [0, 0.38], Extrapolation.CLAMP),
  }));

  const panelStyle = useAnimatedStyle(() => ({
    opacity: interpolate(panel.value, [0, 0.4], [0, 1], Extrapolation.CLAMP),
    transform: [
      { translateY: (1 - panel.value) * fromY.value },
      { scale: 0.985 + panel.value * 0.015 },
    ],
  }));

  const handleSelect = useCallback(
    (route: string) => {
      onClose();
      // Preserve the original navigation timing/behaviour exactly.
      setTimeout(() => router.push(route as any), 100);
    },
    [onClose, router],
  );

  return (
    // box-none root: when closed, children are pointerEvents:none → the app is
    // fully interactive and the menu leaves ZERO visual/touch footprint.
    <View style={styles.overlay} pointerEvents="box-none">
      <Animated.View
        style={[styles.backdrop, { bottom: navH }, backdropStyle]}
        pointerEvents={visible ? "auto" : "none"}
      >
        <Pressable style={styles.backdropPress} onPress={onClose} />
      </Animated.View>

      <Animated.View
        style={[styles.panel, { bottom: navH + 8 }, panelStyle]}
        pointerEvents={visible ? "auto" : "none"}
        onLayout={onPanelLayout}
      >
        <View style={styles.handle} />
        {items.map((it, i) => (
          <MenuRow
            key={it.label}
            item={it}
            index={i}
            panel={panel}
            onSelect={handleSelect}
            isLast={i === items.length - 1}
            muted={colors.muted}
            styles={styles}
          />
        ))}
      </Animated.View>
    </View>
  );
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Tabs
        tabBar={(props) => (
          <CustomTabBar {...props} menuOpen={menuOpen} toggleMenu={() => setMenuOpen((o) => !o)} />
        )}
        screenOptions={{
          headerShown: false,
        }}
      >
        <Tabs.Screen name="index" options={{ title: "Cuentas" }} />
        <Tabs.Screen name="transactions" options={{ title: "IA" }} />
        <Tabs.Screen name="fab" options={{ title: "" }} />
        <Tabs.Screen name="reports" options={{ title: "Informes" }} />
        <Tabs.Screen name="notes" options={{ title: "Notas", lazy: false }} />
        <Tabs.Screen name="more" options={{ title: "Más" }} />
      </Tabs>
      <QuickMenu visible={menuOpen} onClose={() => setMenuOpen(false)} />
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
  centerBtn: { alignItems: "center", justifyContent: "center" },
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
  // --- Floating quick-add list (only visible while the menu is open) ---
  overlay: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  backdrop: { position: "absolute", top: 0, left: 0, right: 0, backgroundColor: "#000" },
  backdropPress: { flex: 1 },
  panel: {
    position: "absolute",
    left: 12,
    right: 12,
    backgroundColor: colors.surface,
    borderRadius: radius.cardLg,
    paddingHorizontal: 6,
    paddingBottom: 6,
    borderWidth: 1,
    borderColor: colors.border,
    // Soft lift off the content; static (never animated per frame).
    shadowColor: "#000",
    shadowOpacity: 0.14,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 14,
  },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginTop: 8, marginBottom: 4 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, paddingHorizontal: 10, borderRadius: 16 },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowPressed: { backgroundColor: colors.surfaceTertiary },
  rowIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", marginRight: 14 },
  rowLabel: { flex: 1, fontSize: 16, fontWeight: "700", color: colors.onSurface },
}));
