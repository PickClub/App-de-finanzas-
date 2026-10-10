import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, ScrollView, ActivityIndicator, RefreshControl, useWindowDimensions } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt } from "@/src/format";
import { AppSheet } from "@/src/components/sheets";
import { FOREST, useMontserrat } from "@/src/budgets/shared";
import {
  CAL_KINDS, KIND_COLOR, LEGEND, addDays, dayTitle, eventIcon, monthGrid, monthShort, monthTitle,
  parseYmd, rangeTitle, weekStart, weekdayShort, ymd, type CalEvent, type CalKind,
} from "@/src/calendar/shared";
import { us } from "@/src/ui-scale";

type Mode = "month" | "week" | "list";
const MAX_DOTS = 4;
const LIST_PAGE = 12;

const fetchGrid = (y: number, m: number) => {
  const g = monthGrid(y, m);
  return api.calendarEvents(ymd(g.start), ymd(g.end));
};

function signed(e: { amount: number | null; sign: number }) {
  if (e.amount === null || e.amount === undefined) return "";
  const v = formatCurrencyInt(e.amount);
  return e.sign > 0 ? `+${v}` : e.sign < 0 ? `\u2212${v}` : v;
}

export default function FinancialCalendar() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const mont = useMontserrat();
  const { width } = useWindowDimensions();
  const forest = isDark ? colors.incomeGreen : FOREST;
  const narrow = width < 430;

  const today = useMemo(() => ymd(new Date()), []);
  const [mode, setMode] = useState<Mode>("month");
  const [selected, setSelected] = useState<string>(today);
  const [filters, setFilters] = useState<Set<CalKind>>(() => new Set(CAL_KINDS));
  const [filterOpen, setFilterOpen] = useState(false);
  const [upLimit, setUpLimit] = useState(3);
  const [listPages, setListPages] = useState(1);

  const sel = useMemo(() => parseYmd(selected), [selected]);
  const year = sel.getFullYear();
  const month = sel.getMonth() + 1;
  const grid = useMemo(() => monthGrid(year, month), [year, month]);

  // One range query per visible month grid (the week view reuses it: no refetch).
  const evQ = useQuery({
    queryKey: ["calendar-events", year, month],
    queryFn: () => fetchGrid(year, month),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const sumQ = useQuery({
    queryKey: ["calendar-summary", year, month],
    queryFn: () => api.calendarSummary(year, month),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const allOn = filters.size === CAL_KINDS.length;
  const typesCsv = allOn ? "" : CAL_KINDS.filter((k) => filters.has(k)).join(",");
  const upQ = useQuery({
    queryKey: ["calendar-upcoming", upLimit, typesCsv],
    queryFn: () => (filters.size === 0 ? Promise.resolve({ items: [], total: 0, has_more: false }) : api.calendarUpcoming(upLimit, typesCsv || undefined)),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  // Prefetch adjacent months so month changes feel instant.
  useEffect(() => {
    for (const dm of [-1, 1]) {
      const d = new Date(year, month - 1 + dm, 1);
      const y = d.getFullYear(), m = d.getMonth() + 1;
      qc.prefetchQuery({ queryKey: ["calendar-events", y, m], queryFn: () => fetchGrid(y, m), staleTime: 30_000 });
    }
  }, [qc, year, month]);

  const refreshAll = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["calendar-events"] });
    qc.invalidateQueries({ queryKey: ["calendar-summary"] });
    qc.invalidateQueries({ queryKey: ["calendar-upcoming"] });
  }, [qc]);
  // Data may change in other sections; refresh when coming back (cache kept meanwhile).
  const [focused, setFocused] = useState(false);
  useFocusEffect(useCallback(() => {
    if (focused) refreshAll();
    setFocused(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshAll]));

  const events: CalEvent[] = useMemo(
    () => ((evQ.data?.events || []) as CalEvent[]).filter((e) => filters.has(e.kind)),
    [evQ.data, filters],
  );
  const byDate = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    for (const e of events) {
      const arr = m.get(e.date);
      if (arr) arr.push(e);
      else m.set(e.date, [e]);
    }
    return m;
  }, [events]);
  const dotsByDate = useMemo(() => {
    const m = new Map<string, string[]>();
    byDate.forEach((list, d) => {
      const seen: string[] = [];
      for (const e of list) {
        const c = KIND_COLOR[e.kind];
        if (!seen.includes(c)) seen.push(c);
      }
      m.set(d, seen);
    });
    return m;
  }, [byDate]);

  const dayEvents = byDate.get(selected) || [];
  const dayNet = useMemo(() => {
    const real = dayEvents.filter((e) => e.counts_in_net && e.amount !== null);
    if (!real.length) return null;
    return real.reduce((s, e) => s + e.sign * (e.amount || 0), 0);
  }, [dayEvents]);

  const onSelect = useCallback((d: string) => setSelected(d), []);
  const shiftMonth = (dm: number) => {
    const d = new Date(year, month - 1 + dm, 1);
    const now = new Date();
    const sameAsToday = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    setSelected(sameAsToday ? today : ymd(d));
    setListPages(1);
  };
  const shiftWeek = (dw: number) => setSelected(ymd(addDays(sel, dw * 7)));

  const openEvent = useCallback((e: CalEvent) => {
    const route =
      e.source === "transaction" ? `/transactions/${e.ref_id}` :
      e.source === "recurring" ? `/recurring/${e.ref_id}` :
      e.source === "debt" ? `/debts/${e.ref_id}` :
      `/goals/${e.ref_id}`;
    router.push(route as any);
  }, [router]);

  const subtitleOf = useCallback((e: CalEvent) => {
    const parts = [t(`calendar.sub.${e.subtype}`, { defaultValue: e.subtype })];
    if (!e.realized && (e.status === "pending" || e.status === "overdue")) {
      parts.push(e.partial ? t("calendar.partial") : t(`calendar.${e.status}`));
    } else if (e.status === "completed") parts.push(t("calendar.completed"));
    const detail = e.account || e.category;
    if (detail) parts.push(detail);
    return parts.join(" \u2022 ");
  }, [t]);

  const weekDays = useMemo(() => {
    const s = weekStart(sel);
    return Array.from({ length: 7 }, (_, i) => addDays(s, i));
  }, [sel]);
  const wdays = useMemo(() => weekdayShort(lang), [lang]);

  // ---------- pieces ----------
  const Segmented = (
    <View style={[styles.segment, narrow && { alignSelf: "stretch" }]} testID="cal-segment">
      {(["month", "week", "list"] as Mode[]).map((m) => {
        const on = mode === m;
        return (
          <Pressable
            key={m}
            testID={`cal-mode-${m}`}
            onPress={() => setMode(m)}
            style={[styles.segBtn, narrow && { flex: 1 }, on && { backgroundColor: forest }]}
          >
            <Text style={[styles.segText, mont(), { color: on ? "#fff" : colors.onSurface }]}>{t(`calendar.${m}`)}</Text>
          </Pressable>
        );
      })}
    </View>
  );

  const NavHeader = ({ title, onPrev, onNext }: { title: string; onPrev: () => void; onNext: () => void }) => (
    <View style={styles.navRow}>
      <Pressable testID="cal-prev" accessibilityLabel={t("calendar.prev")} onPress={onPrev} style={({ pressed }) => [styles.arrowBtn, pressed && styles.pressed]}>
        <Ionicons name="chevron-back" size={us(18)} color={colors.onSurface} />
      </Pressable>
      <Text testID="cal-title" style={[styles.navTitle, mont()]} numberOfLines={1} adjustsFontSizeToFit>{title}</Text>
      <Pressable testID="cal-next" accessibilityLabel={t("calendar.next")} onPress={onNext} style={({ pressed }) => [styles.arrowBtn, pressed && styles.pressed]}>
        <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} />
      </Pressable>
      <View style={{ flex: 1 }} />
      {evQ.isFetching ? <ActivityIndicator size="small" color={forest} style={{ marginRight: us(8) }} /> : null}
      <Pressable testID="cal-filter" onPress={() => setFilterOpen(true)} style={({ pressed }) => [styles.filterBtn, pressed && styles.pressed]}>
        <Ionicons name="options-outline" size={us(16)} color={colors.onSurface} />
        <Text style={[styles.filterText, mont()]}>{t("calendar.filter")}</Text>
        {!allOn ? <View style={[styles.filterBadge, { backgroundColor: forest }]} /> : null}
      </Pressable>
    </View>
  );

  const WeekdayRow = (
    <View style={styles.weekRow}>
      {wdays.map((w) => (
        <Text key={w} style={styles.weekday}>{w}</Text>
      ))}
    </View>
  );

  const renderCell = (d: Date, inMonth: boolean, tall = false) => {
    const key = ymd(d);
    return (
      <DayCell
        key={key}
        ymdKey={key}
        day={d.getDate()}
        inMonth={inMonth}
        selected={key === selected}
        isToday={key === today}
        dots={dotsByDate.get(key)}
        onSelect={onSelect}
        tall={tall}
        forest={forest}
        styles={styles}
        mont={mont}
        colors={colors}
      />
    );
  };

  const Legend = (
    <View style={styles.legend}>
      {LEGEND.map((l) => (
        <View key={l.key} style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: l.color }]} />
          <Text style={styles.legendText}>{t(`calendar.legend.${l.key}`)}</Text>
        </View>
      ))}
    </View>
  );

  const ErrorBox = (q: { refetch: () => any }) => (
    <View style={styles.errorBox}>
      <Ionicons name="cloud-offline-outline" size={us(18)} color={colors.muted} />
      <Text style={[styles.muted, { flex: 1 }]}>{t("calendar.loadError")}</Text>
      <Pressable testID="cal-retry" onPress={() => q.refetch()} style={styles.retryBtn}>
        <Text style={[styles.retryText, { color: forest }]}>{t("calendar.retry")}</Text>
      </Pressable>
    </View>
  );

  const EventCard = ({ e, compact }: { e: CalEvent; compact?: boolean }) => {
    const c = KIND_COLOR[e.kind];
    const amtColor = e.sign > 0 ? KIND_COLOR.income : e.sign < 0 ? KIND_COLOR.expense : e.kind === "goal" ? KIND_COLOR.goal : colors.onSurface;
    return (
      <Pressable
        testID={`cal-event-${e.id}`}
        onPress={() => openEvent(e)}
        style={({ pressed }) => [styles.evCard, { backgroundColor: isDark ? c + "1F" : c + "14" }, compact && { flex: 1 }, pressed && styles.pressed]}
      >
        <View style={[styles.evIcon, { backgroundColor: isDark ? c + "33" : c + "22" }]}>
          <Ionicons name={eventIcon(e) as any} size={us(20)} color={c} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.evTitle, mont()]} numberOfLines={1}>{e.title}</Text>
          <Text style={styles.evSub} numberOfLines={1}>{subtitleOf(e)}</Text>
        </View>
        {e.amount !== null ? (
          <View style={{ alignItems: "flex-end", marginLeft: us(8) }}>
            <Text style={[styles.evAmount, mont(), { color: amtColor }]} numberOfLines={1}>{signed(e)}</Text>
            {!e.realized && e.status !== "done" && e.status !== "marked" ? (
              <Text style={styles.plannedTag}>{t("calendar.planned")}</Text>
            ) : null}
          </View>
        ) : null}
        <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} style={{ marginLeft: us(8) }} />
      </Pressable>
    );
  };

  const timed = dayEvents.filter((e) => e.time);
  const allDay = dayEvents.filter((e) => !e.time);
  const TimelineRow = ({ e, label, last }: { e: CalEvent; label: string; last: boolean }) => (
    <View style={styles.tlRow}>
      <Text style={styles.tlTime} numberOfLines={1}>{label}</Text>
      <View style={styles.tlRail}>
        <View style={[styles.tlLine, last && { bottom: "50%" }]} />
        <View style={[styles.tlDot, { backgroundColor: KIND_COLOR[e.kind] }]} />
      </View>
      <EventCard e={e} compact />
    </View>
  );

  const DaySection = (
    <View testID="cal-day-section">
      <View style={styles.dayHead}>
        <Text style={[styles.dayTitle, mont()]} numberOfLines={1} adjustsFontSizeToFit>{dayTitle(sel, lang)}</Text>
        {dayEvents.length ? (
          <View style={styles.capsule} testID="cal-day-capsule">
            <Text style={styles.capText}>{dayEvents.length === 1 ? t("calendar.eventsOne") : t("calendar.eventsN", { count: dayEvents.length })}</Text>
            {dayNet !== null ? (
              <>
                <View style={styles.capSep} />
                <Text style={styles.capText}>{t("calendar.dayTotal")} </Text>
                <Text style={[styles.capAmount, mont(), { color: dayNet >= 0 ? KIND_COLOR.income : KIND_COLOR.expense }]}>
                  {signed({ amount: Math.abs(dayNet), sign: dayNet > 0 ? 1 : dayNet < 0 ? -1 : 0 })}
                </Text>
              </>
            ) : null}
          </View>
        ) : null}
      </View>
      {evQ.isError && !evQ.data ? ErrorBox(evQ) : evQ.isLoading ? (
        <ActivityIndicator color={forest} style={{ marginVertical: us(20) }} />
      ) : !dayEvents.length ? (
        <View style={styles.emptyDay}>
          <Ionicons name="calendar-clear-outline" size={us(22)} color={colors.muted} />
          <Text style={styles.muted}>{t("calendar.emptyDay")}</Text>
        </View>
      ) : (
        <View>
          {timed.map((e, i) => (
            <TimelineRow key={e.id} e={e} label={e.time as string} last={i === timed.length - 1 && !allDay.length} />
          ))}
          {allDay.length ? (
            <>
              <Text style={styles.allDayLabel}>{t("calendar.allDay")}</Text>
              {allDay.map((e, i) => (
                <TimelineRow key={e.id} e={e} label="" last={i === allDay.length - 1} />
              ))}
            </>
          ) : null}
        </View>
      )}
    </View>
  );

  const s = sumQ.data;
  const SummaryCard = ({ testID, color, icon, label, amount, count, note }: any) => (
    <View testID={testID} style={[styles.sumCard, { backgroundColor: isDark ? color + "1F" : color + "12" }]}>
      <View style={{ flexDirection: "row", alignItems: "flex-start", gap: us(6) }}>
        <View style={[styles.sumIcon, { backgroundColor: isDark ? color + "33" : color + "22" }]}>
          <Ionicons name={icon} size={us(18)} color={color} />
        </View>
        <Text style={styles.sumLabel} numberOfLines={2}>{label}</Text>
      </View>
      <Text style={[styles.sumAmount, mont(), { color }]} numberOfLines={1} adjustsFontSizeToFit>{formatCurrencyInt(amount || 0)}</Text>
      <View style={styles.rowBetween}>
        <Text style={styles.sumCount} numberOfLines={1}>{note || (count === 1 ? t("calendar.eventsOne") : t("calendar.eventsN", { count: count || 0 }))}</Text>
        <Ionicons name="stats-chart" size={us(13)} color={color} />
      </View>
    </View>
  );
  const Summary = (
    <View style={{ marginTop: us(spacing.lg) }}>
      {sumQ.isError && !s ? ErrorBox(sumQ) : (
        <>
          <View style={styles.sumRow}>
            <SummaryCard testID="cal-sum-income" color={KIND_COLOR.income} icon="arrow-down" label={t("calendar.incomeMonth")} amount={s?.income?.amount} count={s?.income?.count} />
            <SummaryCard testID="cal-sum-payments" color={KIND_COLOR.expense} icon="arrow-up" label={t("calendar.paymentsMonth")} amount={s?.payments?.amount} count={s?.payments?.count} />
            <SummaryCard testID="cal-sum-bills" color={KIND_COLOR.bill} icon="document-text" label={t("calendar.billsMonth")} amount={s?.bills?.amount} count={s?.bills?.count} />
          </View>
          {s && (s.planned_expenses?.amount > 0 || s.planned_income?.amount > 0) ? (
            <View style={styles.plannedBox} testID="cal-planned">
              <Ionicons name="time-outline" size={us(15)} color={colors.muted} />
              <View style={{ flex: 1 }}>
                <Text style={styles.plannedText}>
                  {[
                    s.planned_expenses?.amount > 0 ? t("calendar.plannedLine", { expense: formatCurrencyInt(s.planned_expenses.amount) }) : null,
                    s.planned_income?.amount > 0 ? t("calendar.plannedIncomeLine", { income: formatCurrencyInt(s.planned_income.amount) }) : null,
                  ].filter(Boolean).join("  \u2022  ")}
                </Text>
                <Text style={styles.plannedNote}>{t("calendar.plannedNote")}</Text>
              </View>
            </View>
          ) : null}
        </>
      )}
    </View>
  );

  const dueText = (e: CalEvent) => {
    const n = e.days_left ?? 0;
    if (e.subtype === "goal_target") return n <= 0 ? t("calendar.targetToday") : t("calendar.targetIn", { count: n });
    if (n < 0) return n === -1 ? t("calendar.overdueOne") : t("calendar.overdueN", { count: -n });
    if (n === 0) return t("calendar.dueToday");
    if (n === 1) return t("calendar.dueTomorrow");
    return t("calendar.dueIn", { count: n });
  };
  const up = upQ.data;
  const Upcoming = (
    <View style={{ marginTop: us(spacing.xl) }} testID="cal-upcoming">
      <View style={styles.rowBetween}>
        <Text style={[styles.sectionTitle, mont()]}>{t("calendar.upcoming")}</Text>
        {up && (up.has_more || upLimit > 3) ? (
          <Pressable testID="cal-see-all" onPress={() => setUpLimit(upLimit > 3 ? 3 : 10)} style={({ pressed }) => [styles.seeAll, pressed && styles.pressed]}>
            <Text style={styles.seeAllText}>{upLimit > 3 ? t("calendar.seeLess") : t("calendar.seeAll")}</Text>
            <Ionicons name={upLimit > 3 ? "chevron-up" : "chevron-forward"} size={us(14)} color={colors.onSurface} />
          </Pressable>
        ) : null}
      </View>
      {upQ.isError && !up ? ErrorBox(upQ) : upQ.isLoading ? (
        <ActivityIndicator color={forest} style={{ marginVertical: us(16) }} />
      ) : !up?.items?.length ? (
        <Text style={[styles.muted, { marginTop: us(10), textAlign: "left" }]}>{t("calendar.noUpcoming")}</Text>
      ) : (
        <View style={{ marginTop: us(10), gap: us(8) }}>
          {up.items.map((e: CalEvent) => {
            const d = parseYmd(e.date);
            const c = KIND_COLOR[e.kind];
            const overdue = (e.days_left ?? 0) < 0;
            return (
              <View key={e.id} style={styles.upRow}>
                <View style={[styles.upDate, overdue && { backgroundColor: KIND_COLOR.expense + "1A" }]}>
                  <Text style={[styles.upDay, mont(), overdue && { color: KIND_COLOR.expense }]}>{d.getDate()}</Text>
                  <Text style={styles.upMonth}>{monthShort(d, lang)}</Text>
                </View>
                <Pressable testID={`cal-up-${e.id}`} onPress={() => openEvent(e)} style={({ pressed }) => [styles.upCard, pressed && styles.pressed]}>
                  <View style={[styles.evIcon, { backgroundColor: isDark ? c + "33" : c + "1C" }]}>
                    <Ionicons name={eventIcon(e) as any} size={us(19)} color={c} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={[styles.evTitle, mont()]} numberOfLines={1}>{e.title}</Text>
                    <Text style={[styles.evSub, overdue && { color: KIND_COLOR.expense }]} numberOfLines={1}>
                      {t(`calendar.sub.${e.subtype}`, { defaultValue: e.subtype })} {"\u2022"} {dueText(e)}
                    </Text>
                  </View>
                  {e.amount !== null ? (
                    <Text style={[styles.evAmount, mont(), { color: e.sign > 0 ? KIND_COLOR.income : e.sign < 0 ? KIND_COLOR.expense : KIND_COLOR.goal, marginLeft: us(8) }]} numberOfLines={1}>{signed(e)}</Text>
                  ) : null}
                  <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} style={{ marginLeft: us(8) }} />
                </Pressable>
              </View>
            );
          })}
          {upLimit > 3 && up.has_more ? (
            <Pressable testID="cal-up-more" onPress={() => setUpLimit(Math.min(50, upLimit + 10))} style={({ pressed }) => [styles.moreBtn, pressed && styles.pressed]}>
              {upQ.isFetching ? <ActivityIndicator size="small" color={forest} /> : <Text style={[styles.moreText, { color: forest }]}>{t("calendar.loadMore")}</Text>}
            </Pressable>
          ) : null}
        </View>
      )}
    </View>
  );

  // ---------- List view (agenda of the visible month, incremental) ----------
  const monthKey = `${year}-${month < 10 ? "0" + month : month}`;
  const listGroups = useMemo(() => {
    const out: { date: string; items: CalEvent[] }[] = [];
    byDate.forEach((items, date) => {
      if (date.startsWith(monthKey)) out.push({ date, items });
    });
    return out.sort((a, b) => a.date.localeCompare(b.date));
  }, [byDate, monthKey]);
  const shownGroups = listGroups.slice(0, listPages * LIST_PAGE);
  const ListView = (
    <View testID="cal-list">
      <View style={styles.card}>
        <NavHeader title={monthTitle(sel, lang)} onPrev={() => shiftMonth(-1)} onNext={() => shiftMonth(1)} />
      </View>
      {evQ.isError && !evQ.data ? ErrorBox(evQ) : evQ.isLoading ? (
        <ActivityIndicator color={forest} style={{ marginVertical: us(24) }} />
      ) : !listGroups.length ? (
        <View style={styles.emptyDay}>
          <Ionicons name="calendar-clear-outline" size={us(22)} color={colors.muted} />
          <Text style={styles.muted}>{t("calendar.emptyMonth")}</Text>
        </View>
      ) : (
        <View style={{ marginTop: us(spacing.md), gap: us(14) }}>
          {shownGroups.map((g) => {
            const d = parseYmd(g.date);
            const isT = g.date === today;
            return (
              <View key={g.date} style={styles.listGroup} testID={`cal-group-${g.date}`}>
                <View style={[styles.upDate, isT && { backgroundColor: forest }]}>
                  <Text style={[styles.upDay, mont(), isT && { color: "#fff" }]}>{d.getDate()}</Text>
                  <Text style={[styles.upMonth, isT && { color: "#ffffffCC" }]}>{monthShort(d, lang)}</Text>
                </View>
                <View style={{ flex: 1, gap: us(6) }}>
                  <Text style={styles.listDayName} numberOfLines={1}>{dayTitle(d, lang)}</Text>
                  {g.items.map((e) => (
                    <View key={e.id}>
                      {e.time ? <Text style={styles.listTime}>{e.time}</Text> : null}
                      <EventCard e={e} />
                    </View>
                  ))}
                </View>
              </View>
            );
          })}
          {listGroups.length > shownGroups.length ? (
            <Pressable testID="cal-list-more" onPress={() => setListPages(listPages + 1)} style={({ pressed }) => [styles.moreBtn, pressed && styles.pressed]}>
              <Text style={[styles.moreText, { color: forest }]}>{t("calendar.loadMore")}</Text>
            </Pressable>
          ) : null}
        </View>
      )}
    </View>
  );

  const monthEmpty = !evQ.isLoading && !evQ.isError && events.length === 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}
        refreshControl={<RefreshControl refreshing={false} onRefresh={refreshAll} tintColor={forest} />}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={[styles.header, narrow && { flexWrap: "wrap" }]}>
          <Pressable testID="cal-back" onPress={() => router.back()} style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}>
            <Ionicons name="arrow-back" size={us(22)} color={colors.onSurface} />
          </Pressable>
          <Text style={[styles.title, mont()]} numberOfLines={1} adjustsFontSizeToFit>{t("calendar.title")}</Text>
          {!narrow ? Segmented : null}
        </View>
        {narrow ? <View style={{ marginBottom: us(spacing.md) }}>{Segmented}</View> : null}

        {mode === "list" ? ListView : (
          <>
            <View style={styles.card} testID={mode === "month" ? "cal-month" : "cal-week"}>
              {mode === "month" ? (
                <NavHeader title={monthTitle(sel, lang)} onPrev={() => shiftMonth(-1)} onNext={() => shiftMonth(1)} />
              ) : (
                <NavHeader title={rangeTitle(weekDays[0], weekDays[6], lang)} onPrev={() => shiftWeek(-1)} onNext={() => shiftWeek(1)} />
              )}
              {WeekdayRow}
              {mode === "month" ? (
                Array.from({ length: grid.days.length / 7 }, (_, r) => (
                  <View key={r} style={styles.gridRow}>
                    {grid.days.slice(r * 7, r * 7 + 7).map((d) => renderCell(d, d.getMonth() + 1 === month))}
                  </View>
                ))
              ) : (
                <View style={styles.gridRow}>{weekDays.map((d) => renderCell(d, true, true))}</View>
              )}
              {Legend}
              {monthEmpty ? <Text style={[styles.muted, { marginTop: us(6) }]} testID="cal-month-empty">{t("calendar.emptyMonth")}</Text> : null}
            </View>
            <View style={{ marginTop: us(spacing.lg) }}>{DaySection}</View>
          </>
        )}

        {Summary}
        {Upcoming}
      </ScrollView>

      <AppSheet visible={filterOpen} onClose={() => setFilterOpen(false)} testID="cal-filter-sheet">
        <View style={{ paddingBottom: us(8) }}>
          <Text style={[styles.sheetTitle, mont()]}>{t("calendar.filterTitle")}</Text>
          <Text style={[styles.muted, { textAlign: "left", marginBottom: us(10) }]}>{t("calendar.filterHint")}</Text>
          {CAL_KINDS.map((k) => {
            const on = filters.has(k);
            return (
              <Pressable
                key={k}
                testID={`cal-filter-${k}`}
                onPress={() => setFilters((prev) => {
                  const n = new Set(prev);
                  if (n.has(k)) n.delete(k); else n.add(k);
                  return n;
                })}
                style={({ pressed }) => [styles.filterRow, pressed && styles.pressed]}
              >
                <View style={[styles.legendDot, { backgroundColor: KIND_COLOR[k], width: us(10), height: us(10), borderRadius: us(5) }]} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.filterLabel}>{t(`calendar.kinds.${k}`)}</Text>
                  {k === "bill" ? <Text style={styles.filterHint}>{t("calendar.billsSoon")}</Text> : null}
                </View>
                <Ionicons name={on ? "checkbox" : "square-outline"} size={us(22)} color={on ? forest : colors.muted} />
              </Pressable>
            );
          })}
          <View style={{ flexDirection: "row", gap: us(10), marginTop: us(14) }}>
            <Pressable testID="cal-filter-all" onPress={() => setFilters(new Set(CAL_KINDS))} style={[styles.sheetBtn, { backgroundColor: colors.surfaceTertiary }]}>
              <Text style={[styles.sheetBtnText, { color: colors.onSurface }]}>{t("calendar.showAll")}</Text>
            </Pressable>
            <Pressable testID="cal-filter-done" onPress={() => setFilterOpen(false)} style={[styles.sheetBtn, { backgroundColor: forest }]}>
              <Text style={[styles.sheetBtnText, { color: "#fff" }]}>{t("calendar.done")}</Text>
            </Pressable>
          </View>
        </View>
      </AppSheet>
    </View>
  );
}

type CellProps = {
  ymdKey: string; day: number; inMonth: boolean; selected: boolean; isToday: boolean;
  dots?: string[]; onSelect: (d: string) => void; tall: boolean; forest: string;
  styles: any; mont: any; colors: any;
};

const DayCell = React.memo(function DayCell({ ymdKey, day, inMonth, selected, isToday, dots, onSelect, tall, forest, styles, mont, colors }: CellProps) {
  const shown = (dots || []).slice(0, MAX_DOTS);
  const extra = (dots?.length || 0) - shown.length;
  return (
    <Pressable
      testID={`cal-day-${ymdKey}`}
      onPress={() => onSelect(ymdKey)}
      style={[
        styles.cell,
        tall && styles.cellTall,
        !inMonth && styles.cellOut,
        selected && { backgroundColor: forest },
        isToday && !selected && { borderColor: forest, borderWidth: 1.5 },
      ]}
    >
      <Text style={[styles.cellText, mont(), !inMonth && { color: colors.muted, opacity: 0.6 }, selected && { color: "#fff" }]}>{day}</Text>
      <View style={styles.dots}>
        {shown.map((c) => <View key={c} style={[styles.dot, { backgroundColor: c }, !inMonth && { opacity: 0.5 }]} />)}
        {extra > 0 ? <Text style={[styles.dotMore, selected && { color: "#fff" }]}>+</Text> : null}
      </View>
    </Pressable>
  );
});

const useStyles = makeStyles((colors, scheme) => {
  const dark = scheme === "dark";
  const shadow = { shadowColor: "#126046", shadowOpacity: dark ? 0 : 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: dark ? 0 : 1 };
  return {
    pressed: { opacity: 0.7 },
    header: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 14 },
    backBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", ...shadow },
    title: { flex: 1, fontSize: 21, color: colors.onSurface },
    segment: { flexDirection: "row", gap: 6, alignSelf: "flex-start" },
    segBtn: { paddingHorizontal: 14, height: 36, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: dark ? colors.surfaceTertiary : "#F1ECE6" },
    segText: { fontSize: 13.5 },
    card: { backgroundColor: colors.surfaceSecondary, borderRadius: 24, padding: 12, ...shadow },
    navRow: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
    arrowBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
    navTitle: { fontSize: 18, color: colors.onSurface, flexShrink: 1 },
    filterBtn: { flexDirection: "row", alignItems: "center", gap: 6, height: 36, paddingHorizontal: 12, borderRadius: 999, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
    filterText: { fontSize: 13, color: colors.onSurface },
    filterBadge: { width: 7, height: 7, borderRadius: 4, marginLeft: 2 },
    weekRow: { flexDirection: "row", marginTop: 4, marginBottom: 6 },
    weekday: { flex: 1, textAlign: "center", fontSize: 12, color: colors.muted },
    gridRow: { flexDirection: "row", marginBottom: 6 },
    cell: { flex: 1, marginHorizontal: 2.5, height: 50, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: dark ? colors.surfaceTertiary + "66" : "#FBF7F2", borderWidth: 1.5, borderColor: "transparent" },
    cellTall: { height: 62 },
    cellOut: { backgroundColor: dark ? colors.surfaceTertiary + "33" : "#F2EDE8" },
    cellText: { fontSize: 15, color: colors.onSurface },
    dots: { flexDirection: "row", alignItems: "center", gap: 3, height: 8, marginTop: 4 },
    dot: { width: 6, height: 6, borderRadius: 3 },
    dotMore: { fontSize: 10, lineHeight: 10, color: colors.muted, fontWeight: "800" },
    legend: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 6, columnGap: 10, marginTop: 6, paddingHorizontal: 4 },
    legendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
    legendDot: { width: 9, height: 9, borderRadius: 5 },
    legendText: { fontSize: 12, color: colors.muted },
    dayHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 10, flexWrap: "wrap" },
    dayTitle: { fontSize: 17, color: colors.onSurface, flexShrink: 1 },
    capsule: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, height: 32, borderRadius: 999, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    capText: { fontSize: 12.5, color: colors.onSurface },
    capSep: { width: 1, height: 14, backgroundColor: colors.border, marginHorizontal: 8 },
    capAmount: { fontSize: 13 },
    tlRow: { flexDirection: "row", alignItems: "center", minHeight: 70, paddingVertical: 4 },
    tlTime: { width: 46, fontSize: 12.5, color: colors.muted },
    tlRail: { width: 22, alignSelf: "stretch", alignItems: "center", justifyContent: "center" },
    tlLine: { position: "absolute", top: 0, bottom: 0, width: 2, backgroundColor: colors.border },
    tlDot: { width: 11, height: 11, borderRadius: 6, borderWidth: 2, borderColor: colors.surface },
    allDayLabel: { fontSize: 12.5, color: colors.muted, marginTop: 6, marginBottom: 2, fontWeight: "700" },
    evCard: { flexDirection: "row", alignItems: "center", minHeight: 62, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 18, marginLeft: 4 },
    evIcon: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center", marginRight: 10 },
    evTitle: { fontSize: 14.5, color: colors.onSurface },
    evSub: { fontSize: 12.5, color: colors.muted, marginTop: 2 },
    evAmount: { fontSize: 15 },
    plannedTag: { fontSize: 10.5, color: colors.muted, marginTop: 1 },
    emptyDay: { alignItems: "center", paddingVertical: 22, gap: 8 },
    muted: { color: colors.muted, fontSize: 13, textAlign: "center" },
    errorBox: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 16, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, marginTop: 8 },
    retryBtn: { paddingHorizontal: 12, height: 34, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
    retryText: { fontSize: 13, fontWeight: "700" },
    rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    sumRow: { flexDirection: "row", gap: 8 },
    sumCard: { flex: 1, borderRadius: 18, padding: 10, gap: 6, minHeight: 104 },
    sumIcon: { width: 32, height: 32, borderRadius: 10, alignItems: "center", justifyContent: "center" },
    sumLabel: { flex: 1, fontSize: 11.5, color: colors.muted },
    sumAmount: { fontSize: 19 },
    sumCount: { fontSize: 11.5, color: colors.muted, flex: 1 },
    plannedBox: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 10, padding: 10, borderRadius: 14, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    plannedText: { fontSize: 12.5, color: colors.onSurface, fontWeight: "700" },
    plannedNote: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
    sectionTitle: { fontSize: 17, color: colors.onSurface },
    seeAll: { flexDirection: "row", alignItems: "center", gap: 4, height: 34, paddingHorizontal: 12, borderRadius: 999, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    seeAllText: { fontSize: 12.5, color: colors.onSurface, fontWeight: "600" },
    upRow: { flexDirection: "row", alignItems: "center", gap: 8 },
    upDate: { width: 46, height: 52, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: dark ? colors.surfaceTertiary : "#F1ECE6" },
    upDay: { fontSize: 17, color: colors.onSurface },
    upMonth: { fontSize: 10.5, color: colors.muted, marginTop: -1 },
    upCard: { flex: 1, flexDirection: "row", alignItems: "center", minHeight: 60, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 18, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    moreBtn: { alignSelf: "center", height: 40, paddingHorizontal: 20, borderRadius: 999, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, marginTop: 4 },
    moreText: { fontSize: 13, fontWeight: "700" },
    listGroup: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
    listDayName: { fontSize: 12.5, color: colors.muted, fontWeight: "700", marginTop: 2 },
    listTime: { fontSize: 11.5, color: colors.muted, marginBottom: 3, marginLeft: 6 },
    sheetTitle: { fontSize: 18, color: colors.onSurface, marginBottom: 4 },
    filterRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48, paddingVertical: 6 },
    filterLabel: { fontSize: 14.5, color: colors.onSurface, fontWeight: "600" },
    filterHint: { fontSize: 11.5, color: colors.muted },
    sheetBtn: { flex: 1, height: 48, borderRadius: 999, alignItems: "center", justifyContent: "center" },
    sheetBtnText: { fontSize: 14.5, fontWeight: "700" },
  };
});
