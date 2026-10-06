import React, { useEffect, useMemo, useState } from "react";
import { View, StyleSheet } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { AppSheet } from "@/src/components/sheets";
import { useTheme, radius } from "@/src/theme";

import { us, scaleStyles } from "@/src/ui-scale";
export type DateRange = { start: number; end: number };

const WEEKDAYS = ["L", "M", "M", "J", "V", "S", "D"];
const MONTHS = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

// midnight of a given date
function startOfDay(d: Date) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}
function endOfDay(d: Date) {
  const x = new Date(d);
  x.setHours(23, 59, 59, 999);
  return x;
}
function sameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
function longEs(d: Date) {
  return `${d.getDate()} de ${MONTHS[d.getMonth()].toLowerCase()} de ${d.getFullYear()}`;
}

/**
 * Date / date-range selection bottom sheet.
 * Reuses the app's AppSheet primitive + theme tokens so it feels native:
 * pearl surface, mint accents, dark-green selected dates, rounded corners,
 * Spanish labels. Supports single-day and start→end range selection with
 * month navigation. Nothing is applied until the user taps "Aplicar".
 */
export function DateRangeSheet({
  visible,
  value,
  onClose,
  onApply,
}: {
  visible: boolean;
  value: DateRange | null;
  onClose: () => void;
  onApply: (range: DateRange | null) => void;
}) {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";

  const green = isDark ? "#2CA079" : "#126046";
  const mint = isDark ? "rgba(44,160,121,0.22)" : "#DCEBE0";
  const gridLine = colors.border;

  const [viewMonth, setViewMonth] = useState<Date>(new Date());
  const [selStart, setSelStart] = useState<Date | null>(null);
  const [selEnd, setSelEnd] = useState<Date | null>(null);

  // Initialise from the incoming value each time the sheet opens.
  useEffect(() => {
    if (!visible) return;
    if (value) {
      const s = new Date(value.start);
      const e = new Date(value.end);
      setSelStart(startOfDay(s));
      setSelEnd(sameDay(s, e) ? null : startOfDay(e));
      setViewMonth(new Date(s.getFullYear(), s.getMonth(), 1));
    } else {
      setSelStart(null);
      setSelEnd(null);
      setViewMonth(new Date());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const cells = useMemo(() => {
    const y = viewMonth.getFullYear();
    const m = viewMonth.getMonth();
    const first = new Date(y, m, 1);
    const lead = (first.getDay() + 6) % 7; // Monday-first offset
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const arr: (Date | null)[] = [];
    for (let i = 0; i < lead; i++) arr.push(null);
    for (let d = 1; d <= daysInMonth; d++) arr.push(new Date(y, m, d));
    while (arr.length % 7 !== 0) arr.push(null);
    const rows: (Date | null)[][] = [];
    for (let i = 0; i < arr.length; i += 7) rows.push(arr.slice(i, i + 7));
    return rows;
  }, [viewMonth]);

  const onDayPress = (d: Date) => {
    const day = startOfDay(d);
    if (!selStart || (selStart && selEnd)) {
      // start a fresh selection
      setSelStart(day);
      setSelEnd(null);
    } else {
      // we have a start, pick the end
      if (day.getTime() < selStart.getTime()) {
        setSelStart(day);
        setSelEnd(null);
      } else if (day.getTime() === selStart.getTime()) {
        setSelEnd(null);
      } else {
        setSelEnd(day);
      }
    }
  };

  const dayState = (d: Date) => {
    if (!selStart) return "none";
    const t = d.getTime();
    const s = selStart.getTime();
    if (!selEnd) return t === s ? "single" : "none";
    const e = selEnd.getTime();
    if (t === s) return "start";
    if (t === e) return "end";
    if (t > s && t < e) return "range";
    return "none";
  };

  const applyDisabled = !selStart;

  const handleApply = () => {
    if (!selStart) {
      onApply(null);
      return;
    }
    const start = startOfDay(selStart).getTime();
    const end = endOfDay(selEnd || selStart).getTime();
    onApply({ start, end });
  };

  const isRange = !!(selStart && selEnd);
  const summaryText = selStart
    ? isRange
      ? `${longEs(selStart)} — ${longEs(selEnd!)}`
      : longEs(selStart)
    : "Ninguna fecha seleccionada";
  const kindLabel = !selStart ? "—" : isRange ? "Rango" : "Un solo día";

  return (
    <AppSheet visible={visible} onClose={onClose} testID="date-range-sheet">
      {/* Header */}
      <View style={st.headRow}>
        <View style={{ flex: 1, paddingRight: us(12) }}>
          <Text style={[st.title, { color: colors.onSurface }]}>Selecciona un período</Text>
          <Text style={[st.subtitle, { color: colors.muted }]}>
            Elige un rango de fechas para filtrar tus movimientos.
          </Text>
        </View>
        <Pressable
          testID="date-sheet-close"
          onPress={onClose}
          style={[st.closeBtn, { backgroundColor: colors.surfaceTertiary }]}
          hitSlop={8}
        >
          <Ionicons name="close" size={us(18)} color={colors.muted} />
        </Pressable>
      </View>

      {/* Month navigation */}
      <View style={st.monthNav}>
        <Pressable
          testID="date-prev-month"
          onPress={() => setViewMonth((v) => new Date(v.getFullYear(), v.getMonth() - 1, 1))}
          style={[st.navBtn, { backgroundColor: colors.surfaceTertiary }]}
          hitSlop={8}
        >
          <Ionicons name="chevron-back" size={us(18)} color={colors.onSurface} />
        </Pressable>
        <Text style={[st.monthLabel, { color: colors.onSurface }]}>
          {MONTHS[viewMonth.getMonth()]} {viewMonth.getFullYear()}
        </Text>
        <Pressable
          testID="date-next-month"
          onPress={() => setViewMonth((v) => new Date(v.getFullYear(), v.getMonth() + 1, 1))}
          style={[st.navBtn, { backgroundColor: colors.surfaceTertiary }]}
          hitSlop={8}
        >
          <Ionicons name="chevron-forward" size={us(18)} color={colors.onSurface} />
        </Pressable>
      </View>

      {/* Weekday header */}
      <View style={st.weekRow}>
        {WEEKDAYS.map((w, i) => (
          <View key={i} style={st.cell}>
            <Text style={[st.weekLabel, { color: colors.muted }]}>{w}</Text>
          </View>
        ))}
      </View>

      {/* Day grid */}
      <View>
        {cells.map((row, ri) => (
          <View key={ri} style={st.weekRow}>
            {row.map((d, ci) => {
              if (!d) return <View key={ci} style={st.cell} />;
              const state = dayState(d);
              const endpoint = state === "single" || state === "start" || state === "end";
              const inRange = state === "range";
              return (
                <View key={ci} style={st.cell}>
                  <Pressable
                    testID={`date-day-${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`}
                    onPress={() => onDayPress(d)}
                    style={[
                      st.dayBtn,
                      inRange && { backgroundColor: mint },
                      endpoint && { backgroundColor: green },
                    ]}
                  >
                    <Text
                      style={[
                        st.dayText,
                        { color: colors.onSurface },
                        inRange && { color: green, fontWeight: "800" },
                        endpoint && { color: "#FFFFFF", fontWeight: "800" },
                      ]}
                    >
                      {d.getDate()}
                    </Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        ))}
      </View>

      {/* Selected-period summary */}
      <View style={[st.divider, { backgroundColor: gridLine }]} />
      <Text style={[st.selLabel, { color: colors.muted }]}>Período seleccionado</Text>
      <View style={[st.summaryRow, { backgroundColor: colors.surfaceTertiary, borderColor: gridLine }]}>
        <View style={[st.summaryIcon, { backgroundColor: mint }]}>
          <Ionicons name="calendar-outline" size={us(16)} color={green} />
        </View>
        <Text style={[st.summaryText, { color: colors.onSurface }]}>
          {summaryText}
        </Text>
        <View style={[st.kindPill, { backgroundColor: mint }]}>
          <Text style={[st.kindText, { color: green }]}>{kindLabel}</Text>
        </View>
      </View>

      {/* Apply */}
      <Pressable
        testID="date-apply"
        onPress={handleApply}
        disabled={applyDisabled}
        style={[st.applyBtn, { backgroundColor: green, opacity: applyDisabled ? 0.5 : 1 }]}
      >
        <Text style={st.applyText}>Aplicar</Text>
      </Pressable>
    </AppSheet>
  );
}

const st = StyleSheet.create(scaleStyles({
  headRow: { flexDirection: "row", alignItems: "flex-start", marginBottom: 14 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.3 },
  subtitle: { fontSize: 13, marginTop: 4, lineHeight: 18 },
  closeBtn: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  monthNav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  navBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  monthLabel: { fontSize: 16, fontWeight: "800", letterSpacing: -0.2 },
  weekRow: { flexDirection: "row" },
  cell: { flex: 1, alignItems: "center", justifyContent: "center", height: 42 },
  weekLabel: { fontSize: 12.5, fontWeight: "700" },
  dayBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  dayText: { fontSize: 14.5, fontWeight: "600" },
  divider: { height: 1, marginTop: 8, marginBottom: 14 },
  selLabel: { fontSize: 13, fontWeight: "700", marginBottom: 10 },
  summaryRow: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: radius.cardLg,
    borderWidth: 1,
    paddingVertical: 12,
    paddingHorizontal: 12,
    gap: 10,
  },
  summaryIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  summaryText: { flex: 1, fontSize: 14, fontWeight: "700" },
  kindPill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  kindText: { fontSize: 12.5, fontWeight: "800" },
  applyBtn: {
    alignSelf: "stretch",
    marginTop: 18,
    paddingVertical: 16,
    borderRadius: radius.pill,
    alignItems: "center",
  },
  applyText: { color: "#FFFFFF", fontWeight: "800", fontSize: 16 },
}));
