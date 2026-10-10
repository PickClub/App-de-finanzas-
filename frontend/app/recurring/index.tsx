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
  FOREST, useMontserrat, pastel, monthName, deepen, safeHex, sortRp, statusTint, dayLabel,
  RP_SORT_KEYS, RP_SORT_LABEL, type RpSortKey,
} from "@/src/recurring/shared";

import { us } from "@/src/ui-scale";

export default function RecurringPayments() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const forest = isDark ? colors.incomeGreen : FOREST;
  const coral = colors.brandPrimary;

  const today = new Date();
  const [ym, setYm] = useState({ y: today.getFullYear(), m: today.getMonth() + 1 });
  const [pickerYear, setPickerYear] = useState(ym.y);
  const [monthOpen, setMonthOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const [sortKey, setSortKey] = useState<RpSortKey>("due");

  const q = useQuery({ queryKey: ["rp-overview", ym.y, ym.m], queryFn: () => api.rpOverview(ym.y, ym.m) });
  const { refetch } = q;
  useFocusEffect(useCallback(() => { refetch(); }, [refetch]));

  const data = q.data;
  const items = useMemo(() => sortRp(data?.items || [], sortKey), [data?.items, sortKey]);
  const totals = data?.totals || { expected: 0, paid: 0, pending: 0, paid_pct: null };
  const counts = data?.counts || { total: 0, paid: 0, pending: 0, overdue: 0 };
  const reminders: any[] = data?.reminders || [];
  const monthLbl = monthName(ym.y, ym.m, i18n.language);
  const openNew = () => router.push("/recurring/new" as any);

  const freqLabel = (f: string) => t(`rp.f_${f}`);

  const renderCard = (it: any) => {
    const base = safeHex(it.color);
    const strong = deepen(base, isDark);
    const st = it.partial && it.card_status !== "paid" ? "partial" : it.card_status;
    const tint = statusTint(it.card_status, colors);
    const dateTxt = it.due_date ? dayLabel(it.due_date, i18n.language) : "—";
    const multi = it.month_count > 1 ? ` · ${t("rp.times", { paid: it.month_paid_count, total: it.month_count })}` : "";
    return (
      <Pressable key={it.id} testID={`rp-card-${it.id}`} onPress={() => router.push(`/recurring/${it.id}` as any)} style={styles.card}>
        <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
        <View style={[styles.cardIcon, { backgroundColor: base + "29" }]}>
          <Ionicons name={(it.icon || "receipt-outline") as any} size={us(22)} color={strong} />
        </View>
        <View style={{ flex: 1, marginLeft: us(12) }}>
          <Text style={[styles.cardName, mont()]} numberOfLines={1}>{it.name}</Text>
          <Text style={styles.cardSub} numberOfLines={1}>{dateTxt} · {freqLabel(it.frequency)}{multi}</Text>
        </View>
        <View style={{ alignItems: "flex-end", marginLeft: us(8) }}>
          <Text style={[styles.cardAmount, mont(true)]} numberOfLines={1}>{formatCurrencyInt(it.due_expected ?? it.amount)}</Text>
          <View style={[styles.pill, { backgroundColor: tint + "22" }]}>
            <Text style={[styles.pillText, { color: deepen(tint, isDark, 0.15) }]} testID={`rp-status-${it.id}`}>{t(`rp.st_${st}`)}</Text>
          </View>
        </View>
        <Ionicons name="chevron-forward" size={us(16)} color={colors.muted} style={{ marginLeft: us(6) }} />
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
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>{t("rp.title")}</Text>
          <Pressable testID="add-rp" onPress={openNew} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={us(22)} color="#fff" />
          </Pressable>
        </View>

        {q.isLoading ? (
          <View style={styles.center}><ActivityIndicator color={colors.incomeGreen} /></View>
        ) : q.isError ? (
          <View style={styles.center}>
            <Ionicons name="cloud-offline-outline" size={us(30)} color={colors.muted} />
            <Text style={styles.muted}>{t("rp.loadError")}</Text>
            <Pressable testID="rp-retry" onPress={() => refetch()} style={styles.retryBtn}>
              <Text style={[styles.retryText, { color: forest }]}>{t("rp.retry")}</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {/* Pagos del mes */}
            <View style={styles.summary} testID="rp-summary">
              <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={styles.rowBetween}>
                <View style={{ flex: 1, paddingRight: us(8) }}>
                  <Text style={[styles.summaryTitle, mont()]}>{t("rp.monthPayments")}</Text>
                  <Pressable testID="rp-month-picker" onPress={() => { setPickerYear(ym.y); setMonthOpen(true); }} hitSlop={8} style={styles.monthBtn}>
                    <Text style={styles.summarySub}>{t("rp.plannedFor", { month: `${i18n.language === "en" ? monthLbl : monthLbl.toLowerCase()} ${ym.y}` })}</Text>
                    <Ionicons name="chevron-down" size={us(14)} color={colors.muted} />
                  </Pressable>
                </View>
                <View style={[styles.topIcon, { backgroundColor: colors.incomeGreen + "26" }]}>
                  <Ionicons name="repeat" size={us(24)} color={forest} />
                </View>
              </View>
              <Text style={[styles.bigAmount, mont(true), { color: forest }]} testID="rp-total-expected" numberOfLines={1} adjustsFontSizeToFit>
                {formatCurrencyInt(totals.expected)}
              </Text>
              <View style={{ marginTop: us(10), marginBottom: us(12) }}>
                <ProgressBar progress={(totals.paid_pct ?? 0) / 100} color={colors.incomeGreen} height={us(10)} trackColor={colors.incomeGreen + "24"} />
              </View>
              <View style={{ flexDirection: "row" }}>
                <View style={{ flex: 1 }}>
                  <View style={styles.legendRow}>
                    <View style={[styles.dot, { backgroundColor: colors.incomeGreen }]} />
                    <Text style={styles.colLbl}>{t("rp.paid")}</Text>
                  </View>
                  <Text style={[styles.colVal, mont(true), { color: forest }]} testID="rp-total-paid">{formatCurrencyInt(totals.paid)}</Text>
                  <Text style={styles.colSub}>{t("rp.paidOf", { n: counts.paid, total: counts.total })}</Text>
                </View>
                <View style={styles.vDivider} />
                <View style={{ flex: 1, paddingLeft: us(14) }}>
                  <View style={styles.legendRow}>
                    <View style={[styles.dot, { backgroundColor: coral }]} />
                    <Text style={styles.colLbl}>{t("rp.pending")}</Text>
                  </View>
                  <Text style={[styles.colVal, mont(true), { color: deepen(coral, isDark, 0.1) }]} testID="rp-total-pending">{formatCurrencyInt(totals.pending)}</Text>
                  <Text style={styles.colSub}>{t("rp.paidOf", { n: counts.pending, total: counts.total })}</Text>
                </View>
              </View>
            </View>

            {/* Indicators */}
            <View style={styles.indRow}>
              <View style={styles.indCard}>
                <LinearGradient colors={pastel(colors.incomeGreen, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: colors.incomeGreen + "29" }]}>
                  <Ionicons name="checkmark-circle" size={us(24)} color={forest} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={[styles.indCount, mont(true), { color: forest }]} testID="rp-paid-count">{counts.paid}</Text>
                  <Text style={styles.indTitle}>{t("rp.paid")}</Text>
                  <Text style={styles.indSub}>{t("rp.thisMonth")}</Text>
                </View>
              </View>
              <View style={styles.indCard}>
                <LinearGradient colors={pastel(coral, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
                <View style={[styles.indIcon, { backgroundColor: coral + "24" }]}>
                  <Ionicons name="time" size={us(24)} color={deepen(coral, isDark, 0.1)} />
                </View>
                <View style={{ flex: 1, marginLeft: us(10) }}>
                  <Text style={[styles.indCount, mont(true), { color: deepen(coral, isDark, 0.1) }]} testID="rp-pending-count">{counts.pending}</Text>
                  <Text style={styles.indTitle}>{t("rp.pending")}</Text>
                  <Text style={styles.indSub}>{t("rp.thisMonth")}</Text>
                </View>
              </View>
            </View>

            {/* In-app reminders */}
            {reminders.length > 0 && (
              <View style={styles.reminderBox} testID="rp-reminders">
                <Ionicons name="notifications-outline" size={us(18)} color={deepen(colors.brandSecondary, isDark, 0.15)} />
                <View style={{ flex: 1 }}>
                  {reminders.slice(0, 3).map((r) => (
                    <Pressable key={r.id + r.due_date} onPress={() => router.push(`/recurring/${r.id}` as any)}>
                      <Text style={styles.reminderText} numberOfLines={1}>
                        <Text style={{ fontWeight: "800" }}>{r.name}</Text>{" · "}
                        {r.days_left === 0 ? t("rp.dueToday") : r.days_left === 1 ? t("rp.dueTomorrow") : t("rp.dueInDays", { n: r.days_left })}
                        {" · "}{formatCurrencyInt(r.remaining)}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            )}

            {items.length === 0 ? (
              <View style={styles.empty} testID="rp-empty">
                <View style={[styles.emptyIcon, { backgroundColor: colors.incomeGreen + "22" }]}>
                  <Ionicons name="repeat" size={us(32)} color={forest} />
                </View>
                <Text style={[styles.emptyTitle, mont()]}>{t("rp.emptyTitle")}</Text>
                <Text style={styles.emptySub}>{t("rp.emptySub")}</Text>
                <Pressable testID="rp-empty-create" onPress={openNew} style={styles.emptyBtn}>
                  <Ionicons name="add" size={us(18)} color="#fff" />
                  <Text style={styles.emptyBtnText}>{t("rp.emptyCta")}</Text>
                </Pressable>
              </View>
            ) : (
              <>
                <View style={[styles.rowBetween, { marginTop: us(20), marginBottom: us(10) }]}>
                  <Text style={[styles.sectionTitle, mont()]}>{t("rp.yours")}</Text>
                  <Pressable testID="rp-sort" onPress={() => setSortOpen(true)} style={styles.sortBtn} hitSlop={8}>
                    <Text style={styles.sortText} numberOfLines={1}>{t(RP_SORT_LABEL[sortKey])}</Text>
                    <Ionicons name="chevron-down" size={us(14)} color={colors.muted} />
                  </Pressable>
                </View>
                {items.map(renderCard)}
              </>
            )}
          </>
        )}
      </ScrollView>

      <AppSheet visible={monthOpen} onClose={() => setMonthOpen(false)} testID="rp-month-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("rp.monthPick")}</Text>
        <View style={[styles.rowBetween, { marginVertical: us(12) }]}>
          <Pressable testID="rp-year-prev" onPress={() => setPickerYear((y) => y - 1)} style={styles.yearBtn}>
            <Ionicons name="chevron-back" size={us(18)} color={colors.onSurface} />
          </Pressable>
          <Text style={[styles.yearText, mont()]}>{pickerYear}</Text>
          <Pressable testID="rp-year-next" onPress={() => setPickerYear((y) => y + 1)} style={styles.yearBtn}>
            <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} />
          </Pressable>
        </View>
        <View style={styles.monthGrid}>
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => {
            const sel = m === ym.m && pickerYear === ym.y;
            return (
              <Pressable key={m} testID={`rp-month-${m}`} onPress={() => { setYm({ y: pickerYear, m }); setMonthOpen(false); }}
                style={[styles.monthCell, sel && { backgroundColor: forest, borderColor: forest }]}>
                <Text style={[styles.monthCellText, sel && { color: "#fff" }]}>{monthName(pickerYear, m, i18n.language).slice(0, 3)}</Text>
              </Pressable>
            );
          })}
        </View>
      </AppSheet>

      <AppSheet visible={sortOpen} onClose={() => setSortOpen(false)} testID="rp-sort-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("rp.sortLabel")}</Text>
        {RP_SORT_KEYS.map((k) => (
          <Pressable key={k} testID={`rp-sort-${k}`} onPress={() => { setSortKey(k); setSortOpen(false); }} style={styles.sortRow}>
            <Text style={[styles.sortRowText, k === sortKey && { color: forest, fontWeight: "800" }]}>{t(RP_SORT_LABEL[k])}</Text>
            {k === sortKey && <Ionicons name="checkmark" size={us(18)} color={forest} />}
          </Pressable>
        ))}
      </AppSheet>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  center: { alignItems: "center", justifyContent: "center", paddingVertical: 60, gap: 10 },
  muted: { color: colors.muted, fontSize: 13, textAlign: "center" },
  retryBtn: { paddingVertical: 10, paddingHorizontal: 18, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  retryText: { fontWeight: "700", fontSize: 13 },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  summary: {
    borderRadius: radius.cardLg, padding: 16, borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary,
    shadowColor: "#126046", shadowOpacity: scheme === "dark" ? 0 : 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: 1,
  },
  summaryTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  monthBtn: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 3, alignSelf: "flex-start" },
  summarySub: { fontSize: 12.5, color: colors.muted },
  topIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center" },
  bigAmount: { fontSize: 28, fontWeight: "800", marginTop: 8 },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  colLbl: { fontSize: 12.5, color: colors.muted },
  colVal: { fontSize: 17, fontWeight: "800", marginTop: 3 },
  colSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  vDivider: { width: 1, alignSelf: "stretch", backgroundColor: colors.divider },
  indRow: { flexDirection: "row", gap: 12, marginTop: 12 },
  indCard: { flex: 1, flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, padding: 14, borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  indIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  indCount: { fontSize: 22, fontWeight: "800", lineHeight: 26 },
  indTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  indSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  reminderBox: { flexDirection: "row", gap: 10, alignItems: "flex-start", marginTop: 12, padding: 12, borderRadius: radius.lg, backgroundColor: colors.brandSecondary + "16", borderWidth: 1, borderColor: colors.brandSecondary + "33" },
  reminderText: { fontSize: 12.5, color: colors.onSurface, lineHeight: 19 },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  sortBtn: { flexDirection: "row", alignItems: "center", gap: 4, maxWidth: "55%" },
  sortText: { fontSize: 12.5, color: colors.muted },
  card: { flexDirection: "row", alignItems: "center", borderRadius: radius.cardLg, paddingVertical: 12, paddingHorizontal: 12, marginBottom: 10, borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  cardIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  cardName: { fontSize: 14.5, fontWeight: "800", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardAmount: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  pill: { marginTop: 4, paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  pillText: { fontSize: 11, fontWeight: "700" },
  empty: { alignItems: "center", paddingVertical: 32, paddingHorizontal: 16, marginTop: 18 },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  emptyTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  emptySub: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 6, lineHeight: 18 },
  emptyBtn: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 18, backgroundColor: colors.brandPrimary, paddingVertical: 13, paddingHorizontal: 22, borderRadius: radius.pill },
  emptyBtnText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  yearBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  yearText: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  monthGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between", marginBottom: 8 },
  monthCell: { width: "31%", paddingVertical: 12, alignItems: "center", borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  monthCellText: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, textTransform: "capitalize" },
  sortRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sortRowText: { fontSize: 14.5, color: colors.onSurface },
}));
