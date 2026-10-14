import { tr, useTranslation as useInterfaceLanguage } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import React, { useMemo, useRef, useState } from "react";
import { View, ScrollView, Platform, Animated as RNAnimated } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";

import { us } from "@/src/ui-scale";
const RANGES = [
  { id: "7d", label: "7d", get pillLabel() { return tr("ui.7_days"); }, days: 7, get periodLabel() { return tr("ui.last_7_days"); } },
  { id: "30d", label: "30d", get pillLabel() { return tr("ui.30_days"); }, days: 30, get periodLabel() { return tr("ui.last_30_days"); } },
  { id: "3m", label: "3m", get pillLabel() { return tr("ui.3_months"); }, days: 90, get periodLabel() { return tr("ui.last_3_months"); } },
  { id: "6m", label: "6m", get pillLabel() { return tr("ui.6_months"); }, days: 180, get periodLabel() { return tr("ui.last_6_months"); } },
  { id: "1y", label: "1a", get pillLabel() { return tr("ui.1_year"); }, days: 365, get periodLabel() { return tr("ui.last_year"); } },
  { id: "all", get label() { return tr("ui.all"); }, get pillLabel() { return tr("ui.all"); }, days: 99999, get periodLabel() { return tr("ui.all_time"); } },
];

// Solid colored circular icon (white glyph) — colors come from the theme tokens.
function CircleIcon({ icon, color, size = us(42) }: { icon: string; color: string; size?: number }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Ionicons name={icon as any} size={size * 0.5} color="#fff" />
    </View>
  );
}

// Period pill for Informes. Keeps the EXISTING Reports pill design/size/colors
// untouched; it ONLY adds the same press-spring micro-interaction used by the
// "Movimientos recientes" filters (compress to ~0.95 on press-in, soft spring
// back on release). Business logic (setRange) is unchanged.
function RangePill({
  testID,
  active,
  onPress,
  label,
  styles,
}: {
  testID: string;
  active: boolean;
  onPress: () => void;
  label: string;
  styles: any;
}) {
  const scale = useRef(new RNAnimated.Value(1)).current;
  const useNative = Platform.OS !== "web";
  const pressIn = () => {
    RNAnimated.spring(scale, { toValue: 0.95, useNativeDriver: useNative, speed: 50, bounciness: 0 }).start();
  };
  const pressOut = () => {
    RNAnimated.spring(scale, { toValue: 1, useNativeDriver: useNative, speed: 20, bounciness: 12 }).start();
  };
  return (
    <RNAnimated.View style={{ transform: [{ scale }], flexShrink: 0 }}>
      <Pressable
        testID={testID}
        onPress={onPress}
        onPressIn={pressIn}
        onPressOut={pressOut}
        style={[styles.pill, active ? styles.pillActive : styles.pillInactive]}
      >
        <Text style={[styles.pillText, active ? styles.pillTextActive : styles.pillTextInactive]}>{label}</Text>
      </Pressable>
    </RNAnimated.View>
  );
}

export default function Reports() {
  useInterfaceLanguage();
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  // Reuse Home's premium dark-green accent for section-header icons (light mode);
  // dark mode keeps the existing brand accent. No global token is modified.
  const isDark = scheme === "dark";
  const accent = isDark ? colors.brandPrimary : "#126046";
  const [range, setRange] = useState("30d");
  const [showAll, setShowAll] = useState(false);

  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });

  const rangeDef = RANGES.find((r) => r.id === range)!;
  const days = rangeDef.days;
  const now = Date.now();
  const cutoff = now - days * 86400000;
  const cats: any[] = catQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));

  const allTx: any[] = txQ.data || [];
  const isExpenseType = (t: any) => t.type === "expense" || t.type === "debt_payment";

  const filtered = allTx.filter((t: any) => new Date(t.date).getTime() >= cutoff);
  const totalIncome = filtered.filter((t: any) => t.type === "income").reduce((a: number, t: any) => a + t.amount, 0);
  const totalExpense = filtered.filter(isExpenseType).reduce((a: number, t: any) => a + t.amount, 0);
  const incomeCount = filtered.filter((t: any) => t.type === "income").length;
  const expenseCount = filtered.filter(isExpenseType).length;

  // Effective number of days covered by the current window (bounded for "Todo").
  let effDays = days;
  if (range === "all") {
    const times = filtered.map((t: any) => new Date(t.date).getTime());
    const earliest = times.length ? Math.min(...times) : now;
    effDays = Math.max(1, Math.round((now - earliest) / 86400000));
  }

  const balance = totalIncome - totalExpense;
  const incomeDaily = effDays > 0 ? totalIncome / effDays : 0;
  const expenseDaily = effDays > 0 ? totalExpense / effDays : 0;
  const incomeAvg = incomeCount ? totalIncome / incomeCount : 0;
  const expenseAvg = expenseCount ? totalExpense / expenseCount : 0;

  // Cash-flow table rows — real values only, never hardcoded.
  const cashRows = [
    { key: "count", icon: "list-outline", get label() { return tr("ui.count"); }, inc: String(incomeCount), exp: String(expenseCount) },
    { key: "daily", icon: "calendar-outline", get label() { return tr("ui.daily_average"); }, inc: formatCurrency(incomeDaily), exp: formatCurrency(expenseDaily) },
    { key: "perReg", icon: "document-text-outline", get label() { return tr("ui.average_per_transaction"); }, inc: formatCurrency(incomeAvg), exp: formatCurrency(expenseAvg) },
    { key: "total", icon: "calculator-outline", get label() { return tr("ui.period_total"); }, inc: formatCurrency(totalIncome), exp: formatCurrency(totalExpense) },
  ];

  // Expense-by-category (only expenses that have a category).
  const expenseCatTotal = filtered.filter((t: any) => t.type === "expense").reduce((a: number, t: any) => a + t.amount, 0);
  const byCategory = useMemo(() => {
    const map: Record<string, number> = {};
    filtered.forEach((t: any) => {
      if (t.type === "expense" && t.category_id) {
        map[t.category_id] = (map[t.category_id] || 0) + t.amount;
      }
    });
    return Object.entries(map)
      .map(([id, amt]) => ({ id, amount: amt, cat: catById[id] }))
      .filter((x) => x.cat)
      .sort((a, b) => b.amount - a.amount);
  }, [filtered, catById]);

  const maxCat = byCategory.length ? byCategory[0].amount : 0;
  const shownCats = showAll ? byCategory : byCategory.slice(0, 5);

  return (
    <ElasticScrollView
      style={{ flex: 1, backgroundColor: scheme === "dark" ? colors.surface : "#E8EFE7" }}
      contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(120) }}
    >
      <View style={styles.screenHead}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>{tr("ui.reports")}</Text>
          <Text style={styles.subtitle}>{tr("ui.explore_your_financial_activity")}</Text>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {RANGES.map((r) => {
          const active = range === r.id;
          return (
            <RangePill
              key={r.id}
              testID={`range-${r.id}`}
              active={active}
              onPress={() => setRange(r.id)}
              label={r.pillLabel}
              styles={styles}
            />
          );
        })}
      </ScrollView>

      {/* Flujo de efectivo — section header (outside the card, Home visual language) */}
      <View style={styles.sectionHeader}>
        <View style={styles.headIconTile}>
          <Ionicons name="bar-chart" size={us(18)} color={accent} />
        </View>
        <View style={{ flex: 1, marginLeft: us(10) }}>
          <View style={styles.titleRow}>
            <Text style={styles.headTitle}>{tr("ui.cash_flow")}</Text>
            <Ionicons name="information-circle-outline" size={us(15)} color={colors.muted} />
          </View>
          <Text style={styles.headSubtitle}>{tr("ui.your_activity_for_this_period")}</Text>
        </View>
      </View>
      <View style={styles.card}>
        {/* Cash-flow table */}
        <View style={styles.table}>
          <View style={[styles.tRow, styles.tHeaderRow]}>
            <View style={styles.tConcept}>
              <Text style={[styles.tHeaderText, { color: colors.muted }]}>{tr("ui.type")}</Text>
            </View>
            <View style={styles.tCol}>
              <Text style={[styles.tHeaderText, { color: colors.incomeGreen }]}>{tr("ui.income")}</Text>
            </View>
            <View style={styles.tCol}>
              <Text style={[styles.tHeaderText, { color: colors.expenseRed }]}>{tr("ui.expenses")}</Text>
            </View>
          </View>
          {cashRows.map((r, i) => (
            <View
              key={r.key}
              style={[styles.tRow, i < cashRows.length - 1 && styles.tRowDivider]}
              testID={`cash-row-${r.key}`}
            >
              <View style={styles.tConcept}>
                <Ionicons name={r.icon as any} size={us(15)} color={colors.muted} />
                <Text style={styles.tConceptText}>{r.label}</Text>
              </View>
              <View style={styles.tCol}>
                <Text style={[styles.tValue, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
                  {r.inc}
                </Text>
              </View>
              <View style={styles.tCol}>
                <Text style={[styles.tValue, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
                  {r.exp}
                </Text>
              </View>
            </View>
          ))}
        </View>

        {/* Saldo neto del período — full visual calculation */}
        <View style={styles.netPanel} testID="balance-row">
          <View style={[styles.netIcon, { backgroundColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "1F" }]}>
            <Ionicons name="wallet-outline" size={us(20)} color={balance >= 0 ? colors.incomeGreen : colors.expenseRed} />
          </View>
          <View style={styles.netTextWrap}>
            <Text style={styles.netTitle}>{tr("ui.net_balance_for_this_period")}</Text>
            <Text style={styles.netSub}>{tr("ui.income_minus_expenses")}</Text>
          </View>
          <View style={styles.netVDivider} />
          <View style={styles.netCalc}>
            <Text style={[styles.netInc, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.55}>
              {formatCurrency(totalIncome)}
            </Text>
            <Text style={styles.netOp}>−</Text>
            <Text style={[styles.netExp, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.55}>
              {formatCurrency(totalExpense)}
            </Text>
            <Text style={styles.netOp}>=</Text>
            <Text
              style={[styles.netResult, { color: balance >= 0 ? colors.incomeGreen : colors.expenseRed }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.55}
            >
              {balance < 0 ? "-" : ""}{formatCurrency(Math.abs(balance))}
            </Text>
          </View>
        </View>
      </View>

      {/* Gastos por categoría — section header (outside the card, Home visual language) */}
      <View style={styles.sectionHeader}>
        <View style={styles.headIconTile}>
          <Ionicons name="pie-chart" size={us(18)} color={accent} />
        </View>
        <View style={{ flex: 1, marginLeft: us(10) }}>
          <Text style={styles.headTitle}>{tr("ui.expenses_by_category")}</Text>
          <Text style={styles.headSubtitle}>{tr("ui.your_top_categories_for_this_period")}</Text>
        </View>
        {byCategory.length > 0 && (
          <Pressable onPress={() => setShowAll((v) => !v)} style={styles.topBadge} testID="toggle-cats">
            <Text style={styles.topBadgeText}>{showAll ? tr("ui.all") : tr("ui.top_5")}</Text>
            <Ionicons name={showAll ? "chevron-up" : "chevron-down"} size={us(14)} color={colors.muted} />
          </Pressable>
        )}
      </View>
      <View style={styles.card}>
        {byCategory.length > 0 ? (
          <View>
            {shownCats.map((x, i) => {
              const pctOfTotal = expenseCatTotal > 0 ? (x.amount / expenseCatTotal) * 100 : 0;
              const barPct = maxCat > 0 ? (x.amount / maxCat) * 100 : 0;
              return (
                <View
                  key={x.id}
                  style={[styles.catRow, i < shownCats.length - 1 && styles.catRowDivider]}
                  testID={`cat-row-${x.id}`}
                >
                  <CircleIcon icon={x.cat.icon} color={x.cat.color} size={us(42)} />
                  <View style={styles.catMiddle}>
                    <Text style={styles.catName}>{x.cat.name}</Text>
                    <View style={styles.barTrack}>
                      <View style={[styles.barFill, { width: `${Math.max(6, barPct)}%`, backgroundColor: x.cat.color }]} />
                    </View>
                  </View>
                  <View style={styles.catRight}>
                    <Text style={styles.catAmount}>{formatCurrency(x.amount)}</Text>
                    <Text style={styles.catPct}>{pctOfTotal.toFixed(1)}%</Text>
                  </View>
                </View>
              );
            })}
            {byCategory.length > 5 && (
              <Pressable onPress={() => setShowAll((v) => !v)} style={styles.verTodas} testID="ver-todas">
                <Text style={styles.verTodasText}>{showAll ? tr("ui.see_less") : tr("ui.view_all_categories")}</Text>
                <Ionicons name={showAll ? "chevron-up" : "chevron-forward"} size={us(18)} color={colors.onSurface} />
              </Pressable>
            )}
          </View>
        ) : (
          <Text style={styles.emptyText}>{tr("ui.no_data_for_this_period")}</Text>
        )}
      </View>
    </ElasticScrollView>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  const isDark = scheme === "dark";
  // Light-mode values reused/derived from the existing Home screen palette so
  // Reports visually matches Home. These are LOCAL to Reports — no global theme
  // token is modified, so no other screen is affected.
  const cardSurface = isDark ? colors.surfaceSecondary : "#FCFCF8"; // Home cardSurface
  const lineSoft = isDark ? colors.border : "rgba(39,71,56,0.10)"; // Home lineSoft
  const tileGreen = isDark ? colors.brandPrimary + "1A" : "#DCE9DD"; // Home soft mint icon tile
  const headTitleColor = isDark ? colors.onSurface : "#15251E"; // Home wallText
  const headSubColor = isDark ? colors.muted : "#68746D"; // Home wallMuted
  const barTrackColor = isDark ? "#3A352F" : "#E5E9E3"; // Home account-bar track
  return {
  screenHead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  subtitle: { fontSize: 13, color: colors.muted, marginTop: 1 },
  periodControl: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    maxWidth: 160,
    marginTop: 2,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: isDark ? colors.surfaceSecondary : "#DCE9DD",
    borderWidth: 1,
    borderColor: isDark ? colors.border : "#BAD7C2",
  },
  periodControlText: { fontSize: 11.5, fontWeight: "700", color: isDark ? colors.onSurface : "#126046", flexShrink: 1 },
  // --- Section header (outside the card) — mirrors Home's section headers ---
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: 8,
  },
  headIconTile: {
    width: 38, height: 38, borderRadius: 13,
    backgroundColor: tileGreen,
    alignItems: "center", justifyContent: "center",
  },
  headTitle: { fontSize: 18, fontWeight: "800", color: headTitleColor, letterSpacing: -0.4, flexShrink: 1 },
  headSubtitle: { fontSize: 11.5, color: headSubColor, marginTop: 1 },
  chipRow: { paddingHorizontal: spacing.lg, gap: 6, marginTop: 10, height: 32, alignItems: "center" },
  // Compact period pills (Reports-local, so no other screen is affected)
  pill: {
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    justifyContent: "center",
  },
  pillActive: {
    backgroundColor: isDark ? colors.brandPrimary : "#146448",
    borderColor: isDark ? colors.brandPrimary : "#146448",
  },
  pillInactive: {
    backgroundColor: isDark ? colors.surfaceSecondary : "#DCE9DD",
    borderColor: isDark ? colors.border : "#BAD7C2",
  },
  pillText: { fontSize: 11, fontWeight: "700" },
  pillTextActive: { color: isDark ? colors.onBrandPrimary : "#FFFFFF" },
  pillTextInactive: { color: isDark ? colors.onSurface : "#126046" },
  card: {
    marginHorizontal: spacing.lg,
    marginTop: 0,
    backgroundColor: cardSurface,
    borderRadius: radius.lg,
    padding: 13,
    borderWidth: 1,
    borderColor: lineSoft,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  // Card header with a soft coral icon tile
  cHead: { flexDirection: "row", alignItems: "center" },
  cHeadIcon: {
    width: 40, height: 40, borderRadius: 13,
    backgroundColor: colors.brandPrimary + "1A",
    alignItems: "center", justifyContent: "center",
  },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  cardTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  cardHeaderMeta: { fontSize: 11.5, color: colors.muted, fontWeight: "600", marginTop: 1 },

  // --- Cash-flow table (open, horizontal-divider style — no grid box) ---
  table: {
    marginTop: 10,
  },
  tRow: { flexDirection: "row", alignItems: "center", minHeight: 46 },
  tHeaderRow: {
    backgroundColor: isDark ? colors.surfaceTertiary : "#EEF2EC",
    borderRadius: 10,
    minHeight: 40,
  },
  tRowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  tConcept: {
    flex: 1.95,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingLeft: 8,
    paddingRight: 4,
    paddingVertical: 10,
  },
  tConceptText: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  tCol: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 2,
    paddingVertical: 10,
  },
  tHeaderText: { fontSize: 12.5, fontWeight: "800" },
  tValue: { fontSize: 14.5, fontWeight: "800", letterSpacing: -0.3 },

  // --- Saldo neto del período panel ---
  netPanel: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 14,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingVertical: 12,
    paddingHorizontal: 11,
    backgroundColor: isDark ? colors.surfaceTertiary : "#FCFCF8",
    borderColor: isDark ? colors.border : "rgba(39,71,56,0.12)",
  },
  netIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  netTextWrap: { marginLeft: 10, flex: 1, minWidth: 86 },
  netTitle: { fontSize: 12.5, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.3 },
  netSub: { fontSize: 10.5, color: colors.muted, marginTop: 2 },
  netVDivider: {
    width: 1,
    alignSelf: "stretch",
    marginVertical: 2,
    marginHorizontal: 8,
    backgroundColor: colors.divider,
  },
  netCalc: { flexDirection: "row", alignItems: "center", gap: 4, flexShrink: 1 },
  netInc: { fontSize: 14, fontWeight: "800", letterSpacing: -0.3, flexShrink: 1 },
  netExp: { fontSize: 14, fontWeight: "800", letterSpacing: -0.3, flexShrink: 1 },
  netOp: { fontSize: 13, fontWeight: "700", color: colors.muted },
  netResult: { fontSize: 17.5, fontWeight: "800", letterSpacing: -0.5, flexShrink: 1 },

  // Ingresos vs Gastos footer
  ivgFooter: { flexDirection: "row", justifyContent: "space-around", marginTop: 6 },
  ivgLabel: { color: colors.muted, fontSize: 11.5 },
  ivgValue: { fontSize: 16, fontWeight: "800", marginTop: 1 },

  // Resumen — metric grid
  metricsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
  metricCard: {
    flexDirection: "row",
    alignItems: "center",
    flexGrow: 1,
    flexBasis: "46%",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 9,
    paddingHorizontal: 10,
  },
  metricLabel: { fontSize: 11.5, color: colors.muted, fontWeight: "600" },
  metricValueRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 1 },
  metricValue: { fontSize: 15.5, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.3, flexShrink: 1 },
  compareInline: { flexDirection: "row", alignItems: "center", gap: 1 },
  comparePct: { fontSize: 11, fontWeight: "800" },
  metricPrev: { fontSize: 10, color: colors.muted, marginTop: 1 },

  // Balance del período — prominent but compact
  balanceRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 8,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: 10,
  },
  balanceIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  balanceLabel: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  balanceValue: { fontSize: 21, fontWeight: "800", letterSpacing: -0.5, marginTop: 1 },
  balanceBadge: { borderRadius: radius.sm, paddingHorizontal: 9, paddingVertical: 6, alignItems: "center", maxWidth: 120 },
  balanceBadgeTop: { flexDirection: "row", alignItems: "center", gap: 3 },
  balanceBadgePct: { fontSize: 12.5, fontWeight: "800" },
  balanceBadgeMeta: { fontSize: 9.5, color: colors.muted, marginTop: 1, textAlign: "center" },
  balancePrevNeutral: { fontSize: 10.5, color: colors.muted, textAlign: "right", fontWeight: "600" },

  // Gastos por categoría
  topBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: cardSurface,
    borderWidth: 1,
    borderColor: lineSoft,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  topBadgeText: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  catRow: { flexDirection: "row", alignItems: "center", paddingVertical: 9 },
  catRowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  catMiddle: { flex: 1, marginLeft: 12, marginRight: 10 },
  catName: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  barTrack: {
    height: 10,
    borderRadius: 5,
    backgroundColor: barTrackColor,
    marginTop: 7,
    overflow: "hidden",
  },
  barFill: { height: 10, borderRadius: 5 },
  catRight: { alignItems: "flex-end", minWidth: 70 },
  catAmount: { fontSize: 14, fontWeight: "800", color: colors.onSurface },
  catPct: { fontSize: 11.5, color: colors.muted, fontWeight: "600", marginTop: 2 },
  verTodas: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    marginTop: 10,
    paddingVertical: 11,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: lineSoft,
    backgroundColor: cardSurface,
  },
  verTodasText: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface },
  emptyText: { color: colors.muted, textAlign: "center", padding: 16 },
  };
});
