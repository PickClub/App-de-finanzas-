import React, { useState, useMemo } from "react";
import { View, Text, ScrollView, Pressable, StyleSheet, RefreshControl } from "react-native";
import Svg, { Circle as SvgCircle, Path as SvgPath } from "react-native-svg";
import { LinearGradient } from "expo-linear-gradient";
import { useQuery } from "@tanstack/react-query";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeColors } from "@/src/theme";
import { formatCurrency, formatCurrencyInt, formatDateLong } from "@/src/format";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

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

function accountBars(accounts: any[], total: number, colors: ThemeColors) {
  const positives = accounts.filter((a) => a.current_balance > 0);
  const base = total > 0 ? total : positives.reduce((s, a) => s + a.current_balance, 0);
  const sorted = [...positives].sort((a, b) => b.current_balance - a.current_balance);
  if (sorted.length === 0) {
    return <Text style={{ color: colors.muted, fontSize: 10 }}>Sin cuentas</Text>;
  }
  return sorted.map((a) => {
    const pct = base > 0 ? Math.round((a.current_balance / base) * 100) : 0;
    return (
      <View key={a.id}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={{ flexShrink: 1, fontSize: 9, fontWeight: "600", color: colors.onSurface }}>
            {a.name}
          </Text>
          <Text style={{ fontSize: 9, fontWeight: "700", color: a.color, marginLeft: 4 }}>{pct}%</Text>
        </View>
        <View
          style={{
            marginTop: 2,
            height: 4,
            borderRadius: 2,
            backgroundColor: colors.surfaceTertiary,
            overflow: "hidden",
          }}
        >
          <View style={{ width: `${Math.max(4, pct)}%`, height: "100%", backgroundColor: a.color }} />
        </View>
      </View>
    );
  });
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

// "17 sept, 3:24 p.m." — used only by the Movimientos recientes rows.
function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    const date = d.toLocaleDateString("es-ES", { day: "2-digit", month: "short" }).replace(".", "");
    let h = d.getHours();
    const m = d.getMinutes().toString().padStart(2, "0");
    const ampm = h >= 12 ? "p.m." : "a.m.";
    h = h % 12;
    if (h === 0) h = 12;
    return `${date}, ${h}:${m} ${ampm}`;
  } catch {
    return "";
  }
}

export default function Home() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [hidden, setHidden] = useState(false);
  const [txFilter, setTxFilter] = useState("all");
  const [monthOnly, setMonthOnly] = useState(false);

  const summaryQ = useQuery({ queryKey: ["summary"], queryFn: api.summary });
  const userQ = useQuery({ queryKey: ["user"], queryFn: api.getUser });
  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const summary = summaryQ.data;
  const user = userQ.data;
  const recent = useMemo(() => {
    let items: any[] = txQ.data || [];
    if (txFilter === "income") items = items.filter((t: any) => t.type === "income" || t.type === "loan_received");
    else if (txFilter === "expense") items = items.filter((t: any) => t.type === "expense" || t.type === "debt_payment");
    else if (txFilter === "transfer") items = items.filter((t: any) => t.type === "transfer");
    if (monthOnly) {
      const now = new Date();
      const first = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
      items = items.filter((t: any) => new Date(t.date).getTime() >= first);
    }
    return items.slice(0, 6);
  }, [txQ.data, txFilter, monthOnly]);
  const cats: any[] = catQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));
  const accounts: any[] = accQ.data || [];

  const money = (n: number) => (hidden ? "••••" : formatCurrency(n));
  const debtMoney = (n: number) => (hidden ? "••••" : formatCurrencyInt(n));

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
    { id: "all", label: "Todas", icon: "grid", color: colors.brandPrimary },
    { id: "income", label: "Ingresos", icon: "trending-up", color: colors.incomeGreen },
    { id: "expense", label: "Gastos", icon: "trending-down", color: colors.expenseRed },
    { id: "transfer", label: "Transferencias", icon: "swap-horizontal", color: colors.accountsBlue },
  ] as const;

  return (
    <View style={{ flex: 1, backgroundColor: scheme === "dark" ? colors.surface : "#FFFFFF" }}>
    <ScrollView
      testID="home-scroll"
      style={{ flex: 1, backgroundColor: "transparent" }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 120 }}
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
      {/* Header */}
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.hello}>Hola, {user?.name || "Usuario"} 👋</Text>
          <Text style={styles.sub}>Gestionemos tus finanzas</Text>
        </View>
        <Pressable testID="notifications-btn" style={styles.roundIcon}>
          <Ionicons name="notifications-outline" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={styles.avatar}>
          <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>
            {(user?.name || "U").slice(0, 1)}
          </Text>
        </View>
      </View>

      {/* Mis cuentas */}
      <View style={{ paddingTop: spacing.lg }}>
        <View style={styles.sectionHeaderRow}>
          <Text style={styles.sectionTitle}>Mis cuentas</Text>
          <Pressable testID="toggle-hide-btn" onPress={() => setHidden((h) => !h)} hitSlop={8}>
            <Ionicons name={hidden ? "eye-off-outline" : "eye-outline"} size={20} color={colors.muted} />
          </Pressable>
        </View>
        <Text style={styles.totalLine} testID="total-balance">
          Saldo total: <Text style={{ color: colors.onSurface, fontWeight: "800" }}>{money(summary?.total_balance || 0)}</Text>
        </Text>
        <View style={styles.walletGrid}>
          {accounts.map((a, idx) => {
            const isThird = (idx + 1) % 3 === 0;
            return (
              <Pressable
                key={a.id}
                testID={`wallet-${a.id}`}
                onPress={guard(() => router.push(`/accounts/new?id=${a.id}`))}
                style={[styles.walletCard, { backgroundColor: a.color }, isThird && styles.walletCardLast]}
              >
                <View style={styles.walletInner}>
                  <LinearGradient
                    colors={[lighten(a.color, 0.16), a.color, darken(a.color, 0.06)]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={StyleSheet.absoluteFill}
                  />
                  <Ionicons
                    name={a.icon as any}
                    size={58}
                    color="rgba(255,255,255,0.15)"
                    style={styles.walletWatermark}
                  />
                  <View style={styles.walletTopRow}>
                    <View style={styles.walletIconBox}>
                      <Ionicons name={a.icon as any} size={14} color="#fff" />
                    </View>
                    <View style={[styles.walletArrow, { backgroundColor: darken(a.color, 0.16) }]}>
                      <Ionicons name="chevron-forward" size={12} color="#fff" />
                    </View>
                  </View>
                  <View style={styles.walletTextWrap}>
                    <Text style={styles.walletName} numberOfLines={1}>{a.name}</Text>
                    <Text style={styles.walletBalance} numberOfLines={1} adjustsFontSizeToFit>
                      {money(a.current_balance)}
                    </Text>
                  </View>
                </View>
              </Pressable>
            );
          })}
          <Pressable
            testID="wallet-add"
            onPress={() => router.push("/accounts/new")}
            style={[styles.walletAddCard, (accounts.length + 1) % 3 === 0 && styles.walletCardLast]}
          >
            <Ionicons name="add" size={22} color={colors.brandPrimary} />
            <Text style={styles.walletAddText}>Agregar{"\n"}cuenta</Text>
          </Pressable>
        </View>
      </View>

      {/* Income / Expense / Accounts distribution */}
      <View style={styles.miniRow}>
        <View style={styles.miniLeft}>
          <View style={[styles.miniCard, styles.miniHalfLeft, styles.cardIncome]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.incomeGreen }]}>
                <Ionicons name="arrow-up" size={14} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>Este mes</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>Ingresos</Text>
            <Text
              style={[styles.miniAmount, { color: colors.incomeGreen }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              +{money(summary?.month_income || 0)}
            </Text>
            <MiniBars data={stats.incBars} color={colors.incomeGreen} />
            <View style={styles.mcAvg}>
              <Text style={styles.mcAvgLabel}>Promedio diario</Text>
              <Text style={styles.mcAvgVal}>{money(stats.avgIncome)}</Text>
            </View>
          </View>
          <View style={[styles.miniCard, styles.miniHalfRight, styles.cardExpense]}>
            <View style={styles.mcTop}>
              <View style={[styles.miniPill, { backgroundColor: colors.expenseRed }]}>
                <Ionicons name="arrow-down" size={14} color="#fff" />
              </View>
              <View style={styles.mcTopRight}>
                <Text style={styles.miniSub}>Este mes</Text>
                <DragDots color={colors.muted} />
              </View>
            </View>
            <Text style={styles.miniLabel}>Gastos</Text>
            <Text
              style={[styles.miniAmount, { color: colors.expenseRed }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.6}
            >
              -{money(summary?.month_expense || 0)}
            </Text>
            <MiniBars data={stats.expBars} color={colors.expenseRed} />
            <View style={styles.mcAvg}>
              <Text style={styles.mcAvgLabel}>Promedio diario</Text>
              <Text style={styles.mcAvgVal}>{money(stats.avgExpense)}</Text>
            </View>
          </View>
        </View>
        <View style={[styles.miniCard, styles.miniAccounts]}>
          <ScrollView
            testID="cuentas-scroll"
            nestedScrollEnabled
            showsVerticalScrollIndicator={false}
            contentContainerStyle={{ gap: 6 }}
          >
            {accountBars(accounts, summary?.total_balance || 0, colors)}
          </ScrollView>
        </View>
      </View>

      {/* Debts card */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg }}>
        <Pressable testID="debts-card" onPress={() => router.push("/debts")} style={styles.debtCard}>
          {/* soft abstract background */}
          <View pointerEvents="none" style={StyleSheet.absoluteFill}>
            <Svg width="100%" height="100%" viewBox="0 0 320 240" preserveAspectRatio="none">
              <SvgCircle cx="24" cy="200" r="42" fill={colors.brandSecondary} opacity="0.06" />
              <SvgCircle cx="290" cy="30" r="26" fill={colors.statsPurple} opacity="0.05" />
              <SvgPath
                d="M0 60 Q 60 40, 120 55 T 260 45 T 340 55"
                stroke={colors.brandSecondary}
                strokeOpacity="0.12"
                strokeWidth="1"
                fill="none"
              />
              <SvgPath
                d="M20 210 Q 90 195, 160 205 T 320 200"
                stroke={colors.brandPrimary}
                strokeOpacity="0.08"
                strokeWidth="1"
                fill="none"
              />
              <SvgCircle cx="180" cy="122" r="4" fill={colors.brandPrimary} opacity="0.14" />
              <SvgCircle cx="60" cy="120" r="2.5" fill={colors.statsPurple} opacity="0.2" />
              {[0, 1, 2].map((r) =>
                [0, 1, 2].map((c) => (
                  <SvgCircle
                    key={`d-${r}-${c}`}
                    cx={295 + c * 6}
                    cy={112 + r * 6}
                    r="1.2"
                    fill={colors.muted}
                    opacity="0.35"
                  />
                )),
              )}
            </Svg>
          </View>

          {/* header */}
          <View style={styles.debtHeader}>
            <View style={styles.debtHeaderIcon}>
              <Ionicons name="wallet" size={18} color={colors.brandSecondary} />
            </View>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.debtTitle}>Deudas</Text>
              <Text style={styles.debtHeaderSub}>Tu panorama financiero, en un vistazo.</Text>
            </View>
            <View style={styles.debtArrowBtn}>
              <Ionicons name="chevron-forward" size={14} color={colors.onSurface} />
            </View>
          </View>

          {/* first row */}
          <View style={styles.debtQuadRow}>
            <View style={styles.debtQuadLeft}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.expenseRed + "1A" }]}>
                  <Ionicons name="arrow-up" size={14} color={colors.expenseRed} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>Debo</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.expenseRed }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.i_owe || 0)}
                  </Text>
                </View>
              </View>
            </View>
            <View style={styles.debtVDivider} />
            <View style={styles.debtQuadRight}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.incomeGreen + "1A" }]}>
                  <Ionicons name="arrow-down" size={14} color={colors.incomeGreen} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>Me deben</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.incomeGreen }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.they_owe || 0)}
                  </Text>
                </View>
              </View>
            </View>
          </View>

          <View style={styles.debtHDivider} />

          {/* second row */}
          <View style={styles.debtQuadRow}>
            <View style={styles.debtQuadLeft}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.statsPurple + "1A" }]}>
                  <Ionicons name="card" size={14} color={colors.statsPurple} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>Pagado este mes</Text>
                  <Text style={[styles.debtQuadValue, { color: colors.statsPurple }]} numberOfLines={1} adjustsFontSizeToFit>
                    {debtMoney(summary?.debts?.paid_this_month || 0)}
                  </Text>
                  <Text style={styles.debtQuadFoot}>¡Buen progreso!</Text>
                </View>
              </View>
            </View>
            <View style={styles.debtVDivider} />
            <View style={styles.debtQuadRight}>
              <View style={styles.debtQuadInner}>
                <View style={[styles.debtQuadIcon, { backgroundColor: colors.brandSecondary + "1F" }]}>
                  <Ionicons name="calendar" size={14} color={colors.brandSecondary} />
                </View>
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.debtQuadLabel}>Próximo pago</Text>
                  {summary?.debts?.next_payment ? (
                    <>
                      <Text style={styles.debtQuadDate} numberOfLines={1}>
                        {formatDateLong(summary.debts.next_payment.date)}
                      </Text>
                      <Text style={[styles.debtQuadValue, { color: colors.brandSecondary, fontSize: 15 }]} numberOfLines={1} adjustsFontSizeToFit>
                        {debtMoney(summary.debts.next_payment.amount)}
                      </Text>
                      <Text style={styles.debtQuadFoot}>Mantén tus pagos al día</Text>
                    </>
                  ) : (
                    <Text style={styles.debtQuadFoot}>Sin próximos pagos</Text>
                  )}
                </View>
              </View>
            </View>
          </View>
        </Pressable>
      </View>

      {/* Recent transactions — "Movimientos recientes" */}
      <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
        {/* Section header */}
        <View style={styles.mrHeader}>
          <View style={styles.mrIconTile}>
            <Ionicons name="layers" size={22} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Text style={styles.mrTitle}>
              Movimientos <Text style={styles.mrTitleAccent}>recientes</Text>
            </Text>
            <Text style={styles.mrSubtitle} numberOfLines={2}>
              Aquí tienes tus últimos movimientos, en un vistazo.
            </Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <LockToggle testID="lock-home" compact />
            <Pressable testID="see-all-tx" onPress={() => router.push("/(tabs)/transactions")} style={styles.seeAllBtn}>
              <Text style={styles.seeAllText}>Ver todo</Text>
              <Ionicons name="chevron-forward" size={15} color={colors.brandPrimary} />
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
            const content = (
              <>
                <Ionicons name={f.icon as any} size={15} color={active ? "#fff" : f.color} />
                <Text style={[styles.mrPillText, active && styles.mrPillTextActive]}>{f.label}</Text>
              </>
            );
            return active ? (
              <Pressable key={f.id} testID={`mr-filter-${f.id}`} onPress={() => setTxFilter(f.id)}>
                <LinearGradient
                  colors={[colors.brandPrimary, colors.brandSecondary]}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 0 }}
                  style={styles.mrPill}
                >
                  {content}
                </LinearGradient>
              </Pressable>
            ) : (
              <Pressable
                key={f.id}
                testID={`mr-filter-${f.id}`}
                onPress={() => setTxFilter(f.id)}
                style={[styles.mrPill, styles.mrPillIdle]}
              >
                {content}
              </Pressable>
            );
          })}
          <Pressable
            testID="mr-filter-month"
            onPress={() => setMonthOnly((m) => !m)}
            style={[styles.mrIconPill, monthOnly && styles.mrIconPillActive]}
          >
            <Ionicons name="calendar-outline" size={17} color={monthOnly ? colors.brandPrimary : colors.muted} />
          </Pressable>
        </ScrollView>

        {/* List card */}
        <View style={styles.mrCard}>
          {recent.length === 0 && (
            <Text style={{ color: colors.muted, textAlign: "center", padding: spacing.lg }}>
              Aún no hay movimientos
            </Text>
          )}
          {recent.map((t, idx) => {
            const cat = catById[t.category_id];
            const isIncome = t.type === "income" || t.type === "loan_received";
            const isTransfer = t.type === "transfer";
            const color = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
            const sign = isTransfer ? "" : isIncome ? "+" : "-";
            const iconName =
              cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
            const tint = cat?.color || color;
            const badgeLabel = cat?.name || (isTransfer ? "Transferencia" : isIncome ? "Ingreso" : "Gasto");
            const badgeColor = cat?.color || color;
            return (
              <View key={t.id}>
                {idx > 0 && <View style={styles.mrDivider} />}
                <Pressable
                  testID={`mr-tx-${t.id}`}
                  onPress={guard(() => router.push(`/transactions/new?id=${t.id}`))}
                  style={styles.mrRow}
                >
                  <IconTile icon={iconName} tint={tint} size={44} />
                  <View style={{ flex: 1, marginLeft: 12 }}>
                    <Text style={styles.mrName} numberOfLines={1}>{t.name}</Text>
                    <View style={styles.mrTimeRow}>
                      <Ionicons name="time-outline" size={13} color={colors.muted} />
                      <Text style={styles.mrTime} numberOfLines={1}>{formatDateTime(t.date)}</Text>
                    </View>
                  </View>
                  <View style={[styles.mrBadge, { backgroundColor: badgeColor + "1A" }]}>
                    <Text style={[styles.mrBadgeText, { color: badgeColor }]} numberOfLines={1}>{badgeLabel}</Text>
                  </View>
                  <Text style={[styles.mrAmount, { color }]}>{sign}{formatCurrency(t.amount)}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} style={{ marginLeft: 4 }} />
                </Pressable>
              </View>
            );
          })}
        </View>

        {/* AI banner — taps through to the IA tab (same route as the mic in the bottom nav) */}
        <Pressable testID="ai-banner" onPress={() => router.push("/(tabs)/transactions")} style={{ marginTop: spacing.md }}>
          <LinearGradient
            colors={[colors.brandPrimary + "1F", colors.statsPurple + "1F"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.aiBanner}
          >
            <View style={styles.aiIcon}>
              <Ionicons name="sparkles" size={20} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.aiTitle} numberOfLines={1}>Registra un gasto más rápido</Text>
              <Text style={styles.aiSub} numberOfLines={1}>Usa el botón de IA o prueba con tu voz.</Text>
            </View>
            <View style={styles.aiChevron}>
              <Ionicons name="chevron-forward" size={18} color={colors.brandPrimary} />
            </View>
          </LinearGradient>
        </Pressable>
      </View>
    </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
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
    backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center",
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
    backgroundColor: "rgba(255,255,255,0.22)",
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
  walletName: { color: "#fff", fontSize: 12.5, fontWeight: "600", letterSpacing: 0.1 },
  walletBalance: { color: "rgba(255,255,255,0.92)", fontSize: 11, fontWeight: "600", marginTop: 1 },
  walletAddCard: {
    flexBasis: "31%",
    flexGrow: 0,
    flexShrink: 0,
    marginRight: "3.5%",
    marginBottom: 10,
    minHeight: 84,
    borderRadius: radius.md,
    padding: 10,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
  },
  walletAddText: {
    color: colors.brandPrimary,
    fontWeight: "800",
    fontSize: 11,
    lineHeight: 14,
  },
  miniRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md,
    alignItems: "stretch",
  },
  miniLeft: {
    flex: 3, // ~60%
    flexDirection: "row",
    marginRight: 8,
  },
  miniHalfLeft: {
    flex: 1,
    marginRight: 4,
  },
  miniHalfRight: {
    flex: 1,
    marginLeft: 4,
  },
  miniAccounts: {
    flex: 2, // ~40%
    paddingVertical: 10,
    paddingHorizontal: 10,
  },
  miniCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    padding: 12,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 148,
  },
  cardIncome: {
    backgroundColor: colors.incomeGreen + "14",
    borderColor: colors.incomeGreen + "33",
    padding: 10,
    justifyContent: "space-between",
  },
  cardExpense: {
    backgroundColor: colors.expenseRed + "14",
    borderColor: colors.expenseRed + "33",
    padding: 10,
    justifyContent: "space-between",
  },
  miniPill: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  miniLabel: { fontSize: 12, color: colors.muted, marginTop: 4, fontWeight: "700" },
  miniAmount: { fontSize: 14, fontWeight: "800", marginTop: 2 },
  miniSub: { fontSize: 9, color: colors.muted, marginTop: 2, fontWeight: "600" },
  mcTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  mcTopRight: { alignItems: "flex-end", gap: 3 },
  mcAvg: { marginTop: 2 },
  mcAvgLabel: { fontSize: 9, color: colors.muted, fontWeight: "600" },
  mcAvgVal: { fontSize: 13, fontWeight: "800", color: colors.onSurface, marginTop: 1 },
  debtCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    padding: 13,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
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
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  debtTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  debtQuadRow: {
    flexDirection: "row",
    marginTop: 11,
  },
  debtQuadLeft: { flex: 1, paddingRight: 6 },
  debtQuadRight: { flex: 1, paddingLeft: 10 },
  debtQuadInner: { flexDirection: "row", alignItems: "flex-start" },
  debtQuadIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  debtQuadLabel: { fontSize: 10, color: colors.muted, fontWeight: "500" },
  debtQuadValue: { fontSize: 18, fontWeight: "800", marginTop: 2, letterSpacing: -0.5 },
  debtQuadFoot: { fontSize: 8, color: colors.muted, marginTop: 2, fontWeight: "500" },
  debtQuadDate: { fontSize: 10, color: colors.onSurface, fontWeight: "700", marginTop: 2 },
  debtVDivider: { width: 1, backgroundColor: colors.divider, marginVertical: 4 },
  debtHDivider: { height: 1, backgroundColor: colors.divider, marginTop: 11 },
  debtLabel: { fontSize: 12, color: colors.muted, fontWeight: "400" },
  debtValue: { fontSize: 18, fontWeight: "600", marginTop: 4, letterSpacing: -0.3 },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  txList: {
    backgroundColor: colors.surfaceSecondary,
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
  mrHeader: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  mrIconTile: {
    width: 46, height: 46, borderRadius: 16,
    backgroundColor: colors.brandPrimary + "1A",
    alignItems: "center", justifyContent: "center",
  },
  mrTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.4 },
  mrTitleAccent: { color: colors.brandPrimary, fontWeight: "800" },
  mrSubtitle: { fontSize: 12.5, color: colors.muted, marginTop: 2 },
  seeAllBtn: {
    flexDirection: "row", alignItems: "center", gap: 2,
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary + "14",
  },
  seeAllText: { color: colors.brandPrimary, fontWeight: "800", fontSize: 13 },
  mrFilterRow: { flexDirection: "row", gap: 8, paddingVertical: 2, paddingRight: 4, marginBottom: spacing.md },
  mrPill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    height: 40, paddingHorizontal: 16, borderRadius: radius.pill,
    flexShrink: 0,
  },
  mrPillIdle: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  mrPillText: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface },
  mrPillTextActive: { color: "#fff" },
  mrIconPill: {
    width: 40, height: 40, borderRadius: radius.pill,
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    flexShrink: 0,
  },
  mrIconPillActive: {
    backgroundColor: colors.brandPrimary + "1A",
    borderColor: colors.brandPrimary + "55",
  },
  mrCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  mrRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12, paddingHorizontal: 4 },
  mrDivider: { height: 1, backgroundColor: colors.divider, marginLeft: 60, marginRight: 4 },
  mrName: { color: colors.onSurface, fontWeight: "800", fontSize: 14.5, letterSpacing: -0.2 },
  mrTimeRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 3 },
  mrTime: { color: colors.muted, fontSize: 12 },
  mrBadge: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: radius.pill, marginHorizontal: 8, flexShrink: 1,
  },
  mrBadgeText: { fontSize: 11.5, fontWeight: "700" },
  mrAmount: { fontWeight: "800", fontSize: 15.5, letterSpacing: -0.3 },
  aiBanner: {
    flexDirection: "row", alignItems: "center",
    padding: 14, borderRadius: radius.cardLg,
    borderWidth: 1, borderColor: colors.brandPrimary + "3D",
  },
  aiIcon: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.brandPrimary + "26",
    alignItems: "center", justifyContent: "center",
  },
  aiTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.2 },
  aiSub: { fontSize: 12.5, color: colors.muted, marginTop: 2 },
  aiChevron: {
    width: 38, height: 38, borderRadius: 19,
    backgroundColor: colors.brandPrimary + "1F",
    alignItems: "center", justifyContent: "center", marginLeft: 8,
  },
}));
