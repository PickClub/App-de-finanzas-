import { tr, useTranslation as useInterfaceLanguage } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { View, StyleSheet, Animated, Easing, Platform, useWindowDimensions } from "react-native";
import Reanimated, { cancelAnimation, Easing as FlipEasing, runOnJS, useAnimatedStyle, useReducedMotion, useSharedValue, withTiming, ReduceMotion } from "react-native-reanimated";
import { Trans } from "react-i18next";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ColorScheme } from "@/src/theme";
import { formatCurrencyInt } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";
import { IconTile } from "@/src/components/ui";
import { useLock } from "@/src/lock";

import { us, ufs } from "@/src/ui-scale";
const TABS = [
  { id: "all", get label() { return tr("ui.all"); } },
  { id: "paid", get label() { return tr("ui.paid"); } },
  { id: "i_owe", get label() { return tr("ui.i_owe"); } },
  { id: "they_owe", get label() { return tr("ui.owed_to_me"); } },
];

// ---------------------------------------------------------------------------
// Screen-local palette (Debts only). Mirrors the premium green identity of the
// Home/Accounts screens in light mode; falls back to warm-dark tokens in dark.
// This is a VISUAL override scoped to this screen — the global theme system is
// untouched, and both light/dark are respected.
// ---------------------------------------------------------------------------
type DebtPalette = {
  page: string;
  card: string;
  text: string;
  muted: string;
  green: string;
  ring: string;
  ringTrack: string;
  divider: string;
  border: string;
  red: string;
  purple: string;
  incomeGreen: string;
  pillGrad: [string, string];
  tileGreen: string;
};

function palette(scheme: ColorScheme): DebtPalette {
  if (scheme === "dark") {
    return {
      page: "#141210",
      card: "#1E1B18",
      text: "#F5F1EC",
      muted: "#9E9791",
      green: "#2CA079",
      ring: "#2CA079",
      ringTrack: "rgba(255,255,255,0.10)",
      divider: "#2A2622",
      border: "#2C2723",
      red: "#EB6D5F",
      purple: "#A57DFF",
      incomeGreen: "#37C08D",
      pillGrad: ["#1E8F68", "#177A57"],
      tileGreen: "rgba(44,160,121,0.16)",
    };
  }
  return {
    page: "#E8EFE7",
    card: "#FCFCF8",
    text: "#15251E",
    muted: "#68746D",
    green: "#126046",
    ring: "#0C6B4E",
    ringTrack: "#E1EAE4",
    divider: "#E4E7E2",
    border: "rgba(39,71,56,0.10)",
    red: "#D84D45",
    purple: "#7546D7",
    incomeGreen: "#138B66",
    pillGrad: ["#16694A", "#146448"],
    tileGreen: "#DCE9DD",
  };
}

type Stat = { count: number; remaining: number; original: number; paid: number; pct: number };

function buildStat(list: any[]): Stat {
  const count = list.length;
  const remaining = list.reduce((s, d) => s + d.remaining_amount, 0);
  const original = list.reduce((s, d) => s + d.original_amount, 0);
  const paid = list.reduce((s, d) => s + d.total_paid, 0);
  const pct = original > 0 ? paid / original : 0;
  return { count, remaining, original, paid, pct };
}

export default function Debts() {
  useInterfaceLanguage();
  const { scheme } = useTheme();
  const P = useMemo(() => palette(scheme), [scheme]);
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [tab, setTab] = useState("all");
  const q = useQuery({ queryKey: ["debts"], queryFn: api.listDebts });
  const debts: any[] = q.data || [];

  // --- One-time screen-entry progress animation (VISUAL ONLY) --------------
  // A single factor 0..1 that all progress indicators (main ring, card rings,
  // horizontal bars) multiply their REAL percentage by, so they sweep from 0
  // to their current value together when the screen is opened. It runs once
  // per focus and only after the debt data is available (so it doesn't snap on
  // async load), and it does NOT restart on scroll / re-render / filter change.
  const entry = useRef(new Animated.Value(0)).current;
  const [entryT, setEntryT] = useState(0);
  const armed = useRef(false);
  const dataReadyRef = useRef(false);

  useEffect(() => {
    const id = entry.addListener(({ value }) => setEntryT(value));
    return () => entry.removeListener(id);
  }, [entry]);

  const startEntryAnim = useCallback(() => {
    if (!armed.current || !dataReadyRef.current) return;
    armed.current = false;
    entry.setValue(0);
    setEntryT(0);
    Animated.timing(entry, {
      toValue: 1,
      duration: 1000,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [entry]);

  // Track when the debt query has resolved (cached re-entries resolve instantly).
  useEffect(() => {
    if (q.isSuccess || q.data) {
      dataReadyRef.current = true;
      startEntryAnim();
    }
  }, [q.isSuccess, q.data, startEntryAnim]);

  // Arm a fresh one-time animation each time the screen gains focus.
  useFocusEffect(
    useCallback(() => {
      armed.current = true;
      entry.stopAnimation();
      entry.setValue(0);
      setEntryT(0);
      startEntryAnim(); // starts immediately if data already available
      return () => {
        entry.stopAnimation();
      };
    }, [entry, startEntryAnim])
  );

  // Back-side data (presentation only) — derived from the SAME real debt data.
  const oweList = useMemo(() => debts.filter((d) => d.direction === "i_owe"), [debts]);
  const lentList = useMemo(() => debts.filter((d) => d.direction === "they_owe"), [debts]);
  const oweSummary = useMemo(() => buildStat(oweList), [oweList]);
  const lentSummary = useMemo(() => buildStat(lentList), [lentList]);

  const filtered = useMemo(() => {
    if (tab === "all") return debts.filter((d) => d.remaining_amount > 0);
    if (tab === "active") return debts.filter((d) => d.status === "active");
    if (tab === "paid") return debts.filter((d) => d.remaining_amount <= 0);
    return debts.filter((d) => d.direction === tab && d.remaining_amount > 0);
  }, [debts, tab]);

  return (
    <View style={{ flex: 1, backgroundColor: P.page }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL}
        style={{ flex: 1, backgroundColor: "transparent" }}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140) }}
        showsVerticalScrollIndicator={false}
      >
        {/* Header — compact, title + subtitle, lock + add */}
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>{tr("ui.debts_loans")}</Text>
            <Text style={styles.subtitle}>{tr("ui.your_debts_in_one_place")}</Text>
          </View>
          <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="debts-back" beforeActions={<Pressable
            testID="add-debt"
            onPress={() => router.push("/debts/new")}
            style={[styles.addBtn, { backgroundColor: P.green }]}
            accessibilityRole="button"
            accessibilityLabel={tr("common.add")}
          >
            <Ionicons name="add" size={us(22)} color="#fff" />
          </Pressable>} />
        </View>

        <View style={styles.summarySpacing}>
          <DebtSummaryCard front={oweSummary} back={lentSummary} entryT={entryT} />
        </View>

        {/* Filters — fixed row (no horizontal scroll); 4 buttons evenly span
            the same width as the debt cards below */}
        <View style={styles.filterRow}>
          {TABS.map((t) => (
            <FilterPill
              key={t.id}
              testID={`tab-${t.id}`}
              label={t.label}
              active={tab === t.id}
              gradient={P.pillGrad}
              onPress={() => setTab(t.id)}
              styles={styles}
            />
          ))}
        </View>

        {/* Debt cards */}
        <View style={{ paddingHorizontal: us(spacing.lg), gap: us(12) }}>
          {filtered.map((d) => {
            const p = d.original_amount > 0 ? d.total_paid / d.original_amount : 0;
            const pctInt = Math.round(p * 100);
            const isPaid = d.status === "paid";
            const accent = d.color;
            const statusColor = isPaid ? P.incomeGreen : accent;
            return (
              <Pressable
                key={d.id}
                testID={`debt-${d.id}`}
                onPress={guard(() => router.push(`/debts/${d.id}`))}
                style={[styles.card, { borderColor: accent + "2E" }]}
              >
                {/* faint accent wash — decorative, cannot affect layout */}
                <View pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: accent + "0D" }]} />

                {/* top row */}
                <View style={styles.cardTop}>
                  <IconTile icon={d.icon} tint={accent} size={us(44)} />
                  <View style={{ flex: 1, minWidth: 0, marginLeft: us(12) }}>
                    <Text style={styles.debtName}>{d.name}</Text>
                    <View style={styles.subRow}>
                      <View style={[styles.statusPill, { backgroundColor: statusColor + "22" }]}>
                        <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
                        <Text style={{ color: statusColor, fontSize: ufs(11), fontWeight: "700" }}>
                          {isPaid ? tr("ui.paid") : tr("ui.active_2")}
                        </Text>
                      </View>
                      <Text style={styles.debtSub}>
                        {d.direction === "i_owe" ? tr("ui.i_owe") : tr("ui.owed_to_me")}{d.person ? ` · ${d.person}` : ""}
                      </Text>
                    </View>
                  </View>
                  <ProgressRing size={us(52)} stroke={us(6)} progress={p * entryT} color={accent} trackColor={accent + "22"}>
                    <Text style={[styles.ringPctSmall, { color: P.text }]}>{pctInt}%</Text>
                  </ProgressRing>
                </View>

                {/* three info blocks */}
                <View style={styles.amountsRow}>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={styles.amountIcon}>
                        <Ionicons name="document-text" size={us(11)} color={P.red} />
                      </View>
                      <Text style={styles.amountLabel} numberOfLines={1} adjustsFontSizeToFit>{tr("ui.pending")}</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: P.text }]} numberOfLines={1} adjustsFontSizeToFit>
                      {formatCurrencyInt(d.remaining_amount)}
                    </Text>
                  </View>
                  <View pointerEvents="none" style={styles.amountSeparator} />
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={styles.amountIcon}>
                        <Ionicons name="checkmark-circle" size={us(12)} color={accent} />
                      </View>
                      <Text style={styles.amountLabel} numberOfLines={1} adjustsFontSizeToFit>{tr("ui.paid")}</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: P.text }]} numberOfLines={1} adjustsFontSizeToFit>
                      {formatCurrencyInt(d.total_paid)}
                    </Text>
                  </View>
                  <View pointerEvents="none" style={styles.amountSeparator} />
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={styles.amountIcon}>
                        <Ionicons name="stats-chart" size={us(11)} color={P.green} />
                      </View>
                      <Text style={styles.amountLabel} numberOfLines={1} adjustsFontSizeToFit>{tr("ui.total")}</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: P.text }]} numberOfLines={1} adjustsFontSizeToFit>
                      {formatCurrencyInt(d.original_amount)}
                    </Text>
                  </View>
                </View>

                {/* horizontal progress */}
                <View style={styles.trackRow}>
                  <View style={[styles.track, { backgroundColor: accent + "1F" }]}>
                    <LinearGradient
                      colors={[accent + "CC", accent]}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 0 }}
                      style={[styles.trackFill, { width: `${Math.max(3, pctInt) * entryT}%` }]}
                    />
                  </View>
                  <Text style={styles.trackPct}>{pctInt}%</Text>
                </View>
              </Pressable>
            );
          })}

          {filtered.length === 0 && (
            <View style={{ alignItems: "center", padding: us(40) }}>
              <Ionicons name="cash-outline" size={us(48)} color={P.muted} />
              <Text style={{ color: P.muted, marginTop: us(10) }}>{tr("ui.no_debts_in_this_view")}</Text>
            </View>
          )}

          {/* Add debt */}
          <Pressable testID="add-debt-inline" onPress={() => router.push("/debts/new")} style={styles.addRow}>
            <Ionicons name="add" size={us(20)} color={P.green} />
            <Text style={styles.addRowText}>{tr("ui.add_debt_or_loan")}</Text>
          </Pressable>
        </View>
      </ElasticScrollView>
    </View>
  );
}

function FilterPill({
  label,
  active,
  gradient,
  onPress,
  testID,
  styles,
}: {
  label: string;
  active: boolean;
  gradient: [string, string];
  onPress: () => void;
  testID: string;
  styles: any;
}) {
  const scale = useRef(new Animated.Value(1)).current;
  const useNative = Platform.OS !== "web";
  const pressIn = () => {
    // subtle compress
    Animated.spring(scale, { toValue: 0.95, useNativeDriver: useNative, speed: 50, bounciness: 0 }).start();
  };
  const pressOut = () => {
    // elastic spring back with a tiny bounce
    Animated.spring(scale, { toValue: 1, useNativeDriver: useNative, speed: 20, bounciness: 12 }).start();
  };
  return (
    <Animated.View style={{ flex: 1, transform: [{ scale }] }}>
      <Pressable testID={testID} onPress={onPress} onPressIn={pressIn} onPressOut={pressOut}>
        {active ? (
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.pill}>
            <Text style={styles.pillTextActive}>{label}</Text>
          </LinearGradient>
        ) : (
          <View style={[styles.pill, styles.pillIdle]}>
            <Text style={styles.pillText}>{label}</Text>
          </View>
        )}
      </Pressable>
    </Animated.View>
  );
}

function MetricRow({
  icon,
  tint,
  label,
  value,
  valueColor,
  last,
  scale,
}: {
  icon: any;
  tint: string;
  label: string;
  value: string;
  valueColor: string;
  last: boolean;
  scale: number;
}) {
  const styles = useStyles();
  return (
    <View style={[styles.metricRow, { paddingVertical: us(7) * scale }, last && { paddingBottom: 0 }]}>
      <View style={[styles.metricIcon, { width: us(26) * scale, height: us(26) * scale, backgroundColor: tint + "22" }]}>
        <Ionicons name={icon} size={us(13) * scale} color={tint} />
      </View>
      <Text style={[styles.metricLabel, { fontSize: ufs(12.5) * scale, marginLeft: us(10) * scale }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={Math.min(0.85, 1 / scale)}>{label}</Text>
      <Text style={[styles.metricValue, { color: valueColor, fontSize: ufs(15) * scale }]} numberOfLines={1} adjustsFontSizeToFit>{value}</Text>
    </View>
  );
}

// Both faces stay mounted. Only the UI-thread rotation changes during a flip.
const DebtSummaryCard = React.memo(function DebtSummaryCard({ front, back, entryT }: {
  front: Stat; back: Stat; entryT: number;
}) {
  useInterfaceLanguage();
  const styles = useStyles();
  const progress = useSharedValue(0);
  const reducedMotion = useReducedMotion();
  const busy = useRef(false);
  const showingBack = useRef(false);
  const mounted = useRef(true);
  const [showBack, setShowBack] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; cancelAnimation(progress); };
  }, [progress]);

  const finishFlip = useCallback((back: boolean) => {
    if (!mounted.current) return;
    showingBack.current = back;
    busy.current = false;
    setShowBack(back);
  }, []);

  const flipCard = useCallback(() => {
    if (busy.current) return;
    busy.current = true;
    const nextBack = !showingBack.current;
    if (reducedMotion) {
      progress.set(nextBack ? 1 : 0);
      finishFlip(nextBack);
      return;
    }
    progress.set(withTiming(nextBack ? 1 : 0, {
      duration: 440, easing: FlipEasing.inOut(FlipEasing.cubic), reduceMotion: ReduceMotion.System,
    }, (finished) => {
      if (finished) runOnJS(finishFlip)(nextBack);
    }));
  }, [progress, reducedMotion, finishFlip]);

  const frontStyle = useAnimatedStyle(() => ({
    transform: [{ perspective: 1000 }, { rotateY: `${progress.value * 180}deg` }],
    // Android compositing can expose the reverse of a complex SVG face.
    // These complementary gates change only at the edge-on midpoint, not a fade.
    opacity: progress.value < 0.5 ? 1 : 0,
  }));
  const backStyle = useAnimatedStyle(() => ({
    transform: [{ perspective: 1000 }, { rotateY: `${(progress.value - 1) * 180}deg` }],
    opacity: progress.value >= 0.5 ? 1 : 0,
  }));

  return (
    <Pressable testID="debt-summary-flip" onPress={flipCard} accessibilityRole="button"
      accessibilityLabel={tr(showBack ? "debts.flipToDebts" : "debts.flipToReceivables")}>
      <Reanimated.View testID="debt-summary-front" pointerEvents="none"
        accessibilityElementsHidden={showBack} importantForAccessibility={showBack ? "no-hide-descendants" : "auto"}
        style={[styles.summaryCard, styles.summaryFace, frontStyle]}>
        <SummaryFace summary={front} back={false} entryT={entryT} />
      </Reanimated.View>
      <Reanimated.View testID="debt-summary-back" pointerEvents="none"
        accessibilityElementsHidden={!showBack} importantForAccessibility={!showBack ? "no-hide-descendants" : "auto"}
        style={[styles.summaryCard, styles.summaryFace, styles.summaryBack, backStyle]}>
        <SummaryFace summary={back} back entryT={entryT} />
      </Reanimated.View>
    </Pressable>
  );
});

function SummaryFace({ summary, back, entryT }: { summary: Stat; back: boolean; entryT: number }) {
  const { scheme } = useTheme();
  const P = palette(scheme);
  const styles = useStyles();
  const { width } = useWindowDimensions();
  // Keep the original two-column proportions on narrow windows; grow up to 20%.
  const scale = Math.min(1.2, Math.max(1, (width - us(64) - 2) / us(300)));
  const accent = back ? P.purple : P.green;
  const paidLabel = tr(back ? "debts.collected" : "ui.paid");
  return (
    <>
      <View style={[styles.summaryLeft, { width: us(132) * scale }]}>
        <ProgressRing size={us(116) * scale} stroke={us(11) * scale} progress={summary.pct * entryT}
          color={P.ring} trackColor={P.ringTrack}>
          <Text style={[styles.sumPct, { fontSize: ufs(26) * scale }]} numberOfLines={1} adjustsFontSizeToFit>{Math.round(summary.pct * 100)}%</Text>
          <Text style={[styles.sumPctSub, { fontSize: ufs(12) * scale }]}>{paidLabel}</Text>
        </ProgressRing>
        <Text style={[styles.sumCaption, { color: P.muted, fontSize: ufs(12.5) * scale, marginTop: us(12) * scale }]} numberOfLines={2} adjustsFontSizeToFit>
          <Trans i18nKey="debts.summaryProgress"
            values={{ paid: formatCurrencyInt(summary.paid), total: formatCurrencyInt(summary.original) }}
            components={{ paid: <Text style={{ color: P.green, fontWeight: "800" }} /> }} />
        </Text>
      </View>
      <View style={[styles.summaryDivider, { marginHorizontal: us(12) * scale }]} />
      <View style={styles.summaryRight}>
        <MetricRow scale={scale} icon="people" tint={accent} label={tr(back ? "debts.peopleOweYou" : "ui.total_debt")} value={String(summary.count)} valueColor={P.text} last={false} />
        <View style={styles.metricDivider} />
        <MetricRow scale={scale} icon="document-text" tint={P.red} label={tr("ui.pending")} value={formatCurrencyInt(summary.remaining)} valueColor={P.red} last={false} />
        <View style={styles.metricDivider} />
        <MetricRow scale={scale} icon="server" tint={accent} label={tr("ui.total")} value={formatCurrencyInt(summary.original)} valueColor={P.text} last={false} />
        <View style={styles.metricDivider} />
        <MetricRow scale={scale} icon="checkmark-circle" tint={P.incomeGreen} label={paidLabel} value={formatCurrencyInt(summary.paid)} valueColor={P.incomeGreen} last />
      </View>
      <View pointerEvents="none" style={styles.flipHint}>
        <Ionicons name="sync-outline" size={us(11)} color={P.muted} />
        <Text style={styles.flipHintText}>{tr("debts.tapToFlip")}</Text>
      </View>
    </>
  );
}

const useStyles = makeStyles((_c, scheme) => {
  const P = palette(scheme);
  const shadow = scheme === "dark"
    ? { shadowColor: "#000", shadowOpacity: 0.28, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 4 }
    : { shadowColor: "#274738", shadowOpacity: 0.07, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 3 };
  return {
    headerRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: 12,
      paddingHorizontal: spacing.lg,
      marginBottom: spacing.md,
    },
    backBtn: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: P.card,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 1,
      borderColor: P.border,
    },
    title: { fontSize: 20, fontWeight: "800", color: P.text, letterSpacing: -0.3 },
    subtitle: { fontSize: 12.5, color: P.muted, marginTop: 1 },
    addBtn: {
      width: 44,
      height: 44,
      borderRadius: 22,
      alignItems: "center",
      justifyContent: "center",
      ...shadow,
    },

    /* Extra exterior space preserves internal sizes and recovers part of the header gap. */
    summarySpacing: { marginTop: -9 },
    summaryCard: {
      flexDirection: "row",
      alignItems: "center",
      marginHorizontal: spacing.lg,
      backgroundColor: P.card,
      borderRadius: radius.cardLg,
      padding: spacing.lg,
      paddingVertical: 30,
      minHeight: 250,
      borderWidth: 1,
      borderColor: P.border,
      ...shadow,
    },
    summaryLeft: { width: 132, alignItems: "center" },
    sumPct: { fontSize: 26, fontWeight: "800", color: P.text, letterSpacing: -0.5 },
    sumPctSub: { fontSize: 12, color: P.muted, marginTop: -2 },
    sumCaption: { fontSize: 12.5, marginTop: 12, textAlign: "center" },
    summaryDivider: {
      width: 1,
      alignSelf: "stretch",
      backgroundColor: P.divider,
      marginHorizontal: spacing.md,
      marginVertical: 4,
    },
    summaryRight: { flex: 1 },
    metricRow: { flexDirection: "row", alignItems: "center", paddingVertical: 7 },
    metricIcon: { width: 26, height: 26, borderRadius: 8, alignItems: "center", justifyContent: "center" },
    metricLabel: { flex: 1, marginLeft: 10, fontSize: 12.5, color: P.muted },
    metricValue: { fontSize: 15, fontWeight: "800", letterSpacing: -0.3 },
    metricDivider: { height: 1, backgroundColor: P.divider, opacity: 0.7 },

    /* Matched face bounds: the front owns layout, the back overlays it. */
    summaryFace: { backfaceVisibility: "hidden" },
    summaryBack: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
    flipHint: { position: "absolute", bottom: 2, right: 16, flexDirection: "row", alignItems: "center", gap: 3 },
    flipHintText: { fontSize: 9, lineHeight: 12, color: P.muted },

    /* filters */
    filterRow: { flexDirection: "row", paddingHorizontal: spacing.lg, gap: 8, paddingVertical: spacing.sm },
    pill: {
      paddingHorizontal: 6,
      paddingVertical: 6,
      borderRadius: radius.pill,
      alignItems: "center",
      justifyContent: "center",
    },
    pillIdle: {
      backgroundColor: P.card,
      borderWidth: 1,
      borderColor: scheme === "dark" ? P.border : "#D9DED8",
    },
    pillText: { color: P.text, fontSize: 12, fontWeight: "700" },
    pillTextActive: { color: "#fff", fontSize: 12, fontWeight: "700" },

    /* debt card */
    card: {
      backgroundColor: P.card,
      borderRadius: radius.cardLg,
      paddingVertical: 12,
      paddingHorizontal: 14,
      borderWidth: 1,
      overflow: "hidden",
      ...shadow,
    },
    cardTop: { flexDirection: "row", alignItems: "center" },
    debtName: { fontSize: 15.5, fontWeight: "800", color: P.text, letterSpacing: -0.2 },
    subRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 5 },
    statusPill: {
      flexDirection: "row",
      alignItems: "center",
      gap: 5,
      paddingHorizontal: 8,
      paddingVertical: 3,
      borderRadius: radius.pill,
    },
    statusDot: { width: 6, height: 6, borderRadius: 3 },
    debtSub: { fontSize: 11.5, color: P.muted, fontWeight: "500", flexShrink: 1 },
    ringPctSmall: { fontSize: 12.5, fontWeight: "800", letterSpacing: -0.3 },

    amountsRow: { flexDirection: "row", marginTop: 11 },
    amountCol: { flex: 1, flexBasis: 0, minWidth: 0, paddingHorizontal: 8 },
    amountHead: { flexDirection: "row", alignItems: "center", height: 20, gap: 5, marginBottom: 4 },
    amountIcon: { width: 18, height: 18, flexShrink: 0, alignItems: "center", justifyContent: "center" },
    amountLabel: { flexShrink: 1, minWidth: 0, fontSize: 11.5, lineHeight: 16, includeFontPadding: false, color: P.muted, fontWeight: "500" },
    amountValue: { width: "100%", height: 20, lineHeight: 20, includeFontPadding: false, textAlignVertical: "center", fontSize: 15.5, fontWeight: "800", letterSpacing: -0.3 },
    amountSeparator: { width: 1, alignSelf: "stretch", marginHorizontal: 2, marginVertical: 2, backgroundColor: P.divider, opacity: 0.7 },

    trackRow: { flexDirection: "row", alignItems: "center", marginTop: 11, gap: 10 },
    track: { flex: 1, height: 8, borderRadius: 4, overflow: "hidden" },
    trackFill: { height: "100%", borderRadius: 4 },
    trackPct: {
      fontSize: 12.5,
      fontWeight: "800",
      color: P.muted,
      letterSpacing: -0.2,
      minWidth: 36,
      textAlign: "right" as const,
    },

    /* add debt */
    addRow: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: 8,
      marginTop: 4,
      paddingVertical: 16,
      borderRadius: radius.lg,
      borderWidth: 1.5,
      borderStyle: "dashed",
      borderColor: P.green,
      backgroundColor: scheme === "dark" ? "rgba(44,160,121,0.08)" : "rgba(18,96,70,0.05)",
    },
    addRowText: { color: P.green, fontWeight: "800", fontSize: 14 },
  };
});
