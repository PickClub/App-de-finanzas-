import React, { useState, useMemo, useRef } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet, Animated, Easing, Platform } from "react-native";
import * as Haptics from "expo-haptics";
import Ionicons from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeColors, type ColorScheme } from "@/src/theme";
import { formatCurrencyInt } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";
import { Chip, IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

const TABS = [
  { id: "all", label: "Todos" },
  { id: "active", label: "Activos" },
  { id: "paid", label: "Pagados" },
  { id: "i_owe", label: "Yo debo" },
  { id: "they_owe", label: "Me deben" },
];

export default function Debts() {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [tab, setTab] = useState("all");
  const q = useQuery({ queryKey: ["debts"], queryFn: api.listDebts });
  const debts: any[] = q.data || [];

  // Two independent summaries — the top card must NEVER mix "yo debo" with
  // "me deben". Each face aggregates only its own tipoRelacion.
  const faces = useMemo(() => {
    const build = (list: any[]) => {
      const count = list.length;
      const remaining = list.reduce((s, d) => s + d.remaining_amount, 0);
      const original = list.reduce((s, d) => s + d.original_amount, 0);
      const paid = list.reduce((s, d) => s + d.total_paid, 0);
      const pct = original > 0 ? paid / original : 0;
      return { count, remaining, original, paid, pct };
    };
    return {
      owe: build(debts.filter((d) => d.direction === "i_owe")),
      lent: build(debts.filter((d) => d.direction === "they_owe")),
    };
  }, [debts]);

  const filtered = useMemo(() => {
    if (tab === "all") return debts;
    if (tab === "active") return debts.filter((d) => d.status === "active");
    if (tab === "paid") return debts.filter((d) => d.status === "paid");
    return debts.filter((d) => d.direction === tab);
  }, [debts, tab]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140 }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Deudas y préstamos</Text>
          <LockToggle testID="lock-debts" compact />
          <Pressable testID="add-debt" onPress={() => router.push("/debts/new")} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={22} color="#fff" />
          </Pressable>
        </View>

        {/* Summary — flip card: front = "Yo debo", back = "Me deben" */}
        <View style={{ marginHorizontal: spacing.lg }}>
          <DebtSummaryFlip owe={faces.owe} lent={faces.lent} />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {TABS.map((t) => (
            <Chip key={t.id} label={t.label} active={tab === t.id} onPress={() => setTab(t.id)} testID={`tab-${t.id}`} />
          ))}
        </ScrollView>

        <View style={{ paddingHorizontal: spacing.lg, gap: 12 }}>
          {filtered.map((d) => {
            const p = d.original_amount > 0 ? d.total_paid / d.original_amount : 0;
            const pctInt = Math.round(p * 100);
            const isPaid = d.status === "paid";
            return (
              <Pressable
                key={d.id}
                testID={`debt-${d.id}`}
                onPress={guard(() => router.push(`/debts/${d.id}`))}
                style={[styles.card, { backgroundColor: d.color + "0D", borderColor: d.color + "22" }]}
              >
                <View style={{ flexDirection: "row", alignItems: "center" }}>
                  <IconTile icon={d.icon} tint={d.color} size={44} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={styles.debtName}>{d.name}</Text>
                    <View style={styles.subRow}>
                      <View style={[styles.statusPill, { backgroundColor: (isPaid ? colors.incomeGreen : d.color) + "22" }]}>
                        <View style={[styles.statusDot, { backgroundColor: isPaid ? colors.incomeGreen : d.color }]} />
                        <Text style={{ color: isPaid ? colors.incomeGreen : d.color, fontSize: 11, fontWeight: "600" }}>
                          {isPaid ? "Pagada" : "Activa"}
                        </Text>
                      </View>
                      <Text style={styles.debtSub} numberOfLines={1}>
                        {d.direction === "i_owe" ? "Yo debo" : "Me deben"}{d.person ? ` · ${d.person}` : ""}
                      </Text>
                    </View>
                  </View>
                  <ProgressRing size={54} stroke={6} progress={p} color={d.color} trackColor={d.color + "22"}>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 }}>
                      {pctInt}%
                    </Text>
                  </ProgressRing>
                </View>

                <View style={styles.amountsRow}>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: colors.expenseRed + "1F" }]}>
                        <Ionicons name="document-text-outline" size={11} color={colors.expenseRed} />
                      </View>
                      <Text style={styles.amountLabel}>Pendiente</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: colors.expenseRed }]}>
                      {formatCurrencyInt(d.remaining_amount)}
                    </Text>
                  </View>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: colors.statsPurple + "1F" }]}>
                        <Ionicons name="checkmark-circle" size={12} color={colors.statsPurple} />
                      </View>
                      <Text style={styles.amountLabel}>Pagado</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: colors.statsPurple }]}>
                      {formatCurrencyInt(d.total_paid)}
                    </Text>
                  </View>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: colors.accountsBlue + "1F" }]}>
                        <Ionicons name="stats-chart" size={11} color={colors.accountsBlue} />
                      </View>
                      <Text style={styles.amountLabel}>Total</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: colors.onSurface }]}>
                      {formatCurrencyInt(d.original_amount)}
                    </Text>
                  </View>
                </View>

                <View style={styles.trackRow}>
                  <View style={[styles.track, { backgroundColor: d.color + "1F" }]}>
                    <LinearGradient
                      colors={[d.color + "AA", d.color]}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 0 }}
                      style={[styles.trackFill, { width: `${Math.max(2, pctInt)}%` }]}
                    />
                  </View>
                  <Text style={styles.trackPct}>{pctInt}%</Text>
                </View>
              </Pressable>
            );
          })}
          {filtered.length === 0 && (
            <View style={{ alignItems: "center", padding: 40 }}>
              <Ionicons name="cash-outline" size={48} color={colors.muted} />
              <Text style={{ color: colors.muted, marginTop: 10 }}>Sin deudas en esta vista</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  summary: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  sumRow: { flexDirection: "row" },
  sumLabel: { color: colors.muted, fontSize: 12, fontWeight: "400" },
  sumVal: { fontSize: 20, fontWeight: "600", color: colors.onSurface, marginTop: 4, letterSpacing: -0.3 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  chipRow: { paddingHorizontal: spacing.lg, gap: 8, height: 56, alignItems: "center" },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  debtName: { fontSize: 15, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.2 },
  debtSub: { fontSize: 11, color: colors.muted, fontWeight: "400", flexShrink: 1 },
  subRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  amountsRow: { flexDirection: "row", marginTop: 16 },
  amountCol: { flex: 1 },
  amountHead: { flexDirection: "row", alignItems: "center", gap: 5, marginBottom: 4 },
  amountIcon: {
    width: 18,
    height: 18,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
  },
  amountLabel: { fontSize: 11, color: colors.muted, fontWeight: "400" },
  amountValue: { fontSize: 15, fontWeight: "700", letterSpacing: -0.3 },
  trackRow: { flexDirection: "row", alignItems: "center", marginTop: 14, gap: 10 },
  track: {
    flex: 1,
    height: 12,
    borderRadius: 6,
    overflow: "hidden",
  },
  trackFill: {
    height: "100%",
    borderRadius: 6,
  },
  trackPct: {
    fontSize: 12,
    fontWeight: "700",
    color: colors.muted,
    letterSpacing: -0.2,
    minWidth: 34,
    textAlign: "right",
  },
}));


/* ------------------------------------------------------------------ */
/* Summary flip card — front = "Yo debo", back = "Me deben".           */
/* Fully theme-aware: every color derives from the global theme so     */
/* both faces follow light / dark instantly. Layout & flip unchanged.  */
/* ------------------------------------------------------------------ */

type FaceStat = { count: number; remaining: number; original: number; paid: number; pct: number };

function faceConfig(v: "owe" | "lent", colors: ThemeColors, scheme: ColorScheme) {
  const dark = scheme === "dark";
  if (v === "owe") {
    const accent = colors.statsPurple;
    return {
      accent,
      accentSoft: accent + (dark ? "24" : "14"),
      border: accent + (dark ? "61" : "3D"),
      grad: (dark ? ["#241C36", "#15121D"] : [accent + "12", colors.surfaceSecondary]) as [string, string],
      glow: accent + (dark ? "22" : "12"),
      headerIcon: "bar-chart" as const,
      headerIconColor: colors.brandSecondary,
      headerIconBg: colors.brandSecondary + "22",
      title: "Resumen de deudas",
      subtitle: "Tus deudas y préstamos en un vistazo",
      ringSub: "Pagado",
      countLabel: "Total deudas",
      doneLabel: "Pagado",
      pillPrefix: "Has pagado el",
      pillSuffix: "del total de tus deudas",
    };
  }
  const accent = colors.incomeGreen;
  return {
    accent,
    accentSoft: accent + (dark ? "24" : "14"),
    border: accent + (dark ? "5C" : "3D"),
    grad: (dark ? ["#14261F", "#101815"] : [accent + "12", colors.surfaceSecondary]) as [string, string],
    glow: accent + (dark ? "1F" : "12"),
    headerIcon: "cash-outline" as const,
    headerIconColor: accent,
    headerIconBg: accent + "22",
    title: "Resumen de préstamos",
    subtitle: "Lo que te deben, en un vistazo",
    ringSub: "Recibido",
    countLabel: "Total cuentas",
    doneLabel: "Recibido",
    pillPrefix: "Has recibido el",
    pillSuffix: "del total que te deben",
  };
}

function MetricRow({
  icon,
  iconColor,
  label,
  value,
  valueColor,
}: {
  icon: any;
  iconColor: string;
  label: string;
  value: string;
  valueColor: string;
}) {
  const fs = useFlipStyles();
  return (
    <View style={fs.metricRow}>
      <View style={[fs.metricIcon, { backgroundColor: iconColor + "22" }]}>
        <Ionicons name={icon} size={13} color={iconColor} />
      </View>
      <Text style={fs.metricLabel} numberOfLines={1}>
        {label}
      </Text>
      <Text style={[fs.metricValue, { color: valueColor }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function SummaryFace({ v, s }: { v: "owe" | "lent"; s: FaceStat }) {
  const { colors, scheme } = useTheme();
  const fs = useFlipStyles();
  const cfg = faceConfig(v, colors, scheme);
  const ringTrack = scheme === "dark" ? "rgba(255,255,255,0.10)" : colors.surfaceTertiary;
  const pctInt = Math.round(s.pct * 100);
  return (
    <LinearGradient
      colors={cfg.grad}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[fs.card, { borderColor: cfg.border }]}
    >
      <View pointerEvents="none" style={[fs.glow, { backgroundColor: cfg.glow }]} />

      {/* header */}
      <View style={fs.headerRow}>
        <View style={[fs.headerIcon, { backgroundColor: cfg.headerIconBg }]}>
          <Ionicons name={cfg.headerIcon} size={18} color={cfg.headerIconColor} />
        </View>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={fs.title}>{cfg.title}</Text>
          <Text style={fs.subtitle} numberOfLines={1}>
            {cfg.subtitle}
          </Text>
        </View>
        <View style={[fs.flipHint, { borderColor: cfg.border }]}>
          <Ionicons name="sync-outline" size={13} color={cfg.accent} />
        </View>
      </View>

      {/* body */}
      <View style={fs.body}>
        <View style={fs.ringCol}>
          <ProgressRing size={128} stroke={12} progress={s.pct} color={cfg.accent} trackColor={ringTrack}>
            <Text style={fs.ringPct}>{pctInt}%</Text>
            <Text style={fs.ringSub}>{cfg.ringSub}</Text>
          </ProgressRing>
          <Text style={[fs.ringCaption, { color: cfg.accent }]} numberOfLines={1}>
            {formatCurrencyInt(s.paid)} <Text style={fs.ringCaptionMuted}>de {formatCurrencyInt(s.original)}</Text>
          </Text>
        </View>

        <View style={fs.vDivider} />

        <View style={fs.rows}>
          <MetricRow icon="people-outline" iconColor={colors.muted} label={cfg.countLabel} value={String(s.count)} valueColor={colors.onSurface} />
          <View style={fs.rowDivider} />
          <MetricRow icon="document-text-outline" iconColor={colors.expenseRed} label="Pendiente" value={formatCurrencyInt(s.remaining)} valueColor={colors.expenseRed} />
          <View style={fs.rowDivider} />
          <MetricRow icon="server-outline" iconColor={colors.muted} label="Total original" value={formatCurrencyInt(s.original)} valueColor={colors.onSurface} />
          <View style={fs.rowDivider} />
          <MetricRow icon="checkmark-circle" iconColor={cfg.accent} label={cfg.doneLabel} value={formatCurrencyInt(s.paid)} valueColor={cfg.accent} />
        </View>
      </View>

      {/* pill */}
      <View style={[fs.pill, { borderColor: cfg.border, backgroundColor: cfg.accentSoft }]}>
        <View style={[fs.pillIcon, { backgroundColor: cfg.accent }]}>
          <Ionicons name="information" size={12} color="#fff" />
        </View>
        <Text style={fs.pillText} numberOfLines={1}>
          {cfg.pillPrefix} <Text style={[fs.pillBold, { color: cfg.accent }]}>{pctInt}%</Text> {cfg.pillSuffix}
        </Text>
        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
      </View>
    </LinearGradient>
  );
}

function DebtSummaryFlip({ owe, lent }: { owe: FaceStat; lent: FaceStat }) {
  const fs = useFlipStyles();
  const flip = useRef(new Animated.Value(0)).current;
  const flippedRef = useRef(false);

  const toggle = () => {
    Haptics.selectionAsync().catch(() => {});
    const to = flippedRef.current ? 0 : 1;
    flippedRef.current = !flippedRef.current;
    Animated.timing(flip, {
      toValue: to,
      duration: 520,
      easing: Easing.inOut(Easing.cubic),
      useNativeDriver: Platform.OS !== "web",
    }).start();
  };

  const frontRotate = flip.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "180deg"] });
  const backRotate = flip.interpolate({ inputRange: [0, 1], outputRange: ["180deg", "360deg"] });

  return (
    <Pressable onPress={toggle} accessibilityRole="button" testID="debt-summary-flip" style={fs.flipWrap}>
      {/* Invisible in-flow sizer locks the wrapper dimensions so the flip
          happens IN PLACE (both faces overlap this exact box). */}
      <View pointerEvents="none" style={fs.sizer}>
        <SummaryFace v="owe" s={owe} />
      </View>
      <Animated.View style={[fs.faceAbs, { transform: [{ perspective: 1200 }, { rotateY: frontRotate }] }]}>
        <SummaryFace v="owe" s={owe} />
      </Animated.View>
      <Animated.View style={[fs.faceAbs, { transform: [{ perspective: 1200 }, { rotateY: backRotate }] }]}>
        <SummaryFace v="lent" s={lent} />
      </Animated.View>
    </Pressable>
  );
}

const useFlipStyles = makeStyles((colors, scheme) => {
  const dark = scheme === "dark";
  return {
    // Single fixed wrapper; both faces overlap it absolutely (in-place flip).
    flipWrap: { position: "relative" as const },
    // Invisible copy that reserves the exact card height in normal flow.
    sizer: { opacity: 0 },
    // Overlapping face: fills the wrapper and hides its back during rotation
    // so only one card (and one shadow) is ever visible — no dark edges.
    faceAbs: { ...StyleSheet.absoluteFillObject, backfaceVisibility: "hidden" as const },
    card: {
      borderRadius: radius.cardLg,
      padding: spacing.lg,
      borderWidth: 1,
      overflow: "hidden" as const,
      shadowColor: "#000",
      shadowOpacity: dark ? 0.25 : 0.08,
      shadowRadius: 14,
      shadowOffset: { width: 0, height: 8 },
      elevation: 6,
    },
    glow: {
      position: "absolute" as const,
      top: -70,
      right: -50,
      width: 180,
      height: 180,
      borderRadius: 90,
    },
    headerRow: { flexDirection: "row" as const, alignItems: "center" as const },
    headerIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center" as const, justifyContent: "center" as const },
    title: { fontSize: 17, fontWeight: "700" as const, color: colors.onSurface, letterSpacing: -0.3 },
    subtitle: { fontSize: 12, color: colors.muted, marginTop: 2 },
    flipHint: {
      width: 30,
      height: 30,
      borderRadius: 15,
      alignItems: "center" as const,
      justifyContent: "center" as const,
      borderWidth: 1,
      backgroundColor: dark ? "rgba(255,255,255,0.04)" : colors.surfaceTertiary,
    },
    body: { flexDirection: "row" as const, alignItems: "center" as const, marginTop: spacing.lg },
    ringCol: { width: 138, alignItems: "center" as const },
    ringPct: { fontSize: 30, fontWeight: "800" as const, color: colors.onSurface, letterSpacing: -0.5 },
    ringSub: { fontSize: 12, color: colors.muted, marginTop: -2 },
    ringCaption: { fontSize: 13, fontWeight: "700" as const, marginTop: 12, letterSpacing: -0.2 },
    ringCaptionMuted: { color: colors.muted, fontWeight: "400" as const },
    vDivider: {
      width: 1,
      alignSelf: "stretch" as const,
      backgroundColor: dark ? "rgba(255,255,255,0.10)" : colors.divider,
      marginHorizontal: spacing.md,
      marginVertical: 4,
    },
    rows: { flex: 1 },
    metricRow: { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: 7 },
    metricIcon: { width: 22, height: 22, borderRadius: 7, alignItems: "center" as const, justifyContent: "center" as const },
    metricLabel: { flex: 1, marginLeft: 10, fontSize: 13, color: colors.muted },
    metricValue: { fontSize: 16, fontWeight: "800" as const, letterSpacing: -0.3 },
    rowDivider: { height: 1, backgroundColor: dark ? "rgba(255,255,255,0.07)" : colors.divider },
    pill: {
      flexDirection: "row" as const,
      alignItems: "center" as const,
      gap: 10,
      marginTop: spacing.lg,
      paddingHorizontal: 12,
      paddingVertical: 11,
      borderRadius: radius.md,
      borderWidth: 1,
    },
    pillIcon: { width: 22, height: 22, borderRadius: 11, alignItems: "center" as const, justifyContent: "center" as const },
    pillText: { flex: 1, fontSize: 12.5, color: colors.muted },
    pillBold: { fontWeight: "800" as const },
  };
});
