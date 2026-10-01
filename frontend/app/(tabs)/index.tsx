import React, { useState, useMemo, useCallback, useRef } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet, RefreshControl, Dimensions, Platform, Animated as RNAnimated } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedScrollHandler,
  useAnimatedReaction,
  LinearTransition,
  type SharedValue,
} from "react-native-reanimated";
import Svg, { Path as SvgPath } from "react-native-svg";
import { LinearGradient } from "expo-linear-gradient";
import { useQuery } from "@tanstack/react-query";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";

import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeColors } from "@/src/theme";
import { formatCurrency, formatCurrencyInt, formatDateLong, formatDateTime, translateCategoryName } from "@/src/format";
import i18n, { useTranslation } from "@/src/i18n";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";
import { WalletIcon, ChartIcon, HandCoinIcon } from "@/src/components/animated-section-icons";
import { DateRangeSheet, type DateRange } from "@/src/components/date-range-sheet";

// --- HOME-ONLY color redesign (light mode only) ---------------------------
// These tokens SHADOW the global theme ONLY on the Home screen in light mode,
// so no other screen/tab is affected and dark mode keeps its existing look.
// They map onto existing theme-token keys so the many `colors.*` references in
// this file automatically pick up the new premium sage/green identity.
const HOME_LIGHT: Partial<ThemeColors> = {
  onSurface: "#15251E", // strong dark green-black titles/values
  muted: "#68746D", // muted gray-green secondary text
  brandPrimary: "#126046", // green becomes the Home accent (was coral)
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E66B27", // warm burnt-orange accent (próximo pago)
  statsPurple: "#7546D7",
  accountsBlue: "#377FC4",
  incomeGreen: "#138B66",
  expenseRed: "#D84D45",
  border: "rgba(39,71,56,0.10)",
  borderStrong: "rgba(39,71,56,0.14)",
  divider: "#E4E7E2",
  surfaceSecondary: "#FCFCF8", // warm white surfaces
};

// Rich, distinctive per-account identity colors (Home light mode only). Keyed
// by lowercased account name; unknown accounts fall back to their real color.
const HOME_ACCOUNT_COLORS: Record<string, string> = {
  "chase checking": "#0C5C46", // deep emerald
  efectivo: "#C6952C", // premium gold
  ahorros: "#176F78", // blue-teal
  "cuenta 2": "#678E58", // moss green
  "cuenta 6": "#E2763E", // burnt orange
};
function homeAccountColor(a: any, scheme: string): string {
  if (scheme === "dark") return a?.color;
  const key = (a?.name || "").trim().toLowerCase();
  return HOME_ACCOUNT_COLORS[key] || a?.color;
}

// --- Color helpers (visual-only) for the account cards. Blend a hex color
// toward white (lighten) or black (darken) to build subtle gradients and the
// slightly darker arrow button, without touching any data. ---
function hexToRgb(hex: string) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
function mixToward(hex: string, target: number, amt: number) {
  try {
    const { r, g, b } = hexToRgb(hex);
    const c = (v: number) => Math.max(0, Math.min(255, Math.round(v + (target - v) * amt)));
    return `rgb(${c(r)},${c(g)},${c(b)})`;
  } catch {
    return hex;
  }
}
const lighten = (hex: string, amt: number) => mixToward(hex, 255, amt);
const darken = (hex: string, amt: number) => mixToward(hex, 0, amt);

function accountTypeLabel(t: string) {
  const m: Record<string, string> = {
    cash: "Efectivo", checking: "Corriente", savings: "Ahorro",
    credit_card: "Tarjeta", wallet: "Wallet", other: "Otra",
  };
  return m[t] || t;
}

function accountBars(accounts: any[], total: number, colors: ThemeColors, scheme: string) {
  const positives = accounts.filter((a) => a.current_balance > 0);
  const base = total > 0 ? total : positives.reduce((s, a) => s + a.current_balance, 0);
  // Home distribution preview shows a MAXIMUM of 5 accounts (top by balance).
  const sorted = [...positives].sort((a, b) => b.current_balance - a.current_balance).slice(0, 5);
  if (sorted.length === 0) {
    return <Text style={{ color: colors.muted, fontSize: 10 }}>{i18n.t("home.noAccounts")}</Text>;
  }
  // Soft neutral track — clearly visible against the warm-white card surface.
  const track = scheme === "dark" ? "#3A352F" : "#E5E9E3";
  return sorted.map((a) => {
    const ac = homeAccountColor(a, scheme);
    const pct = base > 0 ? Math.round((a.current_balance / base) * 100) : 0;
    return (
      <View key={a.id}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={{ flexShrink: 1, fontSize: 10, fontWeight: "700", color: colors.onSurface }} numberOfLines={1}>
            {a.name}
          </Text>
          <Text style={{ fontSize: 10, fontWeight: "800", color: ac, marginLeft: 4 }}>{pct}%</Text>
        </View>
        <View
          style={{
            marginTop: 4,
            height: 9,
            borderRadius: 4.5,
            backgroundColor: track,
            overflow: "hidden",
          }}
        >
          <View style={{ width: `${Math.max(6, pct)}%`, height: "100%", backgroundColor: ac, borderRadius: 4.5 }} />
        </View>
      </View>
    );
  });
}

// Soft pastel "mountain/hill" decoration that emanates from the RIGHT side of a
// Deudas tile. Two overlapping low-opacity hills (no blur, no image, no deps) —
// static + cheap for Android. Rendered BEHIND the tile content (absoluteFill +
// pointerEvents none) and clipped by the tile's overflow:hidden.
function DebtWave({ color, opacity }: { color: string; opacity: number }) {
  return (
    <View
      pointerEvents="none"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      style={StyleSheet.absoluteFill}
    >
      <Svg width="100%" height="100%" viewBox="0 0 120 80" preserveAspectRatio="none">
        <SvgPath
          d="M120,80 L120,16 C108,11 98,30 82,26 C66,22 56,42 40,37 C26,33 12,43 0,39 L0,80 Z"
          fill={color}
          opacity={opacity * 0.5}
        />
        <SvgPath
          d="M120,80 L120,40 C110,35 100,51 84,48 C66,45 54,61 36,56 C22,52 10,59 0,57 L0,80 Z"
          fill={color}
          opacity={opacity}
        />
      </Svg>
    </View>
  );
}


// Mini 7-bar chart for the income / expense cards. Uses real amounts; when a
// period has no data it falls back to a soft placeholder pattern so the card
// never looks empty. Colors are passed in to respect the current theme.
function MiniBars({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data, 0);
  const nonZero = data.filter((v) => v > 0).length;
  const pattern = [0.45, 0.6, 0.5, 0.8, 0.55, 1, 0.65];
  // With sparse real data (0-2 active days) the chart would look like a flat
  // line, so fall back to a soft pattern to keep the reference look.
  const usePattern = nonZero < 3;
  return (
    <View style={mb.row}>
      {data.map((v, i) => {
        const ratio = usePattern ? pattern[i % pattern.length] : v / max;
        const peak = usePattern ? pattern[i % pattern.length] === 1 : v === max && v > 0;
        return (
          <View
            key={i}
            style={{
              flex: 1,
              height: 6 + ratio * 22,
              borderRadius: 3,
              backgroundColor: color + (peak ? "" : "59"),
            }}
          />
        );
      })}
    </View>
  );
}

// Small drag-handle affordance (2×3 dots) shown at the card's top-right.
function DragDots({ color }: { color: string }) {
  return (
    <View style={{ flexDirection: "row", gap: 3 }}>
      {[0, 1].map((c) => (
        <View key={c} style={{ gap: 3 }}>
          {[0, 1, 2].map((r) => (
            <View key={r} style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: color }} />
          ))}
        </View>
      ))}
    </View>
  );
}

const mb = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "flex-end", height: 34, gap: 3, marginTop: 2 },
});

// Smooth wave / line chart used inside the Gastos card. Mirrors MiniBars'
// sparse-data fallback so it always renders as a clean wave rather than a flat
// line, and fills a soft tinted area under the curve.
function MiniWave({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data, 0);
  const nonZero = data.filter((v) => v > 0).length;
  const pattern = [0.35, 0.55, 0.4, 0.72, 0.5, 0.85, 0.6];
  const usePattern = nonZero < 3;
  const W = 100;
  const H = 34;
  const n = data.length;
  const pts = data.map((v, i) => {
    const ratio = usePattern ? pattern[i % pattern.length] : max > 0 ? v / max : 0;
    const x = n > 1 ? (i / (n - 1)) * W : W / 2;
    const y = H - 4 - ratio * (H - 9);
    return { x, y };
  });
  let line = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const xMid = (pts[i].x + pts[i + 1].x) / 2;
    const yMid = (pts[i].y + pts[i + 1].y) / 2;
    line += ` Q ${pts[i].x.toFixed(1)} ${pts[i].y.toFixed(1)} ${xMid.toFixed(1)} ${yMid.toFixed(1)}`;
  }
  line += ` T ${pts[n - 1].x.toFixed(1)} ${pts[n - 1].y.toFixed(1)}`;
  const area = `${line} L ${W} ${H} L 0 ${H} Z`;
  return (
    <View style={mb.row}>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <SvgPath d={area} fill={color + "22"} />
        <SvgPath d={line} stroke={color} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </Svg>
    </View>
  );
}


// Reusable external section header — same visual style as the "Movimientos
// recientes" header (soft coral icon tile on the left, title + subtitle, and a
// compact very-light-coral "Ver todo >" pill on the right). Visual-only; it
// wires an optional onSeeAll navigation and an optional right-side node.
function SectionHeader({
  icon,
  iconKind,
  title,
  subtitle,
  onSeeAll,
  seeAllTestID,
  right,
  scrollY,
  viewportH,
  sectionY,
  focusId,
}: {
  icon: string;
  iconKind?: "wallet" | "chart" | "hand";
  title: string;
  subtitle: string;
  onSeeAll?: () => void;
  seeAllTestID?: string;
  right?: React.ReactNode;
  // Optional one-time internal-icon animation wiring (Home section icons only).
  scrollY?: SharedValue<number>;
  viewportH?: SharedValue<number>;
  sectionY?: SharedValue<number>;
  focusId?: SharedValue<number>;
}) {
  const { colors: baseColors, scheme } = useTheme();
  const { t } = useTranslation();
  const colors = scheme === "dark" ? baseColors : ({ ...baseColors, ...HOME_LIGHT } as ThemeColors);
  const styles = useStyles();

  // `playSignal` increments once when the section first enters the viewport in
  // the current Home visit; the animated icon watches it to run its internal
  // timeline. `played` gates it to once-per-visit and resets on Home focus.
  const playSignal = useSharedValue(0);
  const played = useSharedValue(false);

  useAnimatedReaction(
    () => {
      if (!scrollY || !viewportH || !sectionY || !focusId) return null;
      const vp = viewportH.value;
      const visible = vp > 0 && sectionY.value + 24 < scrollY.value + vp;
      return { visible, focus: focusId.value };
    },
    (cur, prev) => {
      if (cur == null) return;
      const focusChanged = prev == null || cur.focus !== prev.focus;
      if (focusChanged) {
        // New Home visit → play the entrance once immediately, so it fires when
        // Home is entered (not only after the section is scrolled into view).
        played.value = true;
        playSignal.value = playSignal.value + 1;
        return;
      }
      if (cur.visible && !played.value) {
        played.value = true;
        playSignal.value = playSignal.value + 1;
      }
    },
  );

  const iconColor = colors.brandPrimary;

  return (
    <View style={styles.mrHeader}>
      {/* Static rounded tile — only the internal graphic animates. */}
      <View style={styles.mrIconTile}>
        {iconKind === "wallet" ? (
          <WalletIcon color={iconColor} play={playSignal} />
        ) : iconKind === "chart" ? (
          <ChartIcon color={iconColor} play={playSignal} />
        ) : iconKind === "hand" ? (
          <HandCoinIcon color={iconColor} play={playSignal} />
        ) : (
          <Ionicons name={icon as any} size={18} color={iconColor} />
        )}
      </View>
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={styles.mrTitle} numberOfLines={1}>{title}</Text>
        <Text style={styles.mrSubtitle} numberOfLines={1}>{subtitle}</Text>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        {right}
        {onSeeAll && (
          <Pressable testID={seeAllTestID} onPress={onSeeAll} style={styles.seeAllBtn}>
            <Text style={styles.seeAllText}>{t("common.seeAll")}</Text>
            <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
          </Pressable>
        )}
      </View>
    </View>
  );
}

// Movimientos recientes filter pill. Copies ONLY the visual language + press
// interaction of the Deudas FilterPill (pill shape, border, green selected
// gradient, spring compression to ~0.95 on press-in and a soft spring return on
// release). Business logic (txFilter, testIDs, colors, gradients, layout) is
// unchanged — this wrapper only adds the shared press-spring feedback.
function MRPill({
  testID,
  active,
  onPress,
  icon,
  iconColor,
  label,
  gradient,
  styles,
}: {
  testID: string;
  active: boolean;
  onPress: () => void;
  icon: string;
  iconColor: string;
  label: string;
  gradient: [string, string];
  styles: any;
}) {
  const scale = useRef(new RNAnimated.Value(1)).current;
  const useNative = Platform.OS !== "web";
  const pressIn = () => {
    RNAnimated.spring(scale, { toValue: 0.95, useNativeDriver: useNative, speed: 50, bounciness: 0 }).start();
  };
  const pressOut = () => {
    RNAnimated.spring(scale, { toValue: 1, useNativeDriver: useNative, speed: 20, bounciness: 12 }).start();
  };
  const content = (
    <>
      <Ionicons name={icon as any} size={13} color={active ? "#fff" : iconColor} />
      <Text style={[styles.mrPillText, active && styles.mrPillTextActive]}>{label}</Text>
    </>
  );
  return (
    <RNAnimated.View style={{ transform: [{ scale }], flexShrink: 0 }}>
      <Pressable testID={testID} onPress={onPress} onPressIn={pressIn} onPressOut={pressOut}>
        {active ? (
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.mrPill}>
            {content}
          </LinearGradient>
        ) : (
          <View style={[styles.mrPill, styles.mrPillIdle]}>{content}</View>
        )}
      </Pressable>
    </RNAnimated.View>
  );
}

// Calendar control for Movimientos recientes. Same Deudas-style press spring as
// MRPill; keeps its existing icon-pill appearance and its existing onPress
// (opens the SAME DateRangeSheet). Purely additive press feedback.
function MRIconPill({
  testID,
  active,
  onPress,
  activeColor,
  idleColor,
  styles,
}: {
  testID: string;
  active: boolean;
  onPress: () => void;
  activeColor: string;
  idleColor: string;
  styles: any;
}) {
  const scale = useRef(new RNAnimated.Value(1)).current;
  const useNative = Platform.OS !== "web";
  const pressIn = () => {
    RNAnimated.spring(scale, { toValue: 0.95, useNativeDriver: useNative, speed: 50, bounciness: 0 }).start();
  };
  const pressOut = () => {
    RNAnimated.spring(scale, { toValue: 1, useNativeDriver: useNative, speed: 20, bounciness: 12 }).start();
  };
  return (
    <RNAnimated.View style={{ transform: [{ scale }], flexShrink: 0 }}>
      <Pressable
        testID={testID}
        onPress={onPress}
        onPressIn={pressIn}
        onPressOut={pressOut}
        style={[styles.mrIconPill, active && styles.mrIconPillActive]}
      >
        <Ionicons name="calendar-outline" size={15} color={active ? activeColor : idleColor} />
      </Pressable>
    </RNAnimated.View>
  );
}

export default function Home() {
  const { colors: baseColors, scheme } = useTheme();
  const { t } = useTranslation();
  // Home-only light palette override (dark mode untouched).
  const colors = useMemo(
    () => (scheme === "dark" ? baseColors : ({ ...baseColors, ...HOME_LIGHT } as ThemeColors)),
    [baseColors, scheme],
  );
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [hidden, setHidden] = useState(false);
  const [txFilter, setTxFilter] = useState("all");
  const [dateSheet, setDateSheet] = useState(false);
  const [dateRange, setDateRange] = useState<DateRange | null>(null);

  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const userQ = useQuery({ queryKey: ["user"], queryFn: api.getUser });
  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  // Existing /api/debts endpoint (same one the /debts screen already uses) — read-only.
  // Used ONLY to derive the REAL per-direction debt count for the Deudas cards.
  const debtsListQ = useQuery({ queryKey: ["debts"], queryFn: api.listDebts });

  const summary = summaryQ.data;
  // Display-only proportions of the existing summary, without new requests.
  const debtTotal = (summary?.debts?.i_owe || 0) + (summary?.debts?.they_owe || 0);
  const debtShare = (amount: number) => debtTotal > 0 ? Math.max(0, Math.min(100, amount / debtTotal * 100)) : 0;
  // Real counts derived from existing data (no new API, no backend change).
  const iOweCount = (debtsListQ.data || []).filter((d: any) => d?.direction === "i_owe").length;
  const theyOweCount = (debtsListQ.data || []).filter((d: any) => d?.direction === "they_owe").length;
  // "N deudas · X% del total" — falls back to just the percentage when the count
  // is not yet available / is zero, so no wrong count ever flashes during load.
  const debtCountShareLabel = (amount: number, count: number) => {
    if (hidden) return "••••";
    const isEs = i18n.language.startsWith("es");
    const pct = `${Math.round(debtShare(amount))}% ${isEs ? "del total" : "of total"}`;
    if (!count) return pct;
    const noun = isEs ? (count === 1 ? "deuda" : "deudas") : (count === 1 ? "debt" : "debts");
    return `${count} ${noun} · ${pct}`;
  };
  // Scheme-aware opacity for the decorative pastel hills (subtle but perceptible).
  const debtWaveOpacity = scheme === "dark" ? 0.12 : 0.15;

  const user = userQ.data;
  const recent = useMemo(() => {
    let items: any[] = txQ.data || [];
    if (txFilter === "income") items = items.filter((t: any) => t.type === "income" || t.type === "loan_received");
    else if (txFilter === "expense") items = items.filter((t: any) => t.type === "expense" || t.type === "debt_payment");
    else if (txFilter === "transfer") items = items.filter((t: any) => t.type === "transfer");
    if (dateRange) {
      items = items.filter((t: any) => {
        const ts = new Date(t.date).getTime();
        return ts >= dateRange.start && ts <= dateRange.end;
      });
    }
    return items.slice(0, 10);
  }, [txQ.data, txFilter, dateRange]);
  const cats: any[] = catQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));
  const accounts: any[] = useMemo(() => accQ.data || [], [accQ.data]);

  // --- Accounts carousel (paginate ONLY the colored account cards) ----------
  // Groups of 5 existing accounts per page. Nothing else in the section moves.
  const [acctPage, setAcctPage] = useState(0);
  const [carouselW, setCarouselW] = useState<number>(Dimensions.get("window").width);
  const acctPages = useMemo(() => {
    const groups: any[][] = [];
    for (let i = 0; i < accounts.length; i += 5) groups.push(accounts.slice(i, i + 5));
    return groups.length ? groups : [[]];
  }, [accounts]);
  const acctPageCount = acctPages.length;
  // Keep the active page valid if the number of accounts changes.
  const safeAcctPage = Math.min(acctPage, acctPageCount - 1);
  const onCarouselScroll = (e: any) => {
    const w = e.nativeEvent.layoutMeasurement?.width || carouselW;
    if (w > 0) {
      const p = Math.round(e.nativeEvent.contentOffset.x / w);
      if (p !== acctPage && p >= 0 && p < acctPageCount) setAcctPage(p);
    }
  };

  const money = (n: number) => (hidden ? "••••" : formatCurrency(n));
  const debtMoney = (n: number) => (hidden ? "••••" : formatCurrencyInt(n));

  // Split the existing currency formatting into { symbol, amount } so the
  // account-card balance can show the "$" inside a small circle and the number
  // beside it. Uses the SAME formatCurrency values — display-only, no data change.
  const balanceParts = (n: number) => {
    const full = formatCurrency(n); // e.g. "$2,500" or "-$3,600"
    const m = full.match(/^(-?)(\D*)(.*)$/);
    const sign = m?.[1] || "";
    const symbol = ((m?.[2] || "$").trim() || "$");
    const num = m?.[3] || full;
    return { symbol, amount: hidden ? "••••" : sign + num };
  };

  // Account growth indicator (visual-only) — derived from real summary data:
  // this month's net movement relative to the opening balance. No hardcoding.
  const monthNet = (summary?.month_income || 0) - (summary?.month_expense || 0);
  const openingBalance = (summary?.total_balance || 0) - monthNet;
  const growthPct = openingBalance > 0 ? (monthNet / openingBalance) * 100 : 0;
  const growthPositive = growthPct >= 0;

  // Last-7-days mini-chart data + daily averages for the Income / Expense cards.
  const stats = useMemo(() => {
    const txs = txQ.data || [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const incBars = Array(7).fill(0) as number[];
    const expBars = Array(7).fill(0) as number[];
    txs.forEach((t: any) => {
      const d = new Date(t.date);
      d.setHours(0, 0, 0, 0);
      const diff = Math.round((today.getTime() - d.getTime()) / 86400000);
      if (diff < 0 || diff > 6) return;
      if (t.type === "income") incBars[6 - diff] += t.amount;
      else if (t.type === "expense" || t.type === "debt_payment") expBars[6 - diff] += t.amount;
    });
    const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    return {
      incBars,
      expBars,
      avgIncome: (summary?.month_income || 0) / daysInMonth,
      avgExpense: (summary?.month_expense || 0) / daysInMonth,
    };
  }, [txQ.data, summary?.month_income, summary?.month_expense]);

  const TX_FILTERS = [
    { id: "all", label: t("home.filterAll"), icon: "grid", color: colors.brandPrimary },
    { id: "income", label: t("home.filterIncome"), icon: "trending-up", color: colors.incomeGreen },
    { id: "expense", label: t("home.filterExpenses"), icon: "trending-down", color: colors.expenseRed },
    { id: "transfer", label: t("home.filterTransfers"), icon: "swap-horizontal", color: colors.accountsBlue },
  ] as const;

  // --- Section-icon entrance animation wiring (visual-only, UI thread) ------
  // Shared values track scroll offset + viewport height + each section's Y so
  // each icon can play its entrance once when its section first becomes
  // visible. `focusId` bumps on every Home focus so the entrance can replay
  // after the user leaves and returns (scrolling alone never replays it).
  const scrollY = useSharedValue(0);
  const viewportH = useSharedValue(0);
  const accountsY = useSharedValue(0);
  const summaryY = useSharedValue(0);
  const debtsY = useSharedValue(0);
  const focusId = useSharedValue(0);

  const scrollHandler = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollY.value = e.contentOffset.y;
    },
  });

  useFocusEffect(
    useCallback(() => {
      focusId.value = focusId.value + 1;
      return () => {};
    }, [focusId]),
  );

  return (
    <View style={{ flex: 1, backgroundColor: scheme === "dark" ? colors.surface : "#E8EFE7" }}>
    <Animated.ScrollView
      testID="home-scroll"
      style={{ flex: 1, backgroundColor: "transparent" }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: spacing.lg }}
      onScroll={scrollHandler}
      scrollEventThrottle={16}
      onLayout={(e) => {
        viewportH.value = e.nativeEvent.layout.height;
      }}
      refreshControl={
        <RefreshControl
          refreshing={summaryQ.isFetching}
          onRefresh={() => {
            summaryQ.refetch();
            txQ.refetch();
          }}
          tintColor={colors.brandPrimary}
        />
      }
    >
      {/* Header — compact balance + growth (greeting removed) */}
      <View style={styles.header}>
        <View style={styles.balanceIconTile}>
          <Ionicons name="wallet-outline" size={20} color={colors.brandPrimary} />
        </View>
        <View style={styles.balanceBlock}>
          <Text
            style={styles.balanceNumber}
            testID="total-balance"
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.6}
          >
            {hidden ? "••••" : formatCurrencyInt(summary?.total_balance || 0)}
          </Text>
          <View style={styles.growthRow}>
            <Ionicons
              name={growthPositive ? "arrow-up" : "arrow-down"}
              size={15}
              color={growthPositive ? colors.incomeGreen : colors.expenseRed}
            />
            <Text style={[styles.growthText, { color: growthPositive ? colors.incomeGreen : colors.expenseRed }]}>
              {Math.abs(growthPct).toFixed(1)}%
            </Text>
          </View>
        </View>
        <Pressable testID="notifications-btn" style={styles.roundIcon}>
          <Ionicons name="notifications-outline" size={22} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="profile-more-btn" onPress={() => router.push("/more")} style={styles.avatar}>
          <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>
            {(user?.name || "U").slice(0, 1)}
          </Text>
        </Pressable>
      </View>

      {/* Section divider — before Mis cuentas */}
      <View style={styles.sectionDivider} />

      {/* Mis cuentas */}
      <View
        style={{ paddingTop: spacing.lg }}
        onLayout={(e) => {
          accountsY.value = e.nativeEvent.layout.y;
        }}
      >
        <View style={{ paddingHorizontal: spacing.lg }}>
          <SectionHeader
            icon="wallet-outline"
            iconKind="wallet"
            title={t("home.myAccounts")}
            subtitle={t("home.myAccountsSubtitle")}
            onSeeAll={() => router.push("/accounts")}
            seeAllTestID="see-all-accounts"
            scrollY={scrollY}
            viewportH={viewportH}
            sectionY={accountsY}
            focusId={focusId}
            right={
              <Pressable testID="toggle-hide-btn" onPress={() => setHidden((h) => !h)} hitSlop={8}>
                <Ionicons name={hidden ? "eye-off-outline" : "eye-outline"} size={20} color={colors.muted} />
              </Pressable>
            }
          />
        </View>
        <ScrollView
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          decelerationRate="fast"
          snapToInterval={carouselW}
          snapToAlignment="start"
          disableIntervalMomentum
          scrollEventThrottle={16}
          onScroll={onCarouselScroll}
          onMomentumScrollEnd={onCarouselScroll}
          onLayout={(e) => setCarouselW(e.nativeEvent.layout.width)}
          testID="accounts-carousel"
        >
          {acctPages.map((pageAccounts, pi) => (
            <View key={pi} style={{ width: carouselW }}>
              <View style={styles.walletGrid}>
                {pageAccounts.map((a, idx) => {
                  const isThird = (idx + 1) % 3 === 0;
                  const ac = homeAccountColor(a, scheme);
                  return (
                    <Pressable
                      key={a.id}
                      testID={`wallet-${a.id}`}
                      onPress={guard(() => router.push(`/accounts/new?id=${a.id}`))}
                      style={[styles.walletCard, { backgroundColor: ac }, isThird && styles.walletCardLast]}
                    >
                      <View style={styles.walletInner}>
                        <LinearGradient
                          colors={[lighten(ac, 0.16), ac, darken(ac, 0.06)]}
                          start={{ x: 0, y: 0 }}
                          end={{ x: 1, y: 1 }}
                          style={StyleSheet.absoluteFill}
                        />
                        <Ionicons
                          name={a.icon as any}
                          size={58}
                          color="rgba(255,255,255,0.12)"
                          style={styles.walletWatermark}
                        />
                        <View style={styles.walletTopRow}>
                          <View style={styles.walletIconBox}>
                            <Ionicons name={a.icon as any} size={14} color="#fff" />
                          </View>
                          <View style={[styles.walletArrow, { backgroundColor: darken(ac, 0.16) }]}>
                            <Ionicons name="chevron-forward" size={12} color="#fff" />
                          </View>
                        </View>
                        <View style={styles.walletTextWrap}>
                          <Text style={styles.walletName} numberOfLines={1}>{a.name}</Text>
                          <View style={[styles.balancePill, { backgroundColor: darken(ac, 0.1) }]}>
                            <View style={styles.dollarCircle}>
                              <Text style={styles.dollarSymbol}>{balanceParts(a.current_balance).symbol}</Text>
                            </View>
                            <Text style={styles.walletBalance} numberOfLines={1} adjustsFontSizeToFit>
                              {balanceParts(a.current_balance).amount}
                            </Text>
                          </View>
                        </View>
                      </View>
                    </Pressable>
                  );
                })}
                <Pressable
                  testID="wallet-add"
                  onPress={() => router.push("/accounts/new")}
                  style={[styles.walletAddCard, (pageAccounts.length + 1) % 3 === 0 && styles.walletCardLast]}
                >
                  <Ionicons name="add" size={22} color={colors.brandPrimary} />
                  <Text style={styles.walletAddText}>{t("home.addAccount")}</Text>
                  {acctPageCount > 1 && (
                    <View style={styles.walletDots} pointerEvents="none">
                      {acctPages.map((_, di) => (
                        <View
                          key={di}
                          style={[styles.walletDot, di === safeAcctPage && styles.walletDotActive]}
                        />
                      ))}
                    </View>
                  )}
                </Pressable>
              </View>
            </View>
          ))}
        </ScrollView>
      </View>

      {/* Section divider — before Resumen del mes */}
      <View style={styles.sectionDivider} />

      {/* Resumen del mes */}
      <View
        style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg }}
        onLayout={(e) => {
          summaryY.value = e.nativeEvent.layout.y;
        }}
      >
        <SectionHeader
          icon="stats-chart-outline"
          iconKind="chart"
          title={t("home.monthSummary")}
          subtitle={t("home.monthSummarySubtitle")}
          onSeeAll={() => router.push("/(tabs)/reports")}
          seeAllTestID="see-all-summary"
          scrollY={scrollY}
          viewportH={viewportH}
          sectionY={summaryY}
          focusId={focusId}
        />
      </View>

      {/* Income / Expense / Accounts distribution */}
      <View style={styles.miniRow}>
        <View style={[styles.miniCard, styles.miniHalfLeft, styles.cardIncome]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.incomeGreen }]}>
                <Ionicons name="trending-up" size={16} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>{t("home.thisMonth")}</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>{t("home.income")}</Text>
            <Text
              style={[styles.miniAmount, { color: colors.incomeGreen }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              +{money(summary?.month_income || 0)}
            </Text>
            <MiniBars data={stats.incBars} color={colors.incomeGreen} />
            <View style={styles.mcFooter}>
              <Ionicons name="calendar-outline" size={13} color={colors.incomeGreen} />
              <View style={styles.mcFooterCol}>
                <Text style={styles.mcAvgLabel}>{t("home.dailyAverage")}</Text>
                <Text style={styles.mcAvgVal}>{money(stats.avgIncome)}</Text>
              </View>
            </View>
          </View>
          <View style={[styles.miniCard, styles.miniHalfRight, styles.cardExpense]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.expenseRed }]}>
                <Ionicons name="trending-down" size={16} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>{t("home.thisMonth")}</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>{t("home.expenses")}</Text>
            <Text
              style={[styles.miniAmount, { color: colors.expenseRed }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              -{money(summary?.month_expense || 0)}
            </Text>
            <MiniWave data={stats.expBars} color={colors.expenseRed} />
            <View style={styles.mcFooter}>
              <Ionicons name="calendar-outline" size={13} color={colors.expenseRed} />
              <View style={styles.mcFooterCol}>
                <Text style={styles.mcAvgLabel}>{t("home.dailyAverage")}</Text>
                <Text style={styles.mcAvgVal}>{money(stats.avgExpense)}</Text>
              </View>
            </View>
          </View>
        <View style={[styles.miniCard, styles.miniAccounts]}>
          <View testID="cuentas-scroll" style={{ gap: 6 }}>
            {accountBars(acctPages[safeAcctPage] || [], summary?.total_balance || 0, colors, scheme)}
          </View>
        </View>
      </View>

      {/* Section divider — before Deudas */}
      <View style={styles.sectionDivider} />

      {/* Deudas */}
      <View
        style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}
        onLayout={(e) => {
          debtsY.value = e.nativeEvent.layout.y;
        }}
      >
        <SectionHeader
          icon="wallet-outline"
          iconKind="hand"
          title={t("home.debts")}
          subtitle={t("home.debtsSubtitle")}
          onSeeAll={() => router.push("/debts")}
          seeAllTestID="see-all-debts"
          scrollY={scrollY}
          viewportH={viewportH}
          sectionY={debtsY}
          focusId={focusId}
        />
      </View>

      {/* Debts card */}
      <View style={{ paddingHorizontal: spacing.lg }}>
        <Pressable testID="debts-card" onPress={() => router.push("/debts")} style={styles.debtCard}>
          <View style={styles.debtQuadRow}>
            <View style={[styles.debtQuadTile, styles.debtOweTint]}>
              <DebtWave color={colors.expenseRed} opacity={debtWaveOpacity} />
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.expenseRed + "14" }]}>
                  <Ionicons name="arrow-up" size={15} color={colors.expenseRed} />
                </View>
                <Text style={[styles.debtQuadLabel, { flex: 1 }]} numberOfLines={2}>{t("home.iOwe")}</Text>
                <View style={styles.debtArrowBtn}>
                  <Ionicons name="chevron-forward" size={11} color={colors.muted} />
                </View>
              </View>
              <Text style={[styles.debtQuadValue, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit>
                {debtMoney(summary?.debts?.i_owe || 0)}
              </Text>
              <View style={[styles.debtProgressTrack, { backgroundColor: colors.expenseRed + "12" }]}>
                <View style={[styles.debtProgressFill, { backgroundColor: colors.expenseRed, width: `${hidden ? 0 : debtShare(summary?.debts?.i_owe || 0)}%` }]} />
              </View>
              <Text style={styles.debtQuadFoot} numberOfLines={1}>{debtCountShareLabel(summary?.debts?.i_owe || 0, iOweCount)}</Text>
            </View>
            <View style={[styles.debtQuadTile, styles.debtOwedTint]}>
              <DebtWave color={colors.incomeGreen} opacity={debtWaveOpacity} />
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.incomeGreen + "14" }]}>
                  <Ionicons name="arrow-down" size={15} color={colors.incomeGreen} />
                </View>
                <Text style={[styles.debtQuadLabel, { flex: 1 }]} numberOfLines={2}>{t("home.owedToMe")}</Text>
                <View style={styles.debtArrowBtn}>
                  <Ionicons name="chevron-forward" size={11} color={colors.muted} />
                </View>
              </View>
              <Text style={[styles.debtQuadValue, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit>
                {debtMoney(summary?.debts?.they_owe || 0)}
              </Text>
              <View style={[styles.debtProgressTrack, { backgroundColor: colors.incomeGreen + "12" }]}>
                <View style={[styles.debtProgressFill, { backgroundColor: colors.incomeGreen, width: `${hidden ? 0 : debtShare(summary?.debts?.they_owe || 0)}%` }]} />
              </View>
              <Text style={styles.debtQuadFoot} numberOfLines={1}>{debtCountShareLabel(summary?.debts?.they_owe || 0, theyOweCount)}</Text>
            </View>
          </View>
          <View style={styles.debtQuadRow}>
            <View style={[styles.debtQuadTile, styles.debtPaidTint]}>
              <DebtWave color={colors.statsPurple} opacity={debtWaveOpacity} />
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.statsPurple + "14" }]}>
                  <Ionicons name="card" size={15} color={colors.statsPurple} />
                </View>
                <Text style={[styles.debtQuadLabel, { flex: 1 }]} numberOfLines={2}>{t("home.paidThisMonth")}</Text>
                <View style={styles.debtArrowBtn}>
                  <Ionicons name="chevron-forward" size={11} color={colors.muted} />
                </View>
              </View>
              <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={styles.debtDecorBars}>
                {[13, 20, 29, 39].map((height) => (
                  <View key={height} style={{ width: 6, height, borderRadius: 3, backgroundColor: colors.statsPurple, opacity: 0.16 }} />
                ))}
              </View>
              <Text style={[styles.debtQuadValue, { color: colors.statsPurple }]} numberOfLines={1} adjustsFontSizeToFit>
                {debtMoney(summary?.debts?.paid_this_month || 0)}
              </Text>
              <Text style={styles.debtQuadFoot}>{t("home.goodProgress")}</Text>
            </View>
            <View style={[styles.debtQuadTile, styles.debtNextTint]}>
              <DebtWave color={colors.brandSecondary} opacity={debtWaveOpacity} />
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.brandSecondary + "14" }]}>
                  <Ionicons name="calendar-outline" size={15} color={colors.brandSecondary} />
                </View>
                <Text style={[styles.debtQuadLabel, { flex: 1 }]} numberOfLines={2}>{t("home.nextPayment")}</Text>
                <View style={styles.debtArrowBtn}>
                  <Ionicons name="chevron-forward" size={11} color={colors.muted} />
                </View>
              </View>
              <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={styles.debtDecorCalendar}>
                <Ionicons name="calendar-outline" size={66} color={colors.brandSecondary} />
              </View>
              {summary?.debts?.next_payment ? (
                <>
                  <Text style={styles.debtQuadDate} numberOfLines={1} adjustsFontSizeToFit>
                    {formatDateLong(summary.debts.next_payment.date)}
                  </Text>
                  <Text style={[styles.debtQuadValue, { color: colors.brandSecondary }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary.debts.next_payment.amount)}
                  </Text>
                  <Text style={styles.debtQuadFoot}>{t("home.keepPaymentsUpToDate")}</Text>
                </>
              ) : (
                <Text style={styles.debtQuadFoot}>{t("home.noUpcomingPayments")}</Text>
              )}
            </View>
          </View>
        </Pressable>
      </View>

      {/* Section divider — before Movimientos recientes */}
      <View style={styles.sectionDivider} />

      {/* Recent transactions — "Movimientos recientes" */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
        {/* Section header */}
        <View style={styles.mrHeader}>
          <View style={styles.mrIconTile}>
            <Ionicons name="layers-outline" size={18} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={styles.mrTitle} numberOfLines={1} ellipsizeMode="clip">
              {t("home.recentMovements")} <Text style={styles.mrTitleAccent}>{t("home.recentMovementsAccent")}</Text>
            </Text>
            <Text style={styles.mrSubtitle}>
              {t("home.recentMovementsSubtitle")}
            </Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <LockToggle testID="lock-home" compact />
            <Pressable testID="see-all-tx" onPress={() => router.push("/(tabs)/transactions")} style={styles.seeAllBtn}>
              <Text style={styles.seeAllText}>{t("common.seeAll")}</Text>
              <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
            </Pressable>
          </View>
        </View>

        {/* Filters */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.mrFilterRow}
        >
          {TX_FILTERS.map((f) => {
            const active = txFilter === f.id;
            return (
              <MRPill
                key={f.id}
                testID={`mr-filter-${f.id}`}
                active={active}
                onPress={() => setTxFilter(f.id)}
                icon={f.icon}
                iconColor={f.color}
                label={f.label}
                gradient={scheme === "dark" ? [colors.brandPrimary, colors.brandSecondary] : ["#16694A", "#146448"]}
                styles={styles}
              />
            );
          })}
          <MRIconPill
            testID="mr-filter-month"
            active={!!dateRange}
            onPress={() => setDateSheet(true)}
            activeColor={colors.brandPrimary}
            idleColor={colors.muted}
            styles={styles}
          />
        </ScrollView>

        {/* List card */}
        <Animated.View style={styles.mrCard} layout={LinearTransition.duration(260)}>
          {recent.length === 0 && (
            <Text style={{ color: colors.muted, textAlign: "center", padding: spacing.lg }}>
              {t("home.noMovements")}
            </Text>
          )}
          {recent.map((item, idx) => {
            const cat = catById[item.category_id];
            const isIncome = item.type === "income" || item.type === "loan_received";
            const isTransfer = item.type === "transfer";
            const color = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
            const sign = isTransfer ? "" : isIncome ? "+" : "-";
            const iconName =
              cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
            const tint = cat?.color || color;
            const badgeLabel = cat?.name ? translateCategoryName(cat.name) : (isTransfer ? t("txType.transfer") : isIncome ? t("txType.income") : t("txType.expense"));
            const badgeColor = cat?.color || color;
            return (
              <Animated.View key={item.id} layout={LinearTransition.duration(260)}>
                {idx > 0 && <View style={styles.mrDivider} />}
                <Pressable
                  testID={`mr-tx-${item.id}`}
                  onPress={guard(() => router.push(`/transactions/${item.id}`))}
                  style={styles.mrRow}
                >
                  <IconTile icon={iconName} tint={tint} size={36} />
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={styles.mrName} numberOfLines={1}>{item.name}</Text>
                    <View style={styles.mrTimeRow}>
                      <Ionicons name="time-outline" size={12} color={colors.muted} />
                      <Text style={styles.mrTime} numberOfLines={1}>{formatDateTime(item.date)}</Text>
                    </View>
                  </View>
                  <View style={[styles.mrBadge, { backgroundColor: badgeColor + "1A" }]}>
                    <Text style={[styles.mrBadgeText, { color: badgeColor }]} numberOfLines={1}>{badgeLabel}</Text>
                  </View>
                  <Text style={[styles.mrAmount, { color }]}>{sign}{formatCurrency(item.amount)}</Text>
                  <Ionicons name="chevron-forward" size={15} color={colors.muted} style={{ marginLeft: 4 }} />
                </Pressable>
              </Animated.View>
            );
          })}
        </Animated.View>

        {/* AI banner — taps through to the IA tab (same route as the mic in the bottom nav) */}
        <Animated.View layout={LinearTransition.duration(260)}>
        <Pressable testID="ai-banner" onPress={() => router.push("/(tabs)/transactions")} style={{ marginTop: 8 }}>
          <LinearGradient
            colors={scheme === "dark" ? [colors.brandPrimary + "1F", colors.statsPurple + "1F"] : ["#E5F1E7", "#E5F1E7"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.aiBanner}
          >
            <View style={styles.aiIcon}>
              <Ionicons name="sparkles" size={17} color={scheme === "dark" ? colors.brandPrimary : "#147450"} />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.aiTitle} numberOfLines={1}>{t("home.aiBannerTitle")}</Text>
              <Text style={styles.aiSub} numberOfLines={1}>{t("home.aiBannerSubtitle")}</Text>
            </View>
            <View style={styles.aiChevron}>
              <Ionicons name="chevron-forward" size={16} color={scheme === "dark" ? colors.brandPrimary : "#126047"} />
            </View>
          </LinearGradient>
        </Pressable>
        </Animated.View>
      </View>
    </Animated.ScrollView>
    <DateRangeSheet
      visible={dateSheet}
      value={dateRange}
      onClose={() => setDateSheet(false)}
      onApply={(range) => {
        setDateRange(range);
        setDateSheet(false);
      }}
    />
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  // Home-only light palette (dark keeps its existing card color). Warm-white
  // surfaces pop against the sage page background; text is dark green-black.
  const isDark = scheme === "dark";
  const cardSurface = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const wallText = isDark ? colors.onSurface : "#15251E";
  const wallMuted = isDark ? colors.muted : "#68746D";
  const wallSub = isDark ? colors.muted : "#8B958F";
  const lineSoft = isDark ? colors.border : "rgba(39,71,56,0.10)";
  const dividerSoft = isDark ? colors.divider : "#E4E7E2";
  const tileGreen = isDark ? colors.brandPrimary + "1A" : "#DCE9DD";
  const accentGreen = isDark ? colors.brandPrimary : "#126046";
  const seePill = isDark ? colors.brandPrimary + "14" : "#DFEBDD";
  const chipIdle = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const chipIdleBorder = isDark ? colors.border : "#D9DED8";
  return {
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    gap: 8,
  },
  hello: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  roundIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: cardSurface, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: lineSoft,
  },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: isDark ? colors.brandPrimary : "#0B5941", alignItems: "center", justifyContent: "center",
  },
  balanceIconTile: {
    width: 44, height: 44, borderRadius: 14,
    backgroundColor: tileGreen,
    alignItems: "center", justifyContent: "center",
  },
  balanceBlock: {
    flex: 1,
    marginLeft: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  balanceNumber: {
    flexShrink: 1,
    fontSize: 30,
    fontWeight: "800",
    color: wallText,
    letterSpacing: -0.8,
  },
  growthRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 1,
  },
  growthText: {
    fontSize: 14,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  // Subtle, short, continuous inset divider used to separate Home sections.
  // Neutral warm gray at low opacity — inset ~15% from both ends.
  sectionDivider: {
    height: 1,
    marginHorizontal: "15%",
    marginTop: spacing.md,
    backgroundColor: isDark ? colors.borderStrong : "rgba(39,71,56,0.12)",
    opacity: scheme === "dark" ? 0.5 : 0.6,
  },
  balanceCard: {
    borderRadius: radius.cardLg,
    padding: 22,
    minHeight: 170,
  },
  balanceLabel: { color: "#ffffffcc", fontSize: 13, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase" },
  balanceAmount: { color: "#fff", fontSize: 38, fontWeight: "800", marginTop: 10 },
  balanceSub: { color: "#ffffffcc", fontSize: 13, marginTop: 2 },
  balanceBtn: {
    marginTop: 14,
    alignSelf: "flex-start",
    backgroundColor: "#ffffff33",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
  },
  totalLine: {
    color: colors.muted,
    fontSize: 13,
    marginTop: 2,
    paddingHorizontal: spacing.lg,
  },
  walletGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  walletCard: {
    flexBasis: "31%",
    flexGrow: 0,
    flexShrink: 0,
    marginRight: "3.5%",
    marginBottom: 10,
    minHeight: 84,
    borderRadius: radius.md,
    // Soft, short, diffuse outer shadow only — no heavy floating / 3D look.
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  walletInner: {
    minHeight: 84,
    borderRadius: radius.md,
    overflow: "hidden",
    padding: 10,
    justifyContent: "space-between",
  },
  walletWatermark: {
    position: "absolute",
    right: -6,
    bottom: -8,
  },
  walletTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  walletIconBox: {
    width: 26,
    height: 26,
    borderRadius: 8,
    backgroundColor: "rgba(255,255,255,0.16)",
    alignItems: "center",
    justifyContent: "center",
  },
  walletArrow: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  walletTextWrap: {
    marginTop: 6,
  },
  walletCardLast: {
    marginRight: 0,
  },
  walletName: { color: "#F4F1E8", fontSize: 12.5, fontWeight: "600", letterSpacing: 0.1 },
  walletBalance: { color: "#F4F1E8", fontSize: 12.5, fontWeight: "600" },
  // Compact color-matched balance pill: "$" in a thin outlined circle + amount.
  balancePill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 5,
    paddingLeft: 3,
    paddingRight: 8,
    paddingVertical: 3,
    borderRadius: 999,
    marginTop: 5,
  },
  dollarCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "rgba(244,241,232,0.55)",
    backgroundColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
  },
  dollarSymbol: {
    color: "#F4F1E8",
    fontSize: 9,
    fontWeight: "800",
    lineHeight: 11,
    textAlign: "center",
    includeFontPadding: false,
  },
  walletAddCard: {
    flexBasis: "31%",
    flexGrow: 0,
    flexShrink: 0,
    marginRight: "3.5%",
    marginBottom: 10,
    minHeight: 84,
    borderRadius: radius.md,
    padding: 10,
    backgroundColor: cardSurface,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: isDark ? colors.brandPrimary : "#0D684C",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
  },
  walletAddText: {
    color: isDark ? colors.brandPrimary : "#0D684C",
    fontWeight: "800",
    fontSize: 11,
    lineHeight: 14,
  },
  // Tiny page indicator dots, absolutely pinned to the bottom of the existing
  // "Agregar cuenta" card so the card never grows and no spacing changes.
  walletDots: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 6,
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 4,
  },
  walletDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: isDark ? colors.brandPrimary + "40" : "rgba(13,104,76,0.28)",
  },
  walletDotActive: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: isDark ? colors.brandPrimary : "#0D684C",
  },
  miniRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md,
    alignItems: "stretch",
    gap: 8, // equal gap between all three cards
  },
  miniHalfLeft: {
    flex: 3, // Ingresos 30%
    minWidth: 0,
    flexShrink: 1,
  },
  miniHalfRight: {
    flex: 3, // Gastos 30%
    minWidth: 0,
    flexShrink: 1,
  },
  miniAccounts: {
    flex: 4, // Porcentajes 40%
    minWidth: 0,
    flexShrink: 1,
    paddingVertical: 12,
    paddingHorizontal: 12,
    justifyContent: "center",
    // Warm-white distribution card — pops against the sage page background.
    backgroundColor: isDark ? colors.surfaceSecondary : "#FCFCF8",
    borderColor: lineSoft,
  },
  miniCard: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    padding: 12,
    borderWidth: 1,
    borderColor: lineSoft,
    minHeight: 148,
  },
  cardIncome: {
    backgroundColor: isDark ? colors.incomeGreen + "14" : "#ECF6F0",
    borderColor: isDark ? colors.incomeGreen + "33" : "#BBDDCB",
    padding: 10,
    justifyContent: "space-between",
  },
  cardExpense: {
    backgroundColor: isDark ? colors.expenseRed + "14" : "#F8ECE8",
    borderColor: isDark ? colors.expenseRed + "33" : "#E7C7C0",
    padding: 10,
    justifyContent: "space-between",
  },
  miniPill: {
    width: 30,
    height: 30,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },
  miniLabel: { fontSize: 12, color: wallMuted, marginTop: 4, fontWeight: "700" },
  miniAmount: { fontSize: 14, fontWeight: "800", marginTop: 2 },
  miniSub: { fontSize: 9, color: wallMuted, marginTop: 2, fontWeight: "600" },
  mcTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  mcTopRight: { alignItems: "flex-end", gap: 3 },
  mcFooter: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    marginTop: 8,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderRadius: 12,
    backgroundColor: isDark ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.62)",
  },
  mcFooterCol: { flex: 1 },
  mcAvgLabel: { fontSize: 9, color: wallMuted, fontWeight: "600" },
  mcAvgVal: { fontSize: 13, fontWeight: "800", color: wallText, marginTop: 1 },
  debtCard: {
    backgroundColor: cardSurface,
    borderRadius: 28,
    padding: 8,
    gap: 8,
    borderWidth: 0.5,
    borderColor: lineSoft,
    shadowColor: "#274738",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 1,
  },
  debtHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  debtHeaderIcon: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.brandSecondary + "1A",
    alignItems: "center",
    justifyContent: "center",
  },
  debtHeaderSub: {
    fontSize: 10,
    color: colors.muted,
    fontWeight: "400",
    marginTop: 2,
  },
  debtArrowBtn: {
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: isDark ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.7)",
    alignItems: "center", justifyContent: "center",
  },
  debtTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  debtQuadRow: { flexDirection: "row", gap: 8 },
  debtQuadTile: {
    flex: 1, minWidth: 0, padding: 7, borderRadius: 20,
    borderWidth: 0.5, borderColor: isDark ? colors.border : "rgba(39,71,56,0.035)",
    overflow: "hidden",
  },
  debtOweTint: { backgroundColor: isDark ? colors.expenseRed + "0B" : "#FCF5F3" },
  debtOwedTint: { backgroundColor: isDark ? colors.incomeGreen + "0B" : "#F2F8F4" },
  debtPaidTint: { backgroundColor: isDark ? colors.statsPurple + "0B" : "#F6F3FC" },
  debtNextTint: { backgroundColor: isDark ? colors.brandSecondary + "0B" : "#FCF6EE" },
  debtQuadIcon: {
    width: 22, height: 22, borderRadius: 8,
    alignItems: "center", justifyContent: "center",
  },
  debtQuadLabel: { fontSize: 10, lineHeight: 11, color: wallMuted, fontWeight: "600" },
  debtQuadValue: { fontSize: 23, lineHeight: 27, fontWeight: "700", marginTop: 4, letterSpacing: -0.6 },
  debtQuadFoot: { fontSize: 9.5, lineHeight: 13, color: wallSub, marginTop: 5, fontWeight: "500" },
  debtQuadDate: { fontSize: 9, lineHeight: 11, color: wallMuted, fontWeight: "500", marginTop: 2 },
  debtProgressTrack: { height: 4, borderRadius: 2, overflow: "hidden", marginTop: 6 },
  debtProgressFill: { height: 4, borderRadius: 2 },
  debtDecorBars: { position: "absolute", right: 9, bottom: 8, flexDirection: "row", alignItems: "flex-end", gap: 4 },
  debtDecorCalendar: { position: "absolute", right: -6, bottom: -8, opacity: 0.1 },
  debtLabel: { fontSize: 12, color: colors.muted, fontWeight: "400" },
  debtValue: { fontSize: 18, fontWeight: "600", marginTop: 4, letterSpacing: -0.3 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  txList: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 10,
    paddingHorizontal: 4,
  },
  txName: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  txSub: { color: colors.muted, fontSize: 12, marginTop: 2 },

  /* --- Movimientos recientes (redesigned section) --- */
  mrHeader: { flexDirection: "row", alignItems: "center", marginBottom: 10 },
  mrIconTile: {
    width: 38, height: 38, borderRadius: 13,
    backgroundColor: tileGreen,
    alignItems: "center", justifyContent: "center",
  },
  mrTitle: { fontSize: 18, fontWeight: "800", color: wallText, letterSpacing: -0.4 },
  mrTitleAccent: { color: isDark ? colors.brandPrimary : "#168460", fontWeight: "800" },
  mrSubtitle: { fontSize: 11.5, color: wallMuted, marginTop: 1 },
  seeAllBtn: {
    flexDirection: "row", alignItems: "center", gap: 2,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: seePill,
  },
  seeAllText: { color: accentGreen, fontWeight: "800", fontSize: 12 },
  mrFilterRow: { flexDirection: "row", gap: 6, paddingVertical: 2, paddingRight: 4, marginBottom: 10 },
  mrPill: {
    flexDirection: "row", alignItems: "center", gap: 5,
    height: 32, paddingHorizontal: 12, borderRadius: radius.pill,
    flexShrink: 0,
  },
  mrPillIdle: {
    backgroundColor: chipIdle,
    borderWidth: 1, borderColor: chipIdleBorder,
  },
  mrPillText: { fontSize: 12, fontWeight: "700", color: isDark ? colors.onSurface : "#26352E" },
  mrPillTextActive: { color: "#fff" },
  mrIconPill: {
    width: 32, height: 32, borderRadius: radius.pill,
    alignItems: "center", justifyContent: "center",
    backgroundColor: chipIdle,
    borderWidth: 1, borderColor: chipIdleBorder,
    flexShrink: 0,
  },
  mrIconPillActive: {
    backgroundColor: tileGreen,
    borderColor: isDark ? colors.brandPrimary + "55" : "#BAD7C2",
  },
  mrCard: {
    backgroundColor: cardSurface,
    borderRadius: radius.cardLg,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: lineSoft,
    shadowColor: "#274738",
    shadowOpacity: 0.05,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 5 },
    elevation: 3,
  },
  mrRow: { flexDirection: "row", alignItems: "center", paddingVertical: 9, paddingHorizontal: 4 },
  mrDivider: { height: 1, backgroundColor: dividerSoft, marginLeft: 50, marginRight: 4 },
  mrName: { color: wallText, fontWeight: "800", fontSize: 13.5, letterSpacing: -0.2 },
  mrTimeRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 },
  mrTime: { color: wallMuted, fontSize: 11 },
  mrBadge: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill, marginHorizontal: 6, flexShrink: 1,
  },
  mrBadgeText: { fontSize: 11, fontWeight: "700" },
  mrAmount: { fontWeight: "800", fontSize: 14, letterSpacing: -0.3 },
  aiBanner: {
    flexDirection: "row", alignItems: "center",
    padding: 10, borderRadius: radius.cardLg,
    borderWidth: 1, borderColor: isDark ? colors.brandPrimary + "3D" : "#BAD7C2",
  },
  aiIcon: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: isDark ? colors.brandPrimary + "26" : "#CDE5D3",
    alignItems: "center", justifyContent: "center",
  },
  aiTitle: { fontSize: 13.5, fontWeight: "800", color: isDark ? colors.onSurface : "#193126", letterSpacing: -0.2 },
  aiSub: { fontSize: 11.5, color: isDark ? colors.muted : "#738078", marginTop: 1 },
  aiChevron: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: isDark ? colors.brandPrimary + "1F" : "#CFE4D3",
    alignItems: "center", justifyContent: "center", marginLeft: 8,
  },
  };
});
