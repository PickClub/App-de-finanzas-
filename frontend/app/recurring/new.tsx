import React, { useEffect, useRef, useState } from "react";
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
import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import { catLabel } from "@/src/category-labels";
import {
  FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount, newKey,
  RP_ICONS, RP_COLORS, RP_FREQS, MONTH_BASED, RP_REMINDERS,
} from "@/src/recurring/shared";

import { us } from "@/src/ui-scale";

export default function RecurringForm() {
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

  const rpQ = useQuery({ queryKey: ["rp-detail", id], queryFn: () => api.rpGet(id as string), enabled: editing });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accounts: any[] = accountsQ.data || [];
  const cats: any[] = (catsQ.data || []).filter((c: any) => c.type === "expense" && !c.is_group);

  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [variable, setVariable] = useState(false);
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [freq, setFreq] = useState<string>("monthly");
  const [start, setStart] = useState<string>(toYmd(Date.now()));
  const [end, setEnd] = useState<string | null>(null);
  const [dueDay, setDueDay] = useState<number>(new Date().getDate());
  const [icon, setIcon] = useState(RP_ICONS[0]);
  const [color, setColor] = useState(RP_COLORS[0]);
  const [notes, setNotes] = useState("");
  const [reminder, setReminder] = useState<number | null>(null);
  const [active, setActive] = useState(true);
  const [sheet, setSheet] = useState<null | "cat" | "acc">(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newKey("rp")).current;
  const loaded = useRef(false);
  const dateRef = useRef<DateRangeSheetHandle>(null);
  const dateTarget = useRef<"start" | "end">("start");

  useEffect(() => {
    const r = rpQ.data;
    if (!editing || loaded.current || !r) return;
    loaded.current = true;
    setName(r.name); setAmount(String(r.amount)); setVariable(!!r.variable);
    setCategoryId(r.category_id || null); setAccountId(r.account_id || null);
    setFreq(r.frequency); setStart(r.start_date); setEnd(r.end_date || null);
    setDueDay(r.due_day || Number(r.start_date.slice(8, 10)));
    setIcon(r.icon || RP_ICONS[0]); setColor(safeHex(r.color)); setNotes(r.notes || "");
    setReminder(r.reminder_days ?? null);
  }, [editing, rpQ.data]);

  const strong = deepen(color, isDark);
  const cat = cats.find((c) => c.id === categoryId);
  const acc = accounts.find((a) => a.id === accountId);

  const openDate = (target: "start" | "end") => {
    dateTarget.current = target;
    const v = target === "start" ? start : end;
    const ms = v ? new Date(v + "T12:00:00").getTime() : Date.now();
    dateRef.current?.open({ start: ms, end: ms });
  };
  const onDate = (r: DateRange | null) => {
    if (!r) return;
    const v = toYmd(r.start);
    if (dateTarget.current === "start") { setStart(v); if (!editing) setDueDay(Number(v.slice(8, 10))); }
    else setEnd(v);
    setError(null);
  };

  const save = async () => {
    if (savingRef.current) return;
    const amt = parseAmount(amount);
    if (!name.trim()) return setError(t("rp.errName"));
    if (!Number.isFinite(amt) || amt <= 0) return setError(t("rp.errAmount"));
    if (end && end < start) return setError(t("rp.errEnd"));
    const payload = {
      name: name.trim(), amount: Math.round(amt * 100) / 100, variable, category_id: categoryId, account_id: accountId,
      frequency: freq, start_date: start, end_date: end, due_day: MONTH_BASED.has(freq) ? dueDay : null,
      icon, color, notes: notes.trim() || null, reminder_days: reminder, active,
    };
    savingRef.current = true; setSaving(true); setError(null);
    try {
      if (editing) await api.rpUpdate(id as string, payload);
      else await api.rpCreate(payload, idemKey);
      await Promise.all([["rp-overview"], ["rp-detail"], ["rp-occ"]].map((k) => qc.invalidateQueries({ queryKey: k })));
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("rp.errGeneric"));
      savingRef.current = false; setSaving(false);
    }
  };

  const Chip = ({ sel, label, onPress, testID }: { sel: boolean; label: string; onPress: () => void; testID?: string }) => (
    <Pressable testID={testID} onPress={onPress} style={[styles.chip, sel && { backgroundColor: forest, borderColor: forest }]}>
      <Text style={[styles.chipText, sel && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="rp-form-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.title}>{editing ? t("rp.editPayment") : t("rp.newPayment")}</Text>
          </View>
          {editing && rpQ.isLoading ? <ActivityIndicator color={colors.incomeGreen} /> : null}

          <View style={styles.preview}>
            <View style={[styles.previewIcon, { backgroundColor: color + "29" }]}>
              <Ionicons name={icon as any} size={us(24)} color={strong} />
            </View>
            <Text style={[styles.previewName, mont()]} numberOfLines={1}>{name.trim() || t("rp.namePh")}</Text>
          </View>

          <Text style={styles.label}>{t("rp.name")}</Text>
          <View style={styles.input}>
            <TextInput testID="rp-name-input" value={name} onChangeText={(v) => { setName(v); setError(null); }} placeholder={t("rp.namePh")} placeholderTextColor={colors.muted} maxLength={60} style={[styles.inputText, { flex: 1, padding: 0 }]} />
          </View>

          <Text style={styles.label}>{t("rp.amount")}</Text>
          <View style={styles.input}>
            <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
            <TextInput testID="rp-amount-input" value={amount} onChangeText={(v) => { setAmount(v.replace(/[^0-9.,]/g, "")); setError(null); }} placeholder="0" placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={[styles.inputText, { flex: 1, padding: 0 }, mont()]} />
          </View>
          <View style={[styles.input, { marginTop: us(10) }]}>
            <Ionicons name="pulse-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }]}>{t("rp.variable")}</Text>
            <Switch testID="rp-variable-switch" value={variable} onValueChange={setVariable} trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }} thumbColor="#fff" />
          </View>
          {variable && <Text style={styles.hint}>{t("rp.variableHint")}</Text>}

          <Text style={styles.label}>{t("rp.category")} · {t("rp.optional")}</Text>
          <Pressable testID="rp-category-select" onPress={() => setSheet("cat")} style={styles.input}>
            <Ionicons name={(cat?.icon || "pricetag-outline") as any} size={us(18)} color={cat?.color || forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }, !cat && { color: colors.muted }]} numberOfLines={1}>{cat ? catLabel(cat.name, i18n.language) : t("rp.none")}</Text>
            <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
          </Pressable>

          <Text style={styles.label}>{t("rp.account")} · {t("rp.optional")}</Text>
          <Pressable testID="rp-account-select" onPress={() => setSheet("acc")} style={styles.input}>
            <Ionicons name="wallet-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }, !acc && { color: colors.muted }]} numberOfLines={1}>{acc ? acc.name : t("rp.none")}</Text>
            <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
          </Pressable>

          <Text style={styles.label}>{t("rp.frequency")}</Text>
          <View style={styles.wrapRow}>
            {RP_FREQS.map((f) => <Chip key={f} testID={`rp-freq-${f}`} sel={freq === f} label={t(`rp.f_${f}`)} onPress={() => setFreq(f)} />)}
          </View>

          <Text style={styles.label}>{t("rp.startDate")}</Text>
          <Pressable testID="rp-start" onPress={() => openDate("start")} style={styles.input}>
            <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }]}>{longDate(start, i18n.language)}</Text>
          </Pressable>

          {MONTH_BASED.has(freq) && (
            <>
              <Text style={styles.label}>{t("rp.dueDay")}</Text>
              <View style={styles.input}>
                <Pressable testID="rp-dueday-minus" onPress={() => setDueDay((d) => Math.max(1, d - 1))} style={styles.stepBtn}>
                  <Ionicons name="remove" size={us(18)} color={colors.onSurface} />
                </Pressable>
                <Text style={[styles.inputText, { flex: 1, textAlign: "center" }, mont()]} testID="rp-dueday-value">{dueDay}</Text>
                <Pressable testID="rp-dueday-plus" onPress={() => setDueDay((d) => Math.min(31, d + 1))} style={styles.stepBtn}>
                  <Ionicons name="add" size={us(18)} color={colors.onSurface} />
                </Pressable>
              </View>
              <Text style={styles.hint}>{t("rp.dueDayHint")}</Text>
            </>
          )}

          <Text style={styles.label}>{t("rp.endDate")} · {t("rp.optional")}</Text>
          <Pressable testID="rp-end" onPress={() => openDate("end")} style={styles.input}>
            <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }, !end && { color: colors.muted }]}>{end ? longDate(end, i18n.language) : t("rp.noEnd")}</Text>
            {end ? (
              <Pressable testID="rp-end-clear" onPress={() => setEnd(null)} hitSlop={10}>
                <Ionicons name="close-circle" size={us(18)} color={colors.muted} />
              </Pressable>
            ) : null}
          </Pressable>

          <Text style={styles.label}>{t("rp.icon")}</Text>
          <View style={styles.wrapRow}>
            {RP_ICONS.map((ic) => {
              const sel = ic === icon;
              return (
                <Pressable key={ic} testID={`rp-icon-${ic}`} onPress={() => setIcon(ic)} style={[styles.iconOpt, sel && { borderColor: color, backgroundColor: color + "1F" }]}>
                  <Ionicons name={ic as any} size={us(20)} color={sel ? strong : colors.muted} />
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.label}>{t("rp.color")}</Text>
          <View style={styles.wrapRow}>
            {RP_COLORS.map((c) => (
              <Pressable key={c} testID={`rp-color-${c.slice(1)}`} onPress={() => setColor(c)} style={[styles.swatch, { backgroundColor: c }, color === c && { borderColor: colors.onSurface, borderWidth: us(3) }]}>
                {color === c ? <Ionicons name="checkmark" size={us(16)} color="#fff" /> : null}
              </Pressable>
            ))}
          </View>

          <Text style={styles.label}>{t("rp.reminder")}</Text>
          <View style={styles.wrapRow}>
            {RP_REMINDERS.map((r) => <Chip key={String(r)} testID={`rp-rem-${r ?? "none"}`} sel={reminder === r} label={t(`rp.r_${r ?? "none"}`)} onPress={() => setReminder(r)} />)}
          </View>
          <Text style={styles.hint}>{t("rp.pushPending")}</Text>

          <Text style={styles.label}>{t("rp.description")} · {t("rp.optional")}</Text>
          <View style={styles.input}>
            <TextInput testID="rp-notes-input" value={notes} onChangeText={setNotes} placeholder={t("rp.descPh")} placeholderTextColor={colors.muted} maxLength={200} style={[styles.inputText, { flex: 1, padding: 0 }]} />
          </View>

          {!editing && (
            <View style={[styles.input, { marginTop: us(14) }]}>
              <Ionicons name="play-circle-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
              <Text style={[styles.inputText, { flex: 1 }]}>{t("rp.activeLbl")}</Text>
              <Switch testID="rp-active-switch" value={active} onValueChange={setActive} trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }} thumbColor="#fff" />
            </View>
          )}

          {error ? (
            <View style={styles.errorBox} testID="rp-form-error">
              <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Pressable testID="save-rp" onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}>
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{editing ? t("rp.save") : t("rp.create")}</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={sheet !== null} onClose={() => setSheet(null)} testID="rp-form-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{sheet === "cat" ? t("rp.category") : t("rp.account")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {[{ id: null, name: t("rp.none") }, ...(sheet === "cat" ? cats : accounts)].map((o: any) => {
            const sel = (o.id || null) === (sheet === "cat" ? categoryId : accountId);
            return (
              <Pressable key={o.id || "none"} testID={`rp-opt-${o.id || "none"}`} style={styles.sheetRow}
                onPress={() => { if (sheet === "cat") setCategoryId(o.id || null); else setAccountId(o.id || null); setSheet(null); }}>
                <View style={[styles.accDot, { backgroundColor: o.id ? safeHex(o.color) : colors.borderStrong }]} />
                <Text style={[styles.sheetRowText, sel && { color: forest, fontWeight: "800" }]} numberOfLines={1}>{sheet === "cat" && o.id ? catLabel(o.name, i18n.language) : o.name}</Text>
                {sel && <Ionicons name="checkmark" size={us(18)} color={forest} />}
              </Pressable>
            );
          })}
        </ScrollView>
      </AppSheet>

      <DateRangeSheet ref={dateRef} onApply={onDate} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  preview: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.cardLg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  previewIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  previewName: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 6, lineHeight: 16 },
  wrapRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingVertical: 9, paddingHorizontal: 13, minHeight: 38, justifyContent: "center", borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  chipText: { fontSize: 12.5, fontWeight: "700", color: colors.onSurface },
  stepBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  iconOpt: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1.5, borderColor: colors.border },
  swatch: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  accDot: { width: 12, height: 12, borderRadius: 6 },
}));
