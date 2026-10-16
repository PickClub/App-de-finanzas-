import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import React from "react";
import { View } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useTheme, makeStyles } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { useFonts } from "expo-font";

import { us } from "@/src/ui-scale";
type Tile = {
  icon: string;
  label: string;
  subtitle: string;
  color: string;
  route?: string;
};

// Screen-local pastel surfaces; global theme and navigation stay unchanged.
type MoneyTile = Tile & { tile: string };
const FOREST = "#126046";
const PALETTE = {
  mint: { color: FOREST, tile: "#CDEFDF" },
  orange: { color: "#EE8A2E", tile: "#FFE2C6" },
  coral: { color: "#DB4F4C", tile: "#FFD5D2" },
  green: { color: "#1C9A68", tile: "#CFEEDD" },
  gold: { color: "#D39A2F", tile: "#FFE6B5" },
  violet: { color: "#8457E8", tile: "#E5D9FF" },
  blue: { color: "#2C78E4", tile: "#D4E4FF" },
};

export default function More() {
  const { colors, scheme } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const go = (route?: string) => {
    if (route) router.push(route as any);
  };
  // Reuse the existing local Montserrat assets without changing global typography.
  const [montserratLoaded] = useFonts({
    "Montserrat-Bold": require("../../assets/fonts/Montserrat-Bold.ttf"),
  });
  const boldTitle = montserratLoaded
    ? { fontFamily: "Montserrat-Bold", fontWeight: undefined }
    : { fontWeight: "700" as const };
  const isDark = scheme === "dark";
  const MONEY: MoneyTile[] = [
    { icon: "wallet", label: t("more.accounts"), subtitle: t("more.subAccounts"), ...PALETTE.mint, route: "/accounts" },
    { icon: "pricetag-outline", label: t("more.categories"), subtitle: t("more.subCategories"), ...PALETTE.orange, route: "/categories" },
    { icon: "pie-chart", label: t("more.budgets"), subtitle: t("more.subBudgets"), ...PALETTE.coral, route: "/budgets" },
    { icon: "radio-button-on", label: t("more.savingsGoals"), subtitle: t("more.subGoals"), ...PALETTE.green, route: "/goals" },
    { icon: "server", label: t("more.debtsAndLoans"), subtitle: t("more.subDebts"), ...PALETTE.gold, route: "/debts" },
    { icon: "sync", label: t("more.recurringPayments"), subtitle: t("more.subRecurring"), ...PALETTE.violet, route: "/recurring" },
    { icon: "document-text", label: t("more.invoices"), subtitle: t("more.subInvoices"), ...PALETTE.blue, route: "/bills" },
    { icon: "calendar", label: t("more.financialCalendar"), subtitle: t("more.subCalendar"), ...PALETTE.mint, route: "/calendar" },
    { icon: "document-text", label: t("tabs.notes"), subtitle: t("more.subNotes"), ...PALETTE.mint, route: "/(tabs)/notes" },
  ];

  const groups = [
    { id: "money", title: t("more.moneyManagement"), icon: "wallet", palette: PALETTE.mint, background: "#DFF3EB", items: MONEY.slice(0, 4) },
    { id: "obligations", title: t("more.paymentsObligations"), icon: "server", palette: PALETTE.gold, background: "#FFF4D9", items: MONEY.slice(4, 7) },
    { id: "planning", title: t("more.planning"), icon: "calendar", palette: PALETTE.mint, background: "#DFF3EB", items: MONEY.slice(7) },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.pageBackground }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL}
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + us(14), paddingBottom: insets.bottom + us(132) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1, paddingRight: us(12) }}>
            <Text style={[styles.title, boldTitle]}>{t("more.title")}</Text>
          </View>
          <Pressable
            testID="more-settings-btn"
            accessibilityLabel={t("more.settings")}
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.gearBtn, pressed && styles.pressed]}
          >
            <Ionicons name="settings" size={us(20)} color={isDark ? colors.onSurface : FOREST} />
          </Pressable>
        </View>

        {groups.map((group) => (
          <View key={group.id} testID={`tools-section-${group.id}`} style={[styles.group, { backgroundColor: isDark ? colors.surfaceSecondary : group.background }]}>
            <View style={styles.groupHeader}>
              <View style={[styles.groupIcon, { backgroundColor: group.palette.tile }]}>
                <Ionicons name={group.icon as any} size={us(24)} color={group.palette.color} />
              </View>
              <Text style={[styles.sectionTitle, boldTitle]}>{group.title}</Text>
            </View>
            <View style={styles.groupBody}>
              {group.items.map((it, index) => (
                <Pressable key={it.route} testID={`more-${it.label}`} accessibilityLabel={it.label} onPress={() => go(it.route)} style={({ pressed }) => [styles.toolRow, pressed && styles.pressed]}>
                  <View style={[styles.toolIcon, { backgroundColor: it.tile }]}>
                    <Ionicons name={it.icon as any} size={us(29)} color={isDark && it.color === FOREST ? colors.incomeGreen : it.color} />
                  </View>
                  <View style={styles.toolCopy}>
                    <Text style={[styles.toolTitle, boldTitle]}>{it.label}</Text>
                    <Text style={styles.toolDescription}>{it.subtitle}</Text>
                  </View>
                  {index < group.items.length - 1 && <View pointerEvents="none" style={styles.separator} />}
                </Pressable>
              ))}
            </View>
          </View>
        ))}
      </ElasticScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  container: { paddingHorizontal: 20 },
  pressed: { opacity: 0.65 },
  header: { flexDirection: "row", alignItems: "center", marginBottom: 14 },
  title: { fontSize: 30, fontWeight: "700", color: colors.onSurface },
  gearBtn: {
    width: 48, height: 48, borderRadius: 24, marginLeft: 10,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  group: {
    borderRadius: 24, marginBottom: 16, borderWidth: 1,
    borderColor: scheme === "dark" ? colors.border : "#F5FBF7",
    shadowColor: "#153D2C", shadowOpacity: scheme === "dark" ? 0 : 0.035,
    shadowRadius: 3, shadowOffset: { width: 0, height: 1 }, elevation: 1,
  },
  groupHeader: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 7, gap: 14 },
  groupIcon: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  sectionTitle: { flex: 1, minWidth: 0, fontSize: 18, fontWeight: "700", color: colors.onSurface },
  groupBody: { borderRadius: 23, backgroundColor: scheme === "dark" ? colors.surface : "#FFFFFF", overflow: "hidden" },
  toolRow: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 9, minHeight: 69 },
  toolIcon: { width: 50, height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  toolCopy: { flex: 1, minWidth: 0, marginLeft: 20 },
  toolTitle: { fontSize: 16, fontWeight: "700", color: scheme === "dark" ? colors.onSurface : "#101B17", marginBottom: 3 },
  toolDescription: { fontSize: 13, lineHeight: 18, fontWeight: "400", color: colors.muted },
  separator: { position: "absolute", left: 86, right: 16, bottom: 0, height: 1, backgroundColor: scheme === "dark" ? colors.border : "#E9EBE9" },
}));
