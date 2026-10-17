import { Alert } from "@/src/components/interaction-system";
import { localizedError } from "@/src/i18n/errors";
import { tr, useTranslation as useInterfaceLanguage } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useEffect, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { PaymentPayload } from "@/src/debt-payments/pending";
import type { PaymentDisplay } from "@/src/debt-payments/flow-v2";
import { localPaymentFlow as pendingDebtPayments } from "@/src/debt-payments/local-flow";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency, formatCurrencyInt } from "@/src/format";
import { IconTile } from "@/src/components/ui";
import { AppSheet } from "@/src/components/sheets";

import { us } from "@/src/ui-scale";
import { paymentView } from "@/src/debt-payments/view";

// Local visual identity (same light-mode values as Detalle de deuda / Nueva cuenta).
function payPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    dark,
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    field: dark ? colors.surface : "#FFFFFF",
    forest: dark ? colors.incomeGreen : "#126046",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    mintSoft: dark ? colors.incomeGreen + "14" : "#EEF5EF",
    onSurface: dark ? colors.onSurface : "#15251E",
    muted: dark ? colors.muted : "#68746D",
    border: dark ? colors.border : "rgba(39,71,56,0.10)",
    divider: dark ? colors.divider : "rgba(39,71,56,0.08)",
    coral: dark ? colors.expenseRed : "#D95345",
    coralSoft: dark ? colors.expenseRed + "24" : "#FDE4E0",
  };
}

export default function PayDebt() {
  const params = useLocalSearchParams<{ id: string }>();
  return <PayDebtForm key={params.id || "missing"} debtId={params.id} />;
}

// A route change mounts a fresh form; drafts and async recovery never cross debts.
function PayDebtForm({ debtId }: { debtId: string | undefined }) {
  useInterfaceLanguage();
  const { colors, scheme } = useTheme();
  const pal = payPalette(colors, scheme);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const completedRef = useRef(false);
  const styles = useStyles();
  const params = { id: debtId };
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const debtQ = useQuery({ queryKey: ["debt", params.id], queryFn: () => api.getDebt(params.id as string), enabled: !!params.id });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState<string | undefined>();
  const [notes, setNotes] = useState("");

  const [operation, setOperation] = useState<PaymentDisplay | null>(null);
  const [ready, setReady] = useState(false);
  const recoveryReady = useRef(false);
  const recoveryError = useRef<unknown>(null);
  useEffect(() => {
    let mounted = true;
    recoveryReady.current = false;
    recoveryError.current = null;
    pendingDebtPayments.recover().then(async record => {
      if (!mounted) return;
      if (record?.state === "confirmed") {
        // Opening Record payment is the explicit request for a new blank form.
        // This releases only a validated local receipt, never payment history.
        try { await pendingDebtPayments.startNew(record.key); }
        catch (error) {
          // Strict Mode may have prepared the same confirmed slot already.
          if (await pendingDebtPayments.recover()) throw error;
        }
        if (!mounted) return;
        record = null;
      }
      setOperation(record);
      if (record && record.debtId === params.id) {
        setAmount(String(record.payload.amount));
        setAccountId(record.payload.account_id ?? undefined);
        setNotes(record.payload.notes ?? "");
      }
      recoveryReady.current = true;
      setReady(true);
    }).catch(error => {
      if (mounted) recoveryError.current = error;
    });
    return () => { mounted = false; };
  }, [params.id]);

  const d = debtQ.data;
  const resourceState = !params.id || (debtQ.error instanceof ApiError && debtQ.error.status === 404)
    ? "missing" : debtQ.isLoading && !d ? "loading" : debtQ.isError ? "error" : d ? "ready" : "missing";
  if (resourceState !== "ready") return (
    <View style={{ flex: 1, backgroundColor: pal.bg }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}>
        <View style={styles.headerRow}>
          <Text style={[styles.title, { color: pal.dark ? pal.onSurface : pal.forest, flex: 1 }]}>{tr("ui.debt_payment")}</Text>
          <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="debt-pay-back" />
        </View>
        {resourceState === "loading" ? <ActivityIndicator testID="debt-pay-loading" color={pal.forest} /> : (
          <View style={[styles.card, { backgroundColor: pal.card, borderColor: pal.border }]} testID="debt-pay-query-error">
            <Text style={[styles.debtName, { color: pal.onSurface }]}>{resourceState === "missing" ? tr("ui.debt_not_found") : tr("ui.could_not_load_the_debt")}</Text>
            <Text style={[styles.debtSub, { color: pal.muted }]}>{resourceState === "missing" ? tr("ui.it_may_no_longer_exist_go_back_or_try_again") : tr("ui.check_your_connection_and_try_again")}</Text>
            {operation ? <Text style={[styles.debtSub, { color: pal.muted }]} testID="debt-pay-preserved">{tr("ui.the_payment_record_is_preserved_this_query_does_not_confirm_or_cancel_payments")}</Text> : null}
            {params.id ? <Pressable testID="debt-pay-retry" disabled={debtQ.isFetching} onPress={() => { void debtQ.refetch(); }} style={[styles.saveBtn, { backgroundColor: scheme === "dark" ? pal.forest : colors.primaryAction }]}>
              <Text style={[styles.saveText, { color: pal.dark ? colors.onSuccess : "#fff" }]}>{debtQ.isFetching ? tr("ui.retrying") : tr("ui.retry")}</Text>
            </Pressable> : null}
          </View>
        )}
      </ElasticScrollView>
    </View>
  );

  const view = paymentView(operation, d.id, ready);
  const amt = Number(amount.trim());
  const newBalance = Math.max(0, d.remaining_amount - amt);

  const save = async () => {
    if (savingRef.current || completedRef.current) return;
    savingRef.current = true;
    setSaving(true);
    const finishPayment = (confirmed: PaymentDisplay) => {
      if (confirmed.state !== "confirmed" || confirmed.debtId !== d.id || confirmed.payload.debt_id !== d.id ||
          !confirmed.receipt?.id || !confirmed.receipt.transaction_id) {
        throw new Error(tr("ui.could_not_verify_the_payment"));
      }
      completedRef.current = true;
      // Refresh inactive detail/history queries too, without delaying navigation.
      void Promise.allSettled(
        [["debt", d.id], ["debt-payments", d.id], ["debts"], ["transactions"], ["accounts"], ["summary"]]
          .map(queryKey => qc.invalidateQueries({ queryKey, refetchType: "all" }, { throwOnError: true }))
      ).then(results => {
        if (results.some(result => result.status === "rejected")) {
          Alert.alert(tr("ui.payment_status"), tr("debts.paymentSavedRefreshFailed"));
        }
      });
      try { router.dismissTo(`/debts/${d.id}`); }
      catch (error) { completedRef.current = false; setOperation(confirmed); throw error; }
    };
    try {
      if (!recoveryReady.current) {
        const record = await pendingDebtPayments.verify();
        if (record?.state === "confirmed" && record.debtId === d.id) { finishPayment(record); return; }
        setOperation(record);
        if (record && record.debtId === d.id) {
          setAmount(String(record.payload.amount));
          setAccountId(record.payload.account_id ?? undefined);
          setNotes(record.payload.notes ?? "");
        }
        recoveryError.current = null;
        recoveryReady.current = true;
        setReady(true);
        qc.invalidateQueries();
        return; // Verification is a separate click, never a financial submission.
      }
      const pending = await pendingDebtPayments.recover();
      setOperation(pending);
      if (pending?.state === "confirmed") {
        if (pending.debtId === d.id) { finishPayment(pending); return; }
        // A different form completed while this one was open; never resend it.
        await pendingDebtPayments.startNew(pending.key);
        setOperation(null);
        setAmount("");
        setAccountId(undefined);
        setNotes("");
        return;
      }
      if (operation && (!pending || operation.key !== pending.key)) {
        throw new Error("El registro del pago anterior cambió. No se enviará un pago nuevo.");
      }
      if (pending && pending.debtId !== d.id) {
        Alert.alert(tr("ui.payment_status"), tr("debts.unresolvedOtherPayment"), [
          { text: tr("common.cancel"), style: "cancel" },
          { text: tr("debts.reviewPreviousPayment"), onPress: () => router.push(`/debts/${pending.debtId}/pay`) },
        ]);
        return; // Review navigation only; never send or reassign the stored intention.
      }
      if (pending?.state === "conflict" && !pendingDebtPayments.supportsReconciliation) {
        throw new Error("La discrepancia requiere conciliación. Se conserva la clave y no se enviará ningún pago.");
      }
      if (!pending) {
        if (!Number.isFinite(amt) || amt <= 0) throw new Error(tr("debts.invalidPaymentAmount"));
        if (amt > d.remaining_amount) throw new Error(tr("debts.paymentExceedsBalance"));
      }
      // Never rebuild a recovered intention from editable form values.
      const data: PaymentPayload = pending ? { ...pending.payload } : {
        debt_id: d.id, amount: amt, account_id: accountId ?? null, notes, date: null,
      };
      const confirmed = await pendingDebtPayments.submit(data);
      finishPayment(confirmed);
    } catch (error) {
      if (!recoveryReady.current) recoveryError.current = error;
      // Refresh durable state (including HTTP 409); failed reads keep sending blocked.
      try {
        const record = await pendingDebtPayments.recover();
        setOperation(record);
        if (record && record.debtId === d.id) {
          setAmount(String(record.payload.amount));
          setAccountId(record.payload.account_id ?? undefined);
          setNotes(record.payload.notes ?? "");
        } else if (!record && operation) {
          setAmount("");
          setAccountId(undefined);
          setNotes("");
        }
      } catch (readError) {
        recoveryReady.current = false;
        recoveryError.current = readError;
        setReady(false);
      }
      Alert.alert(tr("ui.payment_status"), localizedError(error instanceof Error ? error.message : tr("ui.could_not_verify_the_payment")));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const accounts: any[] = accQ.data || [];
  const selected = accounts.find((a: any) => a.id === accountId);
  const shadow = pal.dark ? null : styles.softShadow;
  const cardStyle = [styles.card, { backgroundColor: pal.card, borderColor: pal.border }, shadow];
  const isPaid = d.status === "paid";
  const counterpart = d.person ? (d.direction === "i_owe" ? `Yo debo a ${d.person}` : `Me debe ${d.person}`) : (d.direction === "i_owe" ? "Yo debo" : "Me deben");

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: pal.bg }}>
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}>
        <View style={styles.headerRow}>
          <Text style={[styles.title, { color: pal.dark ? pal.onSurface : pal.forest, flex: 1 }]}>{view.title}</Text>
          <MoneyFlowHeaderActions onBack={() => router.back()} backTestID="debt-pay-back" />
        </View>

        {/* Deuda */}
        <View style={cardStyle}>
          <View style={styles.debtTop}>
            <View style={[styles.debtIcon, { backgroundColor: d.color + (pal.dark ? "2E" : "26") }]}>
              <Ionicons name={(d.icon || "cash-outline") as any} size={us(26)} color={d.color} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[styles.debtName, { color: pal.onSurface }]} numberOfLines={2}>{d.name}</Text>
              <Text style={[styles.debtSub, { color: pal.muted }]} numberOfLines={1}>{counterpart}</Text>
            </View>
            <View style={[styles.statusPill, { backgroundColor: isPaid ? pal.mint : pal.coralSoft }]}>
              <Text style={[styles.statusText, { color: isPaid ? pal.forest : pal.coral }]}>{isPaid ? tr("ui.paid_3") : tr("ui.active")}</Text>
            </View>
          </View>
          <View style={[styles.hDivider, { backgroundColor: pal.divider }]} />
          <View style={styles.pendRow}>
            <Text style={[styles.pendLabel, { color: pal.muted }]}>{tr("ui.outstanding_balance")}</Text>
            <Text style={[styles.pendVal, { color: pal.forest }]}>{formatCurrencyInt(d.remaining_amount)}</Text>
          </View>
        </View>

        {/* Monto */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>{tr("ui.payment_amount")}</Text>
          <View style={[styles.amountBox, { backgroundColor: pal.field, borderColor: pal.border }]}>
            <Text style={[styles.amountText, { color: pal.forest }]}>$</Text>
            <TextInput
              testID="pay-amount"
              value={amount}
              editable={view.editable && !saving}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              placeholder="0.00"
              placeholderTextColor={pal.forest + "88"}
              style={[styles.amountText, styles.amountInput, { color: pal.forest }]}
            />
          </View>
          {view.preview && amt > 0 && (
            <View style={[styles.preview, { borderTopColor: pal.divider }]}>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.muted }]}>{tr("ui.previous_balance")}</Text><Text style={[styles.pVal, { color: pal.onSurface }]}>{formatCurrencyInt(d.remaining_amount)}</Text></View>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.muted }]}>{tr("ui.payment")}</Text><Text style={[styles.pVal, { color: pal.coral }]}>-{formatCurrencyInt(amt)}</Text></View>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.onSurface, fontWeight: "700" }]}>{tr("ui.new_balance")}</Text><Text style={[styles.pVal, { color: pal.forest, fontSize: 16 }]}>{formatCurrencyInt(newBalance)}</Text></View>
            </View>
          )}
        </View>

        {/* Cuenta de origen */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>{tr("ui.source_account")}</Text>
          <Pressable
            testID="pay-account-select"
            onPress={() => { if (view.editable && !saving) setPickerOpen(true); }}
            style={({ pressed }) => [styles.selectRow, { backgroundColor: pal.field, borderColor: pal.border }, pressed && { opacity: 0.85 }]}
          >
            {selected ? (
              <IconTile icon={selected.icon} tint={selected.color} size={us(38)} />
            ) : (
              <View style={[styles.selIcon, { backgroundColor: pal.mint }]}>
                <Ionicons name="wallet-outline" size={us(20)} color={pal.forest} />
              </View>
            )}
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[styles.selName, { color: selected ? pal.onSurface : pal.muted }]} numberOfLines={1}>
                {selected ? selected.name : tr("ui.choose_account")}
              </Text>
              {selected && <Text style={[styles.selBal, { color: pal.muted }]}>{formatCurrency(selected.current_balance)}</Text>}
            </View>
            <Ionicons name="chevron-down" size={us(20)} color={pal.muted} />
          </Pressable>
        </View>

        {/* Notas */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>{tr("ui.notes_optional")}</Text>
          <TextInput
            value={notes}
            editable={view.editable && !saving}
            onChangeText={setNotes}
            multiline
            placeholder={tr("ui.add_a_payment_description")}
            placeholderTextColor={pal.muted}
            style={[styles.notes, { backgroundColor: pal.field, borderColor: pal.border, color: pal.onSurface }]}
          />
        </View>

        {operation && operation.debtId !== d.id && <Text testID="debt-pay-previous-context" style={[styles.debtSub, { color: pal.muted, marginBottom: us(12) }]}>
          {tr(operation.state === "confirmed" ? "debts.confirmedOtherPayment" : "debts.unresolvedOtherPayment")}
        </Text>}
        <Pressable
          testID="confirm-pay"
          onPress={save}
          disabled={saving}
          style={[styles.saveBtn, { backgroundColor: scheme === "dark" ? pal.forest : colors.primaryAction, opacity: saving ? 0.7 : 1 }, shadow]}
        >
          <Text style={[styles.saveText, { color: pal.dark ? colors.onSuccess : "#fff" }]}>{view.action}</Text>
        </Pressable>
      </ElasticScrollView>

      <AppSheet visible={pickerOpen} onClose={() => setPickerOpen(false)} testID="pay-account-sheet">
        <Text style={[styles.sheetTitle, { color: pal.dark ? pal.onSurface : pal.forest }]}>{tr("ui.source_account")}</Text>
        <ScrollView style={{ maxHeight: us(420) }} contentContainerStyle={{ paddingHorizontal: us(spacing.lg), gap: us(8), paddingBottom: us(4) }}>
          {accounts.length === 0 ? (
            <Text style={[styles.sheetEmpty, { color: pal.muted }]}>{tr("ui.no_accounts_available")}</Text>
          ) : (
            accounts.map((a: any) => {
              const sel = accountId === a.id;
              return (
                <Pressable
                  key={a.id}
                  testID={`pay-acc-${a.id}`}
                  onPress={() => { if (view.editable && !saving) setAccountId(a.id); setPickerOpen(false); }}
                  style={({ pressed }) => [styles.sheetRow, { backgroundColor: sel ? pal.mintSoft : pal.card, borderColor: sel ? (a.color || pal.forest) : pal.border, borderWidth: sel ? 2 : 1 }, pressed && { opacity: 0.85 }]}
                >
                  <IconTile icon={a.icon} tint={a.color} size={us(38)} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={[styles.selName, { color: pal.onSurface }]} numberOfLines={2}>{a.name}</Text>
                    <Text style={[styles.selBal, { color: pal.muted }]}>{formatCurrency(a.current_balance)}</Text>
                  </View>
                  {sel ? (
                    <Ionicons name="checkmark-circle" size={us(22)} color={a.color || pal.forest} />
                  ) : (
                    <View style={[styles.radio, { borderColor: pal.border }]} />
                  )}
                </Pressable>
              );
            })
          )}
        </ScrollView>
      </AppSheet>
    </KeyboardAvoidingView>
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
  card: { borderRadius: 22, borderWidth: 1, padding: 14, marginBottom: 12 },
  debtTop: { flexDirection: "row", alignItems: "center", gap: 12 },
  debtIcon: { width: 50, height: 50, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  debtName: { fontSize: 17, fontWeight: "800", letterSpacing: -0.2 },
  debtSub: { fontSize: 13, marginTop: 2 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill },
  statusText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.6 },
  hDivider: { height: 1, marginVertical: 12 },
  pendRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pendLabel: { fontSize: 14, fontWeight: "500" },
  pendVal: { fontSize: 18, fontWeight: "800" },
  label: { fontSize: 12, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 8, marginLeft: 2 },
  amountBox: { flexDirection: "row", alignItems: "center", borderRadius: 16, borderWidth: 1, paddingHorizontal: 14, minHeight: 58 },
  amountText: { fontSize: 28, fontWeight: "800" },
  amountInput: { flex: 1, marginLeft: 8, paddingVertical: 6, minWidth: 0, ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as any) : null) },
  preview: { marginTop: 12, paddingTop: 8, borderTopWidth: 1 },
  pRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  pLabel: { fontSize: 13, fontWeight: "500" },
  pVal: { fontSize: 14, fontWeight: "700" },
  selectRow: { flexDirection: "row", alignItems: "center", gap: 12, borderRadius: 16, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 10, minHeight: 60 },
  selIcon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  selName: { fontSize: 15, fontWeight: "700" },
  selBal: { fontSize: 12, marginTop: 2 },
  notes: { fontSize: 15, borderRadius: 16, borderWidth: 1, paddingHorizontal: 14, paddingTop: 12, paddingBottom: 12, minHeight: 64, textAlignVertical: "top" },
  saveBtn: { marginTop: 4, marginHorizontal: 2, minHeight: 56, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 18, fontWeight: "800", paddingHorizontal: spacing.lg, marginBottom: 12, marginTop: 4 },
  sheetEmpty: { textAlign: "center", paddingVertical: 20 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: 18 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2 },
}));
