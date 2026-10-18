import i18n, { tr, useTranslation } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, ScrollView, Platform } from "react-native";
import Animated, { FadeIn } from "react-native-reanimated";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type TransactionPageFilters } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency, formatDateTime, translateCategoryName } from "@/src/format";

import { IconTile } from "@/src/components/ui";
import { useLock } from "@/src/lock";
import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRange, type DateRangeSheetHandle } from "@/src/components/date-range-sheet";
import { us } from "@/src/ui-scale";

/**
 * «Todas las transacciones» — independent route opened from Home → Movimientos
 * recientes → «Ver todo». Shows ONLY real transactions (no placeholders).
 * Reads 20 records per request. Only page-start cursors are retained locally;
 * the backend owns filters, global ordering and the complete filtered count.
 */

const PAGE_SIZE = 20;
const DAY = 24 * 3600 * 1000;
const MONTHS_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];
const MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

type Period = "today" | "7d" | "30d" | "month" | "custom" | "all";
type TypeFilter = "all" | "income" | "expense" | "transfer";
type SortKey = "recent" | "oldest" | "high" | "low";

function palette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    dark,
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    forest: dark ? colors.incomeGreen : "#126046",
    ink: dark ? colors.onSurface : "#123D2E",
    text: dark ? colors.onSurface : "#15251E",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    chip: dark ? colors.surfaceTertiary : "#EEF3EC",
    muted: dark ? colors.muted : "#6F7A73",
    border: dark ? colors.border : "rgba(39,71,56,0.08)",
    divider: dark ? colors.divider : "#E4E7E2",
    onForest: dark ? colors.onSuccess : "#FFFFFF",
  };
}

const startOfDay = (d: Date) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x.getTime(); };
const endOfDay = (d: Date) => { const x = new Date(d); x.setHours(23, 59, 59, 999); return x.getTime(); };

// Compact page window: 1 … p-1 p p+1 … N
function pageWindow(page: number, total: number): (number | "…")[] {
  if (total <= 5) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const from = Math.max(2, Math.min(page - 1, total - 3));
  const to = Math.min(total - 1, Math.max(page + 1, 4));
  if (from > 2) out.push("…");
  for (let i = from; i <= to; i++) out.push(i);
  if (to < total - 1) out.push("…");
  out.push(total);
  return out;
}

export default function AllTransactions() {
  const { colors, scheme } = useTheme();
  const pal = palette(colors, scheme);
  const styles = useStyles();
  const { t } = useTranslation();
  const router = useRouter();
  const { accountId, categoryId } = useLocalSearchParams<{ accountId?: string; categoryId?: string }>();
  const insets = useSafeAreaInsets();
  const { guard } = useLock();
  const en = (i18n.language || "es").startsWith("en");
  const MONTHS = en ? MONTHS_EN : MONTHS_ES;

  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });

  const [period, setPeriod] = useState<Period>("30d");
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [custom, setCustom] = useState<DateRange | null>(null);
  const [type, setType] = useState<TypeFilter>("all");
  const [sort, setSort] = useState<SortKey>("recent");
  const [navigation, setNavigation] = useState<{ scope: string; page: number; cursors: (string | undefined)[] }>({ scope: "", page: 1, cursors: [undefined] });
  const [refreshKey, setRefreshKey] = useState(0);
  const [sortOpen, setSortOpen] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const listY = useRef(0);
  const dateSheetRef = useRef<DateRangeSheetHandle>(null);
  const firstFocus = useRef(true);

  const catById = useMemo(() => Object.fromEntries((catQ.data || []).map((c: any) => [c.id, c])), [catQ.data]);

  // Active window [start, end] for the selected period.
  const range = useMemo(() => {
    if (period === "all") return null;
    const now = new Date();
    if (period === "today") return { start: startOfDay(now), end: endOfDay(now) };
    if (period === "7d") return { start: startOfDay(new Date(now.getTime() - 6 * DAY)), end: endOfDay(now) };
    if (period === "30d") return { start: startOfDay(new Date(now.getTime() - 29 * DAY)), end: endOfDay(now) };
    if (period === "custom" && custom) return custom;
    const s = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const e = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
    return { start: startOfDay(s), end: endOfDay(e) };
  }, [period, cursor, custom]);

  // Header label follows the selected period.
  const label = useMemo(() => {
    if (!range) return tr("ui.all_dates");
    const s = new Date(range.start);
    const e = new Date(range.end);
    if (s.getFullYear() === e.getFullYear() && s.getMonth() === e.getMonth()) return `${MONTHS[e.getMonth()]} ${e.getFullYear()}`;
    const sm = MONTHS[s.getMonth()].slice(0, 3);
    const em = MONTHS[e.getMonth()].slice(0, 3);
    return s.getFullYear() === e.getFullYear() ? `${sm} – ${em} ${e.getFullYear()}` : `${sm} ${s.getFullYear()} – ${em} ${e.getFullYear()}`;
  }, [range, MONTHS]);

  const filters = useMemo<TransactionPageFilters>(() => ({
    account_id: accountId || undefined,
    category_id: categoryId || undefined,
    types: type === "income" ? ["income", "loan_received"] : type === "expense" ? ["expense", "debt_payment"] : type === "transfer" ? ["transfer"] : undefined,
    start: range ? new Date(range.start).toISOString() : undefined,
    // UI ranges include the final millisecond; the backend uses an exclusive end.
    end: range ? new Date(range.end + 1).toISOString() : undefined,
    order: sort,
  }), [accountId, categoryId, type, range, sort]);
  const scope = JSON.stringify(filters);
  // Resolve a new scope synchronously: never send an old cursor with new filters.
  const active = navigation.scope === scope ? navigation : { scope, page: 1, cursors: [undefined] };
  useEffect(() => { setNavigation({ scope, page: 1, cursors: [undefined] }); }, [scope]);
  const safePage = active.page;
  const txQ = useQuery({
    queryKey: ["transactions", "page", scope, refreshKey, active.cursors[safePage - 1]],
    queryFn: ({ signal }) => api.getTransactionPage(filters, active.cursors[safePage - 1], signal),
    retry: false,
    gcTime: 0, // Discard inactive page payloads; keep only the cursor history.
    refetchOnWindowFocus: false,
  });
  const resetPage = useCallback(() => setNavigation({ scope: "", page: 1, cursors: [undefined] }), []);
  const refresh = useCallback(() => {
    resetPage();
    setRefreshKey(key => key + 1);
  }, [resetPage]);
  // Returning from detail/edit starts a fresh traversal after existing invalidations.
  useFocusEffect(useCallback(() => {
    if (firstFocus.current) firstFocus.current = false;
    else refresh();
  }, [refresh]));
  const ready = txQ.isSuccess && !txQ.isFetching;
  const total = ready ? txQ.data.total : 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageItems = ready ? txQ.data.items : [];
  const from = pageItems.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const to = pageItems.length === 0 ? 0 : from + pageItems.length - 1;
  const hasMore = ready && txQ.data.has_more;
  const canVisit = (p: number) => !txQ.isFetching && p >= 1 && p !== safePage && (p <= active.cursors.length || (p === safePage + 1 && hasMore));
  const pageError = txQ.error instanceof ApiError && txQ.error.status === 409
    ? (tr("ui.the_history_contains_unverifiable_or_duplicated_data_retry_or_review_the_records"))
    : (tr("ui.the_history_could_not_be_loaded_try_again"));

  // Any filter / period / sort change returns to page 1.
  const choosePeriod = (p: Period) => { setPeriod(p); resetPage(); };
  const shiftMonth = (delta: number) => {
    const base = new Date(range?.end ?? Date.now());
    setCursor(new Date(base.getFullYear(), base.getMonth() + delta, 1));
    setPeriod("month");
    resetPage();
  };
  const now = new Date();
  const labelEnd = new Date(range?.end ?? Date.now());
  const canNext = labelEnd.getFullYear() < now.getFullYear() || (labelEnd.getFullYear() === now.getFullYear() && labelEnd.getMonth() < now.getMonth());

  const goPage = (p: number) => {
    if (!canVisit(p)) return;
    const cursors = active.cursors.slice();
    if (p === safePage + 1) {
      if (!txQ.data?.next_cursor) return;
      // If live data changed, discard successors derived from the old boundary.
      if (cursors[p - 1] !== txQ.data.next_cursor) cursors.length = p - 1;
      cursors[p - 1] = txQ.data.next_cursor;
    }
    setNavigation({ scope, page: p, cursors });
    scrollRef.current?.scrollTo({ y: Math.max(0, listY.current - us(8)), animated: true });
  };

  const onApplyRange = useCallback((r: DateRange | null) => {
    if (r) { setCustom(r); setPeriod("custom"); } else { setCustom(null); setPeriod("all"); }
    resetPage();
  }, [resetPage]);

  const SORTS: { id: SortKey; label: string }[] = [
    { id: "recent", label: tr("ui.most_recent") },
    { id: "oldest", label: tr("ui.oldest") },
    { id: "high", label: tr("ui.highest_amount") },
    { id: "low", label: tr("ui.lowest_amount") },
  ];
  const PERIODS: { id: Period; label: string }[] = [
    { id: "today", label: tr("ui.today") },
    { id: "7d", label: tr("ui.7_days") },
    { id: "30d", label: tr("ui.30_days") },
    { id: "custom", label: tr("ui.custom") },
  ];
  const TYPES: { id: TypeFilter; label: string; icon: string; color: string }[] = [
    { id: "all", label: t("home.filterAll"), icon: "grid", color: pal.forest },
    { id: "income", label: t("home.filterIncome"), icon: "trending-up", color: colors.incomeGreen },
    { id: "expense", label: t("home.filterExpenses"), icon: "trending-down", color: colors.expenseRed },
    { id: "transfer", label: t("home.filterTransfers"), icon: "swap-horizontal", color: colors.accountsBlue },
  ];
  const shadow = pal.dark ? null : styles.softShadow;
  const cardStyle = [styles.card, { backgroundColor: pal.card, borderColor: pal.border }, shadow];
  const sortLabel = SORTS.find((s) => s.id === sort)?.label;

  return (
    <View style={{ flex: 1, backgroundColor: pal.bg }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL}
        ref={scrollRef}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(32), paddingHorizontal: us(spacing.lg) }}
      >
        {/* Header */}
        <View style={styles.header}>
          <MoneyFlowHeaderActions title={<Text style={[styles.title, { color: pal.ink, flex: 1 }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}>
            {tr("ui.all_transactions")}
          </Text>} onBack={() => router.back()} backTestID="all-tx-back" />
        </View>

        {/* Period card */}
        <View style={cardStyle}>
          <View style={styles.monthRow}>
            <View style={[styles.calIcon, { backgroundColor: pal.mint }]}>
              <Ionicons name="calendar-outline" size={us(20)} color={pal.forest} />
            </View>
            <Text testID="all-tx-month" style={[styles.monthText, { color: pal.text }]} numberOfLines={1}>{label}</Text>
            {range && <Pressable testID="all-tx-clear-date" accessibilityLabel={en ? tr("ui.clear_date_filter") : tr("ui.clear_date_filter")} onPress={() => onApplyRange(null)} hitSlop={8}>
              <Ionicons name="close" size={us(18)} color={pal.muted} />
            </Pressable>}
            <Pressable testID="all-tx-prev-month" onPress={() => shiftMonth(-1)} style={[styles.arrowBtn, { backgroundColor: pal.chip }]}>
              <Ionicons name="chevron-back" size={us(18)} color={pal.text} />
            </Pressable>
            <Pressable testID="all-tx-next-month" onPress={() => canNext && shiftMonth(1)} disabled={!canNext} style={[styles.arrowBtn, { backgroundColor: pal.chip, opacity: canNext ? 1 : 0.4 }]}>
              <Ionicons name="chevron-forward" size={us(18)} color={pal.text} />
            </Pressable>
          </View>
          <View style={styles.periodRow}>
            {PERIODS.map((p) => {
              const active = period === p.id;
              return (
                <Pressable
                  key={p.id}
                  testID={`all-tx-period-${p.id}`}
                  onPress={() => (p.id === "custom" ? dateSheetRef.current?.open(custom) : choosePeriod(p.id))}
                  style={[styles.periodBtn, { backgroundColor: active ? pal.forest : pal.chip }]}
                >
                  <Text style={[styles.periodText, { color: active ? pal.onForest : pal.text }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.8}>{p.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        {/* Type filters */}
        <View style={[cardStyle, styles.typeCard]}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.typeRow}>
            {TYPES.map((f) => {
              const active = type === f.id;
              return (
                <Pressable
                  key={f.id}
                  testID={`all-tx-type-${f.id}`}
                  onPress={() => { setType(f.id); resetPage(); }}
                  style={[styles.typeBtn, active ? { backgroundColor: pal.forest, borderColor: pal.forest } : { backgroundColor: pal.card, borderColor: pal.divider }]}
                >
                  <Ionicons name={f.icon as any} size={us(15)} color={active ? pal.onForest : f.color} />
                  <Text style={[styles.typeText, { color: active ? pal.onForest : pal.text }]}>{f.label}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>

        {/* Count + sort */}
        <View style={styles.infoRow}>
          <Text testID="all-tx-count" style={[styles.infoText, { color: pal.muted }]} numberOfLines={1}>
            {ready ? tr("ui.transactions_found", { count: total }) : tr("ui.count_unavailable")}
          </Text>
          <Pressable testID="all-tx-sort" onPress={() => setSortOpen(true)} style={styles.sortBtn} hitSlop={8}>
            <Ionicons name="filter-outline" size={us(14)} color={pal.muted} />
            <Text style={[styles.infoText, { color: pal.muted }]} numberOfLines={1}>{tr("ui.sort")}: {sortLabel}</Text>
            <Ionicons name="chevron-down" size={us(14)} color={pal.muted} />
          </Pressable>
        </View>

        {(accountId || categoryId) && <Text testID="all-tx-active-filters" style={[styles.infoText, { color: pal.muted }]}>
          {[accountId && (tr("ui.account_filter_active")), categoryId && (tr("ui.category_filter_active"))].filter(Boolean).join(" · ")}
        </Text>}

        {/* List */}
        <View onLayout={(e) => { listY.current = e.nativeEvent.layout.y; }} style={[cardStyle, styles.listCard]}>
          <Animated.View key={`${period}|${range?.start ?? "all"}|${type}|${sort}|${safePage}`} entering={FadeIn.duration(180)}>
            {txQ.isPending || txQ.isFetching ? (
              <Text style={[styles.empty, { color: pal.muted }]}>{tr("ui.loading")}</Text>
            ) : txQ.isError ? (
              <View style={styles.emptyWrap}>
                <Text testID="all-tx-error" style={[styles.empty, { color: pal.muted }]}>{pageError}</Text>
                <Pressable testID="all-tx-retry" onPress={() => txQ.refetch()} style={styles.sortBtn}>
                  <Text style={[styles.infoText, { color: pal.forest }]}>{en ? tr("ui.retry") : tr("ui.retry")}</Text>
                </Pressable>
                {safePage > 1 && <Pressable testID="all-tx-error-prev" onPress={() => goPage(safePage - 1)} style={styles.sortBtn}>
                  <Text style={[styles.infoText, { color: pal.forest }]}>{tr("ui.previous_page")}</Text>
                </Pressable>}
                <Pressable testID="all-tx-error-refresh" onPress={refresh} style={styles.sortBtn}>
                  <Text style={[styles.infoText, { color: pal.forest }]}>{tr("ui.restart_history")}</Text>
                </Pressable>
              </View>
            ) : pageItems.length === 0 ? (
              <View style={styles.emptyWrap}>
                <View style={[styles.calIcon, { backgroundColor: pal.mint }]}>
                  <Ionicons name="receipt-outline" size={us(20)} color={pal.forest} />
                </View>
                <Text testID="all-tx-empty" style={[styles.empty, { color: pal.muted }]}>
                  {total === 0 ? (tr("ui.no_transactions_in_this_period")) : (tr("ui.no_transactions_on_this_page_refresh_to_restart"))}
                </Text>
                {total > 0 && <Pressable testID="all-tx-restart" onPress={refresh} style={styles.sortBtn}>
                  <Text style={[styles.infoText, { color: pal.forest }]}>{tr("ui.refresh")}</Text>
                </Pressable>}
              </View>
            ) : (
              pageItems.map((item: any, idx: number) => {
                const cat = catById[item.category_id];
                const isIncome = item.type === "income" || item.type === "loan_received";
                const isTransfer = item.type === "transfer";
                const color = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
                const sign = isTransfer ? "" : isIncome ? "+" : "-";
                const iconName = cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
                const tint = cat?.color || color;
                const badge = cat?.name ? translateCategoryName(cat.name) : isTransfer ? t("txType.transfer") : isIncome ? t("txType.income") : t("txType.expense");
                return (
                  <View key={item.id}>
                    {idx > 0 && <View style={[styles.divider, { backgroundColor: pal.divider }]} />}
                    <Pressable
                      testID={`all-tx-row-${item.id}`}
                      onPress={guard(() => router.push(`/transactions/${item.id}`))}
                      style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}
                    >
                      <IconTile icon={iconName} tint={tint} size={us(40)} />
                      <View style={{ flex: 1, minWidth: 0, marginLeft: us(12) }}>
                        <Text style={[styles.rowName, { color: pal.text }]} numberOfLines={1}>{item.name || (tr("ui.no_description"))}</Text>
                        <View style={styles.timeRow}>
                          <Ionicons name="time-outline" size={us(12)} color={pal.muted} />
                          <Text style={[styles.rowTime, { color: pal.muted }]} numberOfLines={1}>{formatDateTime(item.date)}</Text>
                        </View>
                      </View>
                      <View style={[styles.badge, { backgroundColor: tint + "1A" }]}>
                        <Text style={[styles.badgeText, { color: tint }]} numberOfLines={1}>{badge}</Text>
                      </View>
                      <Text style={[styles.amount, { color }]} numberOfLines={1}>{sign}{formatCurrency(item.amount)}</Text>
                      <Ionicons name="chevron-forward" size={us(15)} color={pal.muted} style={{ marginLeft: us(4) }} />
                    </Pressable>
                  </View>
                );
              })
            )}
          </Animated.View>
        </View>

        {/* Pagination */}
        {total > 0 && (
          <>
            <View style={styles.pager}>
              <Pressable testID="all-tx-page-prev" onPress={() => goPage(safePage - 1)} disabled={!canVisit(safePage - 1)} style={[styles.pageBtn, { backgroundColor: pal.card, borderColor: pal.border, opacity: !canVisit(safePage - 1) ? 0.4 : 1 }, shadow]}>
                <Ionicons name="chevron-back" size={us(18)} color={pal.text} />
              </Pressable>
              {pageWindow(safePage, pages).map((p, i) =>
                p === "…" ? (
                  <Text key={`e${i}`} style={[styles.ellipsis, { color: pal.muted }]}>…</Text>
                ) : (
                  <Pressable
                    key={p}
                    testID={`all-tx-page-${p}`}
                    onPress={() => goPage(p)}
                    disabled={!canVisit(p)}
                    accessibilityHint={!canVisit(p) && p !== safePage ? (tr("ui.visit_preceding_pages_first")) : undefined}
                    style={[styles.pageBtn, p === safePage ? { backgroundColor: pal.forest, borderColor: pal.forest } : { backgroundColor: pal.card, borderColor: pal.border, opacity: canVisit(p) ? 1 : 0.4 }, shadow]}
                  >
                    <Text style={[styles.pageText, { color: p === safePage ? pal.onForest : pal.text }]}>{p}</Text>
                  </Pressable>
                ),
              )}
              <Pressable testID="all-tx-page-next" onPress={() => goPage(safePage + 1)} disabled={!hasMore} style={[styles.pageBtn, { backgroundColor: pal.card, borderColor: pal.border, opacity: !hasMore ? 0.4 : 1 }, shadow]}>
                <Ionicons name="chevron-forward" size={us(18)} color={pal.text} />
              </Pressable>
            </View>
            <Text testID="all-tx-range" style={[styles.showing, { color: pal.muted }]}>
              {en ? `Showing ${from}–${to} of ${total} transactions` : `Mostrando ${from}–${to} de ${total} transacciones`}
            </Text>
            <Text testID="all-tx-navigation-info" style={[styles.showing, { color: pal.muted }]}>
              {tr("ui.jump_only_to_visited_pages_use_next_to_advance")}
              {!hasMore ? (tr("ui.end_of_history")) : ""}
            </Text>
          </>
        )}
      </ElasticScrollView>

      {/* Sort sheet */}
      <AppSheet visible={sortOpen} onClose={() => setSortOpen(false)} testID="all-tx-sort-sheet">
        <Text style={[styles.sheetTitle, { color: pal.ink }]}>{tr("ui.sort_by")}</Text>
        <View style={{ paddingHorizontal: us(spacing.lg), gap: us(8) }}>
          {SORTS.map((s) => {
            const sel = sort === s.id;
            return (
              <Pressable
                key={s.id}
                testID={`all-tx-sort-${s.id}`}
                onPress={() => { setSort(s.id); resetPage(); setSortOpen(false); }}
                style={[styles.sheetRow, { backgroundColor: sel ? pal.mint : pal.card, borderColor: sel ? pal.forest : pal.border }]}
              >
                <Text style={[styles.sheetRowText, { color: pal.text }]}>{s.label}</Text>
                {sel && <Ionicons name="checkmark-circle" size={us(20)} color={pal.forest} />}
              </Pressable>
            );
          })}
        </View>
      </AppSheet>

      <DateRangeSheet ref={dateSheetRef} onApply={onApplyRange} allowClear />
    </View>
  );
}

const useStyles = makeStyles(() => ({
  header: { flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 },
  circleBtn: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  title: { flex: 1, fontSize: 24, fontWeight: "800", letterSpacing: -0.4 },
  softShadow: Platform.select({
    web: { boxShadow: "0px 3px 12px rgba(39,71,56,0.06)" } as any,
    default: { shadowColor: "#274738", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  }),
  card: { borderRadius: 24, borderWidth: 1, padding: 12, marginBottom: 12 },
  monthRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  calIcon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  monthText: { flex: 1, fontSize: 17, fontWeight: "700" },
  arrowBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  periodRow: { flexDirection: "row", gap: 6, marginTop: 12 },
  periodBtn: { flex: 1, minHeight: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", paddingHorizontal: 6 },
  periodText: { fontSize: 13, fontWeight: "600" },
  typeCard: { paddingHorizontal: 6, paddingVertical: 6 },
  typeRow: { gap: 8, paddingHorizontal: 2 },
  typeBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, minHeight: 36, borderRadius: radius.pill, borderWidth: 1 },
  typeText: { fontSize: 13, fontWeight: "600" },
  infoRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 10, paddingHorizontal: 2 },
  infoText: { fontSize: 12 },
  sortBtn: { flexDirection: "row", alignItems: "center", gap: 4, flexShrink: 1 },
  listCard: { paddingVertical: 2, paddingHorizontal: 10 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 11, paddingHorizontal: 2 },
  divider: { height: 1, marginLeft: 54 },
  rowName: { fontSize: 14, fontWeight: "700", letterSpacing: -0.2 },
  timeRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 3 },
  rowTime: { fontSize: 11.5 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, marginHorizontal: 6, flexShrink: 1, maxWidth: 110 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  amount: { fontSize: 14, fontWeight: "800", letterSpacing: -0.3 },
  emptyWrap: { alignItems: "center", paddingVertical: 26, gap: 10 },
  empty: { textAlign: "center", fontSize: 13, paddingVertical: 4 },
  pager: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 4, flexWrap: "wrap" },
  pageBtn: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  pageText: { fontSize: 14, fontWeight: "700" },
  ellipsis: { fontSize: 14, paddingHorizontal: 2 },
  showing: { textAlign: "center", fontSize: 12, marginTop: 10 },
  sheetTitle: { fontSize: 18, fontWeight: "800", paddingHorizontal: spacing.lg, marginBottom: 12, marginTop: 4 },
  sheetRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 14, borderRadius: 16, borderWidth: 1 },
  sheetRowText: { fontSize: 15, fontWeight: "600" },
}));
