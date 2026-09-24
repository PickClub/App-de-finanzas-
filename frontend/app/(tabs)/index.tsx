import React, { useState, useMemo } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet, RefreshControl } from "react-native";
import Svg, { Circle as SvgCircle, Path as SvgPath } from "react-native-svg";
import { LinearGradient } from "expo-linear-gradient";
import { useQuery } from "@tanstack/react-query";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeColors } from "@/src/theme";
import { formatCurrency, formatCurrencyInt, formatDateLong, formatDateTime, translateCategoryName } from "@/src/format";
import i18n, { useTranslation } from "@/src/i18n";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

// --- HOME-ONLY color redesign (light mode only) ---------------------------
// These tokens SHADOW the global theme ONLY on the Home screen in light mode,
// so no other screen/tab is affected and dark mode keeps its existing look.
// They map onto existing theme-token keys so the many `colors.*` references in
// this file automatically pick up the new premium sage/green identity.
const HOME_LIGHT: Partial<ThemeColors> = {
  onSurface: "#15251E", // strong dark green-black titles/values
  muted: "#68746D", // muted gray-green secondary text
  brandPrimary: "#126046", // green becomes the Home accent (was coral)
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E66B27", // warm burnt-orange accent (próximo pago)
  statsPurple: "#7546D7",
  accountsBlue: "#377FC4",
  incomeGreen: "#138B66",
  expenseRed: "#D84D45",
  border: "rgba(39,71,56,0.10)",
  borderStrong: "rgba(39,71,56,0.14)",
  divider: "#E4E7E2",
  surfaceSecondary: "#FCFCF8", // warm white surfaces
};

// Rich, distinctive per-account identity colors (Home light mode only). Keyed
// by lowercased account name; unknown accounts fall back to their real color.
const HOME_ACCOUNT_COLORS: Record<string, string> = {
  "chase checking": "#0C5C46", // deep emerald
  efectivo: "#C6952C", // premium gold
  ahorros: "#176F78", // blue-teal
  "cuenta 2": "#678E58", // moss green
  "cuenta 6": "#E2763E", // burnt orange
};
function homeAccountColor(a: any, scheme: string): string {
  if (scheme === "dark") return a?.color;
  const key = (a?.name || "").trim().toLowerCase();
  return HOME_ACCOUNT_COLORS[key] || a?.color;
}

// --- Color helpers (visual-only) for the account cards. Blend a hex color
// toward white (lighten) or black (darken) to build subtle gradients and the
// slightly darker arrow button, without touching any data. ---
function hexToRgb(hex: string) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function mixToward(hex: string, target: number, amt: number) {
  try {
    const { r, g, b } = hexToRgb(hex);
    const c = (v: number) => Math.max(0, Math.min(255, Math.round(v + (target - v) * amt)));
    return `rgb(${c(r)},${c(g)},${c(b)})`;
  } catch {
    return hex;
  }
}
const lighten = (hex: string, amt: number) => mixToward(hex, 255, amt);
const darken = (hex: string, amt: number) => mixToward(hex, 0, amt);

function accountTypeLabel(t: string) {
  const m: Record<string, string> = {
    cash: "Efectivo", checking: "Corriente", savings: "Ahorro",
    credit_card: "Tarjeta", wallet: "Wallet", other: "Otra",
  };
  return m[t] || t;
}

function accountBars(accounts: any[], total: number, colors: ThemeColors, scheme: string) {
  const positives = accounts.filter((a) => a.current_balance > 0);
  const base = total > 0 ? total : positives.reduce((s, a) => s + a.current_balance, 0);
  // Home distribution preview shows a MAXIMUM of 5 accounts (top by balance).
  const sorted = [...positives].sort((a, b) => b.current_balance - a.current_balance).slice(0, 5);
  if (sorted.length === 0) {
    return <Text style={{ color: colors.muted, fontSize: 10 }}>{i18n.t("home.noAccounts")}</Text>;
  }
  // Soft neutral track — clearly visible against the warm-white card surface.
  const track = scheme === "dark" ? "#3A352F" : "#E5E9E3";
  return sorted.map((a) => {
    const ac = homeAccountColor(a, scheme);
    const pct = base > 0 ? Math.round((a.current_balance / base) * 100) : 0;
    return (
      <View key={a.id}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={{ flexShrink: 1, fontSize: 10, fontWeight: "700", color: colors.onSurface }} numberOfLines={1}>
            {a.name}
          </Text>
          <Text style={{ fontSize: 10, fontWeight: "800", color: ac, marginLeft: 4 }}>{pct}%</Text>
        </View>
        <View
          style={{
            marginTop: 4,
            height: 9,
            borderRadius: 4.5,
            backgroundColor: track,
            overflow: "hidden",
          }}
        >
          <View style={{ width: `${Math.max(6, pct)}%`, height: "100%", backgroundColor: ac, borderRadius: 4.5 }} />
        </View>
      </View>
    );
  });
}

// Mini 7-bar chart for the income / expense cards. Uses real amounts; when a
// period has no data it falls back to a soft placeholder pattern so the card
// never looks empty. Colors are passed in to respect the current theme.
function MiniBars({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data, 0);
  const nonZero = data.filter((v) => v > 0).length;
  const pattern = [0.45, 0.6, 0.5, 0.8, 0.55, 1, 0.65];
  // With sparse real data (0-2 active days) the chart would look like a flat
  // line, so fall back to a soft pattern to keep the reference look.
  const usePattern = nonZero < 3;
  return (
    <View style={mb.row}>
      {data.map((v, i) => {
        const ratio = usePattern ? pattern[i % pattern.length] : v / max;
        const peak = usePattern ? pattern[i % pattern.length] === 1 : v === max && v > 0;
        return (
          <View
            key={i}
            style={{
              flex: 1,
              height: 6 + ratio * 22,
              borderRadius: 3,
              backgroundColor: color + (peak ? "" : "59"),
            }}
          />
        );
      })}
    </View>
  );
}

// Small drag-handle affordance (2×3 dots) shown at the card's top-right.
function DragDots({ color }: { color: string }) {
  return (
    <View style={{ flexDirection: "row", gap: 3 }}>
      {[0, 1].map((c) => (
        <View key={c} style={{ gap: 3 }}>
          {[0, 1, 2].map((r) => (
            <View key={r} style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: color }} />
          ))}
        </View>
      ))}
    </View>
  );
}

const mb = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "flex-end", height: 34, gap: 3, marginTop: 2 },
});

// Reusable external section header — same visual style as the "Movimientos
// recientes" header (soft coral icon tile on the left, title + subtitle, and a
// compact very-light-coral "Ver todo >" pill on the right). Visual-only; it
// wires an optional onSeeAll navigation and an optional right-side node.
function SectionHeader({
  icon,
  title,
  subtitle,
  onSeeAll,
  seeAllTestID,
  right,
}: {
  icon: string;
  title: string;
  subtitle: string;
  onSeeAll?: () => void;
  seeAllTestID?: string;
  right?: React.ReactNode;
}) {
  const { colors: baseColors, scheme } = useTheme();
  const { t } = useTranslation();
  const colors = scheme === "dark" ? baseColors : ({ ...baseColors, ...HOME_LIGHT } as ThemeColors);
  const styles = useStyles();
  return (
    <View style={styles.mrHeader}>
      <View style={styles.mrIconTile}>
        <Ionicons name={icon as any} size={18} color={colors.brandPrimary} />
      </View>
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={styles.mrTitle} numberOfLines={1}>{title}</Text>
        <Text style={styles.mrSubtitle} numberOfLines={1}>{subtitle}</Text>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        {right}
        {onSeeAll && (
          <Pressable testID={seeAllTestID} onPress={onSeeAll} style={styles.seeAllBtn}>
            <Text style={styles.seeAllText}>{t("common.seeAll")}</Text>
            <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
          </Pressable>
        )}
      </View>
    </View>
  );
}

export default function Home() {
  const { colors: baseColors, scheme } = useTheme();
  const { t } = useTranslation();
  // Home-only light palette override (dark mode untouched).
  const colors = useMemo(
    () => (scheme === "dark" ? baseColors : ({ ...baseColors, ...HOME_LIGHT } as ThemeColors)),
    [baseColors, scheme],
  );
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [hidden, setHidden] = useState(false);
  const [txFilter, setTxFilter] = useState("all");
  const [monthOnly, setMonthOnly] = useState(false);

  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const userQ = useQuery({ queryKey: ["user"], queryFn: api.getUser });
  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const summary = summaryQ.data;
  const user = userQ.data;
  const recent = useMemo(() => {
    let items: any[] = txQ.data || [];
    if (txFilter === "income") items = items.filter((t: any) => t.type === "income" || t.type === "loan_received");
    else if (txFilter === "expense") items = items.filter((t: any) => t.type === "expense" || t.type === "debt_payment");
    else if (txFilter === "transfer") items = items.filter((t: any) => t.type === "transfer");
    if (monthOnly) {
      const now = new Date();
      const first = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
      items = items.filter((t: any) => new Date(t.date).getTime() >= first);
    }
    return items.slice(0, 6);
  }, [txQ.data, txFilter, monthOnly]);
  const cats: any[] = catQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));
  const accounts: any[] = accQ.data || [];

  const money = (n: number) => (hidden ? "••••" : formatCurrency(n));
  const debtMoney = (n: number) => (hidden ? "••••" : formatCurrencyInt(n));

  // Account growth indicator (visual-only) — derived from real summary data:
  // this month's net movement relative to the opening balance. No hardcoding.
  const monthNet = (summary?.month_income || 0) - (summary?.month_expense || 0);
  const openingBalance = (summary?.total_balance || 0) - monthNet;
  const growthPct = openingBalance > 0 ? (monthNet / openingBalance) * 100 : 0;
  const growthPositive = growthPct >= 0;

  // Last-7-days mini-chart data + daily averages for the Income / Expense cards.
  const stats = useMemo(() => {
    const txs = txQ.data || [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const incBars = Array(7).fill(0) as number[];
    const expBars = Array(7).fill(0) as number[];
    txs.forEach((t: any) => {
      const d = new Date(t.date);
      d.setHours(0, 0, 0, 0);
      const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
      if (diff < 0 || diff > 6) return;
      if (t.type === "income") incBars[6 - diff] += t.amount;
      else if (t.type === "expense" || t.type === "debt_payment") expBars[6 - diff] += t.amount;
    });
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    return {
      incBars,
      expBars,
      avgIncome: (summary?.month_income || 0) / daysInMonth,
      avgExpense: (summary?.month_expense || 0) / daysInMonth,
    };
  }, [txQ.data, summary?.month_income, summary?.month_expense]);

  const TX_FILTERS = [
    { id: "all", label: t("home.filterAll"), icon: "grid", color: colors.brandPrimary },
    { id: "income", label: t("home.filterIncome"), icon: "trending-up", color: colors.incomeGreen },
    { id: "expense", label: t("home.filterExpenses"), icon: "trending-down", color: colors.expenseRed },
    { id: "transfer", label: t("home.filterTransfers"), icon: "swap-horizontal", color: colors.accountsBlue },
  ] as const;

  return (
    <View style={{ flex: 1, backgroundColor: scheme === "dark" ? colors.surface : "#E8EFE7" }}>
    <ScrollView
      testID="home-scroll"
      style={{ flex: 1, backgroundColor: "transparent" }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120 }}
      refreshControl={
        <RefreshControl
          refreshing={summaryQ.isFetching}
          onRefresh={() => {
            summaryQ.refetch();
            txQ.refetch();
          }}
          tintColor={colors.brandPrimary}
        />
      }
    >
      {/* Header — compact balance + growth (greeting removed) */}
      <View style={styles.header}>
        <View style={styles.balanceIconTile}>
          <Ionicons name="wallet-outline" size={20} color={colors.brandPrimary} />
        </View>
        <View style={styles.balanceBlock}>
          <Text
            style={styles.balanceNumber}
            testID="total-balance"
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.6}
          >
            {hidden ? "••••" : formatCurrencyInt(summary?.total_balance || 0)}
          </Text>
          <View style={styles.growthRow}>
            <Ionicons
              name={growthPositive ? "arrow-up" : "arrow-down"}
              size={15}
              color={growthPositive ? colors.incomeGreen : colors.expenseRed}
            />
            <Text style={[styles.growthText, { color: growthPositive ? colors.incomeGreen : colors.expenseRed }]}>
              {Math.abs(growthPct).toFixed(1)}%
            </Text>
          </View>
        </View>
        <Pressable testID="notifications-btn" style={styles.roundIcon}>
          <Ionicons name="notifications-outline" size={22} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="profile-more-btn" onPress={() => router.push("/more")} style={styles.avatar}>
          <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>
            {(user?.name || "U").slice(0, 1)}
          </Text>
        </Pressable>
      </View>

      {/* Section divider — before Mis cuentas */}
      <View style={styles.sectionDivider} />

      {/* Mis cuentas */}
      <View style={{ paddingTop: spacing.lg }}>
        <View style={{ paddingHorizontal: spacing.lg }}>
          <SectionHeader
            icon="wallet-outline"
            title={t("home.myAccounts")}
            subtitle={t("home.myAccountsSubtitle")}
            onSeeAll={() => router.push("/accounts")}
            seeAllTestID="see-all-accounts"
            right={
              <Pressable testID="toggle-hide-btn" onPress={() => setHidden((h) => !h)} hitSlop={8}>
                <Ionicons name={hidden ? "eye-off-outline" : "eye-outline"} size={20} color={colors.muted} />
              </Pressable>
            }
          />
        </View>
        <View style={styles.walletGrid}>
          {accounts.map((a, idx) => {
            const isThird = (idx + 1) % 3 === 0;
            const ac = homeAccountColor(a, scheme);
            return (
              <Pressable
                key={a.id}
                testID={`wallet-${a.id}`}
                onPress={guard(() => router.push(`/accounts/new?id=${a.id}`))}
                style={[styles.walletCard, { backgroundColor: ac }, isThird && styles.walletCardLast]}
              >
                <View style={styles.walletInner}>
                  <LinearGradient
                    colors={[lighten(ac, 0.16), ac, darken(ac, 0.06)]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={StyleSheet.absoluteFill}
                  />
                  <Ionicons
                    name={a.icon as any}
                    size={58}
                    color="rgba(255,255,255,0.12)"
                    style={styles.walletWatermark}
                  />
                  <View style={styles.walletTopRow}>
                    <View style={styles.walletIconBox}>
                      <Ionicons name={a.icon as any} size={14} color="#fff" />
                    </View>
                    <View style={[styles.walletArrow, { backgroundColor: darken(ac, 0.16) }]}>
                      <Ionicons name="chevron-forward" size={12} color="#fff" />
                    </View>
                  </View>
                  <View style={styles.walletTextWrap}>
                    <Text style={styles.walletName} numberOfLines={1}>{a.name}</Text>
                    <Text style={styles.walletBalance} numberOfLines={1} adjustsFontSizeToFit>
                      {money(a.current_balance)}
                    </Text>
                  </View>
                </View>
              </Pressable>
            );
          })}
          <Pressable
            testID="wallet-add"
            onPress={() => router.push("/accounts/new")}
            style={[styles.walletAddCard, (accounts.length + 1) % 3 === 0 && styles.walletCardLast]}
          >
            <Ionicons name="add" size={22} color={colors.brandPrimary} />
            <Text style={styles.walletAddText}>{t("home.addAccount")}</Text>
          </Pressable>
        </View>
      </View>

      {/* Section divider — before Resumen del mes */}
      <View style={styles.sectionDivider} />

      {/* Resumen del mes */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg }}>
        <SectionHeader
          icon="stats-chart-outline"
          title={t("home.monthSummary")}
          subtitle={t("home.monthSummarySubtitle")}
          onSeeAll={() => router.push("/(tabs)/reports")}
          seeAllTestID="see-all-summary"
        />
      </View>

      {/* Income / Expense / Accounts distribution */}
      <View style={styles.miniRow}>
        <View style={styles.miniLeft}>
          <View style={[styles.miniCard, styles.miniHalfLeft, styles.cardIncome]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.incomeGreen }]}>
                <Ionicons name="arrow-up" size={14} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>{t("home.thisMonth")}</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>{t("home.income")}</Text>
            <Text
              style={[styles.miniAmount, { color: colors.incomeGreen }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              +{money(summary?.month_income || 0)}
            </Text>
            <MiniBars data={stats.incBars} color={colors.incomeGreen} />
            <View style={styles.mcAvg}>
              <Text style={styles.mcAvgLabel}>{t("home.dailyAverage")}</Text>
              <Text style={styles.mcAvgVal}>{money(stats.avgIncome)}</Text>
            </View>
          </View>
          <View style={[styles.miniCard, styles.miniHalfRight, styles.cardExpense]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.expenseRed }]}>
                <Ionicons name="arrow-down" size={14} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>{t("home.thisMonth")}</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>{t("home.expenses")}</Text>
            <Text
              style={[styles.miniAmount, { color: colors.expenseRed }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              -{money(summary?.month_expense || 0)}
            </Text>
            <MiniBars data={stats.expBars} color={colors.expenseRed} />
            <View style={styles.mcAvg}>
              <Text style={styles.mcAvgLabel}>{t("home.dailyAverage")}</Text>
              <Text style={styles.mcAvgVal}>{money(stats.avgExpense)}</Text>
            </View>
          </View>
        </View>
        <View style={[styles.miniCard, styles.miniAccounts]}>
          <View testID="cuentas-scroll" style={{ gap: 6 }}>
            {accountBars(accounts, summary?.total_balance || 0, colors, scheme)}
          </View>
        </View>
      </View>

      {/* Section divider — before Deudas */}
      <View style={styles.sectionDivider} />

      {/* Deudas */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
        <SectionHeader
          icon="wallet-outline"
          title={t("home.debts")}
          subtitle={t("home.debtsSubtitle")}
          onSeeAll={() => router.push("/debts")}
          seeAllTestID="see-all-debts"
        />
      </View>

      {/* Debts card */}
      <View style={{ paddingHorizontal: spacing.lg }}>
        <Pressable testID="debts-card" onPress={() => router.push("/debts")} style={styles.debtCard}>
          {/* soft abstract background */}
          <View pointerEvents="none" style={StyleSheet.absoluteFill}>
            <Svg width="100%" height="100%" viewBox="0 0 320 240" preserveAspectRatio="none">
              <SvgCircle cx="24" cy="200" r="42" fill={colors.brandSecondary} opacity="0.06" />
              <SvgCircle cx="290" cy="30" r="26" fill={colors.statsPurple} opacity="0.05" />
              <SvgPath
                d="M0 60 Q 60 40, 120 55 T 260 45 T 340 55"
                stroke={colors.brandSecondary}
                strokeOpacity="0.12"
                strokeWidth="1"
                fill="none"
              />
              <SvgPath
                d="M20 210 Q 90 195, 160 205 T 320 200"
                stroke={colors.brandPrimary}
                strokeOpacity="0.08"
                strokeWidth="1"
                fill="none"
              />
              <SvgCircle cx="180" cy="122" r="4" fill={colors.brandPrimary} opacity="0.14" />
              <SvgCircle cx="60" cy="120" r="2.5" fill={colors.statsPurple} opacity="0.2" />
              {[0, 1, 2].map((r) =>
                [0, 1, 2].map((c) => (
                  <SvgCircle
                    key={`d-${r}-${c}`}
                    cx={295 + c * 6}
                    cy={112 + r * 6}
                    r="1.2"
                    fill={colors.muted}
                    opacity="0.35"
                  />
                )),
              )}
            </Svg>
          </View>

          {/* first row */}
          <View style={styles.debtQuadRow}>
            <View style={styles.debtQuadLeft}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.expenseRed + "1A" }]}>
                  <Ionicons name="arrow-up" size={14} color={colors.expenseRed} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>{t("home.iOwe")}</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.i_owe || 0)}
                  </Text>
                </View>
              </View>
            </View>
            <View style={styles.debtVDivider} />
            <View style={styles.debtQuadRight}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.incomeGreen + "1A" }]}>
                  <Ionicons name="arrow-down" size={14} color={colors.incomeGreen} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>{t("home.owedToMe")}</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.they_owe || 0)}
                  </Text>
                </View>
              </View>
            </View>
          </View>

          <View style={styles.debtHDivider} />

          {/* second row */}
          <View style={styles.debtQuadRow}>
            <View style={styles.debtQuadLeft}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.statsPurple + "1A" }]}>
                  <Ionicons name="card" size={14} color={colors.statsPurple} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>{t("home.paidThisMonth")}</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.statsPurple }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.paid_this_month || 0)}
                  </Text>
                  <Text style={styles.debtQuadFoot}>{t("home.goodProgress")}</Text>
                </View>
              </View>
            </View>
            <View style={styles.debtVDivider} />
            <View style={styles.debtQuadRight}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.brandSecondary + "1F" }]}>
                  <Ionicons name="calendar" size={14} color={colors.brandSecondary} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>{t("home.nextPayment")}</Text>
                  {summary?.debts?.next_payment ? (
                    <>
                      <Text style={styles.debtQuadDate} numberOfLines={1}>
                        {formatDateLong(summary.debts.next_payment.date)}
                      </Text>
                      <Text style={[styles.debtQuadValue, { color: colors.brandSecondary, fontSize: 15 }]} numberOfLines={1} adjustsFontSizeToFit>
                        {debtMoney(summary.debts.next_payment.amount)}
                      </Text>
                      <Text style={styles.debtQuadFoot}>{t("home.keepPaymentsUpToDate")}</Text>
                    </>
                  ) : (
                    <Text style={styles.debtQuadFoot}>{t("home.noUpcomingPayments")}</Text>
                  )}
                </View>
              </View>
            </View>
          </View>
        </Pressable>
      </View>

      {/* Section divider — before Movimientos recientes */}
      <View style={styles.sectionDivider} />

      {/* Recent transactions — "Movimientos recientes" */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
        {/* Section header */}
        <View style={styles.mrHeader}>
          <View style={styles.mrIconTile}>
            <Ionicons name="layers-outline" size={18} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={styles.mrTitle} numberOfLines={1} ellipsizeMode="clip">
              {t("home.recentMovements")} <Text style={styles.mrTitleAccent}>{t("home.recentMovementsAccent")}</Text>
            </Text>
            <Text style={styles.mrSubtitle} numberOfLines={1}>
              {t("home.recentMovementsSubtitle")}
            </Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <LockToggle testID="lock-home" compact />
            <Pressable testID="see-all-tx" onPress={() => router.push("/(tabs)/transactions")} style={styles.seeAllBtn}>
              <Text style={styles.seeAllText}>{t("common.seeAll")}</Text>
              <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
            </Pressable>
          </View>
        </View>

        {/* Filters */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.mrFilterRow}
        >
          {TX_FILTERS.map((f) => {
            const active = txFilter === f.id;
            const content = (
              <>
                <Ionicons name={f.icon as any} size={13} color={active ? "#fff" : f.color} />
                <Text style={[styles.mrPillText, active && styles.mrPillTextActive]}>{f.label}</Text>
              </>
            );
            return active ? (
              <Pressable key={f.id} testID={`mr-filter-${f.id}`} onPress={() => setTxFilter(f.id)}>
                <LinearGradient
                  colors={scheme === "dark" ? [colors.brandPrimary, colors.brandSecondary] : ["#16694A", "#146448"]}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 0 }}
                  style={styles.mrPill}
                >
                  {content}
                </LinearGradient>
              </Pressable>
            ) : (
              <Pressable
                key={f.id}
                testID={`mr-filter-${f.id}`}
                onPress={() => setTxFilter(f.id)}
                style={[styles.mrPill, styles.mrPillIdle]}
              >
                {content}
              </Pressable>
            );
          })}
          <Pressable
            testID="mr-filter-month"
            onPress={() => setMonthOnly((m) => !m)}
            style={[styles.mrIconPill, monthOnly && styles.mrIconPillActive]}
          >
            <Ionicons name="calendar-outline" size={15} color={monthOnly ? colors.brandPrimary : colors.muted} />
          </Pressable>
        </ScrollView>

        {/* List card */}
        <View style={styles.mrCard}>
          {recent.length === 0 && (
            <Text style={{ color: colors.muted, textAlign: "center", padding: spacing.lg }}>
              {t("home.noMovements")}
            </Text>
          )}
          {recent.map((t, idx) => {
            const cat = catById[t.category_id];
            const isIncome = t.type === "income" || t.type === "loan_received";
            const isTransfer = t.type === "transfer";
            const color = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
            const sign = isTransfer ? "" : isIncome ? "+" : "-";
            const iconName =
              cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
            const tint = cat?.color || color;
            const badgeLabel = cat?.name ? translateCategoryName(cat.name) : (isTransfer ? t("txType.transfer") : isIncome ? t("txType.income") : t("txType.expense"));
            const badgeColor = cat?.color || color;
            return (
              <View key={t.id}>
                {idx > 0 && <View style={styles.mrDivider} />}
                <Pressable
                  testID={`mr-tx-${t.id}`}
                  onPress={guard(() => router.push(`/transactions/${t.id}`))}
                  style={styles.mrRow}
                >
                  <IconTile icon={iconName} tint={tint} size={36} />
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={styles.mrName} numberOfLines={1}>{t.name}</Text>
                    <View style={styles.mrTimeRow}>
                      <Ionicons name="time-outline" size={12} color={colors.muted} />
                      <Text style={styles.mrTime} numberOfLines={1}>{formatDateTime(t.date)}</Text>
                    </View>
                  </View>
                  <View style={[styles.mrBadge, { backgroundColor: badgeColor + "1A" }]}>
                    <Text style={[styles.mrBadgeText, { color: badgeColor }]} numberOfLines={1}>{badgeLabel}</Text>
                  </View>
                  <Text style={[styles.mrAmount, { color }]}>{sign}{formatCurrency(t.amount)}</Text>
                  <Ionicons name="chevron-forward" size={15} color={colors.muted} style={{ marginLeft: 4 }} />
                </Pressable>
              </View>
            );
          })}
        </View>

        {/* AI banner — taps through to the IA tab (same route as the mic in the bottom nav) */}
        <Pressable testID="ai-banner" onPress={() => router.push("/(tabs)/transactions")} style={{ marginTop: 8 }}>
          <LinearGradient
            colors={scheme === "dark" ? [colors.brandPrimary + "1F", colors.statsPurple + "1F"] : ["#E5F1E7", "#E5F1E7"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.aiBanner}
          >
            <View style={styles.aiIcon}>
              <Ionicons name="sparkles" size={17} color={scheme === "dark" ? colors.brandPrimary : "#147450"} />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.aiTitle} numberOfLines={1}>{t("home.aiBannerTitle")}</Text>
              <Text style={styles.aiSub} numberOfLines={1}>{t("home.aiBannerSubtitle")}</Text>
            </View>
            <View style={styles.aiChevron}>
              <Ionicons name="chevron-forward" size={16} color={scheme === "dark" ? colors.brandPrimary : "#126047"} />
            </View>
          </LinearGradient>
        </Pressable>
      </View>
    </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  // Home-only light palette (dark keeps its existing card color). Warm-white
  // surfaces pop against the sage page background; text is dark green-black.
  const isDark = scheme === "dark";
  const cardSurface = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const wallText = isDark ? colors.onSurface : "#15251E";
  const wallMuted = isDark ? colors.muted : "#68746D";
  const wallSub = isDark ? colors.muted : "#8B958F";
  const lineSoft = isDark ? colors.border : "rgba(39,71,56,0.10)";
  const dividerSoft = isDark ? colors.divider : "#E4E7E2";
  const tileGreen = isDark ? colors.brandPrimary + "1A" : "#DCE9DD";
  const accentGreen = isDark ? colors.brandPrimary : "#126046";
  const seePill = isDark ? colors.brandPrimary + "14" : "#DFEBDD";
  const chipIdle = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const chipIdleBorder = isDark ? colors.border : "#D9DED8";
  return {
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    gap: 8,
  },
  hello: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  roundIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: cardSurface, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: lineSoft,
  },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: isDark ? colors.brandPrimary : "#0B5941", alignItems: "center", justifyContent: "center",
  },
  balanceIconTile: {
    width: 44, height: 44, borderRadius: 14,
    backgroundColor: tileGreen,
    alignItems: "center", justifyContent: "center",
  },
  balanceBlock: {
    flex: 1,
    marginLeft: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  balanceNumber: {
    flexShrink: 1,
    fontSize: 30,
    fontWeight: "800",
    color: wallText,
    letterSpacing: -0.8,
  },
  growthRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 1,
  },
  growthText: {
    fontSize: 14,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  // Subtle, short, continuous inset divider used to separate Home sections.
  // Neutral warm gray at low opacity — inset ~15% from both ends.
  sectionDivider: {
    height: 1,
    marginHorizontal: "15%",
    marginTop: spacing.md,
    backgroundColor: isDark ? colors.borderStrong : "rgba(39,71,56,0.12)",
    opacity: scheme === "dark" ? 0.5 : 0.6,
  },
  balanceCard: {
    borderRadius: radius.cardLg,
    padding: 22,
    minHeight: 170,
  },
  balanceLabel: { color: "#ffffffcc", fontSize: 13, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase" },
  balanceAmount: { color: "#fff", fontSize: 38, fontWeight: "800", marginTop: 10 },
  balanceSub: { color: "#ffffffcc", fontSize: 13, marginTop: 2 },
  balanceBtn: {
    marginTop: 14,
    alignSelf: "flex-start",
    backgroundColor: "#ffffff33",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  totalLine: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 2,
    paddingHorizontal: spacing.lg,
  },
  walletGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  walletCard: {
    flexBasis: "31%",
    flexGrow: 0,
    flexShrink: 0,
    marginRight: "3.5%",
    marginBottom: 10,
    minHeight: 84,
    borderRadius: radius.md,
    // Soft, short, diffuse outer shadow only — no heavy floating / 3D look.
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  walletInner: {
    minHeight: 84,
    borderRadius: radius.md,
    overflow: "hidden",
    padding: 10,
    justifyContent: "space-between",
  },
  walletWatermark: {
    position: "absolute",
    right: -6,
    bottom: -8,
  },
  walletTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  walletIconBox: {
    width: 26,
    height: 26,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.16)",
    alignItems: "center",
    justifyContent: "center",
  },
  walletArrow: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  walletTextWrap: {
    marginTop: 6,
  },
  walletCardLast: {
    marginRight: 0,
  },
  walletName: { color: "#fff", fontSize: 12.5, fontWeight: "600", letterSpacing: 0.1 },
  walletBalance: { color: "rgba(255,255,255,0.92)", fontSize: 11, fontWeight: "600", marginTop: 1 },
  walletAddCard: {
    flexBasis: "31%",
    flexGrow: 0,
    flexShrink: 0,
    marginRight: "3.5%",
    marginBottom: 10,
    minHeight: 84,
    borderRadius: radius.md,
    padding: 10,
    backgroundColor: cardSurface,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: isDark ? colors.brandPrimary : "#0D684C",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
  },
  walletAddText: {
    color: isDark ? colors.brandPrimary : "#0D684C",
    fontWeight: "800",
    fontSize: 11,
    lineHeight: 14,
  },
  miniRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md,
    alignItems: "stretch",
  },
  miniLeft: {
    flex: 3, // ~60%
    flexDirection: "row",
    marginRight: 8,
  },
  miniHalfLeft: {
    flex: 1,
    marginRight: 4,
  },
  miniHalfRight: {
    flex: 1,
    marginLeft: 4,
  },
  miniAccounts: {
    flex: 2, // ~40%
    paddingVertical: 12,
    paddingHorizontal: 12,
    justifyContent: "center",
    // Warm-white distribution card — pops against the sage page background.
    backgroundColor: isDark ? colors.surfaceSecondary : "#FCFCF8",
    borderColor: lineSoft,
  },
  miniCard: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    padding: 12,
    borderWidth: 1,
    borderColor: lineSoft,
    minHeight: 148,
  },
  cardIncome: {
    backgroundColor: isDark ? colors.incomeGreen + "14" : "#ECF6F0",
    borderColor: isDark ? colors.incomeGreen + "33" : "#BBDDCB",
    padding: 10,
    justifyContent: "space-between",
  },
  cardExpense: {
    backgroundColor: isDark ? colors.expenseRed + "14" : "#F8ECE8",
    borderColor: isDark ? colors.expenseRed + "33" : "#E7C7C0",
    padding: 10,
    justifyContent: "space-between",
  },
  miniPill: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  miniLabel: { fontSize: 12, color: wallMuted, marginTop: 4, fontWeight: "700" },
  miniAmount: { fontSize: 14, fontWeight: "800", marginTop: 2 },
  miniSub: { fontSize: 9, color: wallMuted, marginTop: 2, fontWeight: "600" },
  mcTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  mcTopRight: { alignItems: "flex-end", gap: 3 },
  mcAvg: { marginTop: 2 },
  mcAvgLabel: { fontSize: 9, color: wallMuted, fontWeight: "600" },
  mcAvgVal: { fontSize: 13, fontWeight: "800", color: wallText, marginTop: 1 },
  debtCard: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    padding: 13,
    borderWidth: 1,
    borderColor: lineSoft,
    overflow: "hidden",
    shadowColor: "#274738",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  debtHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  debtHeaderIcon: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.brandSecondary + "1A",
    alignItems: "center",
    justifyContent: "center",
  },
  debtHeaderSub: {
    fontSize: 10,
    color: colors.muted,
    fontWeight: "400",
    marginTop: 2,
  },
  debtArrowBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  debtTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  debtQuadRow: {
    flexDirection: "row",
    marginTop: 11,
  },
  debtQuadLeft: { flex: 1, paddingRight: 6 },
  debtQuadRight: { flex: 1, paddingLeft: 10 },
  debtQuadInner: { flexDirection: "row", alignItems: "flex-start" },
  debtQuadIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  debtQuadLabel: { fontSize: 10, color: wallMuted, fontWeight: "500" },
  debtQuadValue: { fontSize: 18, fontWeight: "800", marginTop: 2, letterSpacing: -0.5 },
  debtQuadFoot: { fontSize: 8, color: wallSub, marginTop: 2, fontWeight: "500" },
  debtQuadDate: { fontSize: 10, color: wallText, fontWeight: "700", marginTop: 2 },
  debtVDivider: { width: 1, backgroundColor: dividerSoft, marginVertical: 4 },
  debtHDivider: { height: 1, backgroundColor: dividerSoft, marginTop: 11 },
  debtLabel: { fontSize: 12, color: colors.muted, fontWeight: "400" },
  debtValue: { fontSize: 18, fontWeight: "600", marginTop: 4, letterSpacing: -0.3 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  txList: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 4,
  },
  txName: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  txSub: { color: colors.muted, fontSize: 12, marginTop: 2 },

  /* --- Movimientos recientes (redesigned section) --- */
  mrHeader: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  mrIconTile: {
    width: 38, height: 38, borderRadius: 13,
    backgroundColor: tileGreen,
    alignItems: "center", justifyContent: "center",
  },
  mrTitle: { fontSize: 18, fontWeight: "800", color: wallText, letterSpacing: -0.4 },
  mrTitleAccent: { color: isDark ? colors.brandPrimary : "#168460", fontWeight: "800" },
  mrSubtitle: { fontSize: 11.5, color: wallMuted, marginTop: 1 },
  seeAllBtn: {
    flexDirection: "row", alignItems: "center", gap: 2,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: seePill,
  },
  seeAllText: { color: accentGreen, fontWeight: "800", fontSize: 12 },
  mrFilterRow: { flexDirection: "row", gap: 6, paddingVertical: 2, paddingRight: 4, marginBottom: 10 },
  mrPill: {
    flexDirection: "row", alignItems: "center", gap: 5,
    height: 32, paddingHorizontal: 12, borderRadius: radius.pill,
    flexShrink: 0,
  },
  mrPillIdle: {
    backgroundColor: chipIdle,
    borderWidth: 1, borderColor: chipIdleBorder,
  },
  mrPillText: { fontSize: 12, fontWeight: "700", color: isDark ? colors.onSurface : "#26352E" },
  mrPillTextActive: { color: "#fff" },
  mrIconPill: {
    width: 32, height: 32, borderRadius: radius.pill,
    alignItems: "center", justifyContent: "center",
    backgroundColor: chipIdle,
    borderWidth: 1, borderColor: chipIdleBorder,
    flexShrink: 0,
  },
  mrIconPillActive: {
    backgroundColor: tileGreen,
    borderColor: isDark ? colors.brandPrimary + "55" : "#BAD7C2",
  },
  mrCard: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: lineSoft,
    shadowColor: "#274738",
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 5 },
    elevation: 3,
  },
  mrRow: { flexDirection: "row", alignItems: "center", paddingVertical: 9, paddingHorizontal: 4 },
  mrDivider: { height: 1, backgroundColor: dividerSoft, marginLeft: 50, marginRight: 4 },
  mrName: { color: wallText, fontWeight: "800", fontSize: 13.5, letterSpacing: -0.2 },
  mrTimeRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  mrTime: { color: wallMuted, fontSize: 11 },
  mrBadge: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill, marginHorizontal: 6, flexShrink: 1,
  },
  mrBadgeText: { fontSize: 11, fontWeight: "700" },
  mrAmount: { fontWeight: "800", fontSize: 14, letterSpacing: -0.3 },
  aiBanner: {
    flexDirection: "row", alignItems: "center",
    padding: 10, borderRadius: radius.cardLg,
    borderWidth: 1, borderColor: isDark ? colors.brandPrimary + "3D" : "#BAD7C2",
  },
  aiIcon: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: isDark ? colors.brandPrimary + "26" : "#CDE5D3",
    alignItems: "center", justifyContent: "center",
  },
  aiTitle: { fontSize: 13.5, fontWeight: "800", color: isDark ? colors.onSurface : "#193126", letterSpacing: -0.2 },
  aiSub: { fontSize: 11.5, color: isDark ? colors.muted : "#738078", marginTop: 1 },
  aiChevron: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: isDark ? colors.brandPrimary + "1F" : "#CFE4D3",
    alignItems: "center", justifyContent: "center", marginLeft: 8,
  },
  };
});
