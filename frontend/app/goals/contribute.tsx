import React, { useRef, useState } from "react";
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
import { formatCurrencyInt } from "@/src/format";
import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import { FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount, newGoalKey } from "@/src/goals/shared";

import { us } from "@/src/ui-scale";

type DayChoice = "today" | "yesterday" | "other";

export default function GoalContribution() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id, kind: kindParam } = useLocalSearchParams<{ id: string; kind?: string }>();
  const kind: "deposit" | "withdrawal" = kindParam === "withdrawal" ? "withdrawal" : "deposit";
  const isDeposit = kind === "deposit";

  const goalQ = useQuery({ queryKey: ["goal-detail", id], queryFn: () => api.getGoal(id as string) });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const accounts: any[] = accountsQ.data || [];
  const g = goalQ.data;

  const [amount, setAmount] = useState("");
  const [day, setDay] = useState<DayChoice>("today");
  const [otherDate, setOtherDate] = useState<string | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [real, setReal] = useState(false);
  const [accOpen, setAccOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newGoalKey("contrib")).current;
  const dateRef = useRef<DateRangeSheetHandle>(null);

  const base = safeHex(g?.color);
  const strong = deepen(base, isDark);
  const goalAcc = accounts.find((a) => a.id === g?.account_id);
  const selAcc = accounts.find((a) => a.id === accountId);
  const realPossible = !!goalAcc && !!selAcc && selAcc.id !== goalAcc.id;
  const realOn = real && realPossible;

  const onDate = (r: DateRange | null) => {
    if (!r) return;
    setOtherDate(toYmd(r.start));
    setDay("other");
  };

  const dateIso = () => {
    if (day === "today") return new Date().toISOString();
    if (day === "yesterday") { const d = new Date(); d.setDate(d.getDate() - 1); return d.toISOString(); }
    return new Date((otherDate || toYmd(Date.now())) + "T12:00:00").toISOString();
  };

  const save = async () => {
    if (savingRef.current || !g) return;
    const amt = parseAmount(amount);
    if (!Number.isFinite(amt) || amt <= 0) return setError(t("goals.errAmount"));
    if (!isDeposit && amt > g.current_amount + 1e-9) return setError(t("goals.errWithdrawMax", { amount: formatCurrencyInt(g.current_amount) }));
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await api.createGoalContribution(id as string, {
        kind,
        amount: Math.round(amt * 100) / 100,
        date: dateIso(),
        account_id: accountId,
        notes: notes.trim() || null,
        real_movement: realOn,
      }, idemKey);
      const keys = [["goals-overview"], ["goal-detail"], ["goal-contribs"], ["goals"]];
      if (realOn) keys.push(["accounts"], ["transactions"], ["summary"]);
      await Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("goals.errGeneric"));
      savingRef.current = false;
      setSaving(false);
    }
  };

  const DayChip = ({ k, label }: { k: DayChoice; label: string }) => (
    <Pressable
      testID={`contrib-day-${k}`}
      onPress={() => (k === "other" ? dateRef.current?.open(null) : setDay(k))}
      style={[styles.chip, day === k && { backgroundColor: forest, borderColor: forest }]}
    >
      <Text style={[styles.chipText, day === k && { color: "#fff" }]}>{label}</Text>
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="contrib-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.title}>{isDeposit ? t("goals.addSaving") : t("goals.withdraw")}</Text>
          </View>

          {goalQ.isLoading ? (
            <ActivityIndicator color={colors.incomeGreen} style={{ marginTop: us(30) }} />
          ) : !g ? (
            <Text style={styles.muted}>{t("goals.notFound")}</Text>
          ) : (
            <>
              <View style={[styles.goalRow, { backgroundColor: base + (isDark ? "1F" : "1A") }]} testID="contrib-goal">
                <View style={[styles.goalIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(g.icon || "flag") as any} size={us(22)} color={strong} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.goalName, mont()]} numberOfLines={1}>{g.name}</Text>
                  <Text style={styles.small}>
                    {formatCurrencyInt(g.current_amount)} / {formatCurrencyInt(g.target_amount)}
                  </Text>
                </View>
              </View>

              <Text style={styles.label}>{isDeposit ? t("goals.amount") : t("goals.withdrawAmount")}</Text>
              <View style={styles.input}>
                <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
                <TextInput
                  testID="contrib-amount-input"
                  value={amount}
                  onChangeText={(v) => { setAmount(v.replace(/[^0-9.,]/g, "")); setError(null); }}
                  placeholder="0"
                  placeholderTextColor={colors.muted}
                  keyboardType="decimal-pad"
                  autoFocus
                  style={[styles.inputText, { flex: 1, padding: 0, fontSize: us(18) }, mont()]}
                />
              </View>
              {!isDeposit && <Text style={styles.hint}>{t("goals.available", { amount: formatCurrencyInt(g.current_amount) })}</Text>}

              <Text style={styles.label}>{t("goals.date")}</Text>
              <View style={{ flexDirection: "row", gap: us(8) }}>
                <DayChip k="today" label={t("goals.today")} />
                <DayChip k="yesterday" label={t("goals.yesterday")} />
                <DayChip k="other" label={day === "other" && otherDate ? longDate(otherDate, i18n.language) : t("goals.otherDate")} />
              </View>

              <Text style={styles.label}>{isDeposit ? t("goals.sourceAccount") : t("goals.destAccount")} · {t("goals.optional")}</Text>
              <Pressable testID="contrib-account-select" onPress={() => setAccOpen(true)} style={styles.input}>
                <Ionicons name="wallet-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }, !selAcc && { color: colors.muted }]} numberOfLines={1}>
                  {selAcc ? selAcc.name : t("goals.none")}
                </Text>
                <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
              </Pressable>

              <Text style={styles.label}>{t("goals.description")} · {t("goals.optional")}</Text>
              <View style={styles.input}>
                <TextInput
                  testID="contrib-notes-input"
                  value={notes}
                  onChangeText={setNotes}
                  placeholder={t("goals.descPh")}
                  placeholderTextColor={colors.muted}
                  maxLength={200}
                  style={[styles.inputText, { flex: 1, padding: 0 }]}
                />
              </View>

              {/* Financial rule: tracking by default; real transfer only when explicitly enabled */}
              <View style={[styles.input, { marginTop: us(16) }, !realPossible && { opacity: 0.6 }]}>
                <Ionicons name="swap-horizontal" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1, fontSize: us(14) }]}>{t("goals.realMovement")}</Text>
                <Switch
                  testID="contrib-real-switch"
                  value={realOn}
                  disabled={!realPossible}
                  onValueChange={setReal}
                  trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }}
                  thumbColor="#fff"
                />
              </View>
              <Text style={styles.hint} testID="contrib-real-hint">
                {realOn
                  ? t("goals.realMovementHint", isDeposit ? { from: selAcc?.name, to: goalAcc?.name } : { from: goalAcc?.name, to: selAcc?.name })
                  : realPossible ? t("goals.trackingHint") : `${t("goals.trackingHint")} ${t("goals.realNeedsAccount")}`}
              </Text>

              {error ? (
                <View style={styles.errorBox} testID="contrib-error">
                  <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              ) : null}

              <Pressable
                testID="save-contribution"
                onPress={save}
                disabled={saving}
                style={({ pressed }) => [styles.saveBtn, !isDeposit && { backgroundColor: forest }, (pressed || saving) && { opacity: 0.75 }]}
              >
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{isDeposit ? t("goals.saveContribution") : t("goals.saveWithdrawal")}</Text>}
              </Pressable>
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={accOpen} onClose={() => setAccOpen(false)} testID="contrib-account-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{isDeposit ? t("goals.sourceAccount") : t("goals.destAccount")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {[{ id: null, name: t("goals.none") }, ...accounts].map((a: any) => {
            const sel = (a.id || null) === accountId;
            return (
              <Pressable
                key={a.id || "none"}
                testID={`contrib-account-${a.id || "none"}`}
                onPress={() => { setAccountId(a.id || null); setAccOpen(false); }}
                style={styles.sheetRow}
              >
                <View style={[styles.accDot, { backgroundColor: a.id ? safeHex(a.color) : colors.borderStrong }]} />
                <Text style={[styles.sheetRowText, sel && { color: forest, fontWeight: "800" }]} numberOfLines={1}>{a.name}</Text>
                {a.id ? <Text style={styles.small}>{formatCurrencyInt(a.current_balance || 0)}</Text> : null}
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
  muted: { color: colors.muted, fontSize: 13, textAlign: "center", marginTop: 30 },
  goalRow: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border },
  goalIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  goalName: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  small: { fontSize: 12, color: colors.muted, marginTop: 1 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 6, lineHeight: 16 },
  chip: { flexShrink: 1, paddingVertical: 10, paddingHorizontal: 14, minHeight: 40, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, justifyContent: "center" },
  chipText: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  accDot: { width: 12, height: 12, borderRadius: 6 },
}));
