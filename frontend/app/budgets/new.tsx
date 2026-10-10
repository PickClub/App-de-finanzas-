import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, Switch, ActivityIndicator } from "react-native";
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
import { FOREST, useMontserrat, shortDate, newIdempotencyKey } from "@/src/budgets/shared";

import { us } from "@/src/ui-scale";

type Period = "weekly" | "monthly" | "custom";
const PERIODS: Period[] = ["weekly", "monthly", "custom"];

function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export default function BudgetForm() {
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

  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const budgetsQ = useQuery({ queryKey: ["budgets"], queryFn: api.listBudgets, enabled: editing });

  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [limit, setLimit] = useState("");
  const [period, setPeriod] = useState<Period>("monthly");
  const [start, setStart] = useState<number>(startOfToday());
  const [end, setEnd] = useState<number | null>(null);
  const [alertsOn, setAlertsOn] = useState(true);
  const [threshold, setThreshold] = useState(80);
  const [catOpen, setCatOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const idemKey = useRef(newIdempotencyKey()).current;
  const loadedRef = useRef(false);
  const dateRef = useRef<DateRangeSheetHandle>(null);
  const dateTarget = useRef<"start" | "end" | "range">("start");

  // Prefill when editing.
  useEffect(() => {
    if (!editing || loadedRef.current || !budgetsQ.data) return;
    const b = budgetsQ.data.find((x: any) => x.id === id);
    if (!b) return;
    loadedRef.current = true;
    setCategoryId(b.category_id || undefined);
    setLimit(String(b.amount_limit ?? ""));
    setPeriod((b.period as Period) || "monthly");
    if (b.start_date) setStart(new Date(b.start_date).getTime());
    setEnd(b.end_date ? new Date(b.end_date).getTime() : null);
    setAlertsOn(b.alerts_enabled !== false);
    setThreshold(b.alert_threshold || 80);
  }, [editing, id, budgetsQ.data]);

  const cats: any[] = useMemo(() => catsQ.data || [], [catsQ.data]);
  const groups = useMemo(() => cats.filter((c) => c.type === "expense" && c.is_group), [cats]);
  const childrenOf = (gid: string) => cats.filter((c) => c.type === "expense" && !c.is_group && c.parent_id === gid);
  const orphans = cats.filter((c) => c.type === "expense" && !c.is_group && !c.parent_id);
  const selected = cats.find((c) => c.id === categoryId);
  const name = (c: any) => catLabel(c?.name, i18n.language);

  const openDate = (target: "start" | "end" | "range") => {
    dateTarget.current = target;
    const value: DateRange | null =
      target === "range" ? { start, end: end ?? start } : target === "end" && end ? { start: end, end } : { start, end: start };
    dateRef.current?.open(value);
  };
  const onDate = (r: DateRange | null) => {
    if (!r) return;
    const s = new Date(r.start); s.setHours(0, 0, 0, 0);
    const e = new Date(r.end); e.setHours(0, 0, 0, 0);
    if (dateTarget.current === "range") { setStart(s.getTime()); setEnd(e.getTime()); }
    else if (dateTarget.current === "end") setEnd(e.getTime());
    else setStart(s.getTime());
    setError(null);
  };

  const save = async () => {
    if (savingRef.current) return;
    const amt = Number(limit.replace(",", "."));
    if (!categoryId) return setError(t("budgets.errCategory"));
    if (!Number.isFinite(amt) || amt <= 0) return setError(t("budgets.errAmount"));
    if (period === "custom" && !end) return setError(t("budgets.errDates"));
    if (end !== null && end < start) return setError(t("budgets.errEndBefore"));
    const payload = {
      category_id: categoryId,
      amount_limit: Math.round(amt * 100) / 100,
      period,
      start_date: new Date(start).toISOString(),
      end_date: end !== null ? new Date(end).toISOString() : null,
      alerts_enabled: alertsOn,
      alert_threshold: threshold,
    };
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      if (editing) await api.updateBudget(id as string, payload);
      else await api.createBudget(payload, idemKey);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["budgets-overview"] }),
        qc.invalidateQueries({ queryKey: ["budgets"] }),
        qc.invalidateQueries({ queryKey: ["budget-detail"] }),
      ]);
      router.back();
    } catch (e: any) {
      setError(e instanceof ApiError ? e.detail : t("budgets.errGeneric"));
      savingRef.current = false;
      setSaving(false);
    }
  };

  const catRow = (c: any, indent = false) => {
    const sel = c.id === categoryId;
    return (
      <Pressable
        key={c.id}
        testID={`budget-cat-${c.id}`}
        onPress={() => { setCategoryId(c.id); setCatOpen(false); setError(null); }}
        style={[styles.catRow, indent && { paddingLeft: us(28) }, sel && { backgroundColor: c.color + "1F" }]}
      >
        <View style={[styles.catIcon, { backgroundColor: c.color + "26" }]}>
          <Ionicons name={(c.icon || "pricetag-outline") as any} size={us(16)} color={c.color} />
        </View>
        <Text style={[styles.catName, c.is_group && { fontWeight: "800" }]} numberOfLines={1}>{name(c)}</Text>
        {c.is_group && <Text style={styles.mainBadge}>{t("budgets.mainCategory")}</Text>}
        {sel && <Ionicons name="checkmark" size={us(18)} color={forest} style={{ marginLeft: us(6) }} />}
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1 }}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(40), paddingHorizontal: us(spacing.lg) }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
            <Pressable testID="budget-form-back" onPress={() => router.back()} style={styles.backBtn}>
              <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.title}>{editing ? t("budgets.editBudget") : t("budgets.newBudget")}</Text>
          </View>

          {editing && budgetsQ.isLoading ? <ActivityIndicator color={colors.incomeGreen} /> : null}

          {/* Category */}
          <Text style={styles.label}>{t("budgets.category")}</Text>
          <Pressable testID="budget-category-select" onPress={() => setCatOpen(true)} style={styles.input}>
            {selected ? (
              <View style={{ flexDirection: "row", alignItems: "center", flex: 1 }}>
                <View style={[styles.catIcon, { backgroundColor: selected.color + "26" }]}>
                  <Ionicons name={(selected.icon || "pricetag-outline") as any} size={us(16)} color={selected.color} />
                </View>
                <Text style={styles.inputText} numberOfLines={1}>{name(selected)}</Text>
                {selected.is_group && <Text style={styles.mainBadge}>{t("budgets.mainCategory")}</Text>}
              </View>
            ) : (
              <Text style={[styles.inputText, { color: colors.muted, flex: 1 }]}>{t("budgets.selectCategory")}</Text>
            )}
            <Ionicons name="chevron-down" size={us(18)} color={colors.muted} />
          </Pressable>

          {/* Limit */}
          <Text style={styles.label}>{t("budgets.limitLbl")}</Text>
          <View style={styles.input}>
            <Text style={[styles.inputText, { color: colors.muted, marginRight: us(4) }]}>$</Text>
            <TextInput
              testID="budget-limit-input"
              value={limit}
              onChangeText={(v) => { setLimit(v.replace(/[^0-9.,]/g, "")); setError(null); }}
              placeholder="0"
              placeholderTextColor={colors.muted}
              keyboardType="decimal-pad"
              style={[styles.inputText, { flex: 1, padding: 0 }, mont()]}
            />
          </View>

          {/* Period */}
          <Text style={styles.label}>{t("budgets.period")}</Text>
          <View style={styles.segment}>
            {PERIODS.map((p) => (
              <Pressable
                key={p}
                testID={`budget-period-${p}`}
                onPress={() => { setPeriod(p); setError(null); }}
                style={[styles.segItem, period === p && { backgroundColor: forest }]}
              >
                <Text style={[styles.segText, period === p && { color: "#fff" }]}>{t(`budgets.${p}`)}</Text>
              </Pressable>
            ))}
          </View>
          {period === "weekly" && <Text style={styles.hint}>{t("budgets.weekStartsMonday")}</Text>}

          {/* Dates */}
          {period === "custom" ? (
            <>
              <Text style={styles.label}>{t("budgets.dates")}</Text>
              <Pressable testID="budget-range" onPress={() => openDate("range")} style={styles.input}>
                <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }]}>
                  {shortDate(new Date(start).toISOString(), i18n.language)} — {end ? shortDate(new Date(end).toISOString(), i18n.language) : "…"}
                </Text>
              </Pressable>
            </>
          ) : (
            <>
              <Text style={styles.label}>{t("budgets.startDate")}</Text>
              <Pressable testID="budget-start" onPress={() => openDate("start")} style={styles.input}>
                <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }]}>{shortDate(new Date(start).toISOString(), i18n.language)}</Text>
              </Pressable>
              <Text style={styles.label}>{t("budgets.endDate")} · {t("budgets.optionalEnd")}</Text>
              <Pressable testID="budget-end" onPress={() => openDate("end")} style={styles.input}>
                <Ionicons name="calendar-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
                <Text style={[styles.inputText, { flex: 1 }, !end && { color: colors.muted }]}>
                  {end ? shortDate(new Date(end).toISOString(), i18n.language) : t("budgets.noEnd")}
                </Text>
                {end !== null && (
                  <Pressable testID="budget-end-clear" onPress={() => setEnd(null)} hitSlop={10}>
                    <Ionicons name="close-circle" size={us(18)} color={colors.muted} />
                  </Pressable>
                )}
              </Pressable>
            </>
          )}

          {/* Alerts */}
          <View style={[styles.input, { marginTop: us(18) }]}>
            <Ionicons name="notifications-outline" size={us(18)} color={forest} style={{ marginRight: us(8) }} />
            <Text style={[styles.inputText, { flex: 1 }]}>{t("budgets.alertsEnable")}</Text>
            <Switch
              testID="budget-alerts-switch"
              value={alertsOn}
              onValueChange={setAlertsOn}
              trackColor={{ true: colors.incomeGreen, false: colors.borderStrong }}
              thumbColor="#fff"
            />
          </View>
          {alertsOn && (
            <>
              <Text style={styles.label}>{t("budgets.alertPct")}</Text>
              <View style={styles.input}>
                <Pressable testID="budget-threshold-minus" onPress={() => setThreshold((v) => Math.max(5, v - 5))} style={styles.stepBtn}>
                  <Ionicons name="remove" size={us(18)} color={colors.onSurface} />
                </Pressable>
                <Text style={[styles.inputText, { flex: 1, textAlign: "center" }, mont()]} testID="budget-threshold-value">{threshold}%</Text>
                <Pressable testID="budget-threshold-plus" onPress={() => setThreshold((v) => Math.min(100, v + 5))} style={styles.stepBtn}>
                  <Ionicons name="add" size={us(18)} color={colors.onSurface} />
                </Pressable>
              </View>
            </>
          )}

          {error ? (
            <View style={styles.errorBox} testID="budget-form-error">
              <Ionicons name="alert-circle" size={us(16)} color={colors.expenseRed} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            testID="save-budget"
            onPress={save}
            disabled={saving}
            style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.75 }]}
          >
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveText}>{t("budgets.save")}</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>

      <AppSheet visible={catOpen} onClose={() => setCatOpen(false)} testID="budget-category-sheet">
        <Text style={[styles.sheetTitle, mont()]}>{t("budgets.category")}</Text>
        <ScrollView style={{ maxHeight: us(460) }} contentContainerStyle={{ paddingBottom: us(8) }}>
          {groups.map((g) => (
            <View key={g.id}>
              {catRow(g)}
              {childrenOf(g.id).map((c) => catRow(c, true))}
            </View>
          ))}
          {orphans.map((c) => catRow(c))}
        </ScrollView>
      </AppSheet>

      <DateRangeSheet ref={dateRef} onApply={onDate} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { flexDirection: "row", alignItems: "center", minHeight: 50, backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  inputText: { fontSize: 15, color: colors.onSurface },
  hint: { fontSize: 11.5, color: colors.muted, marginTop: 6 },
  segment: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, padding: 4 },
  segItem: { flex: 1, paddingVertical: 10, borderRadius: radius.pill, alignItems: "center" },
  segText: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  stepBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  catRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, paddingHorizontal: 8, borderRadius: radius.lg },
  catIcon: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center", marginRight: 10 },
  catName: { flex: 1, fontSize: 14.5, color: colors.onSurface },
  mainBadge: { fontSize: 10.5, fontWeight: "700", color: colors.muted, backgroundColor: colors.surfaceTertiary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, overflow: "hidden", marginLeft: 6 },
  sheetTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginTop: 4, marginBottom: 10 },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16, padding: 12, borderRadius: radius.lg, backgroundColor: colors.expenseRed + "14" },
  errorText: { flex: 1, color: colors.expenseRed, fontSize: 13, fontWeight: "600" },
  saveBtn: { marginTop: 22, backgroundColor: colors.brandPrimary, padding: 16, minHeight: 54, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
