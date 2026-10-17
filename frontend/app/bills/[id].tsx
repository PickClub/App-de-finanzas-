import { localizedError } from "@/src/i18n/errors";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useRef, useState } from "react";
import { verifiedDeletionContext, type Context } from "@/src/obligation-payments/journal";
import { View, ScrollView, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt, formatDateTime } from "@/src/format";
import { ConfirmSheet } from "@/src/components/sheets";
import { ContextActionsTrigger } from "@/src/components/interaction-system";
import { ProgressBar } from "@/src/components/ProgressBar";
import { catLabel } from "@/src/category-labels";
import { FOREST, useMontserrat, safeHex, deepen, longDate, statusColor, invalidateBills } from "@/src/bills/shared";
import { us } from "@/src/ui-scale";

export default function BillDetail() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const mont = useMontserrat();
  const { id } = useLocalSearchParams<{ id: string }>();
  const deletionContext = useRef<{ id: string; context: Context } | null>(null);
  const q = useQuery({ queryKey: ["bill", id], queryFn: async () => {
    // Pin the server context observed when loading this screen; never silently
    // replace it after a refresh against another financial environment.
    let context: Context | null = null;
    try { context = verifiedDeletionContext(await api.getFinancialContext(), "bill"); } catch {}
    const bill = await api.billGet(id as string);
    if (context && deletionContext.current?.id !== id) deletionContext.current = { id: id as string, context };
    return bill;
  } });
  const [refreshing, setRefreshing] = useState(false);
  const refreshingRef = useRef(false);
  const onRefresh = async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    try {
      await Promise.allSettled([Promise.resolve().then(() => q.refetch({ cancelRefetch: false }))]);
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  };
  const b = q.data;
  const [confirm, setConfirm] = useState<null | "delete" | { pay: string }>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const doConfirm = async () => {
    if (busy || !confirm) return;
    setBusy(true); setErr(null);
    try {
      if (confirm === "delete") {
        await api.billDelete(id as string);
        setConfirm(null);
        await invalidateBills(qc, true);
        router.back();
        return;
      }
      if (deletionContext.current?.id !== id) throw Error("No se ha verificado el contexto de esta pantalla. Vuelve a abrirla.");
      verifiedDeletionContext(await api.getFinancialContext(), "bill", deletionContext.current.context);
      await api.billDeletePayment(confirm.pay, deletionContext.current.context);
      setConfirm(null);
      await invalidateBills(qc, true);
    } catch (e: any) {
      setErr(e instanceof ApiError ? e.detail : e?.message || t("bills.errGeneric"));
      setConfirm(null);
    } finally {
      setBusy(false);
    }
  };

  if (q.isLoading) {
    return <View style={[styles.center, { backgroundColor: colors.pageBackground }]}><ActivityIndicator color={forest} /></View>;
  }
  if (!b) {
    return (
      <View style={[styles.center, { backgroundColor: colors.pageBackground, paddingTop: insets.top }]}>
        <Text style={styles.muted}>{t("bills.notFound")}</Text>
        <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="bill-back" style={{ alignSelf: "flex-end", marginTop: us(12) }} />
      </View>
    );
  }

  const base = safeHex(b.color || b.category_color);
  const sc = statusColor(b.status, colors);
  const dueText = b.status === "paid" ? null : b.days_left < 0 ? t("bills.overdueBy", { count: -b.days_left }) : b.days_left === 0 ? t("bills.dueToday") : b.days_left === 1 ? t("bills.dueTomorrow") : t("bills.dueIn", { count: b.days_left });

  const Info = ({ icon, label, value, testID }: any) => (
    <View style={styles.infoRow} testID={testID}>
      <Ionicons name={icon} size={us(17)} color={colors.muted} />
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} numberOfLines={2}>{value}</Text>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.pageBackground }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}
      >
        <View style={styles.header}>
          <Text style={[styles.title, mont(), { flex: 1 }]} numberOfLines={1}>{t("bills.title")}</Text>
          <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="bill-back" beforeActions={<ContextActionsTrigger testID="bill-actions" disabled={busy} style={styles.backBtn} iconSize={us(20)} actions={[
            { id: "edit", label: t("bills.edit"), icon: "create-outline", onPress: () => router.push({ pathname: "/bills/new", params: { id: b.id } } as any) },
            { id: "delete", label: t("bills.delete"), icon: "trash-outline", destructive: true, onPress: () => setConfirm("delete") },
          ]} />} />
        </View>

        <View style={[styles.hero, { backgroundColor: base + (isDark ? "1F" : "14") }]}>
          <View style={styles.heroTop}>
            <View style={[styles.heroIcon, { backgroundColor: base + (isDark ? "33" : "26") }]}>
              <Ionicons name={(b.icon || b.category_icon || "receipt-outline") as any} size={us(26)} color={deepen(base, isDark)} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[styles.heroName, mont()]} numberOfLines={1}>{b.name}</Text>
              {b.provider ? <Text style={styles.muted} numberOfLines={1}>{b.provider}</Text> : null}
            </View>
            <View style={[styles.pill, { backgroundColor: sc + (isDark ? "2E" : "1C") }]} testID="bill-status">
              <Text style={[styles.pillText, { color: sc }]}>{b.partial ? t("bills.partial") : t(`bills.s_${b.status}`, { defaultValue: t("common.unknown") })}</Text>
            </View>
          </View>
          <Text style={[styles.heroAmount, mont()]} testID="bill-amount">{formatCurrencyInt(b.amount)}</Text>
          {dueText ? <Text style={[styles.dueText, { color: b.status === "overdue" ? colors.expenseRed : colors.muted }]}>{dueText}</Text> : null}
          <View style={{ marginTop: us(12) }}>
            <ProgressBar progress={b.progress} color={colors.incomeGreen} />
          </View>
          <View style={[styles.rowBetween, { marginTop: us(8) }]}>
            <Text style={styles.small}>{t("bills.paid")}: <Text style={[styles.smallStrong, { color: colors.incomeGreen }]} testID="bill-paid">{formatCurrencyInt(b.paid_amount)}</Text></Text>
            <Text style={styles.small}>{t("bills.remainingLbl")}: <Text style={[styles.smallStrong, { color: b.remaining > 0 ? colors.brandSecondary : colors.muted }]} testID="bill-remaining">{formatCurrencyInt(b.remaining)}</Text></Text>
          </View>
        </View>

        {b.reminder_active ? (
          <View style={[styles.notice, { backgroundColor: colors.brandSecondary + "1A" }]} testID="bill-reminder">
            <Ionicons name="notifications-outline" size={us(16)} color={colors.brandSecondary} />
            <Text style={[styles.small, { color: colors.onSurface, flex: 1 }]}>{b.days_left === 0 ? t("bills.reminderToday") : t("bills.reminderOn", { count: b.days_left })}</Text>
          </View>
        ) : null}

        <View style={styles.card}>
          <Info icon="calendar-outline" label={t("bills.dueDate")} value={longDate(b.due_date, lang)} testID="bill-info-due" />
          <Info icon="pricetag-outline" label={t("bills.category")} value={b.category_name ? catLabel(b.category_name, lang) : t("bills.none")} />
          <Info icon="wallet-outline" label={t("bills.account")} value={b.account_name || t("bills.none")} />
          <Info icon="repeat-outline" label={t("bills.frequency")} value={t(`bills.r_${b.frequency || "once"}`, { defaultValue: t("common.unknown") })} />
          <Info icon="notifications-outline" label={t("bills.reminder")} value={t(`bills.rem_${b.reminder_days ?? "none"}`, { defaultValue: t("common.unknown") })} />
          {b.recurring_payment_name ? <Info icon="link-outline" label={t("bills.linkRp")} value={b.recurring_payment_name} /> : null}
          {b.description ? <Info icon="document-text-outline" label={t("bills.description")} value={b.description} /> : null}
        </View>

        {err ? (
          <View style={[styles.notice, { backgroundColor: colors.expenseRed + "14" }]} testID="bill-error">
            <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
            <Text style={[styles.small, { color: colors.expenseRed, flex: 1 }]}>{localizedError(err)}</Text>
          </View>
        ) : null}

        {b.status !== "paid" ? (
          <Pressable testID="bill-register-pay" onPress={() => router.push({ pathname: "/bills/pay", params: { id: b.id } } as any)} style={({ pressed }) => [styles.primaryBtn, { backgroundColor: scheme === "dark" ? forest : colors.primaryAction }, pressed && { opacity: 0.85 }]}>
            <Ionicons name="card-outline" size={us(20)} color="#fff" />
            <Text style={[styles.primaryText, mont()]}>{t("bills.registerPay")}</Text>
          </Pressable>
        ) : null}
        {b.next_bill_id ? (
          <Pressable testID="bill-next" onPress={() => router.push(`/bills/${b.next_bill_id}` as any)} style={[styles.secondaryBtn, { marginTop: us(10) }]}>
            <Ionicons name="arrow-forward-circle-outline" size={us(18)} color={forest} />
            <Text style={[styles.secondaryText, { color: forest }]}>{t("bills.nextBill")}</Text>
          </Pressable>
        ) : null}

        <Text style={[styles.section, mont()]}>{t("bills.history")}</Text>
        <View style={styles.card} testID="bill-history">
          {!b.payments?.length ? (
            <Text style={[styles.muted, { textAlign: "center", paddingVertical: us(14) }]}>{t("bills.noPayments")}</Text>
          ) : b.payments.map((p: any, i: number) => (
            <View key={p.id} style={[styles.payRow, i > 0 && { borderTopWidth: 1, borderTopColor: colors.divider }]} testID={`bill-pay-${p.id}`}>
              <View style={[styles.payIcon, { backgroundColor: colors.incomeGreen + "1C" }]}>
                <Ionicons name="checkmark" size={us(16)} color={colors.incomeGreen} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[styles.payAmount, mont()]}>{formatCurrencyInt(p.amount)}</Text>
                <Text style={styles.small} numberOfLines={1}>{formatDateTime(p.date)}{p.account_name ? ` · ${p.account_name}` : ""}</Text>
              </View>
              <ContextActionsTrigger testID={`bill-pay-actions-${p.id}`} disabled={busy} iconSize={us(17)} actions={[
                { id: "delete", label: t("bills.deletePayTitle"), icon: "trash-outline", destructive: true, onPress: () => setConfirm({ pay: p.id }) },
              ]} />
            </View>
          ))}
        </View>
      </ElasticScrollView>

      <ConfirmSheet
        visible={confirm !== null}
        busy={busy}
        onClose={() => setConfirm(null)}
        icon="trash-outline"
        accent={colors.expenseRed}
        destructive
        title={confirm === "delete" ? t("bills.deleteTitle") : t("bills.deletePayTitle")}
        description={confirm === "delete" ? t("bills.deleteDesc") : t("bills.deletePayDesc")}
        confirmLabel={t("bills.delete")}
        onConfirm={doConfirm}
        confirmTestID="bill-confirm-delete"
      />
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  const dark = scheme === "dark";
  const shadow = { shadowColor: "#126046", shadowOpacity: dark ? 0 : 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: dark ? 0 : 1 };
  return {
    center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 20 },
    header: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 14 },
    backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
    title: { flex: 1, fontSize: 20, color: colors.onSurface },
    hero: { borderRadius: radius.cardLg, padding: 14, borderWidth: 1, borderColor: colors.border, ...shadow },
    heroTop: { flexDirection: "row", alignItems: "center", gap: 12 },
    heroIcon: { width: 50, height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" },
    heroName: { fontSize: 17, color: colors.onSurface },
    heroAmount: { fontSize: 28, color: colors.onSurface, marginTop: 14 },
    dueText: { fontSize: 13, marginTop: 2, fontWeight: "600" },
    pill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
    pillText: { fontSize: 11.5, fontWeight: "700" },
    rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    small: { fontSize: 12.5, color: colors.muted },
    smallStrong: { fontSize: 13, fontWeight: "800" },
    muted: { fontSize: 13, color: colors.muted },
    notice: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: radius.lg, marginTop: 12 },
    card: { marginTop: 12, backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, paddingHorizontal: 14, paddingVertical: 4, borderWidth: 1, borderColor: colors.border, ...shadow },
    infoRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 11 },
    infoLabel: { fontSize: 13, color: colors.muted, flex: 1 },
    infoValue: { fontSize: 13.5, color: colors.onSurface, fontWeight: "700", maxWidth: "55%", textAlign: "right" },
    primaryBtn: { marginTop: 16, flexDirection: "row", gap: 8, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
    primaryText: { color: "#fff", fontSize: 16 },
    secondaryBtn: { flexDirection: "row", gap: 6, minHeight: 46, paddingHorizontal: 18, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
    secondaryText: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
    section: { fontSize: 17, color: colors.onSurface, marginTop: 22 },
    payRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 12 },
    payIcon: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
    payAmount: { fontSize: 15, color: colors.onSurface },
  };
});
