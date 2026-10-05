import React, { useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency, formatCurrencyInt } from "@/src/format";
import { IconTile } from "@/src/components/ui";

export default function PayDebt() {
  const { colors } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const debtQ = useQuery({ queryKey: ["debt", params.id], queryFn: () => api.getDebt(params.id as string) });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState<string | undefined>();
  const [notes, setNotes] = useState("");

  const d = debtQ.data;
  if (!d) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  const amt = parseFloat(amount) || 0;
  const newBalance = Math.max(0, d.remaining_amount - amt);

  const save = async () => {
    if (!amt) return Alert.alert("Ingresa un monto válido");
    await api.createDebtPayment({ debt_id: d.id, amount: amt, account_id: accountId, notes });
    qc.invalidateQueries();
    router.back();
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140, paddingHorizontal: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Registrar pago</Text>
        </View>

        <View style={styles.debtCard}>
          <Text style={{ color: colors.muted, fontSize: 12 }}>Deuda</Text>
          <Text style={{ fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: 2 }}>{d.name}</Text>
          <Text style={{ fontSize: 13, color: colors.muted, marginTop: 2 }}>
            Pendiente actual: {formatCurrencyInt(d.remaining_amount)}
          </Text>
        </View>

        <Text style={styles.label}>Monto</Text>
        <TextInput
          testID="pay-amount"
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="0.00"
          placeholderTextColor={colors.muted}
          style={[styles.input, { fontSize: 30, fontWeight: "800" }]}
        />

        <Text style={styles.label}>Cuenta</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
          {(accQ.data || []).map((a: any) => (
            <Pressable key={a.id} onPress={() => setAccountId(a.id)} style={[styles.acc, accountId === a.id && { borderColor: a.color, borderWidth: 2 }]}>
              <IconTile icon={a.icon} tint={a.color} size={32} />
              <View style={{ marginLeft: 10 }}>
                <Text style={{ fontWeight: "700", color: colors.onSurface }}>{a.name}</Text>
                <Text style={{ fontSize: 12, color: colors.muted }}>{formatCurrency(a.current_balance)}</Text>
              </View>
            </Pressable>
          ))}
        </ScrollView>

        <Text style={styles.label}>Notas</Text>
        <TextInput value={notes} onChangeText={setNotes} multiline placeholder="Opcional" placeholderTextColor={colors.muted} style={[styles.input, { minHeight: 60 }]} />

        {amt > 0 && (
          <View style={styles.preview}>
            <View style={styles.pRow}><Text style={styles.pLabel}>Saldo anterior</Text><Text style={styles.pVal}>{formatCurrencyInt(d.remaining_amount)}</Text></View>
            <View style={styles.pRow}><Text style={styles.pLabel}>Pago</Text><Text style={[styles.pVal, { color: colors.brandPrimary }]}>-{formatCurrencyInt(amt)}</Text></View>
            <View style={[styles.pRow, { borderTopWidth: 1, borderTopColor: colors.divider, paddingTop: 8, marginTop: 4 }]}>
              <Text style={[styles.pLabel, { fontWeight: "600", color: colors.onSurface }]}>Nuevo saldo</Text>
              <Text style={[styles.pVal, { fontSize: 18 }]}>{formatCurrencyInt(newBalance)}</Text>
            </View>
          </View>
        )}

        <Pressable testID="confirm-pay" onPress={save} style={styles.saveBtn}>
          <Text style={styles.saveText}>Confirmar pago</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  debtCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  acc: { flexDirection: "row", alignItems: "center", padding: 12, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  preview: { marginTop: 20, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  pRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  pLabel: { color: colors.muted, fontWeight: "600" },
  pVal: { color: colors.onSurface, fontWeight: "700" },
  saveBtn: { marginTop: 20, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
