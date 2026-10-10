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
import { useTranslation } from "@/src/i18n";
import { AppSheet } from "@/src/components/sheets";
import { DateRangeSheet, type DateRangeSheetHandle, type DateRange } from "@/src/components/date-range-sheet";
import {
  FOREST, useMontserrat, deepen, safeHex, longDate, toYmd, parseAmount, newGoalKey,
  GOAL_COLORS, GOAL_ICONS, DEFAULT_GOAL_COLOR,
} from "@/src/goals/shared";

import { us } from "@/src/ui-scale";

export default function GoalForm() {
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

  const goalQ = useQuery({ queryKey: ["goal-detail", id], queryFn: () => api.getGoal(id as string), enabled: editing });
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const accounts: any[] = accountsQ.data || [];

  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [initial, setInitial] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [origDate, setOrigDate] = useState<string | null>(null);
  const [icon, setIcon] = useState(GOAL_ICONS[0]);
  const [color, setColor] = useState(DEFAULT_GOAL_COLOR);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [accOpen, setAccOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newGoalKey()).current;
  const loadedRef = useRef(false);
  const dateRef = useRef<DateRangeSheetHandle>(null);

  useEffect(() => {
    const g = goalQ.data;
    if (!editing || loadedRef.current || !g) return;
    loadedRef.current = true;
    setName(g.name || "");
    setTarget(String(g.target_amount ?? ""));
    setInitial(g.initial_amount ? String(g.initial_amount) : "");
    setDate(g.target_date || null);
    setOrigDate(g.target_date || null);
    setIcon(g.icon || GOAL_ICONS[0]);
    setColor(safeHex(g.color));
    setAccountId(g.account_id || null);
  }, [editing, goalQ.data]);

  const strong = deepen(color, isDark);
  const selectedAcc = accounts.find((a) => a.id === accountId);

  const onDate = (r: DateRange | null) => {
    if (!r) return;
    setDate(toYmd(r.start));
    setError(null);
  };

  const save = async () => {
    if (savingRef.current) return;
    const tgt = parseAmount(target);
    const ini = initial.trim() ? parseAmount(initial) : 0;
    if (!name.trim()) return setError(t("goals.errName"));
    if (!Number.isFinite(tgt) || tgt <= 0) return setError(t("goals.errTarget"));
    if (!Number.isFinite(ini) || ini < 0) return setError(t("goals.errInitial"));
    if (date && date !== origDate && date < toYmd(Date.now())) return setError(t("goals.errDatePast"));
    const payload = {
      name: name.trim(),
      target_amount: Math.round(tgt * 100) / 100,
      initial_amount: Math.round(ini * 100) / 100,
      target_date: date,
      icon,
      color,
      account_id: accountId,
    };
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      if (editing) await api.updateGoal(id as string, payload);
      else await api.createGoal(payload, idemKey);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["goals-overview"] }),
        qc.invalidateQueries({ queryKey: ["goal-detail"] }),
        qc.invalidateQueries({ queryKey: ["goals"] }),
      ]);
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("goals.errGeneric"));
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.md) }}>
            <Pressable testID="goal-form-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.title}>{editing ? t("goals.editGoal") : t("goals.newGoal")}</Text>
          </View>

          {editing && goalQ.isLoading ? <ActivityIndicator color={colors.incomeGreen} /> : null}

          {/* Preview */}
          <View style={styles.preview}>
            <View style={[styles.previewIcon, { backgroundColor: color + "29" }]}>
              <Ionicons name={icon as any} size={us(26)} color={strong} />
            </View>
            <Text style={[styles.previewName, mont()]} numberOfLines={1}>{name.trim() || t("goals.namePh")}</Text>
          </View>

          <Text style={styles.label}>{t("goals.name")}</Text>
          <View style={styles.input}>
            <TextInput
              testID="goal-name-input"
              value={name}
              onChangeText={(v) => { setName(v); setError(null); }}
              placeholder={t("goals.namePh")}
              placeholderTextColor={colors.muted}
              maxLength={60}
              style={[styles.inputText, { flex: 1, padding: 0 }]}
            />
          </View>

          <Text style={styles.label}>{t("goals.targetAmount")}</Text>
          <View style={styles.input}>
            <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
            <TextInput
              testID="goal-target-input"
              value={target}
              onChangeText={(v) => { setTarget(v.replace(/[^0-9.,]/g, "")); setError(null); }}
              placeholder="0"
              placeholderTextColor={colors.muted}
              keyboardType="decimal-pad"
              style={[styles.inputText, { flex: 1, padding: 0 }, mont()]}
            />
          </View>

          <Text style={styles.label}>{t("goals.targetDate")} · {t("goals.optional")}</Text>
          <Pressable testID="goal-date" onPress={() => dateRef.current?.open(date ? { start: new Date(date + "T12:00:00").getTime(), end: new Date(date + "T12:00:00").getTime() } : null)} style={styles.input}>
            <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }, !date && { color: colors.muted }]}>
              {date ? longDate(date, i18n.language) : t("goals.noTargetDate")}
            </Text>
            {date ? (
              <Pressable testID="goal-date-clear" onPress={() => setDate(null)} hitSlop={10}>
                <Ionicons name="close-circle" size={us(18)} color={colors.muted} />
              </Pressable>
            ) : null}
          </Pressable>

          <Text style={styles.label}>{t("goals.icon")}</Text>
          <View style={styles.wrapRow}>
            {GOAL_ICONS.map((ic) => {
              const sel = ic === icon;
              return (
                <Pressable
                  key={ic}
                  testID={`goal-icon-${ic}`}
                  onPress={() => setIcon(ic)}
                  style={[styles.iconOpt, sel && { borderColor: color, backgroundColor: color + "1F" }]}
                >
                  <Ionicons name={ic as any} size={us(20)} color={sel ? strong : colors.muted} />
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.label}>{t("goals.color")}</Text>
          <View style={styles.wrapRow}>
            {GOAL_COLORS.map((c) => (
              <Pressable
                key={c}
                testID={`goal-color-${c.slice(1)}`}
                onPress={() => setColor(c)}
                style={[styles.swatch, { backgroundColor: c }, color === c && { borderColor: colors.onSurface, borderWidth: us(3) }]}
              >
                {color === c ? <Ionicons name="checkmark" size={us(16)} color="#fff" /> : null}
              </Pressable>
            ))}
          </View>

          <Text style={styles.label}>{t("goals.initialAmount")} · {t("goals.optional")}</Text>
          <View style={styles.input}>
            <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
            <TextInput
              testID="goal-initial-input"
              value={initial}
              onChangeText={(v) => { setInitial(v.replace(/[^0-9.,]/g, "")); setError(null); }}
              placeholder="0"
              placeholderTextColor={colors.muted}
              keyboardType="decimal-pad"
              style={[styles.inputText, { flex: 1, padding: 0 }, mont()]}
            />
          </View>

          <Text style={styles.label}>{t("goals.account")} · {t("goals.optional")}</Text>
          <Pressable testID="goal-account-select" onPress={() => setAccOpen(true)} style={styles.input}>
            <Ionicons name="wallet-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }, !selectedAcc && { color: colors.muted }]} numberOfLines={1}>
              {selectedAcc ? selectedAcc.name : t("goals.noAccount")}
            </Text>
            <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
          </Pressable>

          {error ? (
            <View style={styles.errorBox} testID="goal-form-error">
              <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            testID="save-goal"
            onPress={save}
            disabled={saving}
            style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}
          >
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{editing ? t("goals.saveChanges") : t("goals.create")}</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={accOpen} onClose={() => setAccOpen(false)} testID="goal-account-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("goals.account")}</Text>
        <ScrollView style={{ maxHeight: us(420) }}>
          {[{ id: null, name: t("goals.noAccount") }, ...accounts].map((a: any) => {
            const sel = (a.id || null) === accountId;
            return (
              <Pressable
                key={a.id || "none"}
                testID={`goal-account-${a.id || "none"}`}
                onPress={() => { setAccountId(a.id || null); setAccOpen(false); }}
                style={styles.sheetRow}
              >
                <View style={[styles.accDot, { backgroundColor: a.id ? safeHex(a.color) : colors.borderStrong }]} />
                <Text style={[styles.sheetRowText, sel && { color: forest, fontWeight: "800" }]} numberOfLines={1}>{a.name}</Text>
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
  previewIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  previewName: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  wrapRow: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  iconOpt: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, borderWidth: 1.5, borderColor: colors.border },
  swatch: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", borderWidth: 0, borderColor: "transparent" },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 8 },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
  sheetRowText: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  accDot: { width: 12, height: 12, borderRadius: 6 },
}));
