import React, { useMemo, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator, Switch } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt, formatDateTime } from "@/src/format";
import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import { catLabel } from "@/src/category-labels";
import { FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount, newKey } from "@/src/recurring/shared";

import { us } from "@/src/ui-scale";

type Mode = "mark" | "expense" | "link";

export default function RecurringPay() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id, due, exp, rem } = useLocalSearchParams<{ id: string; due: string; exp?: string; rem?: string }>();
  const remaining = Number(rem) || 0;
  const expected = Number(exp) || 0;

  const rpQ = useQuery({ queryKey: ["rp-detail", id], queryFn: () => api.rpGet(id as string) });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const candQ = useQuery({ queryKey: ["rp-cand", id, due], queryFn: () => api.rpCandidates(id as string, due as string) });
  const r = rpQ.data;
  const accounts: any[] = accountsQ.data || [];
  const cats: any[] = (catsQ.data || []).filter((c: any) => c.type === "expense" && !c.is_group);
  const candidates: any[] = candQ.data || [];

  const [mode, setMode] = useState<Mode>("mark");
  const [amount, setAmount] = useState(String(Math.round((remaining || expected) * 100) / 100 || ""));
  const [day, setDay] = useState<string>(toYmd(Date.now()));
  const [accountId, setAccountId] = useState<string | null | undefined>(undefined);
  const [categoryId, setCategoryId] = useState<string | null | undefined>(undefined);
  const [notes, setNotes] = useState("");
  const [txId, setTxId] = useState<string | null>(null);
  const [settles, setSettles] = useState<boolean | null>(null);
  const [overpay, setOverpay] = useState(false);
  const [sheet, setSheet] = useState<null | "acc" | "cat">(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newKey("rpay")).current;
  const dateRef = useRef<DateRangeSheetHandle>(null);

  const accId = accountId === undefined ? r?.account_id || null : accountId;
  const catId = categoryId === undefined ? r?.category_id || null : categoryId;
  const acc = accounts.find((a) => a.id === accId);
  const cat = cats.find((c) => c.id === catId);
  const base = safeHex(r?.color);
  const amt = parseAmount(amount);
  const variable = !!r?.variable;
  const isOver = !variable && Number.isFinite(amt) && amt > remaining + 0.001;
  const isPartial = !variable && Number.isFinite(amt) && amt > 0 && amt < remaining - 0.001;
  const sameAmount = useMemo(() => candidates.filter((c) => Number.isFinite(amt) && Math.abs(c.amount - amt) < 0.01), [candidates, amt]);

  const save = async () => {
    if (savingRef.current || !r) return;
    if (mode === "link" && !txId) return setError(t("rp.errLink"));
    if (mode !== "link" && (!Number.isFinite(amt) || amt <= 0)) return setError(t("rp.errAmount"));
    if (mode === "expense" && !accId) return setError(t("rp.errAccount"));
    if (mode !== "link" && isOver && !overpay) return setError(t("rp.overpayHint"));
    const isToday = day === toYmd(Date.now());
    savingRef.current = true; setSaving(true); setError(null);
    try {
      await api.rpPay(id as string, {
        due_date: due, mode, amount: mode === "link" ? null : Math.round(amt * 100) / 100,
        date: isToday ? new Date().toISOString() : new Date(day + "T12:00:00").toISOString(),
        account_id: accId, category_id: catId, notes: notes.trim() || null, transaction_id: mode === "link" ? txId : null,
        settles: settles === null ? null : settles, allow_overpay: overpay,
      }, idemKey);
      const keys = [["rp-overview"], ["rp-detail"], ["rp-occ"], ["rp-cand"]];
      if (mode !== "mark") keys.push(["accounts"], ["transactions"], ["summary"]);
      await Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("rp.errGeneric"));
      savingRef.current = false; setSaving(false);
    }
  };

  const ModeCard = ({ m, icon, title, hint }: { m: Mode; icon: string; title: string; hint: string }) => (
    <Pressable testID={`rp-mode-${m}`} onPress={() => { setMode(m); setError(null); }}
      style={[styles.modeCard, mode === m && { borderColor: forest, backgroundColor: colors.incomeGreen + "12" }]}>
      <Ionicons name={(mode === m ? "radio-button-on" : "radio-button-off") as any} size={us(18)} color={mode === m ? forest : colors.muted} />
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(6) }}>
          <Ionicons name={icon as any} size={us(15)} color={forest} />
          <Text style={styles.modeTitle}>{title}</Text>
        </View>
        <Text style={styles.hint}>{hint}</Text>
      </View>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="rp-pay-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.title}>{t("rp.payTitle")}</Text>
          </View>

          {rpQ.isLoading || !r ? <ActivityIndicator color={colors.incomeGreen} /> : (
            <>
              <View style={[styles.head, { backgroundColor: base + (isDark ? "1F" : "1A") }]}>
                <View style={[styles.headIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(r.icon || "receipt-outline") as any} size={us(22)} color={deepen(base, isDark)} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.headName, mont()]} numberOfLines={1}>{r.name}</Text>
                  <Text style={styles.small}>{t("rp.dueOf")}: {longDate(due, i18n.language)} · {formatCurrencyInt(expected)}</Text>
                  {!variable && remaining !== expected ? <Text style={styles.small}>{t("rp.partialHint", { amount: formatCurrencyInt(remaining) })}</Text> : null}
                </View>
              </View>

              <Text style={styles.label}>{t("rp.modeLbl")}</Text>
              <View style={{ gap: us(8) }}>
                <ModeCard m="mark" icon="bookmark-outline" title={t("rp.modeMark")} hint={t("rp.modeMarkHint")} />
                <ModeCard m="expense" icon="card-outline" title={t("rp.modeExpense")} hint={t("rp.modeExpenseHint")} />
                <ModeCard m="link" icon="link-outline" title={t("rp.modeLink")} hint={t("rp.modeLinkHint")} />
              </View>

              {mode === "link" ? (
                <>
                  <Text style={styles.label}>{t("rp.candidates")}</Text>
                  <View style={styles.listCard}>
                    {candQ.isLoading ? <ActivityIndicator color={forest} style={{ padding: us(12) }} /> : candidates.length === 0 ? (
                      <Text style={[styles.hint, { padding: us(12), textAlign: "center" }]}>{t("rp.noCandidates")}</Text>
                    ) : candidates.map((c) => (
                      <Pressable key={c.id} testID={`rp-cand-${c.id}`} onPress={() => setTxId(c.id)} style={styles.candRow}>
                        <Ionicons name={(txId === c.id ? "radio-button-on" : "radio-button-off") as any} size={us(18)} color={txId === c.id ? forest : colors.muted} />
                        <View style={{ flex: 1 }}>
                          <Text style={styles.candName} numberOfLines={1}>{c.name}</Text>
                          <Text style={styles.small}>{formatDateTime(c.date)}</Text>
                        </View>
                        <Text style={[styles.candAmt, { color: colors.expenseRed }]}>-{formatCurrencyInt(c.amount)}</Text>
                      </Pressable>
                    ))}
                  </View>
                </>
              ) : (
                <>
                  {mode === "expense" && sameAmount.length > 0 && (
                    <View style={styles.suggest} testID="rp-suggest-link">
                      <Ionicons name="information-circle-outline" size={us(18)} color={colors.info} />
                      <Text style={[styles.hint, { flex: 1, marginTop: 0, color: colors.onSurface }]}>{t("rp.suggestLink")}</Text>
                      <Pressable onPress={() => { setMode("link"); setTxId(sameAmount[0].id); }} hitSlop={8}>
                        <Text style={{ color: colors.info, fontWeight: "800", fontSize: us(12.5) }}>{t("rp.viewCandidates")}</Text>
                      </Pressable>
                    </View>
                  )}
                  <Text style={styles.label}>{t("rp.amountPaid")}</Text>
                  <View style={styles.input}>
                    <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
                    <TextInput testID="rp-pay-amount" value={amount} onChangeText={(v) => { setAmount(v.replace(/[^0-9.,]/g, "")); setError(null); }} keyboardType="decimal-pad" placeholder="0" placeholderTextColor={colors.muted} style={[styles.inputText, { flex: 1, padding: 0, fontSize: us(18) }, mont()]} />
                  </View>
                  {isPartial && <Text style={styles.hint} testID="rp-partial-hint">{t("rp.partialHint", { amount: formatCurrencyInt(remaining - amt) })}</Text>}
                  {isOver && (
                    <View style={[styles.input, { marginTop: us(8) }]}>
                      <Text style={[styles.inputText, { flex: 1, fontSize: us(13.5) }]}>{t("rp.overpay")}</Text>
                      <Switch testID="rp-overpay-switch" value={overpay} onValueChange={setOverpay} trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }} thumbColor="#fff" />
                    </View>
                  )}
                  {(variable || isPartial) && (
                    <View style={[styles.input, { marginTop: us(8) }]}>
                      <Text style={[styles.inputText, { flex: 1, fontSize: us(13.5) }]}>{t("rp.settles")}</Text>
                      <Switch testID="rp-settles-switch" value={settles ?? variable} onValueChange={setSettles} trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }} thumbColor="#fff" />
                    </View>
                  )}

                  <Text style={styles.label}>{t("rp.effDate")}</Text>
                  <Pressable testID="rp-pay-date" onPress={() => { const ms = new Date(day + "T12:00:00").getTime(); dateRef.current?.open({ start: ms, end: ms }); }} style={styles.input}>
                    <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                    <Text style={[styles.inputText, { flex: 1 }]}>{longDate(day, i18n.language)}</Text>
                  </Pressable>

                  <Text style={styles.label}>{t("rp.sourceAccount")}{mode === "mark" ? ` · ${t("rp.optional")}` : ""}</Text>
                  <Pressable testID="rp-pay-account" onPress={() => setSheet("acc")} style={styles.input}>
                    <Ionicons name="wallet-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                    <Text style={[styles.inputText, { flex: 1 }, !acc && { color: colors.muted }]} numberOfLines={1}>{acc ? acc.name : t("rp.none")}</Text>
                    <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
                  </Pressable>

                  <Text style={styles.label}>{t("rp.category")} · {t("rp.optional")}</Text>
                  <Pressable testID="rp-pay-category" onPress={() => setSheet("cat")} style={styles.input}>
                    <Ionicons name="pricetag-outline" size={us(18)} color={cat?.color || forest} style={{ marginRight: us(8) }} />
                    <Text style={[styles.inputText, { flex: 1 }, !cat && { color: colors.muted }]} numberOfLines={1}>{cat ? catLabel(cat.name, i18n.language) : t("rp.none")}</Text>
                    <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
                  </Pressable>
                </>
              )}

              <Text style={styles.label}>{t("rp.description")} · {t("rp.optional")}</Text>
              <View style={styles.input}>
                <TextInput testID="rp-pay-notes" value={notes} onChangeText={setNotes} maxLength={200} placeholder={t("rp.descPh")} placeholderTextColor={colors.muted} style={[styles.inputText, { flex: 1, padding: 0 }]} />
              </View>

              {error ? (
                <View style={styles.errorBox} testID="rp-pay-error">
                  <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              ) : null}

              <Pressable testID="rp-pay-save" onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}>
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{t("rp.savePay")}</Text>}
              </Pressable>
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={sheet !== null} onClose={() => setSheet(null)} testID="rp-pay-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{sheet === "cat" ? t("rp.category") : t("rp.sourceAccount")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {[{ id: null, name: t("rp.none") }, ...(sheet === "cat" ? cats : accounts)].map((o: any) => (
            <Pressable key={o.id || "none"} testID={`rp-pay-opt-${o.id || "none"}`} style={styles.sheetRow}
              onPress={() => { if (sheet === "cat") setCategoryId(o.id || null); else setAccountId(o.id || null); setSheet(null); }}>
              <View style={[styles.dot, { backgroundColor: o.id ? safeHex(o.color) : colors.borderStrong }]} />
              <Text style={styles.sheetRowText} numberOfLines={1}>{sheet === "cat" && o.id ? catLabel(o.name, i18n.language) : o.name}</Text>
              {sheet === "acc" && o.id ? <Text style={styles.small}>{formatCurrencyInt(o.current_balance || 0)}</Text> : null}
            </Pressable>
          ))}
        </ScrollView>
      </AppSheet>

      <DateRangeSheet ref={dateRef} onApply={(rg: DateRange | null) => rg && setDay(toYmd(rg.start))} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  head: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border },
  headIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  headName: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  small: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  modeCard: { flexDirection: "row", gap: 10, alignItems: "flex-start", padding: 12, borderRadius: radius.lg, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  modeTitle: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface, flexShrink: 1 },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 4, lineHeight: 16 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  listCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  candRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderBottomWidth: 1, borderBottomColor: colors.divider },
  candName: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface },
  candAmt: { fontSize: 13.5, fontWeight: "800" },
  suggest: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 12, padding: 10, borderRadius: radius.lg, backgroundColor: colors.info + "14" },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  dot: { width: 12, height: 12, borderRadius: 6 },
}));
