import i18n, { localeTag, tr, useTranslation as useInterfaceLanguage } from "@/src/i18n";

import React, { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Modal, ScrollView, View, StyleSheet, useWindowDimensions } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, radius, spacing } from "@/src/theme";
import Animated, { cancelAnimation, Easing, ReduceMotion, runOnJS, useAnimatedStyle, useSharedValue, withTiming } from "react-native-reanimated";

import { us, scaleStyles } from "@/src/ui-scale";
export type DateRange = { start: number; end: number };
export type DateRangeOrigin = { x: number; y: number };
export type DateRangeSheetHandle = {
  open: (value: DateRange | null, origin?: DateRangeOrigin) => void;
  close: () => void;
};

function monthNames(language: string = i18n.language) {
  return Array.from({ length: 12 }, (_, month) => {
    const value = new Date(2024, month, 1).toLocaleDateString(localeTag(language), { month: "long" });
    return value.charAt(0).toUpperCase() + value.slice(1);
  });
}
function weekdayNames(language: string = i18n.language) {
  return Array.from({ length: 7 }, (_, day) => new Date(2024, 0, day + 1).toLocaleDateString(localeTag(language), { weekday: "narrow" }));
}

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
function longEs(d: Date, language: string = i18n.language) {
  return d.toLocaleDateString(localeTag(language), { day: "numeric", month: "long", year: "numeric" });
}

/**
 * Centered date/date-range picker. Selection stays local until Apply is pressed.
 * The public imperative API and calendar content are shared by existing callers.
 */
// Opening is local to this component: Home and its charts do not re-render.
export const DateRangeSheet = memo(forwardRef<DateRangeSheetHandle, {
  onApply: (range: DateRange | null) => void;
  allowClear?: boolean;
}>(function DateRangeSheet({ onApply, allowClear = false }, ref) {
  useInterfaceLanguage();
  const language = i18n.language;
  const months = useMemo(() => monthNames(language), [language]);
  const weekdays = useMemo(() => weekdayNames(language), [language]);
  const { colors, scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const isDark = scheme === "dark";
  const { height } = useWindowDimensions();
  const [modalHeight, setModalHeight] = useState<number | null>(null);
  const maxHeight = Math.max(0, (modalHeight ?? height) - insets.top - insets.bottom - 2 * us(16));
  const presented = useRef(false);
  const closing = useRef(false);
  const [isOpen, setIsOpen] = useState(false);
  const [animated, setAnimated] = useState(false);
  const modalRoot = useRef<View>(null);
  const mounted = useRef(true);
  const presentationId = useRef(0);
  const transition = useRef<{
    origin: DateRangeOrigin;
    root?: { x: number; y: number; width: number; height: number };
    card?: { x: number; y: number; width: number; height: number };
    shown: boolean;
    started: boolean;
  } | null>(null);
  const progress = useSharedValue(0);
  const originOffset = useSharedValue({ x: 0, y: 0 });
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; presentationId.current++; cancelAnimation(progress); };
  }, [progress]);

  const finishClose = useCallback((id: number) => {
    if (!mounted.current || presentationId.current !== id) return;
    presented.current = false;
    setIsOpen(false);
  }, []);

  // Native layout supplies the final, untransformed card bounds. Never measure an animated card.
  const revealWhenReady = useCallback(() => {
    const current = transition.current;
    if (!current?.shown || !current.root || !current.card || closing.current || !presented.current) return;
    const { root, card, origin } = current;
    originOffset.value = {
      x: Math.max(root.x, Math.min(origin.x, root.x + root.width)) - (root.x + card.x + card.width / 2),
      y: Math.max(root.y, Math.min(origin.y, root.y + root.height)) - (root.y + card.y + card.height / 2),
    };
    if (current.started) return;
    current.started = true;
    progress.value = withTiming(1, { duration: 280, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System });
  }, [originOffset, progress]);

  const measureModalRoot = useCallback(() => {
    const current = transition.current;
    if (!current || closing.current) return;
    modalRoot.current?.measureInWindow((x, y, width, measuredHeight) => {
      if (!mounted.current || transition.current !== current || closing.current
        || ![x, y, width, measuredHeight].every(Number.isFinite) || width <= 0 || measuredHeight <= 0) return;
      current.root = { x, y, width, height: measuredHeight };
      revealWhenReady();
    });
  }, [revealWhenReady]);

  const cardAnimation = useAnimatedStyle(() => ({
    opacity: progress.value,
    transform: [
      { translateX: originOffset.value.x * (1 - progress.value) },
      { translateY: originOffset.value.y * (1 - progress.value) },
      { scale: 0.08 + 0.92 * progress.value },
    ],
  }));
  const backdropAnimation = useAnimatedStyle(() => ({ opacity: progress.value }));
  const green = isDark ? "#2CA079" : "#126046";
  const mint = isDark ? "rgba(44,160,121,0.22)" : "#DCEBE0";
  const gridLine = colors.border;

  const [viewMonth, setViewMonth] = useState<Date>(new Date());
  const [selStart, setSelStart] = useState<Date | null>(null);
  const [selEnd, setSelEnd] = useState<Date | null>(null);

  const close = useCallback(() => {
    if (!presented.current || closing.current) return;
    closing.current = true;
    const id = presentationId.current;
    if (!transition.current?.started) { finishClose(id); return; }
    progress.value = withTiming(0, { duration: 220, easing: Easing.in(Easing.cubic), reduceMotion: ReduceMotion.System }, finished => {
      if (finished) runOnJS(finishClose)(id);
    });
  }, [finishClose, progress]);

  const open = useCallback((value: DateRange | null, origin?: DateRangeOrigin) => {
    if (presented.current || !mounted.current) return;
    const anchored = !!origin && Number.isFinite(origin.x) && Number.isFinite(origin.y);
    presentationId.current++;
    transition.current = anchored ? { origin, shown: false, started: false } : null;
    progress.value = anchored ? 0 : 1;
    setAnimated(anchored);
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
  }, [progress]);

  useImperativeHandle(ref, () => ({ open, close }), [open, close]);

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

  const onDayPress = useCallback((d: Date) => {
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
  }, [selStart, selEnd]);

  const dayState = useCallback((d: Date) => {
    if (!selStart) return "none";
    const t = d.getTime();
    const s = selStart.getTime();
    if (!selEnd) return t === s ? "single" : "none";
    const e = selEnd.getTime();
    if (t === s) return "start";
    if (t === e) return "end";
    if (t > s && t < e) return "range";
    return "none";
  }, [selStart, selEnd]);

  // Reuse the same element subtree during visibility and modal-height updates.
  const dayGrid = useMemo(() => (
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
  ), [cells, dayState, onDayPress, mint, green, colors.onSurface]);

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
  const summaryText = useMemo(() => selStart
    ? selEnd
      ? `${longEs(selStart, language)} — ${longEs(selEnd, language)}`
      : longEs(selStart, language)
    : "Ninguna fecha seleccionada", [selStart, selEnd, language]);
  const kindLabel = !selStart ? "—" : isRange ? "Rango" : "Un solo día";
  const Card = animated ? Animated.View : View;
  const backdrop = <Pressable testID="date-modal-backdrop" onPress={close}
    accessibilityRole="button" accessibilityLabel={tr("common.close")}
    style={[StyleSheet.absoluteFill, st.backdrop, { opacity: 0.45 }]} />;

  return (
    <Modal visible={isOpen} transparent animationType="none" hardwareAccelerated onRequestClose={close}
      onShow={animated ? () => {
        if (transition.current) transition.current.shown = true;
        measureModalRoot();
        revealWhenReady();
      } : undefined}
      statusBarTranslucent navigationBarTranslucent>
      <View ref={animated ? modalRoot : undefined} testID="date-modal-root" style={[st.modalRoot, {
        paddingTop: insets.top + us(16), paddingBottom: insets.bottom + us(16),
        paddingLeft: insets.left, paddingRight: insets.right,
      }]} onLayout={(event) => {
        setModalHeight(event.nativeEvent.layout.height);
        measureModalRoot();
      }}>
        {animated ? <Animated.View style={[StyleSheet.absoluteFill, backdropAnimation]}>{backdrop}</Animated.View> : backdrop}
        <Card testID="date-modal-card" accessibilityViewIsModal
          onStartShouldSetResponderCapture={animated ? () => closing.current : undefined}
          onLayout={animated ? (event) => {
            const layout = event.nativeEvent.layout;
            if (!transition.current || ![layout.x, layout.y, layout.width, layout.height].every(Number.isFinite)
              || layout.width <= 0 || layout.height <= 0) return;
            transition.current.card = layout;
            revealWhenReady();
          } : undefined}
          style={[st.sheetBackground, st.sheetShadow, {
            width: "92%", maxHeight, backgroundColor: colors.surface, borderColor: colors.border,
          }, ...(animated ? [cardAnimation] : [])]}>
          <ScrollView testID="date-range-sheet" style={st.scrollContent}
            contentContainerStyle={[st.sheetContent, { paddingBottom: insets.bottom + us(spacing.lg) }]}
            keyboardShouldPersistTaps="handled" bounces={false} overScrollMode="never">
      {/* Header */}
      <View style={st.headRow}>
        <View style={{ flex: 1, paddingRight: us(12) }}>
          <Text style={[st.title, { color: colors.onSurface }]}>{tr("ui.choose_a_period")}</Text>
          <Text style={[st.subtitle, { color: colors.muted }]}>
            {tr("ui.choose_dates_to_filter_transactions")}
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
          {months[viewMonth.getMonth()]} {viewMonth.getFullYear()}
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
        {weekdays.map((w, i) => (
          <View key={i} style={st.cell}>
            <Text style={[st.weekLabel, { color: colors.muted }]}>{w}</Text>
          </View>
        ))}
      </View>

      {/* Day grid */}
      {dayGrid}

      {/* Selected-period summary */}
      <View style={[st.divider, { backgroundColor: gridLine }]} />
      <Text style={[st.selLabel, { color: colors.muted }]}>{tr("ui.selected_period")}</Text>
      <View style={[st.summaryRow, { backgroundColor: colors.surfaceTertiary, borderColor: gridLine }]}>
        <View style={[st.summaryIcon, { backgroundColor: mint }]}>
          <Ionicons name="calendar-outline" size={us(16)} color={green} />
        </View>
        <Text style={[st.summaryText, { color: colors.onSurface }]}>
          {summaryText}
        </Text>
        {allowClear && selStart && <Pressable testID="date-clear" accessibilityLabel={tr("ui.clear_date_filter")} hitSlop={8}
          onPress={() => { setSelStart(null); setSelEnd(null); onApply(null); close(); }}>
          <Ionicons name="close" size={us(18)} color={colors.muted} />
        </Pressable>}
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
        <Text style={st.applyText}>{tr("ui.apply")}</Text>
      </Pressable>
          </ScrollView>
        </Card>
      </View>
    </Modal>
  );
}));

const st = StyleSheet.create(scaleStyles({
  modalRoot: { flex: 1, alignItems: "center", justifyContent: "center" },
  scrollContent: { flexGrow: 0, flexShrink: 1 },
  sheetContent: { paddingHorizontal: spacing.lg, paddingTop: 29 },
  sheetBackground: { borderTopLeftRadius: radius.cardLg, borderTopRightRadius: radius.cardLg, borderBottomLeftRadius: radius.cardLg, borderBottomRightRadius: radius.cardLg, borderWidth: 1 },
  sheetShadow: { shadowColor: "#000", shadowOpacity: 0.18, shadowRadius: 24, shadowOffset: { width: 0, height: -8 }, elevation: 24 },
  backdrop: { backgroundColor: "#14100C" },
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
