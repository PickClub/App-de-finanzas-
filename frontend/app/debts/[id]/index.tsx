import React, { useEffect, useRef, useState } from "react";
import { View, ScrollView, Alert, Platform } from "react-native";
import Svg, { Path } from "react-native-svg";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import i18n, { localeTag } from "@/src/i18n";
import { formatCurrencyInt, formatDateLong } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";

import { us } from "@/src/ui-scale";

// Local visual identity (same light-mode values used by Home / debt forms).
// Dark mode falls back to the global dark theme tokens.
function detailPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    dark,
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    forest: dark ? colors.incomeGreen : "#126046",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    onSurface: dark ? colors.onSurface : "#15251E",
    muted: dark ? colors.muted : "#68746D",
    border: dark ? colors.border : "rgba(39,71,56,0.10)",
    divider: dark ? colors.divider : "rgba(39,71,56,0.08)",
    track: dark ? colors.border : "#ECEDEA",
    coral: dark ? colors.expenseRed : "#D95345",
    coralSoft: dark ? colors.expenseRed + "24" : "#FDE4E0",
    violet: dark ? colors.statsPurple : "#7B4FD6",
    violetSoft: dark ? colors.statsPurple + "24" : "#EEE6FB",
  };
}

const FREQ_LABEL: Record<string, string> = { weekly: "Semanal", biweekly: "Quincenal", monthly: "Mensual" };

// "12 abr 2025" — display only; invalid/missing dates show "No disponible".
function formatCreated(iso?: string | null): string {
  if (!iso) return "No disponible";
  const dt = new Date(iso);
  if (isNaN(dt.getTime())) return "No disponible";
  try {
    return dt.toLocaleDateString(localeTag(i18n.language), { day: "numeric", month: "short", year: "numeric" }).replace(/\./g, "").replace(/ de /g, " ");
  } catch {
    return dt.toISOString().slice(0, 10);
  }
}

export default function DebtDetail() {
  const { colors, scheme } = useTheme();
  const pal = detailPalette(colors, scheme);
  const styles = useStyles();
  const params = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const processing = useRef(false);
  const deleted = useRef(false);
  const [busy, setBusy] = useState(false);
  const debtQ = useQuery({ queryKey: ["debt", params.id], queryFn: () => api.getDebt(params.id as string), enabled: !!params.id });
  const paysQ = useQuery({ queryKey: ["debt-payments", params.id], queryFn: () => api.listDebtPayments(params.id as string), enabled: !!params.id });
  const missing = debtQ.error instanceof ApiError && debtQ.error.status === 404;
  useEffect(() => {
    if (!missing || deleted.current) return;
    deleted.current = true;
    processing.current = true;
    Alert.alert("Deuda no disponible", "Esta deuda ya no existe. Volverás a Deudas.");
    router.dismissTo("/debts");
  }, [missing, router]);

  const d = debtQ.data;
  if (!d || missing || deleted.current) return <View style={{ flex: 1, backgroundColor: pal.bg }} />;

  const progress = d.original_amount > 0 ? d.total_paid / d.original_amount : 0;
  const refreshFinancialData = () => Promise.all(
    [["debt", d.id], ["debt-payments", d.id], ["debts"], ["transactions"], ["accounts"], ["summary"]]
      .map((queryKey) => qc.invalidateQueries({ queryKey }))
  );
  const executeDeletion = async (paymentId?: string) => {
    if (processing.current || deleted.current) return;
    processing.current = true;
    setBusy(true);
    try {
      if (paymentId) {
        await api.deleteDebtPayment(paymentId);
        await refreshFinancialData();
      } else {
        await api.deleteDebt(d.id);
        deleted.current = true;
        qc.removeQueries({ queryKey: ["debt", d.id], exact: true });
        qc.removeQueries({ queryKey: ["debt-payments", d.id], exact: true });
        // Start refreshes, but never keep a deleted detail open while they finish.
        void Promise.all([["debts"], ["transactions"], ["accounts"], ["summary"]]
          .map((queryKey) => qc.invalidateQueries({ queryKey, refetchType: "all" })))
          .catch(() => Alert.alert("Actualizar datos", "La deuda se eliminó. No se pudo actualizar la lista; vuelve a intentarlo."));
        router.dismissTo("/debts");
      }
    } catch (error) {
      const message = error instanceof ApiError && error.status === 409
        ? paymentId
          ? error.detail
          : "Esta deuda tiene pagos o movimientos vinculados. Anúlalos desde el historial antes de eliminarla."
        : error instanceof Error ? error.message : "No se pudo completar la operación. Inténtalo de nuevo.";
      Alert.alert("No se pudo eliminar", message);
    } finally {
      if (!deleted.current) {
        processing.current = false;
        setBusy(false);
      }
    }
  };
  const cancelPayment = (paymentId: string) => {
    if (processing.current) return;
    Alert.alert("Anular pago", "Se eliminará el movimiento asociado y se revertirá el efecto de este pago en el saldo de la cuenta y en el pendiente de la deuda. ¿Continuar?", [
      { text: "Cancelar", style: "cancel" },
      { text: "Anular pago", style: "destructive", onPress: () => { void executeDeletion(paymentId); } },
    ]);
  };
  const remove = () => {
    if (processing.current) return;
    Alert.alert("Eliminar deuda", "¿Estás seguro?", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Eliminar",
        style: "destructive",
        onPress: () => { void executeDeletion(); },
      },
    ]);
  };

  const isPaid = d.status === "paid";
  const pct = Math.round(progress * 100);
  const shadow = pal.dark ? null : styles.softShadow;
  const cardStyle = [styles.card, { backgroundColor: pal.card, borderColor: pal.border }, shadow];
  const freq = FREQ_LABEL[d.payment_frequency];
  const payments = paysQ.data || [];
  const amountCols = [
    { key: "orig", label: "Original", value: d.original_amount, icon: "server-outline", color: pal.forest, soft: pal.mint },
    { key: "pend", label: "Pendiente", value: d.remaining_amount, icon: "time-outline", color: pal.coral, soft: pal.coralSoft },
    { key: "paid", label: "Pagado", value: d.total_paid, icon: "checkmark-circle-outline", color: pal.violet, soft: pal.violetSoft },
  ];
  const infoRows: { key: string; label: string; value: string; icon?: string; muted?: boolean }[] = [
    { key: "min", label: "Pago mínimo", value: formatCurrencyInt(d.minimum_payment), icon: "card-outline" },
    { key: "freq", label: "Frecuencia", value: freq || "Sin configurar", icon: "calendar-outline", muted: !freq },
    { key: "int", label: "Interés", value: `${d.interest_rate}%` },
    { key: "created", label: "Fecha de creación", value: formatCreated(d.start_date), icon: "calendar-number-outline" },
    ...(d.due_date ? [{ key: "due", label: "Próximo vencimiento", value: formatDateLong(d.due_date), icon: "alarm-outline" }] : []),
  ];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: pal.bg }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={[styles.circleBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
          <Ionicons name="chevron-back" size={us(24)} color={pal.forest} />
        </Pressable>
        <Text style={[styles.title, { color: pal.dark ? pal.onSurface : pal.forest }]} numberOfLines={1}>{d.name}</Text>
        <Pressable onPress={remove} disabled={busy} accessibilityState={{ disabled: busy, busy }} style={[styles.circleBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
          <Ionicons name="trash-outline" size={us(22)} color={colors.expenseRed} />
        </Pressable>
      </View>

      {/* Resumen de la deuda */}
      <View style={[cardStyle, styles.hero]}>
        <Svg width="100%" height={us(70)} viewBox="0 0 400 70" preserveAspectRatio="none" style={styles.heroWave} pointerEvents="none">
          <Path d="M0 46 C 70 20, 140 64, 220 40 S 340 14, 400 34 L 400 70 L 0 70 Z" fill={d.color} opacity={pal.dark ? 0.1 : 0.07} />
          <Path d="M0 58 C 90 40, 170 70, 260 52 S 360 40, 400 50 L 400 70 L 0 70 Z" fill={d.color} opacity={pal.dark ? 0.08 : 0.05} />
        </Svg>
        <View style={styles.heroLeft}>
          <View style={[styles.heroIcon, { backgroundColor: d.color + (pal.dark ? "2E" : "26") }]}>
            <Ionicons name={(d.icon || "cash-outline") as any} size={us(30)} color={d.color} />
          </View>
          <Text style={[styles.heroTitle, { color: pal.onSurface }]} numberOfLines={2}>
            {d.direction === "i_owe" ? "Yo debo a" : "Me debe"} {d.person || ""}
          </Text>
          <Text style={[styles.heroSub, { color: pal.muted }]} numberOfLines={1}>{d.name}</Text>
          <View style={[styles.statusPill, { backgroundColor: isPaid ? pal.mint : pal.coralSoft }]}>
            <Text style={[styles.statusText, { color: isPaid ? pal.forest : pal.coral }]}>{isPaid ? "PAGADA ✓" : "ACTIVA"}</Text>
          </View>
        </View>
        <ProgressRing progress={progress} color={d.color} trackColor={pal.track} size={us(128)} stroke={us(11)}>
          <View style={{ alignItems: "center" }}>
            <Text style={[styles.ringLabel, { color: pal.muted }]}>Pagado</Text>
            <Text style={[styles.ringValue, { color: pal.onSurface }]}>{pct}%</Text>
          </View>
        </ProgressRing>
      </View>

      {/* Montos */}
      <View style={[cardStyle, styles.amountCard]}>
        {amountCols.map((c, idx) => (
          <React.Fragment key={c.key}>
            {idx > 0 && <View style={[styles.vDivider, { backgroundColor: pal.divider }]} />}
            <View style={styles.amountCol}>
              <View style={styles.amountHead}>
                <View style={[styles.amountIcon, { backgroundColor: c.soft }]}>
                  <Ionicons name={c.icon as any} size={us(16)} color={c.color} />
                </View>
                <Text style={[styles.amountLabel, { color: pal.muted }]} numberOfLines={1}>{c.label}</Text>
              </View>
              <Text style={[styles.amountValue, { color: c.color }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
                {formatCurrencyInt(c.value)}
              </Text>
            </View>
          </React.Fragment>
        ))}
      </View>

      {/* Información adicional */}
      <View style={[cardStyle, styles.infoCard]}>
        {infoRows.map((r, idx) => (
          <View key={r.key} style={styles.infoRow}>
            <View style={[styles.infoIcon, { backgroundColor: pal.mint }]}>
              {r.icon ? (
                <Ionicons name={r.icon as any} size={us(18)} color={pal.forest} />
              ) : (
                <Text style={[styles.percentGlyph, { color: pal.forest }]}>%</Text>
              )}
            </View>
            <View style={[styles.infoBody, idx > 0 && { borderTopWidth: 1, borderTopColor: pal.divider }]}>
              <Text style={[styles.infoLabel, { color: pal.onSurface }]} numberOfLines={1}>{r.label}</Text>
              <Text style={[styles.infoVal, { color: r.muted ? pal.muted : pal.onSurface, fontWeight: r.muted ? "400" : "600" }]} numberOfLines={1}>{r.value}</Text>
            </View>
          </View>
        ))}
      </View>

      <Pressable
        testID="pay-btn"
        onPress={() => {
          if (!processing.current && !deleted.current && d.status !== "paid") router.push(`/debts/${d.id}/pay`);
        }}
        disabled={busy || d.status === "paid"}
        accessibilityState={{ disabled: busy || d.status === "paid", busy }}
        style={[styles.payBtn, { backgroundColor: pal.forest }, shadow, d.status === "paid" && { opacity: 0.5 }]}
      >
        <Ionicons name="add-circle-outline" size={us(26)} color={pal.dark ? colors.onSuccess : "#fff"} />
        <Text style={[styles.payText, { color: pal.dark ? colors.onSuccess : "#fff" }]}>Registrar pago</Text>
      </Pressable>

      <Text style={[styles.historyTitle, { color: pal.dark ? pal.onSurface : pal.forest }]}>Historial de pagos</Text>
      {payments.length > 0 ? (
        <View style={[cardStyle, styles.historyCard]}>
          {payments.map((p: any, idx: number) => (
            <View key={p.id} style={[styles.histRow, idx > 0 && { borderTopWidth: 1, borderTopColor: pal.divider }]}>
              <View style={[styles.infoIcon, { backgroundColor: pal.mint }]}>
                <Ionicons name="checkmark" size={us(18)} color={pal.forest} />
              </View>
              <View style={{ flex: 1, marginLeft: us(12) }}>
                <Text style={[styles.histAmount, { color: pal.onSurface }]}>{formatCurrencyInt(p.amount)}</Text>
                <Text style={[styles.histDate, { color: pal.muted }]}>{formatDateLong(p.date)}</Text>
              </View>
              <Pressable
                testID={`cancel-payment-${p.id}`}
                onPress={() => cancelPayment(p.id)}
                disabled={busy}
                accessibilityState={{ disabled: busy, busy }}
                style={[styles.cancelBtn, { backgroundColor: pal.coralSoft }]}
              >
                <Text style={[styles.cancelText, { color: pal.coral }]}>Anular pago</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : (
        <View style={[cardStyle, styles.emptyCard]}>
          <View style={styles.emptyArt}>
            <View style={[styles.sparkle, { top: 6, left: 18, backgroundColor: pal.mint }]} />
            <View style={[styles.sparkle, { top: 40, left: 6, width: 10, height: 10, backgroundColor: pal.mint }]} />
            <View style={[styles.sparkle, { top: 4, right: 14, width: 12, height: 12, backgroundColor: pal.mint }]} />
            <View style={[styles.sparkle, { bottom: 10, right: 6, backgroundColor: pal.mint }]} />
            <View style={[styles.emptyIcon, { backgroundColor: pal.mint }]}>
              <Ionicons name="list-outline" size={us(28)} color={pal.forest} />
            </View>
          </View>
          <Text style={[styles.emptyTitle, { color: pal.dark ? pal.onSurface : pal.forest }]}>Sin pagos registrados</Text>
          <Text style={[styles.emptySub, { color: pal.muted }]}>Cuando registres un pago, aparecerá aquí en orden cronológico.</Text>
        </View>
      )}
    </ScrollView>
  );
}

const useStyles = makeStyles(() => ({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 14 },
  circleBtn: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  title: { flex: 1, fontSize: 22, fontWeight: "800", letterSpacing: -0.3 },
  softShadow: Platform.select({
    web: { boxShadow: "0px 2px 10px rgba(18,96,70,0.06)" } as any,
    default: { shadowColor: "#126046", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  }),
  card: { borderRadius: 22, borderWidth: 1, marginBottom: 12, overflow: "hidden" },
  hero: { flexDirection: "row", alignItems: "center", padding: 18, gap: 12 },
  heroWave: { position: "absolute", left: 0, right: 0, bottom: 0 },
  heroLeft: { flex: 1, minWidth: 0 },
  heroIcon: { width: 56, height: 56, borderRadius: 18, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  heroTitle: { fontSize: 22, fontWeight: "800", letterSpacing: -0.3 },
  heroSub: { fontSize: 14, marginTop: 2 },
  statusPill: { alignSelf: "flex-start", marginTop: 10, paddingHorizontal: 12, paddingVertical: 5, borderRadius: radius.pill },
  statusText: { fontSize: 11, fontWeight: "800", letterSpacing: 0.6 },
  ringLabel: { fontSize: 12, fontWeight: "500" },
  ringValue: { fontSize: 24, fontWeight: "800", marginTop: 2 },
  amountCard: { flexDirection: "row", alignItems: "stretch", paddingVertical: 14, paddingHorizontal: 8 },
  vDivider: { width: 1, marginVertical: 4 },
  amountCol: { flex: 1, paddingHorizontal: 8, minWidth: 0 },
  amountHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  amountIcon: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  amountLabel: { flex: 1, fontSize: 12, fontWeight: "500" },
  amountValue: { fontSize: 20, fontWeight: "800", marginTop: 8, letterSpacing: -0.3 },
  infoCard: { paddingVertical: 4, paddingHorizontal: 14 },
  infoRow: { flexDirection: "row", alignItems: "center" },
  infoIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  percentGlyph: { fontSize: 17, fontWeight: "800" },
  infoBody: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginLeft: 12, paddingVertical: 15, gap: 10 },
  infoLabel: { fontSize: 14, fontWeight: "500", flexShrink: 1 },
  infoVal: { fontSize: 14, textAlign: "right", flexShrink: 1 },
  payBtn: { flexDirection: "row", gap: 10, alignItems: "center", justifyContent: "center", marginTop: 4, marginHorizontal: 2, minHeight: 56, borderRadius: radius.pill },
  payText: { fontWeight: "800", fontSize: 16 },
  historyTitle: { fontSize: 18, fontWeight: "800", marginTop: 22, marginBottom: 10, marginLeft: 2 },
  historyCard: { paddingHorizontal: 14, paddingVertical: 2 },
  histRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12 },
  histAmount: { fontSize: 15, fontWeight: "700" },
  histDate: { fontSize: 12, marginTop: 2 },
  cancelBtn: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill },
  cancelText: { fontSize: 12, fontWeight: "700" },
  emptyCard: { alignItems: "center", paddingVertical: 22, paddingHorizontal: 20 },
  emptyArt: { width: 120, height: 76, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  sparkle: { position: "absolute", width: 8, height: 8, borderRadius: 4 },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 16, fontWeight: "800", textAlign: "center" },
  emptySub: { fontSize: 13, textAlign: "center", marginTop: 4, lineHeight: 19 },
}));
