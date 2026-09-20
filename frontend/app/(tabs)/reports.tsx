import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { BarChart } from "react-native-gifted-charts";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { Chip } from "@/src/components/ui";
import { premiumizeColor } from "@/src/color";

const RANGES = [
  { id: "7d", label: "7d", days: 7, periodLabel: "Últimos 7 días" },
  { id: "30d", label: "30d", days: 30, periodLabel: "Últimos 30 días" },
  { id: "3m", label: "3m", days: 90, periodLabel: "Últimos 3 meses" },
  { id: "6m", label: "6m", days: 180, periodLabel: "Últimos 6 meses" },
  { id: "1y", label: "1a", days: 365, periodLabel: "Último año" },
  { id: "all", label: "Todo", days: 99999, periodLabel: "Histórico" },
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

  // Immediately previous equivalent period (only for fixed ranges).
  const prevCutoff = cutoff - days * 86400000;
  const prevFiltered = range === "all"
    ? []
    : allTx.filter((t: any) => {
        const d = new Date(t.date).getTime();
        return d >= prevCutoff && d < cutoff;
      });
  const prevIncome = prevFiltered.filter((t: any) => t.type === "income").reduce((a: number, t: any) => a + t.amount, 0);
  const prevExpense = prevFiltered.filter(isExpenseType).reduce((a: number, t: any) => a + t.amount, 0);
  const prevIncomeCount = prevFiltered.filter((t: any) => t.type === "income").length;
  const prevExpenseCount = prevFiltered.filter(isExpenseType).length;
  const hasPrev = range !== "all" && prevFiltered.length > 0;

  // Percentage change vs previous period; null => neutral (not enough history).
  const pctChange = (cur: number, prev: number): number | null => {
    if (!hasPrev || !prev) return null;
    return ((cur - prev) / Math.abs(prev)) * 100;
  };

  const balance = totalIncome - totalExpense;
  const prevBalance = prevIncome - prevExpense;
  const dailyAvg = totalIncome + totalExpense > 0 ? (totalIncome + totalExpense) / effDays : 0;
  const prevDailyAvg = (prevIncome + prevExpense) / days;
  const incomeAvg = incomeCount ? totalIncome / incomeCount : 0;
  const prevIncomeAvg = prevIncomeCount ? prevIncome / prevIncomeCount : 0;
  const expenseAvg = expenseCount ? totalExpense / expenseCount : 0;
  const prevExpenseAvg = prevExpenseCount ? prevExpense / prevExpenseCount : 0;

  const metrics = [
    { key: "count", icon: "list", color: colors.statsPurple, label: "Movimientos", value: String(filtered.length), pct: pctChange(filtered.length, prevFiltered.length), goodWhenUp: true },
    { key: "daily", icon: "calendar-outline", color: colors.loansYellow, label: "Promedio diario", value: formatCurrency(dailyAvg), pct: pctChange(dailyAvg, prevDailyAvg), goodWhenUp: true },
    { key: "incomeAvg", icon: "arrow-up", color: colors.incomeGreen, label: "Ingreso promedio", value: formatCurrency(incomeAvg), pct: pctChange(incomeAvg, prevIncomeAvg), goodWhenUp: true },
    { key: "expenseAvg", icon: "arrow-down", color: colors.expenseRed, label: "Gasto promedio", value: formatCurrency(expenseAvg), pct: pctChange(expenseAvg, prevExpenseAvg), goodWhenUp: false },
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

  const barData = [
    { value: totalIncome, label: "Ingresos", frontColor: colors.incomeGreen, topLabelComponent: () => null },
    { value: totalExpense, label: "Gastos", frontColor: colors.expenseRed, topLabelComponent: () => null },
  ];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120 }}
    >
      <Text style={styles.title}>Informes</Text>
      <Text style={styles.subtitle}>Analiza tus finanzas y toma mejores decisiones</Text>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {RANGES.map((r) => (
          <Chip key={r.id} label={r.label} active={range === r.id} onPress={() => setRange(r.id)} testID={`range-${r.id}`} />
        ))}
      </ScrollView>

      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>Ingresos vs Gastos</Text>
          <Text style={styles.cardHeaderMeta}>{rangeDef.periodLabel}</Text>
        </View>
        <View style={{ alignItems: "center", marginTop: 12 }}>
          <BarChart
            data={barData}
            barWidth={44}
            spacing={28}
            hideRules
            xAxisColor={colors.border}
            yAxisColor={colors.border}
            yAxisTextStyle={{ color: colors.muted, fontSize: 10 }}
            xAxisLabelTextStyle={{ color: colors.onSurface, fontSize: 12 }}
            noOfSections={4}
            height={128}
          />
        </View>
        <View style={styles.ivgFooter}>
          <View style={{ alignItems: "center" }}>
            <Text style={styles.ivgLabel}>Ingresos</Text>
            <Text style={[styles.ivgValue, { color: colors.incomeGreen }]}>{formatCurrency(totalIncome)}</Text>
          </View>
          <View style={{ alignItems: "center" }}>
            <Text style={styles.ivgLabel}>Gastos</Text>
            <Text style={[styles.ivgValue, { color: colors.expenseRed }]}>{formatCurrency(totalExpense)}</Text>
          </View>
        </View>
      </View>

      {/* Resumen del período */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={styles.titleRow}>
            <Text style={styles.cardTitle}>Resumen del período</Text>
            <Ionicons name="information-circle-outline" size={16} color={colors.muted} />
          </View>
          <Text style={styles.cardHeaderMeta}>{rangeDef.periodLabel}</Text>
        </View>

        <View style={styles.metricsGrid}>
          {metrics.map((m) => {
            const up = (m.pct ?? 0) >= 0;
            const good = m.goodWhenUp ? up : !up;
            const cc = good ? colors.incomeGreen : colors.expenseRed;
            return (
              <View key={m.key} style={styles.metricCard} testID={`metric-${m.key}`}>
                <CircleIcon icon={m.icon} color={m.color} size={34} />
                <View style={{ flex: 1, marginLeft: 9 }}>
                  <Text style={styles.metricLabel} numberOfLines={1}>{m.label}</Text>
                  <View style={styles.metricValueRow}>
                    <Text style={styles.metricValue} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.75}>{m.value}</Text>
                    {m.pct !== null && (
                      <View style={styles.compareInline}>
                        <Ionicons name={up ? "arrow-up" : "arrow-down"} size={10} color={cc} />
                        <Text style={[styles.comparePct, { color: cc }]}>
                          {up ? "+" : ""}{Math.round(m.pct)}%
                        </Text>
                      </View>
                    )}
                  </View>
                  <Text style={styles.metricPrev}>
                    {m.pct !== null ? "vs. período anterior" : "Sin datos previos"}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        {/* Balance del período — prominent */}
        <View
          style={[
            styles.balanceRow,
            {
              backgroundColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "12",
              borderColor: (balance >= 0 ? colors.incomeGreen : colors.expenseRed) + "33",
            },
          ]}
          testID="balance-row"
        >
          <View style={[styles.balanceIcon, { backgroundColor: colors.brandPrimary + "1F" }]}>
            <Ionicons name="scale-outline" size={20} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={styles.balanceLabel}>Balance del período</Text>
            <Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7} style={[styles.balanceValue, { color: balance >= 0 ? colors.incomeGreen : colors.expenseRed }]}>
              {balance < 0 ? "-" : ""}{formatCurrency(Math.abs(balance))}
            </Text>
          </View>
          {(() => {
            const p = pctChange(balance, prevBalance);
            if (p === null) return <Text style={styles.balancePrevNeutral}>Sin datos{"\n"}previos</Text>;
            const good = p >= 0;
            const c = good ? colors.incomeGreen : colors.expenseRed;
            return (
              <View style={[styles.balanceBadge, { backgroundColor: c + "14" }]}>
                <View style={styles.balanceBadgeTop}>
                  <Ionicons name={good ? "arrow-up" : "arrow-down"} size={11} color={c} />
                  <Text style={[styles.balanceBadgePct, { color: c }]}>{good ? "+" : ""}{Math.round(p)}%</Text>
                </View>
                <Text style={styles.balanceBadgeMeta}>vs. período anterior</Text>
              </View>
            );
          })()}
        </View>
      </View>

      {/* Gastos por categoría */}
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>Gastos por categoría</Text>
          {byCategory.length > 0 && (
            <Pressable onPress={() => setShowAll((v) => !v)} style={styles.topBadge} testID="toggle-cats">
              <Text style={styles.topBadgeText}>{showAll ? "Todas" : "Top 5"}</Text>
              <Ionicons name={showAll ? "chevron-up" : "chevron-down"} size={14} color={colors.muted} />
            </Pressable>
          )}
        </View>

        {byCategory.length > 0 ? (
          <View style={{ marginTop: 14 }}>
            {shownCats.map((x) => {
              const pctOfTotal = expenseCatTotal > 0 ? (x.amount / expenseCatTotal) * 100 : 0;
              const barPct = maxCat > 0 ? (x.amount / maxCat) * 100 : 0;
              return (
                <View key={x.id} style={styles.catRow} testID={`cat-row-${x.id}`}>
                  <CircleIcon icon={x.cat.icon} color={premiumizeColor(x.cat.color, scheme)} size={36} />
                  <View style={styles.catMiddle}>
                    <Text style={styles.catName} numberOfLines={1}>{x.cat.name}</Text>
                    <View style={styles.barTrack}>
                      <View style={[styles.barFill, { width: `${barPct}%`, backgroundColor: premiumizeColor(x.cat.color, scheme) }]} />
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

const useStyles = makeStyles((colors) => ({
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface, paddingHorizontal: spacing.lg },
  subtitle: { fontSize: 13, color: colors.muted, paddingHorizontal: spacing.lg, marginTop: 1 },
  chipRow: { paddingHorizontal: spacing.lg, gap: 8, marginTop: 10, height: 46, alignItems: "center" },
  card: {
    marginHorizontal: spacing.lg,
    marginTop: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: 13,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  cardTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  cardHeaderMeta: { fontSize: 11.5, color: colors.muted, fontWeight: "600" },

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
  catRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6 },
  catMiddle: { flex: 1, marginLeft: 10, marginRight: 10 },
  catName: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  barTrack: { height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, marginTop: 5, overflow: "hidden" },
  barFill: { height: 6, borderRadius: 3 },
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
