import { localizedError } from "@/src/i18n/errors";
import { tr, useTranslation } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";

import { formatCurrencyInt } from "@/src/format";
import { AppSheet, ConfirmSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import { FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount } from "@/src/bills/shared";
import { us } from "@/src/ui-scale";

import { useObligationPayment } from "@/src/obligation-payments/use-payment";
import { invalidateObligationPayments, reconciliationMessage } from "@/src/obligation-payments/journal";

export default function BillPay() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id } = useLocalSearchParams<{ id: string }>();
  const billQ = useQuery({ queryKey: ["bill", id], queryFn: () => api.billGet(id as string), enabled: !!id });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const b = billQ.data;
  const resourceState = !id || (billQ.error instanceof ApiError && billQ.error.status === 404)
    ? "missing" : billQ.isLoading && !b ? "loading" : billQ.isError ? "error" : b ? "ready" : "missing";
  const payment = useObligationPayment({ kind: "bill", id: id || "", due: b?.due_date || "" });
  const accounts: any[] = accountsQ.data || [];

  const [amount, setAmount] = useState<string | null>(null);
  const [day, setDay] = useState<string>(toYmd(Date.now()));
  const [accountId, setAccountId] = useState<string | null | undefined>(undefined);
  const [notes, setNotes] = useState("");
  const [sheet, setSheet] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const screenEpoch = useRef(0);
  useFocusEffect(useCallback(() => {
    screenEpoch.current++; savingRef.current = false; setSaving(false);
    if (id && b?.due_date) void payment.recover().catch(() => {});
    return () => { screenEpoch.current++; };
  }, [id, b?.due_date]));
  useEffect(() => {
    screenEpoch.current++; savingRef.current = false; setSaving(false);
    return () => { screenEpoch.current++; };
  }, [id, b?.due_date]);
  const dateRef = useRef<DateRangeSheetHandle>(null);
  useEffect(() => {
    const p = payment.record?.payload;
    if (!p) return;
    setAmount(String(p.amount ?? "")); setDay(toYmd(Date.parse(p.date)));
    setAccountId(p.account_id); setNotes(p.notes || "");
    setSheet(false);
  }, [payment.record?.key]);


  const remaining = b?.remaining || 0;
  const amountStr = amount ?? (remaining ? String(Math.round(remaining * 100) / 100) : "");
  const amt = parseAmount(amountStr);
  const accId = accountId === undefined ? b?.account_id || null : accountId;
  const acc = accounts.find((a) => a.id === accId);
  const isOver = !payment.locked && Number.isFinite(amt) && amt > remaining + 0.001;
  const isPartial = !payment.locked && Number.isFinite(amt) && amt > 0 && amt < remaining - 0.001;
  const base = safeHex(b?.color || b?.category_color);

  const ask = () => {
    if (!b) return;
    if (payment.record || payment.problem) { void save(); return; }
    if (!Number.isFinite(amt) || amt <= 0) return setError(t("bills.errAmount"));
    if (isOver) return setError(t("bills.payOver"));
    if (!accId) return setError(t("bills.errAccount"));
    setError(null);
    setConfirm(true);
  };

  const save = async () => {
    if (savingRef.current || !b) return;
    savingRef.current = true; setSaving(true); setConfirm(false);
    const epoch = screenEpoch.current;
    let completed = false;
    const isToday = day === toYmd(Date.now());
    try {
      if (!payment.ready) { await payment.recover(); return; }
      if (payment.record && payment.record.state !== "reconciled") {
        await payment.reconcile();
        await invalidateObligationPayments(qc);
        return; // Verification never sends a payment or acknowledges automatically.
      }
      const result = payment.record ? await payment.retry() : await payment.submit({
        amount: Math.round(amt * 100) / 100, account_id: accId,
        date: isToday ? new Date().toISOString() : new Date(day + "T12:00:00").toISOString(),
        notes: notes.trim() || null,
      });
      await invalidateObligationPayments(qc);
      if (epoch !== screenEpoch.current) return;
      await payment.acknowledge(result.key);
      if (epoch === screenEpoch.current) { completed = true; router.back(); }
    } catch (e: any) {
      if (epoch === screenEpoch.current) setError(e instanceof ApiError ? e.detail : e?.message || t("bills.errGeneric"));
    } finally {
      if (!completed && epoch === screenEpoch.current) { savingRef.current = false; setSaving(false); }
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ElasticScrollView {...NATIVE_VERTICAL_SCROLL} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="bill-pay-back" onPress={() => { screenEpoch.current++; router.back(); }} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={[styles.title, mont()]}>{t("bills.payTitle")}</Text>
          </View>

          {resourceState === "loading" ? <ActivityIndicator testID="bill-pay-loading" color={forest} /> : resourceState !== "ready" ? (
            <View testID="bill-pay-query-error">
              <View style={styles.errorBox}>
                <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
                <Text style={styles.errorText}>{localizedError((i18n.language || "es").startsWith("en")
                  ? resourceState === "missing" ? tr("ui.bill_not_found_it_may_no_longer_exist") : tr("ui.could_not_load_the_bill_check_your_connection_and_try_again")
                  : resourceState === "missing" ? tr("ui.bill_not_found_it_may_no_longer_exist") : tr("ui.could_not_load_the_bill_check_your_connection_and_try_again"))}</Text>
              </View>
              {payment.record || payment.problem ? <Text style={styles.hint} testID="bill-pay-preserved">{tr("ui.the_payment_record_is_preserved_this_query_does_not_confirm_or_cancel_payments")}</Text> : null}
              {id ? <Pressable testID="bill-pay-retry" disabled={billQ.isFetching} onPress={() => { void billQ.refetch(); }} style={styles.saveBtn}>
                <Text style={styles.saveText}>{(i18n.language || "es").startsWith("en") ? billQ.isFetching ? tr("ui.retrying") : tr("ui.retry") : billQ.isFetching ? tr("ui.retrying") : tr("ui.retry")}</Text>
              </Pressable> : null}
            </View>
          ) : (
            <>
              <View style={[styles.head, { backgroundColor: base + (isDark ? "1F" : "1A") }]}>
                <View style={[styles.headIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(b.icon || b.category_icon || "receipt-outline") as any} size={us(22)} color={deepen(base, isDark)} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.headName, mont()]} numberOfLines={1}>{b.name}</Text>
                  <Text style={styles.small}>{t("bills.dueOn")}: {longDate(b.due_date, i18n.language)} · {formatCurrencyInt(b.amount)}</Text>
                  <Text style={styles.small} testID="bill-pay-remaining">{t("bills.payHintRemaining", { amount: formatCurrencyInt(remaining) })}</Text>
                </View>
              </View>

              {payment.record || payment.problem ? <Text style={styles.hint} testID="payment-pending-status">{localizedError(payment.problem || (payment.record ? reconciliationMessage(payment.record) : ""))}</Text> : null}
              <View pointerEvents={payment.locked ? "none" : "auto"}>
              <Text style={styles.label}>{t("bills.payAmount")}</Text>
              <View style={styles.input}>
                <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
                <TextInput editable={!payment.locked} testID="bill-pay-amount" value={amountStr} onChangeText={(v) => { setAmount(v.replace(/[^0-9.,]/g, "")); setError(null); }} keyboardType="decimal-pad" placeholder={tr("ui.0")} placeholderTextColor={colors.muted} style={[styles.inputText, { flex: 1, padding: 0, fontSize: us(18) }, mont()]} />
              </View>
              {isPartial ? <Text style={styles.hint} testID="bill-pay-partial">{t("bills.payPartial", { amount: formatCurrencyInt(remaining - amt) })}</Text> : null}
              {isOver ? <Text style={[styles.hint, { color: colors.expenseRed }]}>{t("bills.payOver")}</Text> : null}

              <Text style={styles.label}>{t("bills.payDate")}</Text>
              <Pressable testID="bill-pay-date" onPress={() => { const ms = new Date(day + "T12:00:00").getTime(); dateRef.current?.open({ start: ms, end: ms }); }} style={styles.input}>
                <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }]}>{longDate(day, i18n.language)}</Text>
              </Pressable>

              <Text style={styles.label}>{t("bills.payAccount")}</Text>
              <Pressable testID="bill-pay-account" onPress={() => setSheet(true)} style={styles.input}>
                <Ionicons name="wallet-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }, !acc && { color: colors.muted }]} numberOfLines={1}>{acc ? acc.name : t("bills.none")}</Text>
                {acc ? <Text style={styles.small}>{formatCurrencyInt(acc.current_balance || 0)}</Text> : null}
                <Ionicons name="chevron-down" size={us(18)} color={colors.muted} style={{ marginLeft: us(6) }} />
              </Pressable>

              <Text style={styles.label}>{t("bills.description")} · {t("bills.optional")}</Text>
              <View style={styles.input}>
                <TextInput editable={!payment.locked} testID="bill-pay-notes" value={notes} onChangeText={setNotes} maxLength={200} placeholder={t("bills.descPh")} placeholderTextColor={colors.muted} style={[styles.inputText, { flex: 1, padding: 0 }]} />
              </View>
              <Text style={styles.hint}>{t("bills.payRealNote")}</Text>

              </View>
              {error ? (
                <View style={styles.errorBox} testID="bill-pay-error">
                  <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
                  <Text style={styles.errorText}>{localizedError(error)}</Text>
                </View>
              ) : null}

              <Pressable testID="bill-pay-save" onPress={ask} disabled={saving || (!payment.ready && !payment.problem)} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}>
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{payment.record?.state === "reconciled" ? tr("ui.close_verification") : payment.problem || payment.record ? tr("ui.verify_record") : t("bills.registerPay")}</Text>}
              </Pressable>
            </>
          )}
        </ElasticScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={sheet && resourceState === "ready"} onClose={() => setSheet(false)} testID="bill-pay-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("bills.payAccount")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {accounts.map((o: any) => (
            <Pressable key={o.id} testID={`bill-pay-opt-${o.id}`} style={styles.sheetRow} onPress={() => { setAccountId(o.id); setSheet(false); setError(null); }}>
              <View style={[styles.dot, { backgroundColor: safeHex(o.color) }]} />
              <Text style={[styles.sheetRowText, o.id === accId && { color: forest, fontWeight: "800" }]} numberOfLines={1}>{o.name}</Text>
              <Text style={styles.small}>{formatCurrencyInt(o.current_balance || 0)}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </AppSheet>

      <ConfirmSheet
        visible={confirm && resourceState === "ready"}
        onClose={() => setConfirm(false)}
        icon="card-outline"
        accent={forest}
        title={t("bills.confirmPay")}
        description={t("bills.confirmPayDesc", { amount: formatCurrencyInt(Number.isFinite(amt) ? amt : 0), account: acc?.name || "" })}
        confirmLabel={t("bills.confirmPay")}
        onConfirm={save}
        confirmTestID="bill-pay-confirm"
      />
      <DateRangeSheet ref={dateRef} onApply={(rg: DateRange | null) => rg && setDay(toYmd(rg.start))} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, color: colors.onSurface },
  head: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border },
  headIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  headName: { fontSize: 15, color: colors.onSurface },
  small: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 6, lineHeight: 16 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  dot: { width: 12, height: 12, borderRadius: 6 },
}));
