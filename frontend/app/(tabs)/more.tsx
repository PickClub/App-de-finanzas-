import React from "react";
import { View, Text, Pressable, ScrollView } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useTheme, makeStyles, radius } from "@/src/theme";
import { useTranslation } from "@/src/i18n";

type Tile = {
  icon: string;
  label: string;
  subtitle: string;
  color: string;
  route?: string;
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
  // Pastel card fill derived from the module accent — adapts to both themes.
  const tileBg = (c: string) => c + (scheme === "dark" ? "22" : "16");

  const MONEY: Tile[] = [
    { icon: "wallet-outline", label: t("more.accounts"), subtitle: t("more.subAccounts"), color: colors.accountsBlue, route: "/accounts" },
    { icon: "pricetag-outline", label: t("more.categories"), subtitle: t("more.subCategories"), color: colors.brandSecondary, route: "/categories" },
    { icon: "pie-chart-outline", label: t("more.budgets"), subtitle: t("more.subBudgets"), color: colors.expenseRed, route: "/budgets" },
    { icon: "flag-outline", label: t("more.savingsGoals"), subtitle: t("more.subGoals"), color: colors.savingsTurquoise, route: "/goals" },
    { icon: "cash-outline", label: t("more.debtsAndLoans"), subtitle: t("more.subDebts"), color: colors.loansYellow, route: "/debts" },
    { icon: "sync-outline", label: t("more.recurringPayments"), subtitle: t("more.subRecurring"), color: colors.statsPurple },
  ];

  const APP: Tile[] = [
    { icon: "settings-outline", label: t("more.settings"), subtitle: t("more.subSettings"), color: colors.muted, route: "/settings" },
    { icon: "shield-checkmark-outline", label: t("more.privacySecurity"), subtitle: t("more.subPrivacy"), color: colors.accountsBlue },
    { icon: "help-circle-outline", label: t("more.helpCenter"), subtitle: t("more.subHelp"), color: colors.success },
    { icon: "star-outline", label: t("more.rateApp"), subtitle: t("more.subRate"), color: colors.warning },
    { icon: "information-circle-outline", label: t("more.about"), subtitle: t("more.subAbout"), color: colors.info },
  ];

  const rows: Tile[][] = [
    [MONEY[0], MONEY[1]],
    [MONEY[2], MONEY[3]],
    [MONEY[4], MONEY[5]],
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + 14, paddingBottom: insets.bottom + 132 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={styles.title}>{t("more.title")}</Text>
            <Text style={styles.subtitle}>
              {t("more.headerSubtitle")}
            </Text>
          </View>
          <Pressable
            testID="more-profile"
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.profilePill, pressed && styles.pressed]}
          >
            <View style={styles.avatar}>
              <Ionicons name="person" size={16} color={colors.brandPrimary} />
            </View>
            <View style={{ marginHorizontal: 8 }}>
              <Text style={styles.profileHi}>{t("more.greeting")}</Text>
              <Text style={styles.profileName}>{t("more.defaultUser")}</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.muted} />
          </Pressable>
        </View>

        {/* Premium banner */}
        <Pressable testID="more-premium" style={({ pressed }) => [styles.banner, pressed && styles.pressed]}>
          <View style={styles.bannerIcon}>
            <Ionicons name="ribbon" size={26} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 14 }}>
            <Text style={styles.bannerTitle}>{t("more.premiumTitle")}</Text>
            <Text style={styles.bannerSub}>
              {t("more.premiumSubtitleFull")}
            </Text>
          </View>
          <View style={styles.bannerBtn}>
            <Text style={styles.bannerBtnText}>{t("more.learnMore")}</Text>
          </View>
        </Pressable>

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
                  style={({ pressed }) => [styles.tile, { backgroundColor: tileBg(it.color) }, pressed && styles.pressed]}
                >
                  <View style={styles.tileTop}>
                    <View style={[styles.tileIcon, { backgroundColor: it.color + "2E" }]}>
                      <Ionicons name={it.icon as any} size={20} color={it.color} />
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </View>
                  <Text style={styles.tileLabel} numberOfLines={1}>{it.label}</Text>
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
                <Ionicons name={it.icon as any} size={19} color={it.color} />
              </View>
              <View style={{ flex: 1, marginLeft: 14 }}>
                <Text style={styles.appLabel} numberOfLines={1}>{it.label}</Text>
                <Text style={styles.appSub} numberOfLines={1}>{it.subtitle}</Text>
              </View>
              <Ionicons name="chevron-forward" size={19} color={colors.muted} />
            </Pressable>
          ))}
        </View>

        {/* Suggestion */}
        <Pressable testID="more-suggestion" style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}>
          <View style={styles.suggIcon}>
            <Ionicons name="bulb-outline" size={22} color={colors.success} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 14 }}>
            <Text style={styles.suggTitle} numberOfLines={2}>{t("more.suggestionTitle")}</Text>
            <Text style={styles.suggSub} numberOfLines={2}>{t("more.suggestionSubFull")}</Text>
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
  header: { flexDirection: "row", alignItems: "flex-start", marginBottom: 22 },
  title: { fontSize: 30, fontWeight: "800", color: colors.onSurface, marginBottom: 5 },
  subtitle: { fontSize: 13.5, color: colors.muted, lineHeight: 19 },
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

  // Banner
  banner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandTertiary,
    borderRadius: 22,
    padding: 16,
    marginBottom: 28,
  },
  bannerIcon: {
    width: 48,
    height: 48,
    borderRadius: 16,
    backgroundColor: colors.brandPrimary + "2E",
    alignItems: "center",
    justifyContent: "center",
  },
  bannerTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface, lineHeight: 20 },
  bannerSub: { fontSize: 12.5, color: scheme === "dark" ? colors.muted : colors.onSurfaceTertiary, lineHeight: 17, marginTop: 4, opacity: scheme === "dark" ? 1 : 0.8 },
  bannerBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: 16 },
  bannerBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "700" },

  // Section headers
  sectionHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14 },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  sectionHint: { fontSize: 12, color: colors.muted },

  // Grid (Tu dinero) — natural, consistent card heights
  grid: { gap: 12, marginBottom: 28 },
  gridRow: { flexDirection: "row", gap: 12 },
  tile: { flex: 1, minHeight: 128, borderRadius: 20, padding: 14, justifyContent: "flex-start" },
  tileTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  tileIcon: { width: 40, height: 40, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  tileLabel: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface, marginBottom: 4 },
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
