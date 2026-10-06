import React, { useState } from "react";
import { View, ScrollView, StyleSheet, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing } from "react-native-reanimated";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";

import { us, ufs } from "@/src/ui-scale";
const COLORS = ["#F5B83B", "#FF654A", "#D95345", "#4C83EA", "#8F5BE8", "#29C4A9", "#2FA47C"];
const ICONS = ["cash-outline", "card-outline", "car-outline", "home-outline", "person-outline", "briefcase-outline", "gift-outline"];
const FREQ = [
  { id: "weekly", label: "Semanal" },
  { id: "biweekly", label: "Quincenal" },
  { id: "monthly", label: "Mensual" },
  { id: "none", label: "Sin frecuencia" },
];

// Visual-only selection card used on the first step of "Nueva deuda".
// It is fully pressable and runs a light 1 -> 0.96 -> 1 scale response, then
// calls the SAME handler the old big button used (no logic/route change).
function SelectCard({
  testID,
  title,
  subtitle,
  arrowIcon,
  accent,
  circleBg,
  bandBg,
  styles,
  onPress,
}: {
  testID: string;
  title: string;
  subtitle: string;
  arrowIcon: string;
  accent: string;
  circleBg: string;
  bandBg: string;
  styles: any;
  onPress: () => void;
}) {
  const scale = useSharedValue(1);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      onPressIn={() => {
        scale.value = withTiming(0.96, { duration: 90, easing: Easing.out(Easing.quad) });
      }}
      onPressOut={() => {
        scale.value = withTiming(1, { duration: 140, easing: Easing.out(Easing.quad) });
      }}
      style={{ flex: 1 }}
    >
      <Animated.View style={[styles.selCard, aStyle]}>
        <View style={[styles.selBand, { backgroundColor: bandBg }]} pointerEvents="none" />
        <Ionicons name="wallet-outline" size={us(58)} color={accent} style={styles.selBandIcon} />
        <View style={[styles.selCircle, { backgroundColor: circleBg }]}>
          <Ionicons name={arrowIcon as any} size={us(28)} color={accent} />
        </View>
        <Text style={styles.selCardTitle}>{title}</Text>
        <Text style={styles.selCardSub}>{subtitle}</Text>
      </Animated.View>
    </Pressable>
  );
}

export default function NewDebt() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ direction?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  // Forest green accent, consistent with Home (hardcoded brand green on light,
  // brightened green on dark). Used only for the decorative selection screen.
  const forest = scheme === "dark" ? colors.incomeGreen : "#126046";

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
      <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top + us(8) }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Nueva deuda</Text>
          <View style={{ width: us(40) }} />
        </View>
        <View style={styles.selWrap}>
          <View style={[styles.selIconTile, { backgroundColor: colors.incomeGreen + "1A" }]}>
            <Ionicons name="wallet-outline" size={us(28)} color={forest} />
          </View>
          <Text style={styles.selHeading}>¿Qué quieres registrar?</Text>
          <Text style={styles.selSubheading}>Selecciona el tipo de deuda</Text>
          <View style={styles.selRow}>
            <SelectCard
              testID="dir-i-owe"
              title="Yo debo"
              subtitle={"Dinero que debo\npagar"}
              arrowIcon="arrow-down"
              accent={colors.expenseRed}
              circleBg={colors.expenseRed + "1A"}
              bandBg={colors.expenseRed + "0F"}
              styles={styles}
              onPress={() => { setDirection("i_owe"); setStep2(true); }}
            />
            <SelectCard
              testID="dir-they-owe"
              title="Me deben"
              subtitle={"Dinero por\ncobrar"}
              arrowIcon="arrow-up"
              accent={forest}
              circleBg={colors.incomeGreen + "1A"}
              bandBg={colors.incomeGreen + "0F"}
              styles={styles}
              onPress={() => { setDirection("they_owe"); setStep2(true); }}
            />
          </View>
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>{direction === "i_owe" ? "Yo debo" : "Me deben"}</Text>
          <View style={{ width: us(40) }} />
        </View>

        <Text style={styles.label}>Nombre</Text>
        <TextInput value={name} onChangeText={setName} placeholder="Ej. Tarjeta Chase" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>{direction === "i_owe" ? "A quién debo" : "Quién me debe"}</Text>
        <TextInput value={person} onChangeText={setPerson} placeholder="Nombre" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Monto</Text>
        <TextInput value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} style={[styles.input, { fontSize: ufs(22), fontWeight: "800" }]} />

        <Text style={styles.label}>Pago mínimo</Text>
        <TextInput value={minPay} onChangeText={setMinPay} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Frecuencia</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(8) }}>
          {FREQ.map((f) => (
            <Pressable key={f.id} onPress={() => setFrequency(f.id)} style={[styles.freqChip, frequency === f.id && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]}>
              <Text style={{ color: frequency === f.id ? "#fff" : colors.onSurface, fontWeight: "700", fontSize: ufs(12) }}>{f.label}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Interés (%) opcional</Text>
        <TextInput value={interest} onChangeText={setInterest} keyboardType="decimal-pad" placeholder="0" placeholderTextColor={colors.muted} style={styles.input} />

        <Text style={styles.label}>Icono</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(10) }}>
          {ICONS.map((ic) => (
            <Pressable key={ic} onPress={() => setIcon(ic)} style={[styles.iconOpt, icon === ic && { borderColor: color, borderWidth: 2 }]}>
              <IconTile icon={ic} tint={color} size={us(34)} />
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Color</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(10) }}>
          {COLORS.map((c) => (
            <Pressable key={c} onPress={() => setColor(c)} style={{ width: us(40), height: us(40), borderRadius: us(20), backgroundColor: c, borderWidth: color === c ? us(3) : 0, borderColor: colors.onSurface }} />
          ))}
        </View>

        <Text style={styles.label}>Notas</Text>
        <TextInput value={notes} onChangeText={setNotes} multiline placeholder="Opcional" placeholderTextColor={colors.muted} style={[styles.input, { minHeight: us(60) }]} />

        <Pressable testID="save-debt" onPress={save} style={styles.saveBtn}>
          <Text style={styles.saveText}>Guardar deuda</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  // --- First step: debt-type selection (visual redesign) ---
  selWrap: { paddingHorizontal: spacing.lg, flex: 1, justifyContent: "center", paddingBottom: 48 },
  selIconTile: { alignSelf: "center", width: 60, height: 60, borderRadius: 18, alignItems: "center", justifyContent: "center", marginBottom: 18 },
  selHeading: { fontSize: 24, fontWeight: "800", color: colors.onSurface, textAlign: "center", letterSpacing: -0.5 },
  selSubheading: { fontSize: 14, color: colors.muted, textAlign: "center", marginTop: 6, fontWeight: "500" },
  selRow: { flexDirection: "row", gap: 14, marginTop: 28 },
  selCard: {
    flex: 1,
    minHeight: 208,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingTop: 26,
    paddingHorizontal: 14,
    alignItems: "center",
    overflow: "hidden",
    ...Platform.select({
      ios: { shadowColor: "#000", shadowOpacity: scheme === "dark" ? 0.25 : 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 2 },
      default: {},
    }),
  },
  selBand: { position: "absolute", left: 0, right: 0, bottom: 0, height: 92, borderTopLeftRadius: 78, borderTopRightRadius: 14 },
  selBandIcon: { position: "absolute", right: 8, bottom: 6, opacity: scheme === "dark" ? 0.14 : 0.1 },
  selCircle: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 16 },
  selCardTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  selCardSub: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 6, fontWeight: "500", lineHeight: 18 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  freqChip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  iconOpt: { padding: 4, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  saveBtn: { marginTop: 28, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
