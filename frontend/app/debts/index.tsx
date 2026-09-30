import React, { useState, useMemo, useRef } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet, Animated, Easing, Platform } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ColorScheme } from "@/src/theme";
import { formatCurrencyInt } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

const TABS = [
  { id: "all", label: "Todos" },
  { id: "paid", label: "Pagados" },
  { id: "i_owe", label: "Yo debo" },
  { id: "they_owe", label: "Me deben" },
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
  const { scheme } = useTheme();
  const P = useMemo(() => palette(scheme), [scheme]);
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [tab, setTab] = useState("all");
  const q = useQuery({ queryKey: ["debts"], queryFn: api.listDebts });
  const debts: any[] = q.data || [];

  // ONE aggregate summary across all debts — real data only.
  const summary = useMemo(() => buildStat(debts), [debts]);
  const summaryPct = Math.round(summary.pct * 100);

  // Back-side data (presentation only) — derived from the SAME real debt data.
  const oweList = useMemo(() => debts.filter((d) => d.direction === "i_owe"), [debts]);
  const lentList = useMemo(() => debts.filter((d) => d.direction === "they_owe"), [debts]);
  const oweTotal = useMemo(() => oweList.reduce((s, d) => s + d.remaining_amount, 0), [oweList]);
  const lentTotal = useMemo(() => lentList.reduce((s, d) => s + d.remaining_amount, 0), [lentList]);

  // Safe in-place flip: ONE container. A single Animated value drives scaleX
  // (1 -> ~0.04 -> 1) plus a subtle scaleY / translateX / opacity for a premium
  // "card turning" feel. Content is swapped ONLY at the edge-on midpoint (no
  // flash, never two contents at once). Transforms never affect layout, and the
  // card height is locked to the front's measured height so nothing below drifts.
  const [showBack, setShowBack] = useState(false);
  const [lockH, setLockH] = useState<number | null>(null);
  const anim = useRef(new Animated.Value(1)).current; // 1 = flat, 0 = edge-on
  const animating = useRef(false);
  const onCardLayout = (e: any) => {
    if (lockH == null && !showBack) {
      const h = e?.nativeEvent?.layout?.height;
      if (h && h > 0) setLockH(h);
    }
  };
  const flipCard = () => {
    if (animating.current) return; // reject taps while a flip is running
    animating.current = true;
    Animated.timing(anim, {
      toValue: 0,
      duration: 230,
      easing: Easing.in(Easing.cubic),
      useNativeDriver: Platform.OS !== "web",
    }).start(({ finished }) => {
      if (!finished) {
        animating.current = false;
        return;
      }
      setShowBack((b) => !b); // swap while edge-on
      Animated.timing(anim, {
        toValue: 1,
        duration: 230,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: Platform.OS !== "web",
      }).start(() => {
        animating.current = false;
      });
    });
  };
  const cardScaleX = anim.interpolate({ inputRange: [0, 1], outputRange: [0.04, 1] });
  const cardScaleY = anim.interpolate({ inputRange: [0, 1], outputRange: [0.985, 1] });
  const cardTranslateX = anim.interpolate({ inputRange: [0, 1], outputRange: [6, 0] });
  const cardOpacity = anim.interpolate({ inputRange: [0, 1], outputRange: [0.94, 1] });

  const filtered = useMemo(() => {
    if (tab === "all") return debts;
    if (tab === "active") return debts.filter((d) => d.status === "active");
    if (tab === "paid") return debts.filter((d) => d.status === "paid");
    return debts.filter((d) => d.direction === tab);
  }, [debts, tab]);

  return (
    <View style={{ flex: 1, backgroundColor: P.page }}>
      <ScrollView
        style={{ flex: 1, backgroundColor: "transparent" }}
        contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140 }}
        showsVerticalScrollIndicator={false}
      >
        {/* Header — compact, title + subtitle, lock + add */}
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={22} color={P.text} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.title} numberOfLines={1}>Deudas y préstamos</Text>
            <Text style={styles.subtitle} numberOfLines={1}>Tus deudas en un solo lugar</Text>
          </View>
          <LockToggle testID="lock-debts" compact />
          <Pressable
            testID="add-debt"
            onPress={() => router.push("/debts/new")}
            style={[styles.addBtn, { backgroundColor: P.green }]}
          >
            <Ionicons name="add" size={22} color="#fff" />
          </Pressable>
        </View>

        {/* Summary card — tap to flip. SINGLE container, scaleX flip, height
            locked to the front's measured height so nothing below can drift.
            Front is unchanged; back shows "A quién debo" / "Quién me debe". */}
        <Pressable testID="debt-summary-flip" onPress={flipCard}>
          <Animated.View
            onLayout={onCardLayout}
            style={[
              styles.summaryCard,
              lockH ? { height: lockH } : null,
              { opacity: cardOpacity, transform: [{ translateX: cardTranslateX }, { scaleX: cardScaleX }, { scaleY: cardScaleY }] },
            ]}
          >
            {showBack ? (
              <>
                <BackBlock
                  icon="arrow-up"
                  accent={P.red}
                  title="A quién debo"
                  total={formatCurrencyInt(oweTotal)}
                  list={oweList}
                  emptyText="Sin deudas"
                />
                <View style={styles.summaryDivider} />
                <BackBlock
                  icon="arrow-down"
                  accent={P.incomeGreen}
                  title="Quién me debe"
                  total={formatCurrencyInt(lentTotal)}
                  list={lentList}
                  emptyText="Nadie te debe"
                />
              </>
            ) : (
              <>
                <View style={styles.summaryLeft}>
                  <ProgressRing size={116} stroke={11} progress={summary.pct} color={P.ring} trackColor={P.ringTrack}>
                    <Text style={styles.sumPct}>{summaryPct}%</Text>
                    <Text style={styles.sumPctSub}>Pagado</Text>
                  </ProgressRing>
                  <Text style={styles.sumCaption} numberOfLines={1}>
                    <Text style={{ color: P.green, fontWeight: "800" }}>{formatCurrencyInt(summary.paid)}</Text>
                    <Text style={{ color: P.muted }}> de {formatCurrencyInt(summary.original)}</Text>
                  </Text>
                </View>

                <View style={styles.summaryDivider} />

                <View style={styles.summaryRight}>
                  <MetricRow icon="people" tint={P.green} label="Total de deudas" value={String(summary.count)} valueColor={P.text} last={false} />
                  <View style={styles.metricDivider} />
                  <MetricRow icon="document-text" tint={P.red} label="Pendiente" value={formatCurrencyInt(summary.remaining)} valueColor={P.red} last={false} />
                  <View style={styles.metricDivider} />
                  <MetricRow icon="server" tint={P.green} label="Total" value={formatCurrencyInt(summary.original)} valueColor={P.text} last={false} />
                  <View style={styles.metricDivider} />
                  <MetricRow icon="checkmark-circle" tint={P.incomeGreen} label="Pagado" value={formatCurrencyInt(summary.paid)} valueColor={P.incomeGreen} last />
                </View>
              </>
            )}

            {/* Flip indicator — subtle swap icon, both faces, inside card bounds */}
            <View pointerEvents="none" style={styles.flipHint}>
              <Ionicons name="swap-horizontal" size={15} color={P.muted} />
            </View>
          </Animated.View>
        </Pressable>

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
        <View style={{ paddingHorizontal: spacing.lg, gap: 12 }}>
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
                  <IconTile icon={d.icon} tint={accent} size={44} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={styles.debtName} numberOfLines={1}>{d.name}</Text>
                    <View style={styles.subRow}>
                      <View style={[styles.statusPill, { backgroundColor: statusColor + "22" }]}>
                        <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
                        <Text style={{ color: statusColor, fontSize: 11, fontWeight: "700" }}>
                          {isPaid ? "Pagada" : "Activa"}
                        </Text>
                      </View>
                      <Text style={styles.debtSub} numberOfLines={1}>
                        {d.direction === "i_owe" ? "Yo debo" : "Me deben"}{d.person ? ` · ${d.person}` : ""}
                      </Text>
                    </View>
                  </View>
                  <ProgressRing size={52} stroke={6} progress={p} color={accent} trackColor={accent + "22"}>
                    <Text style={[styles.ringPctSmall, { color: P.text }]}>{pctInt}%</Text>
                  </ProgressRing>
                </View>

                {/* three info blocks */}
                <View style={styles.amountsRow}>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: P.red + "1F" }]}>
                        <Ionicons name="document-text" size={11} color={P.red} />
                      </View>
                      <Text style={styles.amountLabel}>Pendiente</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: P.text }]} numberOfLines={1} adjustsFontSizeToFit>
                      {formatCurrencyInt(d.remaining_amount)}
                    </Text>
                  </View>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: accent + "1F" }]}>
                        <Ionicons name="checkmark-circle" size={12} color={accent} />
                      </View>
                      <Text style={styles.amountLabel}>Pagado</Text>
                    </View>
                    <Text style={[styles.amountValue, { color: P.text }]} numberOfLines={1} adjustsFontSizeToFit>
                      {formatCurrencyInt(d.total_paid)}
                    </Text>
                  </View>
                  <View style={styles.amountCol}>
                    <View style={styles.amountHead}>
                      <View style={[styles.amountIcon, { backgroundColor: P.green + "1F" }]}>
                        <Ionicons name="stats-chart" size={11} color={P.green} />
                      </View>
                      <Text style={styles.amountLabel}>Total</Text>
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
                      style={[styles.trackFill, { width: `${Math.max(3, pctInt)}%` }]}
                    />
                  </View>
                  <Text style={styles.trackPct}>{pctInt}%</Text>
                </View>
              </Pressable>
            );
          })}

          {filtered.length === 0 && (
            <View style={{ alignItems: "center", padding: 40 }}>
              <Ionicons name="cash-outline" size={48} color={P.muted} />
              <Text style={{ color: P.muted, marginTop: 10 }}>Sin deudas en esta vista</Text>
            </View>
          )}

          {/* Add debt */}
          <Pressable testID="add-debt-inline" onPress={() => router.push("/debts/new")} style={styles.addRow}>
            <Ionicons name="add" size={20} color={P.green} />
            <Text style={styles.addRowText}>Agregar nueva deuda o préstamo</Text>
          </Pressable>
        </View>
      </ScrollView>
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
            <Text style={styles.pillTextActive} numberOfLines={1}>{label}</Text>
          </LinearGradient>
        ) : (
          <View style={[styles.pill, styles.pillIdle]}>
            <Text style={styles.pillText} numberOfLines={1}>{label}</Text>
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
}: {
  icon: any;
  tint: string;
  label: string;
  value: string;
  valueColor: string;
  last: boolean;
}) {
  const styles = useStyles();
  return (
    <View style={[styles.metricRow, last && { paddingBottom: 0 }]}>
      <View style={[styles.metricIcon, { backgroundColor: tint + "22" }]}>
        <Ionicons name={icon} size={13} color={tint} />
      </View>
      <Text style={styles.metricLabel} numberOfLines={1}>{label}</Text>
      <Text style={[styles.metricValue, { color: valueColor }]} numberOfLines={1}>{value}</Text>
    </View>
  );
}

// Back-face block — ONE template used identically for both "A quién debo" and
// "Quién me debe" (same icon/title/total/row structure; only data + accent
// differ). Max 2 rows fit safely inside the locked card height; extras show
// "+ N más". Real debt data only.
function BackBlock({
  icon,
  accent,
  title,
  total,
  list,
  emptyText,
}: {
  icon: any;
  accent: string;
  title: string;
  total: string;
  list: any[];
  emptyText: string;
}) {
  const { scheme } = useTheme();
  const P = palette(scheme);
  const styles = useStyles();
  const rows = list.slice(0, 2);
  const more = list.length - rows.length;
  return (
    <View style={styles.backBlock}>
      <View style={[styles.backIcon, { backgroundColor: accent + "22" }]}>
        <Ionicons name={icon} size={15} color={accent} />
      </View>
      <Text style={styles.backBlockTitle} numberOfLines={1}>{title}</Text>
      <Text style={[styles.backBlockTotal, { color: accent }]} numberOfLines={1}>{total}</Text>
      {rows.map((d) => (
        <View key={d.id} style={styles.backRow}>
          <Text style={styles.backRowLabel} numberOfLines={1}>{d.person || d.name}</Text>
          <Text style={[styles.backRowValue, { color: P.text }]} numberOfLines={1}>{formatCurrencyInt(d.remaining_amount)}</Text>
        </View>
      ))}
      {more > 0 && <Text style={styles.backMore}>+ {more} más</Text>}
      {list.length === 0 && <Text style={styles.backEmpty}>{emptyText}</Text>}
    </View>
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

    /* summary */
    summaryCard: {
      flexDirection: "row",
      alignItems: "center",
      marginHorizontal: spacing.lg,
      backgroundColor: P.card,
      borderRadius: radius.cardLg,
      padding: spacing.lg,
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

    /* summary back face (flip) — ONE template reused for both blocks */
    backBlock: { flex: 1, alignSelf: "stretch" },
    backIcon: { width: 30, height: 30, borderRadius: 10, alignItems: "center", justifyContent: "center", marginBottom: 8 },
    backBlockTitle: { fontSize: 12.5, fontWeight: "700", color: P.muted, marginBottom: 4 },
    backBlockTotal: { fontSize: 19, fontWeight: "800", letterSpacing: -0.4, marginBottom: 10 },
    backRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, paddingVertical: 3.5 },
    backRowLabel: { flex: 1, fontSize: 11.5, color: P.muted },
    backRowValue: { fontSize: 12, fontWeight: "700", letterSpacing: -0.2 },
    backMore: { fontSize: 11, color: P.muted, fontWeight: "600", marginTop: 5 },
    backEmpty: { fontSize: 12, color: P.muted, marginTop: 2 },
    flipHint: { position: "absolute", top: 8, right: 8 },

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
    amountCol: { flex: 1 },
    amountHead: { flexDirection: "row", alignItems: "center", gap: 5, marginBottom: 4 },
    amountIcon: { width: 18, height: 18, borderRadius: 6, alignItems: "center", justifyContent: "center" },
    amountLabel: { fontSize: 11.5, color: P.muted, fontWeight: "500" },
    amountValue: { fontSize: 15.5, fontWeight: "800", letterSpacing: -0.3 },

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
