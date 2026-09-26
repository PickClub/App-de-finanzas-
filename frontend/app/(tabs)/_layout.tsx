import React, { useState, useEffect, useRef, useCallback } from "react";
import { Tabs, useRouter } from "expo-router";
import { Pressable, View, Text, Modal, TouchableOpacity, Easing } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withSequence,
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

function CustomTabBar({ state, navigation, openMenu }: any) {
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
                  openMenu();
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

function QuickMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const router = useRouter();
  const items = [
    { icon: "trending-down-outline", label: t("quickAdd.expense"), color: colors.expenseRed, route: "/transactions/new?type=expense" },
    { icon: "trending-up-outline", label: t("quickAdd.income"), color: colors.incomeGreen, route: "/transactions/new?type=income" },
    { icon: "swap-horizontal-outline", label: t("quickAdd.transfer"), color: colors.accountsBlue, route: "/transactions/new?type=transfer" },
    { icon: "card-outline", label: t("quickAdd.createDebt"), color: colors.statsPurple, route: "/debts/new?direction=i_owe" },
    { icon: "hand-left-outline", label: t("quickAdd.registerLoan"), color: colors.loansYellow, route: "/debts/new?direction=they_owe" },
    { icon: "cash-outline", label: t("quickAdd.debtPayment"), color: colors.brandPrimary, route: "/debts" },
  ];
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>{t("quickAdd.title")}</Text>
          <View style={styles.grid}>
            {items.map((it) => (
              <TouchableOpacity
                key={it.label}
                testID={`quick-${it.label}`}
                style={styles.gridItem}
                onPress={() => {
                  onClose();
                  setTimeout(() => router.push(it.route as any), 100);
                }}
              >
                <View style={[styles.gridIcon, { backgroundColor: it.color + "22" }]}>
                  <Ionicons name={it.icon as any} size={26} color={it.color} />
                </View>
                <Text style={styles.gridLabel}>{it.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Tabs
        tabBar={(props) => <CustomTabBar {...props} openMenu={() => setMenuOpen(true)} />}
        screenOptions={{
          headerShown: false,
          // Bottom-tab switching stays near-instant: only a very subtle
          // cross-fade (~140ms). No horizontal screen slide between tabs.
          animation: "fade",
          transitionSpec: {
            animation: "timing",
            config: { duration: 140, easing: Easing.out(Easing.ease) },
          },
        }}
      >
        <Tabs.Screen name="index" options={{ title: "Cuentas" }} />
        <Tabs.Screen name="transactions" options={{ title: "IA" }} />
        <Tabs.Screen name="fab" options={{ title: "" }} />
        <Tabs.Screen name="reports" options={{ title: "Informes" }} />
        <Tabs.Screen name="notes" options={{ title: "Notas" }} />
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
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.cardLg,
    borderTopRightRadius: radius.cardLg,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 32,
  },
  sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  sheetTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginBottom: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  gridItem: { width: "31%", alignItems: "center", marginBottom: 20 },
  gridIcon: { width: 60, height: 60, borderRadius: 20, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  gridLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
}));
