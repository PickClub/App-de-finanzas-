import { localizedError } from "@/src/i18n/errors";
import { tr, useTranslation } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import React, { useEffect, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";

import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import { catLabel } from "@/src/category-labels";
import {
  FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount, newKey,
  BILL_ICONS, BILL_COLORS, BILL_FREQS, BILL_REMINDERS, invalidateBills,
} from "@/src/bills/shared";
import { us } from "@/src/ui-scale";

type SheetKind = null | "cat" | "acc" | "rp";

export default function BillForm() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const editing = !!id;

  const billQ = useQuery({ queryKey: ["bill", id], queryFn: () => api.billGet(id as string), enabled: editing });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const rpQ = useQuery({ queryKey: ["rp-list"], queryFn: api.rpList });
  const accounts: any[] = accountsQ.data || [];
  const cats: any[] = (catsQ.data || []).filter((c: any) => c.type === "expense" && !c.is_group);
  const rps: any[] = (rpQ.data || []).filter((r: any) => r.state !== "ended");

  const [name, setName] = useState("");
  const [provider, setProvider] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [rpId, setRpId] = useState<string | null>(null);
  const [due, setDue] = useState<string>(toYmd(Date.now()));
  const [freq, setFreq] = useState<string>("once");
  const [reminder, setReminder] = useState<number | null>(null);
  const [desc, setDesc] = useState("");
  const [icon, setIcon] = useState<string>("receipt-outline");
  const [color, setColor] = useState<string>(BILL_COLORS[3]);
  const [sheet, setSheet] = useState<SheetKind>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newKey("bill")).current;
  const loaded = useRef(false);
  const dateRef = useRef<DateRangeSheetHandle>(null);

  useEffect(() => {
    const b = billQ.data;
    if (!editing || loaded.current || !b) return;
    loaded.current = true;
    setName(b.name); setProvider(b.provider || ""); setAmount(String(b.amount));
    setCategoryId(b.category_id || null); setAccountId(b.account_id || null); setRpId(b.recurring_payment_id || null);
    setDue(b.due_date); setFreq(b.frequency || "once"); setReminder(b.reminder_days ?? null);
    setDesc(b.description || ""); setIcon(b.icon || "receipt-outline"); setColor(safeHex(b.color || BILL_COLORS[3]));
  }, [editing, billQ.data]);

  const cat = cats.find((c) => c.id === categoryId);
  const acc = accounts.find((a) => a.id === accountId);
  const rp = rps.find((r) => r.id === rpId) || (rpId ? (rpQ.data || []).find((r: any) => r.id === rpId) : null);
  const strong = deepen(color, isDark);

  const save = async () => {
    if (savingRef.current) return;
    const amt = parseAmount(amount);
    if (!name.trim()) return setError(t("bills.errName"));
    if (!Number.isFinite(amt) || amt <= 0) return setError(t("bills.errAmount"));
    const payload = {
      name: name.trim(), provider: provider.trim() || null, amount: Math.round(amt * 100) / 100,
      category_id: categoryId, account_id: accountId, due_date: due, frequency: freq, reminder_days: reminder,
      description: desc.trim() || null, recurring_payment_id: rpId, icon, color,
    };
    savingRef.current = true; setSaving(true); setError(null);
    try {
      if (editing) await api.billUpdate(id as string, payload);
      else await api.billCreate(payload, idemKey);
      await invalidateBills(qc);
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("bills.errGeneric"));
      savingRef.current = false; setSaving(false);
    }
  };

  const Chip = ({ sel, label, onPress, testID }: { sel: boolean; label: string; onPress: () => void; testID?: string }) => (
    <Pressable testID={testID} onPress={onPress} style={[styles.chip, sel && { backgroundColor: forest, borderColor: forest }]}>
      <Text style={[styles.chipText, sel && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );

  const Select = ({ testID, icon: ic, tint, value, placeholder, onPress }: any) => (
    <Pressable testID={testID} onPress={onPress} style={styles.input}>
      <Ionicons name={ic} size={us(18)} color={tint || forest} style={{ marginRight: us(8) }} />
      <Text style={[styles.inputText, { flex: 1 }, !value && { color: colors.muted }]} numberOfLines={1}>{value || placeholder}</Text>
      <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
    </Pressable>
  );

  const options: any[] = sheet === "cat" ? cats : sheet === "acc" ? accounts : rps;
  const selectedId = sheet === "cat" ? categoryId : sheet === "acc" ? accountId : rpId;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ElasticScrollView {...NATIVE_VERTICAL_SCROLL} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(24), paddingHorizontal: us(spacing.lg) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="bill-form-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={[styles.title, mont()]}>{editing ? t("bills.editBill") : t("bills.newBill")}</Text>
          </View>
          {editing && billQ.isLoading ? <ActivityIndicator color={forest} /> : null}

          <View style={styles.preview}>
            <View style={[styles.previewIcon, { backgroundColor: color + "29" }]}>
              <Ionicons name={icon as any} size={us(24)} color={strong} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.previewName, mont()]} numberOfLines={1}>{name.trim() || t("bills.namePh")}</Text>
              {provider.trim() ? <Text style={styles.hint} numberOfLines={1}>{provider.trim()}</Text> : null}
            </View>
          </View>

          <Text style={styles.label}>{t("bills.name")}</Text>
          <View style={styles.input}>
            <TextInput testID="bill-name-input" value={name} onChangeText={(v) => { setName(v); setError(null); }} placeholder={t("bills.namePh")} placeholderTextColor={colors.muted} maxLength={60} style={[styles.inputText, { flex: 1, padding: 0 }]} />
          </View>

          <Text style={styles.label}>{t("bills.provider")} · {t("bills.optional")}</Text>
          <View style={styles.input}>
            <TextInput testID="bill-provider-input" value={provider} onChangeText={setProvider} placeholder={t("bills.providerPh")} placeholderTextColor={colors.muted} maxLength={60} style={[styles.inputText, { flex: 1, padding: 0 }]} />
          </View>

          <Text style={styles.label}>{t("bills.amount")}</Text>
          <View style={styles.input}>
            <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
            <TextInput testID="bill-amount-input" value={amount} onChangeText={(v) => { setAmount(v.replace(/[^0-9.,]/g, "")); setError(null); }} placeholder={tr("ui.0")} placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={[styles.inputText, { flex: 1, padding: 0 }, mont()]} />
          </View>

          <Text style={styles.label}>{t("bills.category")} · {t("bills.optional")}</Text>
          <Select testID="bill-category-select" icon={(cat?.icon || "pricetag-outline")} tint={cat?.color} value={cat ? catLabel(cat.name, i18n.language) : null} placeholder={t("bills.none")} onPress={() => setSheet("cat")} />

          <Text style={styles.label}>{t("bills.account")} · {t("bills.optional")}</Text>
          <Select testID="bill-account-select" icon="wallet-outline" value={acc?.name} placeholder={t("bills.none")} onPress={() => setSheet("acc")} />

          <Text style={styles.label}>{t("bills.dueDate")}</Text>
          <Pressable testID="bill-due" onPress={() => { const ms = new Date(due + "T12:00:00").getTime(); dateRef.current?.open({ start: ms, end: ms }); }} style={styles.input}>
            <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }]}>{longDate(due, i18n.language)}</Text>
          </Pressable>

          <Text style={styles.label}>{t("bills.repeat")}</Text>
          <View style={styles.wrapRow}>
            {BILL_FREQS.map((f) => <Chip key={f} testID={`bill-freq-${f}`} sel={freq === f} label={t(`bills.r_${f}`, { defaultValue: t("common.unknown") })} onPress={() => setFreq(f)} />)}
          </View>

          <Text style={styles.label}>{t("bills.reminder")}</Text>
          <View style={styles.wrapRow}>
            {BILL_REMINDERS.map((r) => <Chip key={String(r)} testID={`bill-rem-${r ?? "none"}`} sel={reminder === r} label={t(`bills.rem_${r ?? "none"}`, { defaultValue: t("common.unknown") })} onPress={() => setReminder(r)} />)}
          </View>
          <Text style={styles.hint}>{t("bills.reminderHint")}</Text>

          <Text style={styles.label}>{t("bills.linkRp")} · {t("bills.optional")}</Text>
          <Select testID="bill-rp-select" icon="repeat-outline" value={rp?.name} placeholder={t("bills.none")} onPress={() => setSheet("rp")} />
          <Text style={styles.hint}>{t("bills.linkRpHint")}</Text>

          <Text style={styles.label}>{t("bills.icon")}</Text>
          <View style={styles.wrapRow}>
            {BILL_ICONS.map((ic) => {
              const sel = ic === icon;
              return (
                <Pressable key={ic} testID={`bill-icon-${ic}`} onPress={() => setIcon(ic)} style={[styles.iconOpt, sel && { borderColor: color, backgroundColor: color + "1F" }]}>
                  <Ionicons name={ic as any} size={us(20)} color={sel ? strong : colors.muted} />
                </Pressable>
              );
            })}
          </View>
          <View style={[styles.wrapRow, { marginTop: us(10) }]}>
            {BILL_COLORS.map((c) => (
              <Pressable key={c} testID={`bill-color-${c.slice(1)}`} onPress={() => setColor(c)} style={[styles.swatch, { backgroundColor: c }, color === c && { borderColor: colors.onSurface, borderWidth: us(3) }]}>
                {color === c ? <Ionicons name="checkmark" size={us(16)} color="#fff" /> : null}
              </Pressable>
            ))}
          </View>

          <Text style={styles.label}>{t("bills.description")} · {t("bills.optional")}</Text>
          <View style={styles.input}>
            <TextInput testID="bill-desc-input" value={desc} onChangeText={setDesc} placeholder={t("bills.descPh")} placeholderTextColor={colors.muted} maxLength={200} style={[styles.inputText, { flex: 1, padding: 0 }]} />
          </View>

          {error ? (
            <View style={styles.errorBox} testID="bill-form-error">
              <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
              <Text style={styles.errorText}>{localizedError(error)}</Text>
            </View>
          ) : null}
        </ElasticScrollView>
        {/* Save button stays reachable above the keyboard / safe area. */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + us(12) }]}>
          <Pressable testID="save-bill" onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}>
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{editing ? t("bills.save") : t("bills.create")}</Text>}
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      <AppSheet visible={sheet !== null} onClose={() => setSheet(null)} testID="bill-form-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{sheet === "cat" ? t("bills.category") : sheet === "acc" ? t("bills.account") : t("bills.linkRp")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {[{ id: null, name: t("bills.none") }, ...options].map((o: any) => {
            const sel = (o.id || null) === selectedId;
            return (
              <Pressable key={o.id || "none"} testID={`bill-opt-${o.id || "none"}`} style={styles.sheetRow}
                onPress={() => {
                  if (sheet === "cat") {
                    setCategoryId(o.id || null);
                    if (o.icon && icon === "receipt-outline") setIcon(o.icon);
                  } else if (sheet === "acc") setAccountId(o.id || null);
                  else setRpId(o.id || null);
                  setSheet(null);
                }}>
                <View style={[styles.accDot, { backgroundColor: o.id ? safeHex(o.color) : colors.borderStrong }]} />
                <Text style={[styles.sheetRowText, sel && { color: forest, fontWeight: "800" }]} numberOfLines={1}>{sheet === "cat" && o.id ? catLabel(o.name, i18n.language) : o.name}</Text>
                {sel && <Ionicons name="checkmark" size={us(18)} color={forest} />}
              </Pressable>
            );
          })}
        </ScrollView>
      </AppSheet>

      <DateRangeSheet ref={dateRef} onApply={(r: DateRange | null) => { if (r) { setDue(toYmd(r.start)); setError(null); } }} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, color: colors.onSurface },
  preview: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.cardLg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  previewIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  previewName: { fontSize: 15, color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 6, lineHeight: 16 },
  wrapRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingVertical: 9, paddingHorizontal: 13, minHeight: 38, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  chipText: { fontSize: 12.5, fontWeight: "700", color: colors.onSurface },
  iconOpt: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1.5, borderColor: colors.border },
  swatch: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  footer: { paddingHorizontal: spacing.lg, paddingTop: 10, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  saveBtn: { backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  accDot: { width: 12, height: 12, borderRadius: 6 },
}));
