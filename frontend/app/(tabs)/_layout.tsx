import React, { useState } from "react";
import { Tabs, useRouter } from "expo-router";
import { Pressable, View, Text, Modal, TouchableOpacity, Easing } from "react-native";
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
  more: { labelKey: "tabs.more", icon: "grid" },
};

// Custom bottom navigation bar. Keeps every existing route/action; only the
// visual presentation is redefined (rounded top, cream surface, compact
// height, integrated wallet+ center button, discreet coral selection dot).
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
                  // Same ultra-light selection "tick" as the other tabs.
                  Haptics.selectionAsync().catch(() => {});
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
        if (!cfg) return <View key={route.key} style={styles.item} />;
        const tint = isFocused ? activeCol : inactiveCol;

        const onPress = () => {
          // Ultra-light selection "tick" (softest supported haptic). Web/unsupported
          // platforms reject silently via catch — navigation is unaffected.
          Haptics.selectionAsync().catch(() => {});
          const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
          if (!isFocused && !event.defaultPrevented) {
            navigation.navigate(route.name);
          }
        };

        return (
          <Pressable
            key={route.key}
            testID={`tab-${route.name}`}
            accessibilityRole="button"
            accessibilityState={isFocused ? { selected: true } : {}}
            onPress={onPress}
            style={styles.item}
          >
            <Ionicons name={cfg.icon as any} size={22} color={tint} />
            <Text style={[styles.label, { color: tint }]} numberOfLines={1}>{t(cfg.labelKey)}</Text>
            <View style={[styles.dot, { backgroundColor: isFocused ? activeCol : "transparent" }]} />
          </Pressable>
        );
      })}
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
