import React, { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { BackHandler, View, StyleSheet } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import {
  BottomSheetBackdrop,
  BottomSheetModal,
  BottomSheetView,
  useBottomSheetTimingConfigs,
  type BottomSheetBackdropProps,
} from "@gorhom/bottom-sheet";
import { Easing } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, radius, spacing } from "@/src/theme";

import { us, scaleStyles } from "@/src/ui-scale";
export type DateRange = { start: number; end: number };
export type DateRangeSheetHandle = {
  open: (value: DateRange | null) => void;
  close: () => void;
};

const WEEKDAYS = ["L", "M", "M", "J", "V", "S", "D"];
const OPEN_EASING = Easing.out(Easing.cubic);
const CLOSE_EASING = Easing.in(Easing.cubic);
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
 * Uses the existing Reanimated sheet provider + the same theme tokens:
 * pearl surface, mint accents, dark-green selected dates, rounded corners,
 * Spanish labels. Supports single-day and start→end range selection with
 * month navigation. Nothing is applied until the user taps "Aplicar".
 */
// Opening is local to this component: Home and its charts do not re-render.
export const DateRangeSheet = memo(forwardRef<DateRangeSheetHandle, {
  onApply: (range: DateRange | null) => void;
}>(function DateRangeSheet({ onApply }, ref) {
  const { colors, scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const isDark = scheme === "dark";
  const sheetRef = useRef<BottomSheetModal>(null);
  const presented = useRef(false);
  const closing = useRef(false);
  const [isOpen, setIsOpen] = useState(false);
  const animationConfigs = useBottomSheetTimingConfigs({
    duration: 260,
    easing: OPEN_EASING,
  });
  const closeAnimationConfigs = useBottomSheetTimingConfigs({
    duration: 200,
    easing: CLOSE_EASING,
  });

  const green = isDark ? "#2CA079" : "#126046";
  const mint = isDark ? "rgba(44,160,121,0.22)" : "#DCEBE0";
  const gridLine = colors.border;

  const [viewMonth, setViewMonth] = useState<Date>(new Date());
  const [selStart, setSelStart] = useState<Date | null>(null);
  const [selEnd, setSelEnd] = useState<Date | null>(null);

  const close = useCallback(() => {
    if (!presented.current || closing.current) return;
    closing.current = true;
    sheetRef.current?.dismiss(closeAnimationConfigs);
  }, [closeAnimationConfigs]);

  const open = useCallback((value: DateRange | null) => {
    if (presented.current) return;
    // Prepare the draft before presenting; no post-open effect / second grid.
    let month: Date;
    if (value) {
      const s = new Date(value.start);
      const e = new Date(value.end);
      setSelStart(startOfDay(s));
      setSelEnd(sameDay(s, e) ? null : startOfDay(e));
      month = new Date(s.getFullYear(), s.getMonth(), 1);
    } else {
      setSelStart(null);
      setSelEnd(null);
      month = new Date();
    }
    // Keep the cached month grid when re-opening the same month.
    setViewMonth((current) => current.getFullYear() === month.getFullYear()
      && current.getMonth() === month.getMonth() ? current : month);
    presented.current = true;
    closing.current = false;
    setIsOpen(true);
    sheetRef.current?.present();
  }, []);

  useImperativeHandle(ref, () => ({ open, close }), [open, close]);

  useEffect(() => {
    if (!isOpen) return;
    const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
      close();
      return true;
    });
    return () => subscription.remove();
  }, [isOpen, close]);

  const handleDismiss = useCallback(() => {
    presented.current = false;
    closing.current = false;
    setIsOpen(false);
  }, []);

  const renderBackdrop = useCallback((props: BottomSheetBackdropProps) => (
    <BottomSheetBackdrop
      {...props}
      appearsOnIndex={0}
      disappearsOnIndex={-1}
      opacity={0.45}
      pressBehavior="none"
      onPress={close}
      style={[props.style, st.backdrop]}
    />
  ), [close]);

  const renderHandle = useCallback(() => (
    <View style={st.handle}>
      <View style={[st.grip, { backgroundColor: colors.borderStrong }]} />
    </View>
  ), [colors.borderStrong]);

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
    if (closing.current) return;
    if (!selStart) {
      onApply(null);
      close();
      return;
    }
    const start = startOfDay(selStart).getTime();
    const end = endOfDay(selEnd || selStart).getTime();
    onApply({ start, end });
    close();
  };

  const isRange = !!(selStart && selEnd);
  const summaryText = selStart
    ? isRange
      ? `${longEs(selStart)} — ${longEs(selEnd!)}`
      : longEs(selStart)
    : "Ninguna fecha seleccionada";
  const kindLabel = !selStart ? "—" : isRange ? "Rango" : "Un solo día";

  return (
    <BottomSheetModal
      ref={sheetRef}
      enableDynamicSizing
      enablePanDownToClose={false}
      enableContentPanningGesture={false}
      enableHandlePanningGesture={false}
      animationConfigs={animationConfigs}
      backdropComponent={renderBackdrop}
      handleComponent={renderHandle}
      backgroundStyle={[st.sheetBackground, { backgroundColor: colors.surface, borderColor: colors.border }]}
      style={st.sheetShadow}
      topInset={insets.top}
      onDismiss={handleDismiss}
    >
    <BottomSheetView testID="date-range-sheet" style={[st.sheetContent, { paddingBottom: insets.bottom + us(spacing.lg) }]}>
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
          onPress={close}
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
    </BottomSheetView>
    </BottomSheetModal>
  );
}));

const st = StyleSheet.create(scaleStyles({
  sheetContent: { paddingHorizontal: spacing.lg },
  sheetBackground: { borderTopLeftRadius: radius.cardLg, borderTopRightRadius: radius.cardLg, borderBottomLeftRadius: 0, borderBottomRightRadius: 0, borderWidth: 1 },
  sheetShadow: { shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 24, shadowOffset: { width: 0, height: -8 }, elevation: 24 },
  backdrop: { backgroundColor: "#14100C" },
  handle: { paddingTop: 10 },
  grip: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, marginBottom: 14 },
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
