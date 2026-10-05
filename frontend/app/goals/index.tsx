import React, { useState } from "react";
import { View, ScrollView, Pressable, StyleSheet, Modal, KeyboardAvoidingView, Platform } from "react-native";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";
import { IconTile } from "@/src/components/ui";

const COLORS = ["#29C4A9", "#4C83EA", "#FF654A", "#F5B83B", "#8F5BE8", "#2FA47C"];
const ICONS = ["flag-outline", "desktop-outline", "airplane-outline", "shield-checkmark-outline", "car-outline", "home-outline", "gift-outline", "school-outline"];

export default function Goals() {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["goals"], queryFn: api.listGoals });
  const goals: any[] = q.data || [];

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [current, setCurrent] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const [icon, setIcon] = useState(ICONS[0]);

  const save = async () => {
    if (!name.trim() || !parseFloat(target)) return;
    await api.createGoal({ name, target_amount: parseFloat(target), current_amount: parseFloat(current) || 0, color, icon, priority: "medium" });
    qc.invalidateQueries();
    setOpen(false); setName(""); setTarget(""); setCurrent("");
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140, paddingHorizontal: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Metas de ahorro</Text>
          <Pressable testID="add-goal" onPress={() => setOpen(true)} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={22} color="#fff" />
          </Pressable>
        </View>

        <View style={styles.grid}>
          {goals.map((g) => {
            const p = Math.min(1, g.current_amount / g.target_amount);
            return (
              <View key={g.id} style={styles.card}>
                <ProgressRing progress={p} color={g.color} size={90} stroke={10}>
                  <View style={{ alignItems: "center" }}>
                    <IconTile icon={g.icon} tint={g.color} size={36} />
                  </View>
                </ProgressRing>
                <Text style={styles.name}>{g.name}</Text>
                <Text style={styles.amt}>{formatCurrency(g.current_amount)}</Text>
                <Text style={styles.of}>de {formatCurrency(g.target_amount)}</Text>
                <Text style={{ color: g.color, fontWeight: "800", marginTop: 4 }}>{Math.round(p * 100)}%</Text>
              </View>
            );
          })}
        </View>
      </ScrollView>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, justifyContent: "flex-end", backgroundColor: "#00000055" }}>
          <ScrollView style={styles.sheet} contentContainerStyle={{ paddingBottom: 40 }}>
            <View style={styles.sheetHandle} />
            <Text style={styles.title}>Nueva meta</Text>
            <Text style={styles.label}>Nombre</Text>
            <TextInput value={name} onChangeText={setName} placeholder="Ej. PC nueva" placeholderTextColor={colors.muted} style={styles.input} />
            <Text style={styles.label}>Objetivo</Text>
            <TextInput value={target} onChangeText={setTarget} placeholder="0.00" placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={styles.input} />
            <Text style={styles.label}>Ya ahorrado</Text>
            <TextInput value={current} onChangeText={setCurrent} placeholder="0.00" placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={styles.input} />
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
            <Pressable testID="save-goal" onPress={save} style={styles.saveBtn}>
              <Text style={styles.saveText}>Guardar</Text>
            </Pressable>
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  card: { width: "48%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, padding: spacing.md, alignItems: "center", borderWidth: 1, borderColor: colors.border, marginBottom: 12 },
  name: { fontSize: 14, fontWeight: "800", color: colors.onSurface, marginTop: 10, textAlign: "center" },
  amt: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: 6 },
  of: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sheet: { backgroundColor: colors.surface, padding: spacing.lg, borderTopLeftRadius: radius.cardLg, borderTopRightRadius: radius.cardLg, maxHeight: "88%" },
  sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  iconOpt: { padding: 4, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  saveBtn: { marginTop: 20, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
