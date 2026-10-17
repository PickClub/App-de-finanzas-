import { ElasticFlatList } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useCallback, useRef, useState } from "react";
import { View, FlatList, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt } from "@/src/format";
import { FOREST, useMontserrat, safeHex, deepen, statusColor, shortDate, BILL_FILTERS, type BillFilter } from "@/src/bills/shared";
import { us } from "@/src/ui-scale";

export default function BillsScreen() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const mont = useMontserrat();
  const [filter, setFilter] = useState<BillFilter>("all");

  const listQ = useQuery({ queryKey: ["bills"], queryFn: () => api.billsList("all"), placeholderData: keepPreviousData });
  const sumQ = useQuery({ queryKey: ["bills-summary"], queryFn: api.billsSummary, placeholderData: keepPreviousData });
  const [refreshing, setRefreshing] = useState(false);
  const refreshingRef = useRef(false);
  const onRefresh = async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    try {
      await Promise.allSettled([
        Promise.resolve().then(() => listQ.refetch({ cancelRefetch: false })),
        Promise.resolve().then(() => sumQ.refetch({ cancelRefetch: false })),
      ]);
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  };
  const [ready, setReady] = useState(false);
  useFocusEffect(useCallback(() => {
    if (ready) { listQ.refetch(); sumQ.refetch(); }
    setReady(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []));

  const all: any[] = listQ.data?.items || [];
  // Status is the server's payment-aware classification for this bill occurrence.
  const groups = {
    all: all.filter((b) => b.status !== "paid" && b.remaining > 0),
    pending: all.filter((b) => b.status === "pending" && b.remaining > 0),
    paid: all.filter((b) => b.status === "paid"),
    overdue: all.filter((b) => b.status === "overdue" && b.remaining > 0),
  };
  const counts = Object.fromEntries(BILL_FILTERS.map((key) => [key, groups[key].length]));
  const items = groups[filter];
  const s = sumQ.data;

  const SumCard = ({ testID, tint, icon, label, value, onPress }: any) => (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [styles.sumCard, { backgroundColor: tint + (isDark ? "1F" : "16") }, pressed && { opacity: 0.8 }]}>
      <View style={styles.rowBetween}>
        <View style={[styles.sumIcon, { backgroundColor: tint + (isDark ? "33" : "24") }]}>
          <Ionicons name={icon} size={us(20)} color={tint} />
        </View>
        <View style={styles.sumChevron}>
          <Ionicons name="chevron-forward" size={us(15)} color={colors.onSurface} />
        </View>
      </View>
      <Text style={styles.sumLabel} numberOfLines={1}>{label}</Text>
      <Text style={[styles.sumValue, mont(), { color: tint }]} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
    </Pressable>
  );

  const BillRow = ({ b }: { b: any }) => {
    const base = safeHex(b.color || b.category_color);
    const sc = statusColor(b.status, colors);
    return (
      <Pressable testID={`bill-row-${b.id}`} onPress={() => router.push(`/bills/${b.id}` as any)} style={({ pressed }) => [styles.row, pressed && { opacity: 0.85 }]}>
        <View style={[styles.rowIcon, { backgroundColor: base + (isDark ? "2E" : "1F") }]}>
          <Ionicons name={(b.icon || b.category_icon || "receipt-outline") as any} size={us(22)} color={deepen(base, isDark)} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.rowName, mont()]} numberOfLines={1}>{b.name}</Text>
          {b.provider ? <Text style={styles.rowSub} numberOfLines={1}>{b.provider}</Text> : null}
          <View style={styles.dateRow}>
            <Ionicons name="calendar-outline" size={us(13)} color={colors.muted} />
            <Text style={styles.rowSub}>{shortDate(b.due_date, lang)}</Text>
            {b.reminder_active ? <Ionicons name="notifications" size={us(12)} color={colors.brandSecondary} /> : null}
          </View>
        </View>
        <View style={{ alignItems: "flex-end", gap: us(4), marginLeft: us(8) }}>
          <Text style={[styles.rowAmount, mont()]} numberOfLines={1}>{formatCurrencyInt(b.status === "paid" ? b.amount : b.remaining)}</Text>
          <View style={[styles.pill, { backgroundColor: sc + (isDark ? "2E" : "1C") }]}>
            <Text style={[styles.pillText, { color: sc }]}>{b.partial ? t("bills.partial") : t(`bills.s_${b.status}`, { defaultValue: t("common.unknown") })}</Text>
          </View>
        </View>
        <View style={styles.chev}>
          <Ionicons name="chevron-forward" size={us(16)} color={colors.onSurface} />
        </View>
      </Pressable>
    );
  };

  const Header = (
    <View>
      <View style={styles.header}>
        <Text style={[styles.title, mont(), { flex: 1 }]} numberOfLines={1}>{t("bills.title")}</Text>
        <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="bills-back" />
      </View>
      <Text style={styles.subtitle}>{t("bills.subtitle")}</Text>

      {sumQ.isError && !s ? null : (
        <View style={styles.grid} testID="bills-summary">
          <View style={styles.gridRow}>
            <SumCard testID="bills-sum-pending" tint={colors.brandSecondary} icon="time-outline" label={t("bills.pending")} value={formatCurrencyInt(s?.pending?.amount || 0)} onPress={() => setFilter("pending")} />
            <SumCard testID="bills-sum-paid" tint={colors.incomeGreen} icon="checkmark-circle" label={t("bills.paidMonth")} value={formatCurrencyInt(s?.paid_month?.amount || 0)} onPress={() => setFilter("paid")} />
          </View>
          <View style={styles.gridRow}>
            <SumCard testID="bills-sum-next" tint={colors.info} icon="calendar" label={t("bills.nextDue")} value={s?.next_due ? shortDate(s.next_due.due_date, lang) : t("bills.noNext")}
              onPress={() => (s?.next_due ? router.push(`/bills/${s.next_due.id}` as any) : setFilter("pending"))} />
            <SumCard testID="bills-sum-overdue" tint={colors.expenseRed} icon="alert-circle" label={t("bills.overdueTotal")} value={formatCurrencyInt(s?.overdue?.amount || 0)} onPress={() => setFilter("overdue")} />
          </View>
        </View>
      )}

      <View style={[styles.rowBetween, { marginTop: us(spacing.lg) }]}>
        <Text style={[styles.section, mont()]}>{t("bills.myBills")}</Text>
        <Pressable testID="bills-new" onPress={() => router.push("/bills/new" as any)} style={({ pressed }) => [styles.newBtn, { backgroundColor: scheme === "dark" ? forest : colors.primaryAction }, pressed && { opacity: 0.85 }]}>
          <Ionicons name="add" size={us(20)} color="#fff" />
          <Text style={[styles.newText, mont()]}>{t("bills.newBill")}</Text>
        </Pressable>
      </View>
      <View style={styles.filters}>
        {BILL_FILTERS.map((f) => {
          const on = filter === f;
          return (
            <Pressable key={f} testID={`bills-filter-${f}`} onPress={() => setFilter(f)} style={[styles.chip, on && { backgroundColor: colors.incomeGreen + "26", borderColor: "transparent" }]}>
              <Text style={[styles.chipText, on && { color: forest, fontWeight: "800" }]} numberOfLines={1}>
                {t(`bills.f_${f}`)}{` ${counts[f]}`}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );

  const Empty = listQ.isLoading ? (
    <ActivityIndicator color={forest} style={{ marginTop: us(30) }} />
  ) : listQ.isError ? (
    <View style={styles.empty}>
      <Ionicons name="cloud-offline-outline" size={us(26)} color={colors.muted} />
      <Text style={styles.emptyText}>{t("bills.loadError")}</Text>
      <Pressable testID="bills-retry" onPress={() => listQ.refetch()} style={styles.retry}><Text style={{ color: forest, fontWeight: "800" }}>{t("bills.retry")}</Text></Pressable>
    </View>
  ) : all.length === 0 ? (
    <View style={styles.empty} testID="bills-empty">
      <View style={[styles.emptyIcon, { backgroundColor: colors.info + "1C" }]}>
        <Ionicons name="document-text-outline" size={us(30)} color={colors.info} />
      </View>
      <Text style={[styles.emptyTitle, mont()]}>{t("bills.emptyTitle")}</Text>
      <Text style={styles.emptyText}>{t("bills.emptyText")}</Text>
    </View>
  ) : (
    <View style={styles.empty} testID="bills-empty-filter">
      <Text style={styles.emptyText}>{t("bills.emptyFilter")}</Text>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.pageBackground }}>
      <ElasticFlatList {...NATIVE_VERTICAL_SCROLL}
        data={items}
        keyExtractor={(b) => b.id}
        renderItem={({ item }) => <BillRow b={item} />}
        ListHeaderComponent={Header}
        ListEmptyComponent={Empty}
        ItemSeparatorComponent={() => <View style={{ height: us(10) }} />}
        initialNumToRender={12}
        windowSize={7}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const useStyles = makeStyles((colors) => {
  return {
    header: { flexDirection: "row", alignItems: "center", gap: 12 },
    backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
    title: { flex: 1, fontSize: 24, color: colors.onSurface },
    subtitle: { fontSize: 13.5, color: colors.muted, marginTop: 8, marginBottom: 14 },
    grid: { gap: 10 },
    gridRow: { flexDirection: "row", gap: 10 },
    sumCard: { flex: 1, borderRadius: radius.cardLg, padding: 12, minHeight: 112, borderWidth: 1, borderColor: colors.border },
    sumIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center" },
    sumChevron: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
    sumLabel: { fontSize: 12.5, color: colors.muted, marginTop: 10 },
    sumValue: { fontSize: 21, marginTop: 2 },
    rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    section: { fontSize: 18, color: colors.onSurface, flexShrink: 1 },
    newBtn: { flexDirection: "row", alignItems: "center", gap: 6, height: 44, paddingHorizontal: 16, borderRadius: radius.pill },
    newText: { color: "#fff", fontSize: 14 },
    filters: { flexDirection: "row", gap: 6, marginTop: 12, marginBottom: 12 },
    chip: { flex: 1, height: 38, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", paddingHorizontal: 4, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    chipText: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface },
    row: { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: radius.cardLg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    rowIcon: { width: 46, height: 46, borderRadius: 14, alignItems: "center", justifyContent: "center", marginRight: 12 },
    rowName: { fontSize: 15, color: colors.onSurface },
    rowSub: { fontSize: 12.5, color: colors.muted, marginTop: 1 },
    dateRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 2 },
    rowAmount: { fontSize: 15.5, color: colors.onSurface },
    pill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: radius.pill },
    pillText: { fontSize: 11.5, fontWeight: "700" },
    chev: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center", marginLeft: 8, backgroundColor: colors.surface },
    empty: { alignItems: "center", paddingVertical: 32, paddingHorizontal: 20, gap: 8 },
    emptyIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 4 },
    emptyTitle: { fontSize: 16, color: colors.onSurface },
    emptyText: { fontSize: 13, color: colors.muted, textAlign: "center", lineHeight: 18 },
    retry: { marginTop: 6, paddingHorizontal: 16, height: 38, borderRadius: radius.pill, justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  };
});
