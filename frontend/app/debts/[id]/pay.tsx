import React, { useRef, useState } from "react";
import { View, ScrollView, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency, formatCurrencyInt } from "@/src/format";
import { IconTile } from "@/src/components/ui";
import { AppSheet } from "@/src/components/sheets";

import { us } from "@/src/ui-scale";

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
  const { colors, scheme } = useTheme();
  const pal = payPalette(colors, scheme);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
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
  if (!d) return <View style={{ flex: 1, backgroundColor: pal.bg }} />;

  const amt = parseFloat(amount) || 0;
  const newBalance = Math.max(0, d.remaining_amount - amt);

  const save = async () => {
    if (!amt) return Alert.alert("Ingresa un monto válido");
    if (savingRef.current) return; // ignore double taps while the request is in flight
    savingRef.current = true;
    setSaving(true);
    try {
      await api.createDebtPayment({ debt_id: d.id, amount: amt, account_id: accountId, notes });
      qc.invalidateQueries();
      router.back();
    } catch (error) {
      // Keep the entered data so the user can retry.
      Alert.alert("No se pudo registrar el pago", error instanceof Error ? error.message : "Inténtalo de nuevo.");
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
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40), paddingHorizontal: us(spacing.lg) }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={[styles.circleBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
            <Ionicons name="chevron-back" size={us(24)} color={pal.forest} />
          </Pressable>
          <Text style={[styles.title, { color: pal.dark ? pal.onSurface : pal.forest }]}>Registrar pago</Text>
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
              <Text style={[styles.statusText, { color: isPaid ? pal.forest : pal.coral }]}>{isPaid ? "PAGADA" : "ACTIVA"}</Text>
            </View>
          </View>
          <View style={[styles.hDivider, { backgroundColor: pal.divider }]} />
          <View style={styles.pendRow}>
            <Text style={[styles.pendLabel, { color: pal.muted }]}>Pendiente actual</Text>
            <Text style={[styles.pendVal, { color: pal.forest }]}>{formatCurrencyInt(d.remaining_amount)}</Text>
          </View>
        </View>

        {/* Monto */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>Monto del pago</Text>
          <View style={[styles.amountBox, { backgroundColor: pal.field, borderColor: pal.border }]}>
            <Text style={[styles.amountText, { color: pal.forest }]}>$</Text>
            <TextInput
              testID="pay-amount"
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              placeholder="0.00"
              placeholderTextColor={pal.forest + "88"}
              style={[styles.amountText, styles.amountInput, { color: pal.forest }]}
            />
          </View>
          {amt > 0 && (
            <View style={[styles.preview, { borderTopColor: pal.divider }]}>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.muted }]}>Saldo anterior</Text><Text style={[styles.pVal, { color: pal.onSurface }]}>{formatCurrencyInt(d.remaining_amount)}</Text></View>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.muted }]}>Pago</Text><Text style={[styles.pVal, { color: pal.coral }]}>-{formatCurrencyInt(amt)}</Text></View>
              <View style={styles.pRow}><Text style={[styles.pLabel, { color: pal.onSurface, fontWeight: "700" }]}>Nuevo saldo</Text><Text style={[styles.pVal, { color: pal.forest, fontSize: 16 }]}>{formatCurrencyInt(newBalance)}</Text></View>
            </View>
          )}
        </View>

        {/* Cuenta de origen */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>Cuenta de origen</Text>
          <Pressable
            testID="pay-account-select"
            onPress={() => setPickerOpen(true)}
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
                {selected ? selected.name : "Seleccionar cuenta"}
              </Text>
              {selected && <Text style={[styles.selBal, { color: pal.muted }]}>{formatCurrency(selected.current_balance)}</Text>}
            </View>
            <Ionicons name="chevron-down" size={us(20)} color={pal.muted} />
          </Pressable>
        </View>

        {/* Notas */}
        <View style={cardStyle}>
          <Text style={[styles.label, { color: pal.muted }]}>Notas (opcional)</Text>
          <TextInput
            value={notes}
            onChangeText={setNotes}
            multiline
            placeholder="Agregar una descripción del pago..."
            placeholderTextColor={pal.muted}
            style={[styles.notes, { backgroundColor: pal.field, borderColor: pal.border, color: pal.onSurface }]}
          />
        </View>

        <Pressable
          testID="confirm-pay"
          onPress={save}
          disabled={saving}
          style={[styles.saveBtn, { backgroundColor: pal.forest, opacity: saving ? 0.7 : 1 }, shadow]}
        >
          <Text style={[styles.saveText, { color: pal.dark ? colors.onSuccess : "#fff" }]}>Confirmar pago</Text>
        </Pressable>
      </ScrollView>

      <AppSheet visible={pickerOpen} onClose={() => setPickerOpen(false)} testID="pay-account-sheet">
        <Text style={[styles.sheetTitle, { color: pal.dark ? pal.onSurface : pal.forest }]}>Cuenta de origen</Text>
        <ScrollView style={{ maxHeight: us(420) }} contentContainerStyle={{ paddingHorizontal: us(spacing.lg), gap: us(8), paddingBottom: us(4) }}>
          {accounts.length === 0 ? (
            <Text style={[styles.sheetEmpty, { color: pal.muted }]}>No hay cuentas disponibles</Text>
          ) : (
            accounts.map((a: any) => {
              const sel = accountId === a.id;
              return (
                <Pressable
                  key={a.id}
                  testID={`pay-acc-${a.id}`}
                  onPress={() => { setAccountId(a.id); setPickerOpen(false); }}
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
