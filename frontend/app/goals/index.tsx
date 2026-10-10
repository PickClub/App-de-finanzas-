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
import { AppSheet } from "@/src/components/sheets";
import {
  FOREST, useMontserrat, pastel, deepen, safeHex, monthYear, sortGoals,
  GOAL_SORT_KEYS, GOAL_SORT_LABEL, PiggyIcon, TargetIcon, type GoalSortKey,
} from "@/src/goals/shared";

import { us } from "@/src/ui-scale";

export default function Goals() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const forest = isDark ? colors.incomeGreen : FOREST;
  const orange = colors.brandSecondary;

  const [sortOpen, setSortOpen] = useState(false);
  const [sortKey, setSortKey] = useState<GoalSortKey>("recent");

  const q = useQuery({ queryKey: ["goals-overview"], queryFn: api.goalsOverview });
  const { refetch } = q;
  useFocusEffect(useCallback(() => { refetch(); }, [refetch]));

  const data = q.data;
  const goals = useMemo(() => sortGoals(data?.goals || [], sortKey), [data?.goals, sortKey]);
  const totals = data?.totals || { saved: 0, target: 0, remaining: 0, pct: null };
  const pctInt = totals.pct === null || totals.pct === undefined ? 0 : Math.floor(totals.pct);

  const openNew = () => router.push("/goals/new" as any);
  const openAdd = (g: any) => router.push(`/goals/contribute?id=${g.id}&kind=deposit` as any);

  const renderGoal = (g: any) => {
    const base = safeHex(g.color);
    const strong = deepen(base, isDark);
    const pct = g.pct ?? 0;
    const sub = g.target_date ? t("goals.targetOn", { date: monthYear(g.target_date, i18n.language) }) : t("goals.noDate");
    let rightFoot: string | null = null;
    let footColor = colors.muted;
    if (g.completed) { rightFoot = t("goals.reached"); footColor = strong; }
    else if (g.overdue) { rightFoot = t("goals.overdue"); footColor = colors.expenseRed; }
    else if (g.monthly_recommended) rightFoot = t("goals.perMonth", { amount: formatCurrencyInt(g.monthly_recommended) });
    return (
      <Pressable
        key={g.id}
        testID={`goal-card-${g.id}`}
        onPress={() => router.push(`/goals/${g.id}` as any)}
        style={({ pressed }) => [styles.goalCard, pressed && styles.pressed]}
      >
        <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
        <View style={[styles.goalIcon, { backgroundColor: base + "29" }]}>
          <Ionicons name={(g.icon || "flag") as any} size={us(26)} color={strong} />
        </View>
        <View style={styles.goalBody}>
          <Text style={[styles.goalName, mont()]} numberOfLines={1}>{g.name}</Text>
          <Text style={styles.goalSub} numberOfLines={1}>{sub}</Text>
          <View style={styles.amountRow}>
            <Text style={styles.goalAmount} numberOfLines={1}>
              <Text style={[styles.goalSaved, mont(true), { color: strong }]}>{formatCurrencyInt(g.current_amount)}</Text>
              {" / "}{formatCurrencyInt(g.target_amount)}
            </Text>
            <Text style={styles.goalPct} testID={`goal-pct-${g.id}`}>{Math.floor(pct)}%</Text>
          </View>
          <View style={{ marginVertical: us(6) }}>
            <ProgressBar progress={pct / 100} color={base} height={us(8)} trackColor={base + "26"} />
          </View>
          <View style={styles.amountRow}>
            <Text style={styles.goalFoot} numberOfLines={1}>{t("goals.remainingN", { amount: formatCurrencyInt(g.remaining) })}</Text>
            {rightFoot ? <Text style={[styles.goalFoot, { color: footColor }, g.completed && { fontWeight: "700" }]} numberOfLines={1}>{rightFoot}</Text> : null}
          </View>
        </View>
        <View style={styles.goalSide}>
          <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} style={{ alignSelf: "flex-end" }} />
          <Pressable
            testID={`goal-add-${g.id}`}
            onPress={() => openAdd(g)}
            hitSlop={6}
            style={({ pressed }) => [styles.addPill, { borderColor: base + "55" }, pressed && styles.pressed]}
          >
            <Ionicons name="add" size={us(15)} color={strong} />
            <Text style={[styles.addPillText, { color: strong }]}>{t("goals.add")}</Text>
          </Pressable>
          <View style={{ height: us(18) }} />
        </View>
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}
        refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={refetch} tintColor={colors.incomeGreen} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Header (unchanged) */}
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>{t("goals.title")}</Text>
          <Pressable testID="add-goal" onPress={openNew} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={us(22)} color="#fff" />
          </Pressable>
        </View>

        {q.isLoading ? (
          <View style={styles.center}><ActivityIndicator color={colors.incomeGreen} /></View>
        ) : q.isError ? (
          <View style={styles.center}>
            <Ionicons name="cloud-offline-outline" size={us(30)} color={colors.muted} />
            <Text style={styles.muted}>{t("goals.loadError")}</Text>
            <Pressable testID="goals-retry" onPress={() => refetch()} style={styles.retryBtn}>
              <Text style={[styles.retryText, { color: forest }]}>{t("goals.retry")}</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {/* Mis ahorros */}
            <View style={styles.summary} testID="goals-summary">
              <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={styles.rowBetween}>
                <View style={{ flex: 1, paddingRight: us(8) }}>
                  <Text style={[styles.summaryTitle, mont()]}>{t("goals.mySavings")}</Text>
                  <Text style={styles.summarySub}>{t("goals.mySavingsSub")}</Text>
                </View>
                <View style={[styles.piggy, { backgroundColor: colors.incomeGreen + "26" }]}>
                  <PiggyIcon size={us(28)} color={forest} />
                </View>
              </View>
              <View style={styles.summaryCols}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.colLbl}>{t("goals.totalSaved")}</Text>
                  <Text style={[styles.colVal, mont(true), { color: forest }]} numberOfLines={1} adjustsFontSizeToFit testID="goals-total-saved">
                    {formatCurrencyInt(totals.saved)}
                  </Text>
                </View>
                <View style={styles.vDivider} />
                <View style={{ flex: 1, paddingLeft: us(14) }}>
                  <Text style={styles.colLbl}>{t("goals.totalTarget")}</Text>
                  <Text style={[styles.colVal, mont(true)]} numberOfLines={1} adjustsFontSizeToFit testID="goals-total-target">
                    {formatCurrencyInt(totals.target)}
                  </Text>
                </View>
              </View>
              <View style={{ marginTop: us(12), marginBottom: us(8) }}>
                <ProgressBar progress={totals.target > 0 ? totals.saved / totals.target : 0} color={colors.incomeGreen} height={us(12)} trackColor={colors.incomeGreen + "24"} />
              </View>
              <View style={styles.rowBetween}>
                <Text style={styles.summaryFoot} testID="goals-total-pct">{t("goals.pctDone", { pct: pctInt })}</Text>
                <Text style={styles.summaryFoot} testID="goals-total-remaining">{t("goals.remainingN", { amount: formatCurrencyInt(totals.remaining) })}</Text>
              </View>
            </View>

            {/* Indicators */}
            <View style={styles.indRow}>
              <View style={styles.indCard} testID="goals-active-card">
                <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: colors.incomeGreen + "29" }]}>
                  <TargetIcon size={us(26)} color={forest} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={[styles.indCount, mont(true), { color: forest }]} testID="goals-active-count">{data?.active_count ?? 0}</Text>
                  <Text style={styles.indTitle} numberOfLines={1}>{t("goals.activeGoals")}</Text>
                  <Text style={styles.indSub} numberOfLines={1}>{t("goals.inProgress")}</Text>
                </View>
              </View>
              <View style={styles.indCard} testID="goals-completed-card">
                <LinearGradient colors={pastel(orange, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: orange + "29" }]}>
                  <Ionicons name="trophy" size={us(24)} color={deepen(orange, isDark, 0.08)} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={[styles.indCount, mont(true), { color: deepen(orange, isDark, 0.08) }]} testID="goals-completed-count">{data?.completed_count ?? 0}</Text>
                  <Text style={styles.indTitle} numberOfLines={1}>{t("goals.completedGoals")}</Text>
                  <Text style={styles.indSub} numberOfLines={1}>{t("goals.achieved")}</Text>
                </View>
              </View>
            </View>

            {goals.length === 0 ? (
              <View style={styles.empty} testID="goals-empty">
                <View style={[styles.emptyIcon, { backgroundColor: colors.incomeGreen + "22" }]}>
                  <PiggyIcon size={us(34)} color={forest} />
                </View>
                <Text style={[styles.emptyTitle, mont()]}>{t("goals.emptyTitle")}</Text>
                <Text style={styles.emptySub}>{t("goals.emptySub")}</Text>
                <Pressable testID="goals-empty-create" onPress={openNew} style={({ pressed }) => [styles.emptyBtn, pressed && styles.pressed]}>
                  <Ionicons name="add" size={us(18)} color="#fff" />
                  <Text style={styles.emptyBtnText}>{t("goals.emptyCta")}</Text>
                </Pressable>
              </View>
            ) : (
              <>
                <View style={[styles.rowBetween, { marginTop: us(20), marginBottom: us(10) }]}>
                  <Text style={[styles.sectionTitle, mont()]}>{t("goals.yours")}</Text>
                  <Pressable testID="goals-sort" onPress={() => setSortOpen(true)} style={styles.sortBtn} hitSlop={8}>
                    <Text style={styles.sortText} numberOfLines={1}>{t("goals.sortLabel")}: {t(GOAL_SORT_LABEL[sortKey])}</Text>
                    <Ionicons name="chevron-down" size={us(14)} color={colors.muted} />
                  </Pressable>
                </View>
                {goals.map(renderGoal)}
              </>
            )}
          </>
        )}
      </ScrollView>

      <AppSheet visible={sortOpen} onClose={() => setSortOpen(false)} testID="goals-sort-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("goals.sortLabel")}</Text>
        {GOAL_SORT_KEYS.map((k) => (
          <Pressable key={k} testID={`goals-sort-${k}`} onPress={() => { setSortKey(k); setSortOpen(false); }} style={styles.sortRow}>
            <Text style={[styles.sortRowText, k === sortKey && { color: forest, fontWeight: "800" }]}>{t(GOAL_SORT_LABEL[k])}</Text>
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
  summaryTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  summarySub: { fontSize: 12.5, color: colors.muted, marginTop: 3 },
  piggy: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  summaryCols: { flexDirection: "row", alignItems: "center", marginTop: 12 },
  colLbl: { fontSize: 12.5, color: colors.muted },
  colVal: { fontSize: 25, fontWeight: "800", color: colors.onSurface, marginTop: 2 },
  vDivider: { width: 1, alignSelf: "stretch", backgroundColor: colors.divider },
  summaryFoot: { fontSize: 12, color: colors.muted },
  // Indicators
  indRow: { flexDirection: "row", gap: 12, marginTop: 12 },
  indCard: {
    flex: 1, flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, padding: 14, borderWidth: 1, borderColor: colors.border,
    overflow: "hidden", backgroundColor: colors.surfaceSecondary,
  },
  indIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  indCount: { fontSize: 22, fontWeight: "800", lineHeight: 26 },
  indTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  indSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  // List
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  sortBtn: { flexDirection: "row", alignItems: "center", gap: 4, maxWidth: "58%" },
  sortText: { fontSize: 12.5, color: colors.muted },
  goalCard: {
    flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, paddingVertical: 12, paddingLeft: 12, paddingRight: 10, marginBottom: 10,
    borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary,
  },
  goalIcon: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center", alignSelf: "flex-start", marginTop: 4 },
  goalBody: { flex: 1, marginLeft: 12, marginRight: 8 },
  goalName: { fontSize: 14.5, fontWeight: "800", color: colors.onSurface },
  goalSub: { fontSize: 12, color: colors.muted, marginTop: 1 },
  amountRow: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 6 },
  goalAmount: { flexShrink: 1, fontSize: 12.5, color: colors.onSurface, marginTop: 4 },
  goalSaved: { fontSize: 16, fontWeight: "800" },
  goalPct: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface },
  goalFoot: { fontSize: 11, color: colors.muted, flexShrink: 1 },
  goalSide: { alignSelf: "stretch", justifyContent: "space-between", alignItems: "center" },
  addPill: {
    flexDirection: "row", alignItems: "center", gap: 3, paddingVertical: 8, paddingHorizontal: 11, minHeight: 36, borderRadius: radius.pill,
    borderWidth: 1, backgroundColor: scheme === "dark" ? colors.surfaceTertiary : "rgba(255,255,255,0.85)",
  },
  addPillText: { fontSize: 12.5, fontWeight: "700" },
  // Empty
  empty: { alignItems: "center", paddingVertical: 32, paddingHorizontal: 16, marginTop: 18 },
  emptyIcon: { width: 68, height: 68, borderRadius: 34, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  emptyTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 6, lineHeight: 18 },
  emptyBtn: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 18, backgroundColor: colors.brandPrimary, paddingVertical: 13, paddingHorizontal: 22, borderRadius: radius.pill },
  emptyBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  // Sheet
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sortRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sortRowText: { fontSize: 14.5, color: colors.onSurface },
}));
