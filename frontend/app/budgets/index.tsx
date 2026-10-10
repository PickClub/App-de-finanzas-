import React, { useCallback, useMemo, useState } from "react";
import { View, ScrollView, ActivityIndicator, RefreshControl } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt } from "@/src/format";
import { ProgressBar } from "@/src/components/ProgressBar";
import { ProgressRing } from "@/src/components/ProgressRing";
import { AppSheet } from "@/src/components/sheets";
import {
  FOREST, useMontserrat, monthName, statusColor, budgetLabel, pastel,
  sortBudgets, SORT_KEYS, SORT_LABEL, type SortKey,
} from "@/src/budgets/shared";

import { us } from "@/src/ui-scale";

export default function Budgets() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const forest = isDark ? colors.incomeGreen : FOREST;

  const today = new Date();
  const [ym, setYm] = useState({ y: today.getFullYear(), m: today.getMonth() + 1 });
  const [pickerYear, setPickerYear] = useState(ym.y);
  const [monthOpen, setMonthOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("recent");

  const overviewQ = useQuery({
    queryKey: ["budgets-overview", ym.y, ym.m],
    queryFn: () => api.budgetsOverview(ym.y, ym.m),
  });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const { refetch } = overviewQ;

  // Always recompute on focus so movements added/edited/deleted elsewhere are reflected.
  useFocusEffect(useCallback(() => { refetch(); }, [refetch]));

  const catById = useMemo(
    () => Object.fromEntries((catsQ.data || []).map((c: any) => [c.id, c])),
    [catsQ.data],
  );
  const labelOf = useCallback((b: any) => budgetLabel(b, catById[b.category_id], i18n.language), [catById, i18n.language]);

  const data = overviewQ.data;
  const all: any[] = data?.budgets || [];
  const active = sortBudgets(all.filter((b) => b.active), sortKey, labelOf);
  const inactive = sortBudgets(all.filter((b) => !b.active), sortKey, labelOf);
  const totals = data?.totals;
  const pct: number | null = totals?.pct ?? null;
  const pctInt = pct === null ? null : Math.round(pct);
  const overall = pct === null ? "normal" : pct > 100 ? "exceeded" : pct >= 100 ? "reached" : "normal";
  const ringColor = overall === "normal" ? colors.incomeGreen : colors.expenseRed;
  const monthLbl = monthName(ym.y, ym.m, i18n.language);
  const alertsSub = !data?.alerts_count ? t("budgets.allGood") : data.exceeded_count ? t("budgets.overLimit") : t("budgets.nearLimit");

  const openMonth = () => { setPickerYear(ym.y); setMonthOpen(true); };

  const renderCard = (b: any, dim = false) => {
    const cat = catById[b.category_id];
    const base = cat?.color || colors.brandPrimary;
    const barColor = statusColor(b.status, base, colors);
    const over = b.available < 0;
    return (
      <Pressable
        key={b.id}
        testID={`budget-card-${b.id}`}
        onPress={() => router.push(`/budgets/${b.id}?y=${ym.y}&m=${ym.m}` as any)}
        style={({ pressed }) => [styles.budgetCard, dim && { opacity: 0.6 }, pressed && styles.pressed]}
      >
        <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
        <View style={[styles.catIcon, { backgroundColor: base + "29" }]}>
          <Ionicons name={(cat?.icon || "pie-chart-outline") as any} size={us(22)} color={base} />
        </View>
        <View style={{ flex: 1, marginLeft: us(12) }}>
          <View style={styles.rowBetween}>
            <Text style={[styles.cardTitle, mont()]} numberOfLines={1}>{labelOf(b)}</Text>
            <Text style={styles.cardAmount} numberOfLines={1}>
              <Text style={[styles.cardAmountStrong, over && { color: colors.expenseRed }]}>{formatCurrencyInt(b.spent)}</Text>
              {" / "}{formatCurrencyInt(b.amount_limit)}
            </Text>
          </View>
          <View style={{ marginVertical: us(7) }}>
            <ProgressBar progress={b.amount_limit > 0 ? b.spent / b.amount_limit : 0} color={barColor} height={us(8)} trackColor={base + "1F"} />
          </View>
          <View style={styles.rowBetween}>
            <Text style={[styles.cardSmall, b.status !== "normal" && { color: barColor, fontWeight: "700" }]}>
              {dim ? t("budgets.inactive") : t("budgets.pctUsed", { pct: Math.round(b.pct ?? 0) })}
            </Text>
            <Text style={[styles.cardSmall, over && { color: colors.expenseRed, fontWeight: "700" }]}>
              {over
                ? t("budgets.exceededN", { amount: formatCurrencyInt(-b.available) })
                : t("budgets.availableN", { amount: formatCurrencyInt(b.available) })}
            </Text>
          </View>
        </View>
        <Ionicons name="chevron-forward" size={us(18)} color={colors.muted} style={{ marginLeft: us(8) }} />
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}
        refreshControl={<RefreshControl refreshing={overviewQ.isRefetching} onRefresh={refetch} tintColor={colors.incomeGreen} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Header (unchanged) */}
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>{t("budgets.title")}</Text>
          <Pressable testID="add-budget" onPress={() => router.push("/budgets/new" as any)} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={us(22)} color="#fff" />
          </Pressable>
        </View>

        {overviewQ.isLoading ? (
          <View style={styles.center}><ActivityIndicator color={colors.incomeGreen} /></View>
        ) : overviewQ.isError ? (
          <View style={styles.center}>
            <Ionicons name="cloud-offline-outline" size={us(30)} color={colors.muted} />
            <Text style={styles.muted}>{t("budgets.loadError")}</Text>
            <Pressable testID="budgets-retry" onPress={() => refetch()} style={styles.retryBtn}>
              <Text style={[styles.retryText, { color: forest }]}>{t("budgets.retry")}</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {/* Monthly summary */}
            <View style={styles.summary} testID="budget-summary">
              <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={styles.rowBetween}>
                <View style={{ flex: 1, paddingRight: us(8) }}>
                  <Text style={[styles.summaryTitle, mont()]} numberOfLines={1}>{t("budgets.summaryOf", { month: i18n.language === "en" ? monthLbl : monthLbl.toLowerCase() })}</Text>
                  <Text style={styles.summarySub} numberOfLines={2}>{t("budgets.summarySub")}</Text>
                </View>
                <Pressable testID="budget-month-picker" onPress={openMonth} style={({ pressed }) => [styles.monthPill, pressed && styles.pressed]}>
                  <Ionicons name="calendar-outline" size={us(15)} color={forest} />
                  <Text style={styles.monthPillText}>{monthLbl} {ym.y}</Text>
                  <Ionicons name="chevron-down" size={us(14)} color={colors.onSurface} />
                </Pressable>
              </View>

              <View style={styles.summaryBody}>
                <ProgressRing size={us(100)} stroke={us(11)} progress={pct === null ? 0 : Math.min(1, pct / 100)} color={ringColor} trackColor={colors.incomeGreen + "24"}>
                  <Text style={[styles.ringPct, mont(true)]} testID="budget-pct">{pctInt === null ? "—" : `${pctInt}%`}</Text>
                  <Text style={styles.ringSub}>{pctInt === null ? t("budgets.noData") : t("budgets.used")}</Text>
                </ProgressRing>
                <View style={styles.vDivider} />
                <View style={{ flex: 1 }}>
                  <View style={styles.statRow}>
                    <View style={[styles.dot, { backgroundColor: colors.brandPrimary }]} />
                    <Text style={styles.statLbl}>{t("budgets.spentLbl")}</Text>
                    <Text style={styles.statVal} numberOfLines={1} testID="budget-total-spent">
                      <Text style={[styles.statStrong, { color: colors.expenseRed }]}>{formatCurrencyInt(totals?.spent || 0)}</Text>
                      <Text style={styles.statOf}> {t("budgets.of")} {formatCurrencyInt(totals?.budgeted || 0)}</Text>
                    </Text>
                  </View>
                  <View style={styles.statRow}>
                    <View style={[styles.dot, { backgroundColor: colors.incomeGreen }]} />
                    <Text style={styles.statLbl}>{(totals?.available ?? 0) < 0 ? t("budgets.exceededLbl") : t("budgets.availableLbl")}</Text>
                    <Text style={[styles.statStrong, { color: (totals?.available ?? 0) < 0 ? colors.expenseRed : forest }]} testID="budget-total-available">
                      {formatCurrencyInt(Math.abs(totals?.available || 0))}
                    </Text>
                  </View>
                  <View style={{ marginTop: us(10), marginBottom: us(8) }}>
                    <ProgressBar progress={pct === null ? 0 : pct / 100} color={ringColor} height={us(9)} trackColor={colors.incomeGreen + "22"} />
                  </View>
                  <Text style={styles.summaryFoot}>
                    {pctInt === null ? t("budgets.noBudgetLine") : t("budgets.usedLine", { pct: pctInt })}
                  </Text>
                </View>
              </View>
            </View>

            {/* Indicators */}
            <View style={styles.indRow}>
              <View style={styles.indCard} testID="budget-active-card">
                <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: colors.incomeGreen + "29" }]}>
                  <Ionicons name="wallet" size={us(22)} color={forest} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={styles.indTitle}>{t("budgets.budgetsCard")}</Text>
                  <Text style={[styles.indCount, mont(true), { color: forest }]} testID="budget-active-count">{data?.active_count ?? 0}</Text>
                  <Text style={styles.indSub} numberOfLines={1}>{t("budgets.activeThisMonth")}</Text>
                </View>
              </View>
              <View style={styles.indCard} testID="budget-alerts-card">
                <LinearGradient colors={pastel(colors.expenseRed, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: colors.expenseRed + "24" }]}>
                  <Ionicons name="warning" size={us(22)} color={colors.expenseRed} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={[styles.indTitle, { color: colors.expenseRed }]}>{t("budgets.alerts")}</Text>
                  <Text style={[styles.indCount, mont(true), { color: colors.expenseRed }]} testID="budget-alerts-count">{data?.alerts_count ?? 0}</Text>
                  <Text style={styles.indSub} numberOfLines={1}>{alertsSub}</Text>
                </View>
              </View>
            </View>

            {/* Your budgets */}
            {all.length === 0 ? (
              <View style={styles.empty} testID="budgets-empty">
                <View style={[styles.emptyIcon, { backgroundColor: colors.incomeGreen + "22" }]}>
                  <Ionicons name="pie-chart" size={us(30)} color={forest} />
                </View>
                <Text style={[styles.emptyTitle, mont()]}>{t("budgets.emptyTitle")}</Text>
                <Text style={styles.emptySub}>{t("budgets.emptySub")}</Text>
                <Pressable testID="budgets-empty-create" onPress={() => router.push("/budgets/new" as any)} style={({ pressed }) => [styles.emptyBtn, pressed && styles.pressed]}>
                  <Ionicons name="add" size={us(18)} color="#fff" />
                  <Text style={styles.emptyBtnText}>{t("budgets.create")}</Text>
                </Pressable>
              </View>
            ) : (
              <>
                <View style={[styles.rowBetween, { marginTop: us(22), marginBottom: us(12) }]}>
                  <Text style={[styles.sectionTitle, mont()]}>{t("budgets.yours")}</Text>
                  <Pressable testID="budget-sort" onPress={() => setSortOpen(true)} style={styles.sortBtn} hitSlop={8}>
                    <Text style={styles.sortText} numberOfLines={1}>{t("budgets.sortLabel")}: {t(SORT_LABEL[sortKey])}</Text>
                    <Ionicons name="chevron-down" size={us(14)} color={colors.muted} />
                  </Pressable>
                </View>
                {active.length === 0 && <Text style={[styles.muted, { marginBottom: us(10) }]}>{t("budgets.noneActive")}</Text>}
                {active.map((b) => renderCard(b))}
                {inactive.map((b) => renderCard(b, true))}
              </>
            )}
          </>
        )}
      </ScrollView>

      {/* Month / year picker */}
      <AppSheet visible={monthOpen} onClose={() => setMonthOpen(false)} testID="budget-month-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("budgets.selectMonth")}</Text>
        <View style={[styles.rowBetween, { marginVertical: us(12) }]}>
          <Pressable testID="budget-year-prev" onPress={() => setPickerYear((y) => y - 1)} style={styles.yearBtn}>
            <Ionicons name="chevron-back" size={us(18)} color={colors.onSurface} />
          </Pressable>
          <Text style={[styles.yearText, mont()]}>{pickerYear}</Text>
          <Pressable testID="budget-year-next" onPress={() => setPickerYear((y) => y + 1)} style={styles.yearBtn}>
            <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} />
          </Pressable>
        </View>
        <View style={styles.monthGrid}>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
            const sel = m === ym.m && pickerYear === ym.y;
            return (
              <Pressable
                key={m}
                testID={`budget-month-${m}`}
                onPress={() => { setYm({ y: pickerYear, m }); setMonthOpen(false); }}
                style={[styles.monthCell, sel && { backgroundColor: forest, borderColor: forest }]}
              >
                <Text style={[styles.monthCellText, sel && { color: "#fff" }]}>{monthName(pickerYear, m, i18n.language).slice(0, 3)}</Text>
              </Pressable>
            );
          })}
        </View>
      </AppSheet>

      {/* Sort */}
      <AppSheet visible={sortOpen} onClose={() => setSortOpen(false)} testID="budget-sort-sheet">
        <Text style={[styles.sheetTitle, mont(), { marginBottom: us(8) }]}>{t("budgets.sortLabel")}</Text>
        {SORT_KEYS.map((k) => (
          <Pressable key={k} testID={`budget-sort-${k}`} onPress={() => { setSortKey(k); setSortOpen(false); }} style={styles.sortRow}>
            <Text style={[styles.sortRowText, k === sortKey && { color: forest, fontWeight: "800" }]}>{t(SORT_LABEL[k])}</Text>
            {k === sortKey && <Ionicons name="checkmark" size={us(18)} color={forest} />}
          </Pressable>
        ))}
      </AppSheet>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  pressed: { opacity: 0.7 },
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  center: { alignItems: "center", justifyContent: "center", paddingVertical: 60, gap: 10 },
  muted: { color: colors.muted, fontSize: 13, textAlign: "center" },
  retryBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  retryText: { fontWeight: "700", fontSize: 13 },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  // Summary
  summary: {
    borderRadius: radius.cardLg, padding: 16, borderWidth: 1, borderColor: colors.border, overflow: "hidden",
    backgroundColor: colors.surfaceSecondary,
    shadowColor: "#126046", shadowOpacity: scheme === "dark" ? 0 : 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: 1,
  },
  summaryTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  summarySub: { fontSize: 12.5, color: colors.muted, marginTop: 3 },
  monthPill: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8, paddingHorizontal: 12, borderRadius: radius.pill,
    backgroundColor: scheme === "dark" ? colors.surfaceTertiary : "rgba(255,255,255,0.85)", borderWidth: 1, borderColor: colors.border,
  },
  monthPillText: { fontSize: 12.5, fontWeight: "700", color: colors.onSurface },
  summaryBody: { flexDirection: "row", alignItems: "center", marginTop: 16 },
  ringPct: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  ringSub: { fontSize: 11, color: colors.muted, marginTop: 1 },
  vDivider: { width: 1, alignSelf: "stretch", backgroundColor: colors.divider, marginHorizontal: 14 },
  statRow: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  dot: { width: 9, height: 9, borderRadius: 5, marginRight: 7 },
  statLbl: { fontSize: 12.5, color: colors.muted, flex: 1 },
  statVal: { fontSize: 12.5, color: colors.muted },
  statStrong: { fontSize: 14, fontWeight: "800" },
  statOf: { fontSize: 12, color: colors.muted },
  summaryFoot: { fontSize: 11.5, color: colors.muted },
  // Indicators
  indRow: { flexDirection: "row", gap: 12, marginTop: 12 },
  indCard: {
    flex: 1, flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, padding: 14, borderWidth: 1, borderColor: colors.border,
    overflow: "hidden", backgroundColor: colors.surfaceSecondary,
  },
  indIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  indTitle: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface },
  indCount: { fontSize: 22, fontWeight: "800", marginVertical: 1 },
  indSub: { fontSize: 11.5, color: colors.muted },
  // List
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  sortBtn: { flexDirection: "row", alignItems: "center", gap: 4, maxWidth: "58%" },
  sortText: { fontSize: 12.5, color: colors.muted },
  budgetCard: {
    flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary,
  },
  catIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  cardTitle: { flex: 1, fontSize: 14.5, fontWeight: "800", color: colors.onSurface, marginRight: 8 },
  cardAmount: { fontSize: 13, color: colors.muted },
  cardAmountStrong: { fontSize: 14, fontWeight: "800", color: colors.onSurface },
  cardSmall: { fontSize: 11.5, color: colors.muted },
  // Empty
  empty: { alignItems: "center", paddingVertical: 32, paddingHorizontal: 16, marginTop: 18 },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  emptyTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 6, lineHeight: 18 },
  emptyBtn: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 18, backgroundColor: colors.brandPrimary, paddingVertical: 13, paddingHorizontal: 22, borderRadius: radius.pill },
  emptyBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  // Sheets
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4 },
  yearBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  yearText: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  monthGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between", marginBottom: 8 },
  monthCell: { width: "31%", paddingVertical: 12, alignItems: "center", borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  monthCellText: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, textTransform: "capitalize" },
  sortRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sortRowText: { fontSize: 14.5, color: colors.onSurface },
}));

