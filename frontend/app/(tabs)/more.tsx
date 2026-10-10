import React from "react";
import { View, ScrollView } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useTheme, makeStyles, radius } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { LinearGradient } from "expo-linear-gradient";
import { useFonts } from "expo-font";

import { us } from "@/src/ui-scale";
type Tile = {
  icon: string;
  label: string;
  subtitle: string;
  color: string;
  route?: string;
};

// "Tu dinero" card palette (screen-scoped, does NOT touch the global theme).
// accent = icon colour, tile = icon square bg, from = strong pastel (top-right),
// to = light pastel (bottom-left).
type MoneyTile = Tile & { tile: string; from: string; to: string };
const FOREST = "#126046";
const PALETTE = {
  mint: { color: FOREST, tile: "#CDEFDF", from: "#BDEAD4", to: "#F2FBF6" },
  orange: { color: "#EE8A2E", tile: "#FFE2C6", from: "#FFD2AA", to: "#FFF7EF" },
  coral: { color: "#DB4F4C", tile: "#FFD5D2", from: "#FFC7C3", to: "#FFF4F3" },
  green: { color: "#1C9A68", tile: "#CFEEDD", from: "#C2ECD6", to: "#F2FBF6" },
  gold: { color: "#D39A2F", tile: "#FFE6B5", from: "#FFE0A3", to: "#FFFAEE" },
  violet: { color: "#8457E8", tile: "#E5D9FF", from: "#DACBFF", to: "#F8F4FF" },
  blue: { color: "#2C78E4", tile: "#D4E4FF", from: "#C4DAFF", to: "#F3F7FF" },
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
  // Montserrat is loaded ONLY for the "Tu dinero" card titles (global font untouched).
  const [montserratLoaded] = useFonts({
    "Montserrat-Bold": require("../../assets/fonts/Montserrat-Bold.ttf"),
    "Montserrat-ExtraBold": require("../../assets/fonts/Montserrat-ExtraBold.ttf"),
  });
  const isDark = scheme === "dark";
  // Light: pastel diagonal gradient. Dark: same hue as translucent tint over the surface.
  const grad = (m: MoneyTile): [string, string] =>
    isDark ? [m.color + "38", m.color + "10"] : [m.from, m.to];

  // Navigation of the first six cards is preserved exactly (recurring had no route).
  // Facturas / Calendario financiero have no screens yet -> no route (visual only).
  const MONEY: MoneyTile[] = [
    { icon: "wallet", label: t("more.accounts"), subtitle: t("more.subAccounts"), ...PALETTE.mint, route: "/accounts" },
    { icon: "pricetag-outline", label: t("more.categories"), subtitle: t("more.subCategories"), ...PALETTE.orange, route: "/categories" },
    { icon: "pie-chart", label: t("more.budgets"), subtitle: t("more.subBudgets"), ...PALETTE.coral, route: "/budgets" },
    { icon: "radio-button-on", label: t("more.savingsGoals"), subtitle: t("more.subGoals"), ...PALETTE.green, route: "/goals" },
    { icon: "server", label: t("more.debtsAndLoans"), subtitle: t("more.subDebts"), ...PALETTE.gold, route: "/debts" },
    { icon: "sync", label: t("more.recurringPayments"), subtitle: t("more.subRecurring"), ...PALETTE.violet },
    { icon: "document-text", label: t("more.invoices"), subtitle: t("more.subInvoices"), ...PALETTE.blue },
    { icon: "calendar", label: t("more.financialCalendar"), subtitle: t("more.subCalendar"), ...PALETTE.mint },
  ];

  const APP: Tile[] = [
    { icon: "settings-outline", label: t("more.settings"), subtitle: t("more.subSettings"), color: colors.muted, route: "/settings" },
    { icon: "shield-checkmark-outline", label: t("more.privacySecurity"), subtitle: t("more.subPrivacy"), color: colors.accountsBlue },
    { icon: "help-circle-outline", label: t("more.helpCenter"), subtitle: t("more.subHelp"), color: colors.success },
    { icon: "star-outline", label: t("more.rateApp"), subtitle: t("more.subRate"), color: colors.warning },
    { icon: "information-circle-outline", label: t("more.about"), subtitle: t("more.subAbout"), color: colors.info },
  ];

  const rows: MoneyTile[][] = [
    [MONEY[0], MONEY[1]],
    [MONEY[2], MONEY[3]],
    [MONEY[4], MONEY[5]],
    [MONEY[6], MONEY[7]],
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
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
            <Text style={styles.title}>{t("more.title")}</Text>
          </View>
          <Pressable
            testID="more-profile"
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.profilePill, pressed && styles.pressed]}
          >
            <View style={styles.avatar}>
              <Ionicons name="person" size={us(16)} color={colors.brandPrimary} />
            </View>
            <View style={{ marginHorizontal: us(8) }}>
              <Text style={styles.profileHi}>{t("more.greeting")}</Text>
              <Text style={styles.profileName}>{t("more.defaultUser")}</Text>
            </View>
            <Ionicons name="chevron-forward" size={us(16)} color={colors.muted} />
          </Pressable>
          <Pressable
            testID="more-settings-btn"
            accessibilityLabel={t("more.settings")}
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.gearBtn, pressed && styles.pressed]}
          >
            <Ionicons name="settings" size={us(20)} color={isDark ? colors.onSurface : FOREST} />
          </Pressable>
        </View>

        {/* Tu dinero */}
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>{t("more.yourMoney")}</Text>
          <Text style={styles.sectionHint}>{t("more.moneyHint")}</Text>
        </View>
        <View style={styles.grid}>
          {rows.map((pair, ri) => (
            <View key={ri} style={styles.gridRow}>
              {pair.map((it) => (
                <Pressable
                  key={it.label}
                  testID={`more-${it.label}`}
                  onPress={() => go(it.route)}
                  style={({ pressed }) => [
                    styles.tile,
                    { borderColor: isDark ? it.color + "33" : it.from + "AA" },
                    pressed && styles.pressed,
                  ]}
                >
                  {/* Diagonal: strongest at top-right, fading to bottom-left */}
                  <LinearGradient
                    colors={grad(it)}
                    start={{ x: 1, y: 0 }}
                    end={{ x: 0, y: 1 }}
                    style={styles.tileGradient}
                    pointerEvents="none"
                  />
                  <View style={styles.tileTop}>
                    <View style={[styles.tileIcon, { backgroundColor: isDark ? it.color + "2E" : it.tile }]}>
                      <Ionicons name={it.icon as any} size={us(24)} color={isDark && it.color === FOREST ? colors.incomeGreen : it.color} />
                    </View>
                    <View style={styles.tileArrow}>
                      <Ionicons name="chevron-forward" size={us(15)} color={isDark ? colors.onSurface : "#1C2B24"} />
                    </View>
                  </View>
                  <Text
                    style={[styles.tileLabel, montserratLoaded && { fontFamily: "Montserrat-Bold", fontWeight: undefined }]}
                    numberOfLines={1}
                    adjustsFontSizeToFit
                    minimumFontScale={0.8}
                  >
                    {it.label}
                  </Text>
                  <Text style={styles.tileSub} numberOfLines={2}>{it.subtitle}</Text>
                </Pressable>
              ))}
            </View>
          ))}
        </View>

        {/* Aplicación */}
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>{t("more.application")}</Text>
          <Text style={styles.sectionHint}>{t("more.appHint")}</Text>
        </View>
        <View style={styles.appCard}>
          {APP.map((it, i) => (
            <Pressable
              key={it.label}
              testID={`more-${it.label}`}
              onPress={() => go(it.route)}
              style={({ pressed }) => [styles.appRow, i < APP.length - 1 && styles.appRowBorder, pressed && styles.pressed]}
            >
              <View style={[styles.appIcon, { backgroundColor: it.color + "24" }]}>
                <Ionicons name={it.icon as any} size={us(19)} color={it.color} />
              </View>
              <View style={{ flex: 1, marginLeft: us(14) }}>
                <Text style={styles.appLabel}>{it.label}</Text>
                <Text style={styles.appSub}>{it.subtitle}</Text>
              </View>
              <Ionicons name="chevron-forward" size={us(19)} color={colors.muted} />
            </Pressable>
          ))}
        </View>

        {/* Suggestion */}
        <Pressable testID="more-suggestion" style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}>
          <View style={styles.suggIcon}>
            <Ionicons name="bulb-outline" size={us(22)} color={colors.success} />
          </View>
          <View style={{ flex: 1, marginHorizontal: us(14) }}>
            <Text style={styles.suggTitle}>{t("more.suggestionTitle")}</Text>
            <Text style={styles.suggSub}>{t("more.suggestionSubFull")}</Text>
          </View>
          <View style={styles.suggBtn}>
            <Text style={styles.suggBtnText}>{t("more.send")}</Text>
          </View>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  container: { paddingHorizontal: 20 },
  pressed: { opacity: 0.65 },

  // Header
  header: { flexDirection: "row", alignItems: "center", marginBottom: 26 },
  title: { fontSize: 30, fontWeight: "800", color: colors.onSurface },
  gearBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    marginLeft: 10,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  profilePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 8,
    paddingHorizontal: 11,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  profileHi: { fontSize: 11, color: colors.muted, lineHeight: 14 },
  profileName: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, lineHeight: 17 },

  // Section headers
  sectionHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14 },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  sectionHint: { fontSize: 12, color: colors.muted },

  // Grid (Tu dinero) — natural, consistent card heights
  grid: { gap: 12, marginBottom: 28 },
  gridRow: { flexDirection: "row", gap: 12 },
  // Uniform cards: fixed height, pastel diagonal gradient, hairline border, ultra-soft shadow.
  tile: {
    flex: 1,
    height: 150,
    borderRadius: 22,
    padding: 14,
    borderWidth: 1,
    overflow: "hidden",
    backgroundColor: colors.surfaceSecondary,
    justifyContent: "flex-start",
    shadowColor: "#0B2A1E",
    shadowOpacity: scheme === "dark" ? 0 : 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 3 },
    elevation: 1,
  },
  tileGradient: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  tileTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 },
  tileIcon: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  tileArrow: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: scheme === "dark" ? "rgba(255,255,255,0.10)" : "rgba(255,255,255,0.72)",
    alignItems: "center",
    justifyContent: "center",
  },
  tileLabel: { fontSize: 14.5, fontWeight: "800", color: scheme === "dark" ? colors.onSurface : "#13201A", marginBottom: 4 },
  tileSub: { fontSize: 12, color: colors.muted, lineHeight: 16 },

  // App list
  appCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    marginBottom: 28,
    overflow: "hidden",
  },
  appRow: { flexDirection: "row", alignItems: "center", paddingVertical: 15 },
  appRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  appIcon: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  appLabel: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: 3 },
  appSub: { fontSize: 12.5, color: colors.muted, lineHeight: 16 },

  // Suggestion
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.success + (scheme === "dark" ? "1F" : "14"),
    borderRadius: 20,
    padding: 16,
  },
  suggIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.success + "26",
    alignItems: "center",
    justifyContent: "center",
  },
  suggTitle: { fontSize: 14.5, fontWeight: "800", color: colors.onSurface, marginBottom: 3, lineHeight: 19 },
  suggSub: { fontSize: 12.5, color: colors.muted, lineHeight: 16 },
  suggBtn: { backgroundColor: colors.success + (scheme === "dark" ? "2E" : "1F"), borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: 16 },
  suggBtnText: { color: colors.success, fontSize: 13, fontWeight: "700" },
}));
