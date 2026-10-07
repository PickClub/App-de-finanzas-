import React, { useEffect, useState } from "react";
import { View, ScrollView, StyleSheet, KeyboardAvoidingView, Platform, Alert } from "react-native";
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
import { ConfirmSheet } from "@/src/components/sheets";

import { us } from "@/src/ui-scale";
const TYPE_LABEL: Record<string, string> = {
  income: "Ingreso",
  expense: "Gasto",
  transfer: "Transferencia",
  debt_payment: "Pago de deuda",
};

export default function NewTransaction() {
  const { colors } = useTheme();
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
  const [notes, setNotes] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);

  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const cats = (catQ.data || []).filter((c: any) => (type === "income" ? c.type === "income" : c.type === "expense"));

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

  const save = async () => {
    if (deletion.locked.current || (params.id && !resourceLoaded)) return;
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      Alert.alert("Falta información", "Ingresa un monto válido");
      return;
    }
    const finalName = name.trim() || "Sin descripción";
    const payload: any = {
      name: finalName,
      amount: amt,
      type,
      category_id: categoryId,
      account_id: accountId,
      to_account_id: type === "transfer" ? toAccountId : undefined,
      notes,
    };
    try {
      if (params.id) await api.updateTransaction(params.id as string, payload);
      else await api.createTransaction(payload);
      qc.invalidateQueries();
      router.back();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  };

  const remove = async () => {
    if (!params.id) return;
    await deletion.remove(() => api.deleteTransaction(params.id as string));
  };

  if (params.id && (!resourceLoaded || deletion.deleted.current)) return <View />;

  return (
    <KeyboardAvoidingView
      pointerEvents={deletion.busy ? "none" : "auto"}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={{ flex: 1, backgroundColor: colors.surface }}
    >
      <View style={[styles.header, { paddingTop: insets.top + us(8) }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{params.id ? "Editar" : "Nuevo"} movimiento</Text>
        {params.id && (
          <Pressable testID="delete-tx" disabled={deletion.busy} onPress={() => { if (!deletion.locked.current) setConfirmDel(true); }} style={styles.backBtn}>
            <Ionicons name="trash-outline" size={us(22)} color={colors.expenseRed} />
          </Pressable>
        )}
      </View>

      <ScrollView contentContainerStyle={{ padding: us(spacing.lg), paddingBottom: us(160) }}>
        {/* type selector */}
        <View style={styles.typeRow}>
          {["expense", "income", "transfer"].map((tp) => (
            <Pressable
              key={tp}
              testID={`type-${tp}`}
              onPress={() => setType(tp)}
              style={[styles.typeBtn, type === tp && styles.typeBtnActive]}
            >
              <Text style={[styles.typeBtnText, type === tp && { color: "#fff" }]}>{TYPE_LABEL[tp]}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Monto</Text>
        <TextInput
          testID="amount-input"
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="0.00"
          placeholderTextColor={colors.muted}
          style={styles.amountInput}
        />

        <Text style={styles.label}>Descripción</Text>
        <TextInput
          testID="name-input"
          value={name}
          onChangeText={setName}
          placeholder="Ej. Supermercado"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />

        {type !== "transfer" && (
          <>
            <Text style={styles.label}>Categoría</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: us(10), paddingVertical: us(4) }}>
              {cats.map((c: any) => (
                <Pressable
                  key={c.id}
                  testID={`cat-${c.id}`}
                  onPress={() => setCategoryId(c.id)}
                  style={[styles.catChip, categoryId === c.id && { borderColor: c.color, borderWidth: 2 }]}
                >
                  <IconTile icon={c.icon} tint={c.color} size={us(36)} />
                  <Text style={styles.catText}>{c.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </>
        )}

        <Text style={styles.label}>{type === "transfer" ? "Desde cuenta" : "Cuenta"}</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: us(10), paddingVertical: us(4) }}>
          {(accQ.data || []).map((a: any) => (
            <Pressable
              key={a.id}
              testID={`acc-${a.id}`}
              onPress={() => setAccountId(a.id)}
              style={[styles.accChip, accountId === a.id && { borderColor: a.color, borderWidth: 2 }]}
            >
              <IconTile icon={a.icon} tint={a.color} size={us(30)} />
              <Text style={styles.catText}>{a.name}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {type === "transfer" && (
          <>
            <Text style={styles.label}>Hacia cuenta</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: us(10), paddingVertical: us(4) }}>
              {(accQ.data || []).map((a: any) => (
                <Pressable
                  key={a.id}
                  onPress={() => setToAccountId(a.id)}
                  style={[styles.accChip, toAccountId === a.id && { borderColor: a.color, borderWidth: 2 }]}
                >
                  <IconTile icon={a.icon} tint={a.color} size={us(30)} />
                  <Text style={styles.catText}>{a.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </>
        )}

        <Text style={styles.label}>Notas</Text>
        <TextInput
          value={notes}
          onChangeText={setNotes}
          placeholder="Opcional"
          placeholderTextColor={colors.muted}
          style={[styles.input, { minHeight: us(60) }]}
          multiline
        />

        <Pressable testID="save-tx" onPress={save} style={styles.saveBtn}>
          <Text style={styles.saveText}>Guardar</Text>
        </Pressable>
      </ScrollView>

      <ConfirmSheet
        visible={confirmDel}
        onClose={() => setConfirmDel(false)}
        icon="trash-outline"
        accent={colors.expenseRed}
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

const useStyles = makeStyles((colors) => ({
  header: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md, gap: 12,
  },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  typeRow: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, padding: 4, marginBottom: spacing.lg, borderWidth: 1, borderColor: colors.border },
  typeBtn: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: radius.pill },
  typeBtnActive: { backgroundColor: colors.brandPrimary },
  typeBtnText: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  amountInput: {
    fontSize: 34, fontWeight: "800", color: colors.onSurface,
    backgroundColor: colors.surfaceSecondary, padding: 16, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  input: {
    fontSize: 15, color: colors.onSurface,
    backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  catChip: {
    alignItems: "center", backgroundColor: colors.surfaceSecondary,
    padding: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    minWidth: 84,
  },
  accChip: {
    alignItems: "center", flexDirection: "row", gap: 8,
    backgroundColor: colors.surfaceSecondary,
    padding: 10, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  catText: { fontSize: 12, color: colors.onSurface, fontWeight: "600", marginTop: 4 },
  saveBtn: {
    marginTop: 28,
    backgroundColor: colors.brandPrimary,
    padding: 16,
    borderRadius: radius.pill,
    alignItems: "center",
  },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
