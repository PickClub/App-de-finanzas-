import React, { useState } from "react";
import { View, Text, TextInput, ScrollView, Pressable, StyleSheet, Alert, KeyboardAvoidingView, Platform } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";

const COLORS = ["#F5B83B", "#FF654A", "#D95345", "#4C83EA", "#8F5BE8", "#29C4A9", "#2FA47C"];
const ICONS = ["cash-outline", "card-outline", "car-outline", "home-outline", "person-outline", "briefcase-outline", "gift-outline"];
const FREQ = [
  { id: "weekly", label: "Semanal" },
  { id: "biweekly", label: "Quincenal" },
  { id: "monthly", label: "Mensual" },
  { id: "none", label: "Sin frecuencia" },
];

export default function NewDebt() {
  const { colors } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ direction?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const [direction, setDirection] = useState<string>(params.direction || "");
  const [step2, setStep2] = useState(!!params.direction);
  const [name, setName] = useState("");
  const [person, setPerson] = useState("");
  const [amount, setAmount] = useState("");
  const [minPay, setMinPay] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [interest, setInterest] = useState("");
  const [notes, setNotes] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const [icon, setIcon] = useState(ICONS[0]);

  const save = async () => {
    const amt = parseFloat(amount);
    if (!name.trim() || !amt) return Alert.alert("Completa nombre y monto");
    await api.createDebt({
      name,
      direction,
      person,
      original_amount: amt,
      minimum_payment: parseFloat(minPay) || 0,
      payment_frequency: frequency,
      interest_rate: parseFloat(interest) || 0,
      notes,
      color,
      icon,
    });
    qc.invalidateQueries();
    // Reuse the existing list; replace only when opened directly from Home.
    router.dismissTo("/debts");
  };

  if (!step2) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top + 8 }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Nueva deuda</Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={{ padding: spacing.lg, flex: 1, justifyContent: "center" }}>
          <Text style={{ fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center" }}>
            ¿Qué tipo de deuda quieres registrar?
          </Text>
          <View style={{ gap: 14, marginTop: 30 }}>
            <Pressable testID="dir-i-owe" onPress={() => { setDirection("i_owe"); setStep2(true); }} style={[styles.bigBtn, { backgroundColor: colors.expenseRed }]}>
              <Ionicons name="arrow-down-outline" size={26} color="#fff" />
              <Text style={styles.bigBtnText}>Yo debo</Text>
            </Pressable>
            <Pressable testID="dir-they-owe" onPress={() => { setDirection("they_owe"); setStep2(true); }} style={[styles.bigBtn, { backgroundColor: colors.incomeGreen }]}>
              <Ionicons name="arrow-up-outline" size={26} color="#fff" />
              <Text style={styles.bigBtnText}>Me deben</Text>
            </Pressable>
          </View>
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140, paddingHorizontal: spacing.lg }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>{direction === "i_owe" ? "Yo debo" : "Me deben"}</Text>
          <View style={{ width: 40 }} />
        </View>

        <Text style={styles.label}>Nombre</Text>
        <TextInput value={name} onChangeText={setName} placeholder="Ej. Tarjeta Chase" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>{direction === "i_owe" ? "A quién debo" : "Quién me debe"}</Text>
        <TextInput value={person} onChangeText={setPerson} placeholder="Nombre" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Monto</Text>
        <TextInput value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} style={[styles.input, { fontSize: 22, fontWeight: "800" }]} />

        <Text style={styles.label}>Pago mínimo</Text>
        <TextInput value={minPay} onChangeText={setMinPay} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Frecuencia</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {FREQ.map((f) => (
            <Pressable key={f.id} onPress={() => setFrequency(f.id)} style={[styles.freqChip, frequency === f.id && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]}>
              <Text style={{ color: frequency === f.id ? "#fff" : colors.onSurface, fontWeight: "700", fontSize: 12 }}>{f.label}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Interés (%) opcional</Text>
        <TextInput value={interest} onChangeText={setInterest} keyboardType="decimal-pad" placeholder="0" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Icono</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          {ICONS.map((ic) => (
            <Pressable key={ic} onPress={() => setIcon(ic)} style={[styles.iconOpt, icon === ic && { borderColor: color, borderWidth: 2 }]}>
              <IconTile icon={ic} tint={color} size={34} />
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Color</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          {COLORS.map((c) => (
            <Pressable key={c} onPress={() => setColor(c)} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: c, borderWidth: color === c ? 3 : 0, borderColor: colors.onSurface }} />
          ))}
        </View>

        <Text style={styles.label}>Notas</Text>
        <TextInput value={notes} onChangeText={setNotes} multiline placeholder="Opcional" placeholderTextColor={colors.muted} style={[styles.input, { minHeight: 60 }]} />

        <Pressable testID="save-debt" onPress={save} style={styles.saveBtn}>
          <Text style={styles.saveText}>Guardar deuda</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors) => ({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  bigBtn: { flexDirection: "row", padding: 22, borderRadius: radius.cardLg, alignItems: "center", justifyContent: "center", gap: 12 },
  bigBtnText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  freqChip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  iconOpt: { padding: 4, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  saveBtn: { marginTop: 28, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
