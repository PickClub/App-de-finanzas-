import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { Chip } from "@/src/components/ui";

const RANGES = [
  { id: "7d", label: "7d", pillLabel: "7 días", days: 7, periodLabel: "Últimos 7 días" },
  { id: "30d", label: "30d", pillLabel: "30 días", days: 30, periodLabel: "Últimos 30 días" },
  { id: "3m", label: "3m", pillLabel: "3 meses", days: 90, periodLabel: "Últimos 3 meses" },
  { id: "6m", label: "6m", pillLabel: "6 meses", days: 180, periodLabel: "Últimos 6 meses" },
  { id: "1y", label: "1a", pillLabel: "1 año", days: 365, periodLabel: "Último año" },
  { id: "all", label: "Todo", pillLabel: "Todo", days: 99999, periodLabel: "Histórico" },
];

// Solid colored circular icon (white glyph) — colors come from the theme tokens.
function CircleIcon({ icon, color, size = 42 }: { icon: string; color: string; size?: number }) {
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

export default function Reports() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
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
    { key: "count", icon: "list-outline", label: "Cantidad", inc: String(incomeCount), exp: String(expenseCount) },
    { key: "daily", icon: "calendar-outline", label: "Promedio diario", inc: formatCurrency(incomeDaily), exp: formatCurrency(expenseDaily) },
    { key: "perReg", icon: "document-text-outline", label: "Promedio por registro", inc: formatCurrency(incomeAvg), exp: formatCurrency(expenseAvg) },
    { key: "total", icon: "calculator-outline", label: "Total del período", inc: formatCurrency(totalIncome), exp: formatCurrency(totalExpense) },
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
    <ScrollView
      style={{ flex: 1, backgroundColor: scheme === "dark" ? colors.surface : "#F3E8DC" }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120 }}
    >
      <View style={styles.screenHead}>
        <View style={{ flex: 1, paddingRight: 10 }}>
          <Text style={styles.title}>Informes</Text>
          <Text style={styles.subtitle}>Analiza tu actividad financiera</Text>
        </View>
        <View style={styles.periodControl} testID="period-control">
          <Text style={styles.periodControlText} numberOfLines={1}>{rangeDef.periodLabel}</Text>
          <Ionicons name="chevron-down" size={15} color={colors.muted} />
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {RANGES.map((r) => (
          <Chip key={r.id} label={r.pillLabel} active={range === r.id} onPress={() => setRange(r.id)} testID={`range-${r.id}`} />
        ))}
      </ScrollView>

      {/* Flujo de efectivo */}
      <View style={styles.card}>
        <View style={styles.cHead}>
          <View style={styles.cHeadIcon}>
            <Ionicons name="bar-chart" size={18} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <View style={styles.titleRow}>
              <Text style={styles.cardTitle}>Flujo de efectivo</Text>
              <Ionicons name="information-circle-outline" size={15} color={colors.muted} />
            </View>
            <Text style={styles.cardHeaderMeta}>Resumen de tu actividad en el período</Text>
          </View>
        </View>

        {/* Cash-flow table */}
        <View style={styles.table}>
          <View style={[styles.tRow, styles.tHeaderRow]}>
            <View style={styles.tConcept}>
              <Text style={[styles.tHeaderText, { color: colors.muted }]}>Concepto</Text>
            </View>
            <View style={styles.tCol}>
              <Text style={[styles.tHeaderText, { color: colors.incomeGreen }]}>Ingresos</Text>
            </View>
            <View style={styles.tCol}>
              <Text style={[styles.tHeaderText, { color: colors.expenseRed }]}>Gastos</Text>
            </View>
          </View>
          {cashRows.map((r, i) => (
            <View
              key={r.key}
              style={[styles.tRow, i < cashRows.length - 1 && styles.tRowDivider]}
              testID={`cash-row-${r.key}`}
            >
              <View style={styles.tConcept}>
                <Ionicons name={r.icon as any} size={15} color={colors.muted} />
                <Text style={styles.tConceptText} numberOfLines={1}>{r.label}</Text>
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
        <View
          style={[
            styles.netPanel,
            {
              backgroundColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "12",
              borderColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "2E",
            },
          ]}
          testID="balance-row"
        >
          <View style={[styles.netIcon, { backgroundColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "1F" }]}>
            <Ionicons name="wallet-outline" size={20} color={balance >= 0 ? colors.incomeGreen : colors.expenseRed} />
          </View>
          <View style={styles.netTextWrap}>
            <Text style={styles.netTitle} numberOfLines={1}>Saldo neto del período</Text>
            <Text style={styles.netSub} numberOfLines={1}>Ingresos menos gastos</Text>
          </View>
          <View style={styles.netCalc}>
            <Text style={[styles.netInc, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
              {formatCurrency(totalIncome)}
            </Text>
            <Text style={styles.netOp}>−</Text>
            <Text style={[styles.netExp, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
              {formatCurrency(totalExpense)}
            </Text>
            <Text style={styles.netOp}>=</Text>
            <Text
              style={[styles.netResult, { color: balance >= 0 ? colors.incomeGreen : colors.expenseRed }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              {balance < 0 ? "-" : ""}{formatCurrency(Math.abs(balance))}
            </Text>
          </View>
        </View>
      </View>

      {/* Gastos por categoría */}
      <View style={styles.card}>
        <View style={styles.cHead}>
          <View style={styles.cHeadIcon}>
            <Ionicons name="pie-chart" size={18} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={styles.cardTitle}>Gastos por categoría</Text>
            <Text style={styles.cardHeaderMeta}>Tus principales categorías en este período</Text>
          </View>
          {byCategory.length > 0 && (
            <Pressable onPress={() => setShowAll((v) => !v)} style={styles.topBadge} testID="toggle-cats">
              <Text style={styles.topBadgeText}>{showAll ? "Todas" : "Top 5"}</Text>
              <Ionicons name={showAll ? "chevron-up" : "chevron-down"} size={14} color={colors.muted} />
            </Pressable>
          )}
        </View>

        {byCategory.length > 0 ? (
          <View style={{ marginTop: 12 }}>
            {shownCats.map((x, i) => {
              const pctOfTotal = expenseCatTotal > 0 ? (x.amount / expenseCatTotal) * 100 : 0;
              const barPct = maxCat > 0 ? (x.amount / maxCat) * 100 : 0;
              return (
                <View
                  key={x.id}
                  style={[styles.catRow, i < shownCats.length - 1 && styles.catRowDivider]}
                  testID={`cat-row-${x.id}`}
                >
                  <CircleIcon icon={x.cat.icon} color={x.cat.color} size={42} />
                  <View style={styles.catMiddle}>
                    <Text style={styles.catName} numberOfLines={1}>{x.cat.name}</Text>
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
                <Text style={styles.verTodasText}>{showAll ? "Ver menos" : "Ver todas las categorías"}</Text>
                <Ionicons name={showAll ? "chevron-up" : "chevron-forward"} size={18} color={colors.onSurface} />
              </Pressable>
            )}
          </View>
        ) : (
          <Text style={styles.emptyText}>Sin datos para este período</Text>
        )}
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
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
    gap: 6,
    maxWidth: 160,
    marginTop: 2,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: scheme === "dark" ? colors.surfaceSecondary : "#F1EEE9",
    borderWidth: 1,
    borderColor: colors.border,
  },
  periodControlText: { fontSize: 12.5, fontWeight: "700", color: colors.onSurface, flexShrink: 1 },
  chipRow: { paddingHorizontal: spacing.lg, gap: 8, marginTop: 10, height: 46, alignItems: "center" },
  card: {
    marginHorizontal: spacing.lg,
    marginTop: 10,
    backgroundColor: scheme === "dark" ? colors.surfaceSecondary : "#F1EEE9",
    borderRadius: radius.lg,
    padding: 13,
    borderWidth: 1,
    borderColor: scheme === "dark" ? colors.border : "#E4DCD2",
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

  // --- Cash-flow table ---
  table: {
    marginTop: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: scheme === "dark" ? colors.border : "#E4DCD2",
    overflow: "hidden",
  },
  tRow: { flexDirection: "row", alignItems: "stretch", minHeight: 44 },
  tHeaderRow: { backgroundColor: scheme === "dark" ? colors.surfaceTertiary : "#ECE5DB" },
  tRowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  tConcept: {
    flex: 1.5,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 11,
  },
  tConceptText: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface, flexShrink: 1 },
  tCol: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 6,
    paddingVertical: 11,
    borderLeftWidth: 1,
    borderLeftColor: colors.divider,
  },
  tHeaderText: { fontSize: 13, fontWeight: "800" },
  tValue: { fontSize: 14.5, fontWeight: "800", letterSpacing: -0.3 },

  // --- Saldo neto del período panel ---
  netPanel: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: 11,
  },
  netIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  netTextWrap: { marginLeft: 10, flexShrink: 1 },
  netTitle: { fontSize: 13, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.2 },
  netSub: { fontSize: 10.5, color: colors.muted, marginTop: 1 },
  netCalc: { flexDirection: "row", alignItems: "center", gap: 5, marginLeft: "auto", flexShrink: 1 },
  netInc: { fontSize: 15, fontWeight: "800", letterSpacing: -0.3 },
  netExp: { fontSize: 15, fontWeight: "800", letterSpacing: -0.3 },
  netOp: { fontSize: 14, fontWeight: "700", color: colors.muted },
  netResult: { fontSize: 20, fontWeight: "800", letterSpacing: -0.5 },

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
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
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
    backgroundColor: scheme === "dark" ? "#3A352F" : "#DED6CB",
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
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  verTodasText: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface },
  emptyText: { color: colors.muted, textAlign: "center", padding: 16 },
}));
