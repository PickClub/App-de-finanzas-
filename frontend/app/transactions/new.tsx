import React, { useEffect, useMemo, useRef, useState } from "react";
import { View, ScrollView, KeyboardAvoidingView, Platform, Alert, Keyboard } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useResourceDeletion } from "@/src/use-resource-deletion";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";
import { ConfirmSheet, AppSheet } from "@/src/components/sheets";

import { us } from "@/src/ui-scale";
const TYPE_LABEL: Record<string, string> = {
  income: "Ingreso",
  expense: "Gasto",
  transfer: "Transferencia",
  debt_payment: "Pago de deuda",
};
const TYPE_ICON: Record<string, string> = {
  expense: "trending-down",
  income: "trending-up",
  transfer: "swap-horizontal",
};

// Same light-mode identity values used by Home (app/(tabs)/index.tsx HOME_LIGHT
// + its sage background / mint badge / forest green). Local to this screen only;
// dark mode keeps the global dark theme exactly like Home does.
const HOME_IDENTITY_LIGHT = {
  onSurface: "#15251E",
  muted: "#68746D",
  brandPrimary: "#126046",
  accountsBlue: "#377FC4",
  incomeGreen: "#138B66",
  expenseRed: "#D84D45",
  border: "rgba(39,71,56,0.10)",
  borderStrong: "rgba(39,71,56,0.14)",
  surfaceSecondary: "#FCFCF8",
};
function screenPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  const c = dark ? colors : { ...colors, ...HOME_IDENTITY_LIGHT };
  return {
    ...c,
    bg: dark ? colors.surface : "#E8EFE7",
    card: c.surfaceSecondary,
    mint: dark ? colors.brandPrimary + "26" : "#DCE9DD",
    forest: dark ? colors.brandPrimary : "#126046",
    coral: colors.brand,
  };
}
function typeColor(p: any, tp: string) {
  if (tp === "income") return p.incomeGreen;
  if (tp === "transfer") return p.accountsBlue;
  return p.coral;
}

// ---- Calculator helpers (2-decimal monetary precision) ----
type Op = "+" | "−" | "×" | "÷";
const MAX_INT_DIGITS = 9;
const round2 = (x: number) => Math.round((x + Math.sign(x) * Number.EPSILON) * 100) / 100;
const numStr = (n: number) => String(round2(n));
function applyOp(a: number, op: Op, b: number): number | null {
  let r: number;
  if (op === "+") r = a + b;
  else if (op === "−") r = a - b;
  else if (op === "×") r = a * b;
  else {
    if (b === 0) return null;
    r = a / b;
  }
  return Number.isFinite(r) ? round2(r) : null;
}
const CALC_ROWS: { k: string; kind: "op" | "num" | "eq" }[][] = [
  [{ k: "+", kind: "op" }, { k: "7", kind: "num" }, { k: "8", kind: "num" }, { k: "9", kind: "num" }],
  [{ k: "−", kind: "op" }, { k: "4", kind: "num" }, { k: "5", kind: "num" }, { k: "6", kind: "num" }],
  [{ k: "×", kind: "op" }, { k: "1", kind: "num" }, { k: "2", kind: "num" }, { k: "3", kind: "num" }],
  [{ k: "÷", kind: "op" }, { k: "0", kind: "num" }, { k: ".", kind: "num" }, { k: "=", kind: "eq" }],
];
const KEY_ID: Record<string, string> = { "+": "plus", "−": "minus", "×": "times", "÷": "divide", ".": "dot", "=": "equals" };

export default function NewTransaction() {
  const { colors, scheme } = useTheme();
  const pal = useMemo(() => screenPalette(colors, scheme), [colors, scheme]);
  const styles = useStyles();
  const params = useLocalSearchParams<{ id?: string; type?: string; dupFrom?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const deletion = useResourceDeletion("/(tabs)", [["accounts"], ["transactions"], ["categories"], ["debts"], ["debt-payments"], ["debt"], ["summary"]]);
  const [loadedId, setResourceLoaded] = useState<string>();
  const resourceLoaded = loadedId === params.id;

  const [type, setType] = useState<string>(params.type || "expense");
  const [amount, setAmount] = useState("");
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [accountId, setAccountId] = useState<string | undefined>();
  const [toAccountId, setToAccountId] = useState<string | undefined>();
  // Notes field is no longer shown here, but existing notes are preserved on save.
  const [notes, setNotes] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);
  // Calculator state: `amount` is the current entry; acc/op hold a pending operation.
  const [acc, setAcc] = useState<number | null>(null);
  const [op, setOp] = useState<Op | null>(null);
  const [fresh, setFresh] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [picker, setPicker] = useState<null | "account" | "toAccount" | "category">(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const cats = (catQ.data || []).filter((c: any) => (type === "income" ? c.type === "income" : c.type === "expense") && !c.is_group);

  // Ensure the default category catalog exists so selection always has options.
  const ensuredRef = React.useRef(false);
  useEffect(() => {
    if (!catQ.isSuccess || ensuredRef.current) return;
    ensuredRef.current = true;
    if ((catQ.data || []).length === 0) {
      api.initDefaultCategories().then(() => qc.invalidateQueries({ queryKey: ["categories"] })).catch(() => {});
    }
  }, [catQ.isSuccess, catQ.data, qc]);

  useEffect(() => {
    if (params.id) {
      api.listTransactions().then((all) => {
        const t = all.find((x: any) => x.id === params.id);
        if (!t) { deletion.unavailable(); return; }
        if (t) {
          setResourceLoaded(params.id);
          setType(t.type);
          setAmount(String(t.amount));
          setName(t.name);
          setCategoryId(t.category_id);
          setAccountId(t.account_id);
          setToAccountId(t.to_account_id);
          setNotes(t.notes || "");
        }
      }).catch((error) => Alert.alert("No se pudo cargar", error instanceof Error ? error.message : "Inténtalo de nuevo."));
    }
  }, [params.id]);

  // Duplicate: prefill from the source transaction but WITHOUT an id, so this
  // opens as a NEW unsaved movement. Nothing is created until the user taps
  // "Guardar" (which runs createTransaction because params.id is undefined).
  useEffect(() => {
    if (params.dupFrom && !params.id) {
      api.listTransactions().then((all) => {
        const t = all.find((x: any) => x.id === params.dupFrom);
        if (t) {
          setType(t.type);
          setAmount(String(t.amount));
          setName(t.name);
          setCategoryId(t.category_id);
          setAccountId(t.account_id);
          setToAccountId(t.to_account_id);
          setNotes(t.notes || "");
        }
      });
    }
  }, [params.dupFrom, params.id]);

  // Final monetary value (evaluates a pending operation); null = invalid/empty.
  const finalAmount = useMemo<number | null>(() => {
    if (acc !== null && op) {
      if (amount === "") return acc;
      const cur = parseFloat(amount);
      return Number.isFinite(cur) ? applyOp(acc, op, cur) : null;
    }
    if (amount === "") return null;
    const v = parseFloat(amount);
    return Number.isFinite(v) ? round2(v) : null;
  }, [acc, op, amount]);

  const pressDigit = (d: string) => {
    Keyboard.dismiss();
    setCalcError(null);
    const base = fresh ? "" : amount;
    let next: string;
    if (d === ".") {
      if (base.includes(".")) return;
      next = base === "" ? "0." : base + ".";
    } else if (base.includes(".")) {
      if (base.split(".")[1].length >= 2) return;
      next = base + d;
    } else {
      const intPart = base === "0" ? "" : base;
      if (intPart.replace("-", "").length >= MAX_INT_DIGITS) return;
      next = intPart + d;
    }
    setAmount(next);
    setFresh(false);
  };

  const pressOp = (o: Op) => {
    Keyboard.dismiss();
    setCalcError(null);
    if (amount === "") {
      if (acc !== null) setOp(o);
      return;
    }
    const cur = parseFloat(amount);
    if (!Number.isFinite(cur)) return;
    if (acc !== null && op) {
      const r = applyOp(acc, op, cur);
      if (r === null) { setCalcError("No se puede dividir entre 0"); return; }
      setAcc(r);
    } else {
      setAcc(round2(cur));
    }
    setOp(o);
    setAmount("");
    setFresh(false);
  };

  const pressEquals = () => {
    Keyboard.dismiss();
    setCalcError(null);
    if (acc === null || !op) {
      const v = parseFloat(amount);
      if (amount !== "" && Number.isFinite(v)) setAmount(numStr(v));
      setFresh(true);
      return;
    }
    if (amount === "") {
      setAmount(numStr(acc));
    } else {
      const r = applyOp(acc, op, parseFloat(amount));
      if (r === null) { setCalcError("No se puede dividir entre 0"); return; }
      setAmount(numStr(r));
    }
    setAcc(null);
    setOp(null);
    setFresh(true);
  };

  const backspace = () => {
    setCalcError(null);
    if (amount !== "") {
      const next = amount.slice(0, -1);
      setAmount(next === "-" ? "" : next);
      setFresh(false);
      return;
    }
    if (acc !== null && op) {
      setOp(null);
      setAmount(numStr(acc));
      setAcc(null);
    }
  };

  const clearAll = () => {
    setCalcError(null);
    setAmount("");
    setAcc(null);
    setOp(null);
    setFresh(false);
  };

  const pressKey = (k: string, kind: "op" | "num" | "eq") => {
    if (kind === "num") pressDigit(k);
    else if (kind === "op") pressOp(k as Op);
    else pressEquals();
  };

  const save = async () => {
    if (savingRef.current) return;
    if (deletion.locked.current || (params.id && !resourceLoaded)) return;
    const amt = finalAmount;
    if (amt === null || !Number.isFinite(amt) || amt <= 0) {
      Alert.alert("Falta información", calcError || "Ingresa un monto válido");
      return;
    }
    const finalName = name.trim() || "Sin descripción";
    const payload: any = {
      name: finalName,
      amount: round2(amt),
      type,
      category_id: categoryId,
      account_id: accountId,
      to_account_id: type === "transfer" ? toAccountId : undefined,
      notes,
    };
    savingRef.current = true;
    setSaving(true);
    try {
      if (params.id) await api.updateTransaction(params.id as string, payload);
      else await api.createTransaction(payload);
      qc.invalidateQueries();
      router.back();
    } catch (e: any) {
      savingRef.current = false;
      setSaving(false);
      Alert.alert("Error", e.message);
    }
  };

  const remove = async () => {
    if (!params.id) return;
    await deletion.remove(() => api.deleteTransaction(params.id as string));
  };

  if (params.id && (!resourceLoaded || deletion.deleted.current)) return <View />;

  const accounts = accQ.data || [];
  const selAcc = accounts.find((a: any) => a.id === accountId);
  const selToAcc = accounts.find((a: any) => a.id === toAccountId);
  const selCat = cats.find((c: any) => c.id === categoryId);
  const activeColor = typeColor(pal, type);
  const pending = acc !== null && op;
  const display = pending ? `${numStr(acc as number)} ${op} ${amount}` : amount || "0.00";
  const hint = calcError
    ? calcError
    : pending && amount !== "" && finalAmount !== null
      ? `= ${finalAmount.toFixed(2)}`
      : !pending && amount !== "" && finalAmount !== null && finalAmount <= 0
        ? "El monto debe ser mayor que 0"
        : null;

  const renderSelectCard = (opts: {
    testID: string;
    label: string;
    icon?: string;
    tint?: string;
    value?: string;
    onPress: () => void;
  }) => (
    <Pressable
      testID={opts.testID}
      onPress={() => { Keyboard.dismiss(); opts.onPress(); }}
      style={({ pressed }) => [styles.selectCard, pressed && styles.pressed]}
    >
      <Text style={styles.cardLabel}>{opts.label}</Text>
      <View style={styles.selectRow}>
        {opts.icon && opts.tint ? (
          <IconTile icon={opts.icon} tint={opts.tint} size={us(34)} />
        ) : (
          <View style={[styles.emptyIcon, { backgroundColor: pal.mint }]}>
            <Ionicons name="add" size={us(18)} color={pal.forest} />
          </View>
        )}
        <Text style={[styles.selectName, !opts.value && { color: pal.muted }]} numberOfLines={1}>
          {opts.value || "Seleccionar"}
        </Text>
        <Ionicons name="chevron-forward" size={us(16)} color={pal.onSurface} />
      </View>
    </Pressable>
  );

  const pickerItems: any[] = picker === "category" ? cats : picker ? accounts : [];
  const pickerSelected = picker === "category" ? categoryId : picker === "toAccount" ? toAccountId : accountId;
  const pickerTitle = picker === "category" ? "Categoría" : picker === "toAccount" ? "Hacia cuenta" : type === "transfer" ? "Desde cuenta" : "Cuenta";
  const onPick = (id: string) => {
    if (picker === "category") setCategoryId(id);
    else if (picker === "toAccount") setToAccountId(id);
    else setAccountId(id);
    setPicker(null);
  };

  return (
    <KeyboardAvoidingView
      pointerEvents={deletion.busy ? "none" : "auto"}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: pal.bg }}
    >
      <View style={[styles.header, { paddingTop: insets.top + us(8) }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={pal.onSurface} />
        </Pressable>
        <Text style={styles.title}>{params.id ? "Editar" : "Nuevo"} movimiento</Text>
        {params.id && (
          <Pressable testID="delete-tx" disabled={deletion.busy} onPress={() => { if (!deletion.locked.current) setConfirmDel(true); }} style={styles.backBtn}>
            <Ionicons name="trash-outline" size={us(22)} color={pal.expenseRed} />
          </Pressable>
        )}
      </View>

      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: us(spacing.lg), paddingBottom: us(spacing.lg) }}
      >
        {/* type selector */}
        <View style={styles.typeRow}>
          {["expense", "income", "transfer"].map((tp) => {
            const active = type === tp;
            const tc = typeColor(pal, tp);
            return (
              <Pressable
                key={tp}
                testID={`type-${tp}`}
                onPress={() => setType(tp)}
                style={[styles.typeBtn, active && { backgroundColor: tc }]}
              >
                <Ionicons name={TYPE_ICON[tp] as any} size={us(15)} color={active ? "#fff" : tc} />
                <Text style={[styles.typeBtnText, active && { color: "#fff" }]} numberOfLines={1}>{TYPE_LABEL[tp]}</Text>
              </Pressable>
            );
          })}
        </View>

        {/* account + category (transfer: from + to) */}
        <View style={styles.selectGrid}>
          {renderSelectCard({
            testID: "pick-account",
            label: type === "transfer" ? "Desde cuenta" : "Cuenta",
            icon: selAcc?.icon,
            tint: selAcc?.color,
            value: selAcc?.name,
            onPress: () => setPicker("account"),
          })}
          {type === "transfer"
            ? renderSelectCard({
                testID: "pick-to-account",
                label: "Hacia cuenta",
                icon: selToAcc?.icon,
                tint: selToAcc?.color,
                value: selToAcc?.name,
                onPress: () => setPicker("toAccount"),
              })
            : renderSelectCard({
                testID: "pick-category",
                label: "Categoría",
                icon: selCat?.icon,
                tint: selCat?.color,
                value: selCat?.name,
                onPress: () => setPicker("category"),
              })}
        </View>

        {/* description (multiline) */}
        <Text style={styles.label}>Descripción</Text>
        <View style={styles.descCard}>
          <View style={[styles.descIcon, { backgroundColor: pal.mint }]}>
            <Ionicons name="create-outline" size={us(17)} color={pal.forest} />
          </View>
          <TextInput
            testID="name-input"
            value={name}
            onChangeText={setName}
            placeholder="Ej. Supermercado, cena, etc."
            placeholderTextColor={pal.muted}
            style={styles.descInput}
            multiline
            textAlignVertical="top"
          />
        </View>

        {/* amount */}
        <View style={styles.amountCard}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.cardLabel}>Monto</Text>
            <Text
              testID="amount-display"
              style={[styles.amountText, { color: amount === "" && !pending ? pal.muted : pal.forest }]}
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {display}
            </Text>
            {hint ? (
              <Text testID="amount-hint" style={[styles.amountHint, calcError && { color: pal.expenseRed }]} numberOfLines={1}>
                {hint}
              </Text>
            ) : null}
          </View>
          <Pressable
            testID="calc-backspace"
            onPress={backspace}
            onLongPress={clearAll}
            style={({ pressed }) => [styles.backspaceBtn, pressed && styles.pressed]}
          >
            <Ionicons name="backspace-outline" size={us(22)} color={pal.onSurface} />
          </Pressable>
        </View>

        {/* calculator */}
        <View style={styles.calc}>
          {CALC_ROWS.map((row, ri) => (
            <View key={ri} style={styles.calcRow}>
              {row.map(({ k, kind }) => (
                <Pressable
                  key={k}
                  testID={`calc-${KEY_ID[k] || k}`}
                  onPress={() => pressKey(k, kind)}
                  style={({ pressed }) => [
                    styles.calcKey,
                    kind === "op" && { backgroundColor: pal.mint, borderColor: "transparent" },
                    kind === "op" && op === k && amount === "" && { borderColor: pal.forest },
                    kind === "eq" && { backgroundColor: pal.forest, borderColor: pal.forest },
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={[styles.calcKeyText, kind === "op" && { color: pal.forest }, kind === "eq" && { color: "#fff" }]}>{k}</Text>
                </Pressable>
              ))}
            </View>
          ))}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + us(12) }]}>
        <Pressable
          testID="save-tx"
          onPress={save}
          disabled={saving}
          style={({ pressed }) => [styles.saveBtn, { backgroundColor: activeColor }, (pressed || saving) && { opacity: 0.85 }]}
        >
          <Text style={styles.saveText}>{saving ? "Guardando…" : "Guardar"}</Text>
        </Pressable>
      </View>

      <AppSheet visible={picker !== null} onClose={() => setPicker(null)} testID="picker-sheet">
        <Text style={styles.sheetTitle}>{pickerTitle}</Text>
        <ScrollView style={{ maxHeight: us(380) }} contentContainerStyle={{ paddingHorizontal: us(spacing.lg), gap: us(8) }}>
          {pickerItems.length === 0 ? (
            <Text style={styles.sheetEmpty}>No hay opciones disponibles</Text>
          ) : (
            pickerItems.map((it: any) => {
              const sel = pickerSelected === it.id;
              return (
                <Pressable
                  key={it.id}
                  testID={`${picker === "category" ? "cat" : picker === "toAccount" ? "toacc" : "acc"}-${it.id}`}
                  onPress={() => onPick(it.id)}
                  style={({ pressed }) => [styles.sheetRow, sel && { borderColor: it.color || pal.forest, borderWidth: 2 }, pressed && styles.pressed]}
                >
                  <IconTile icon={it.icon} tint={it.color} size={us(34)} />
                  <Text style={styles.sheetRowText} numberOfLines={1}>{it.name}</Text>
                  {sel && <Ionicons name="checkmark-circle" size={us(20)} color={it.color || pal.forest} />}
                </Pressable>
              );
            })
          )}
        </ScrollView>
      </AppSheet>

      <ConfirmSheet
        visible={confirmDel}
        onClose={() => setConfirmDel(false)}
        icon="trash-outline"
        accent={pal.expenseRed}
        destructive
        title="¿Eliminar este movimiento?"
        description="Esta acción eliminará permanentemente este movimiento y puede afectar tus saldos y estadísticas."
        confirmLabel="Eliminar"
        confirmTestID="confirm-delete-edit"
        onConfirm={remove}
      />
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  const p = screenPalette(colors, scheme);
  return {
    header: {
      flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
      paddingBottom: spacing.md, gap: 12,
    },
    backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: p.card, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: p.border },
    title: { flex: 1, fontSize: 20, fontWeight: "800", color: p.onSurface },
    typeRow: { flexDirection: "row", backgroundColor: p.card, borderRadius: radius.pill, padding: 4, marginBottom: spacing.md, borderWidth: 1, borderColor: p.border },
    typeBtn: { flex: 1, flexDirection: "row", gap: 6, paddingVertical: 10, alignItems: "center", justifyContent: "center", borderRadius: radius.pill },
    typeBtnText: { color: p.onSurface, fontWeight: "700", fontSize: 13 },
    label: { color: p.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
    cardLabel: { color: p.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5 },
    pressed: { opacity: 0.85, transform: [{ scale: 0.97 }] },
    selectGrid: { flexDirection: "row", gap: 10 },
    selectCard: {
      flex: 1, minWidth: 0, backgroundColor: p.card, borderRadius: radius.lg,
      borderWidth: 1, borderColor: p.border, padding: 12, gap: 10,
      shadowColor: "#274738", shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 1,
    },
    selectRow: { flexDirection: "row", alignItems: "center", gap: 8 },
    selectName: { flex: 1, minWidth: 0, fontSize: 15, fontWeight: "600", color: p.onSurface },
    emptyIcon: { width: 34, height: 34, borderRadius: 11, alignItems: "center", justifyContent: "center" },
    descCard: {
      flexDirection: "row", alignItems: "flex-start", gap: 10,
      backgroundColor: p.card, borderRadius: radius.lg, borderWidth: 1, borderColor: p.border,
      padding: 12, minHeight: 110,
    },
    descIcon: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
    descInput: { flex: 1, minHeight: 84, fontSize: 15, color: p.onSurface, paddingTop: 6, paddingBottom: 6, textAlignVertical: "top" },
    amountCard: {
      flexDirection: "row", alignItems: "center", gap: 12, marginTop: spacing.md,
      backgroundColor: p.card, borderRadius: radius.lg, borderWidth: 1, borderColor: p.border,
      paddingVertical: 14, paddingHorizontal: 16,
    },
    amountText: { fontSize: 34, fontWeight: "800", marginTop: 4 },
    amountHint: { fontSize: 12, fontWeight: "600", color: p.muted, marginTop: 2 },
    backspaceBtn: {
      width: 56, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center",
      backgroundColor: p.card, borderWidth: 1, borderColor: p.border,
    },
    calc: { marginTop: spacing.md, gap: 8 },
    calcRow: { flexDirection: "row", gap: 8 },
    calcKey: {
      flex: 1, height: 54, borderRadius: 16, alignItems: "center", justifyContent: "center",
      backgroundColor: p.card, borderWidth: 1, borderColor: p.border,
    },
    calcKeyText: { fontSize: 22, fontWeight: "700", color: p.onSurface },
    footer: { paddingHorizontal: spacing.lg, paddingTop: 10, backgroundColor: p.bg },
    saveBtn: { padding: 16, borderRadius: radius.pill, alignItems: "center" },
    saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
    sheetTitle: { fontSize: 16, fontWeight: "800", color: p.onSurface, paddingHorizontal: spacing.lg, marginBottom: 12, marginTop: 4 },
    sheetEmpty: { fontSize: 13, color: p.muted, paddingVertical: 12 },
    sheetRow: {
      flexDirection: "row", alignItems: "center", gap: 10, padding: 10,
      backgroundColor: p.card, borderRadius: radius.lg, borderWidth: 1, borderColor: p.border,
    },
    sheetRowText: { flex: 1, minWidth: 0, fontSize: 15, fontWeight: "600", color: p.onSurface },
  };
});
