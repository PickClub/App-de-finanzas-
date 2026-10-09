import React, { useMemo, useState, useEffect } from "react";
import { View, ScrollView, StyleSheet, Modal, KeyboardAvoidingView, Platform } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { ProgressBar } from "@/src/components/ProgressBar";
import { IconTile } from "@/src/components/ui";

import { us, ufs } from "@/src/ui-scale";
export default function Budgets() {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();

  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [limit, setLimit] = useState("");
  const [categoryId, setCategoryId] = useState<string | undefined>();

  const budgetsQ = useQuery({ queryKey: ["budgets"], queryFn: api.listBudgets });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });

  const cats: any[] = catsQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));

  const budgetsWithProgress = useMemo(() => {
    const now = new Date();
    return (budgetsQ.data || []).map((b: any) => {
      const spent = (txQ.data || [])
        .filter((t: any) => {
          const d = new Date(t.date);
          return (
            t.type === "expense" &&
            t.category_id === b.category_id &&
            d.getMonth() === now.getMonth() &&
            d.getFullYear() === now.getFullYear()
          );
        })
        .reduce((s: number, t: any) => s + t.amount, 0);
      return { ...b, spent };
    });
  }, [budgetsQ.data, txQ.data]);

  const saveBudget = async () => {
    const amt = parseFloat(limit);
    if (!name.trim() || !amt) return;
    await api.createBudget({ name, amount_limit: amt, category_id: categoryId, period: "monthly" });
    qc.invalidateQueries();
    setModalOpen(false);
    setName(""); setLimit(""); setCategoryId(undefined);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Presupuestos</Text>
          <Pressable testID="add-budget" onPress={() => setModalOpen(true)} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
            <Ionicons name="add" size={us(22)} color="#fff" />
          </Pressable>
        </View>

        {budgetsWithProgress.map((b: any) => {
          const cat = catById[b.category_id];
          const p = Math.min(1, b.spent / b.amount_limit);
          const alert = p > 0.85;
          return (
            <View key={b.id} style={styles.card}>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <IconTile icon={cat?.icon || "pie-chart-outline"} tint={cat?.color || colors.brandPrimary} size={us(42)} />
                <View style={{ flex: 1, marginLeft: us(12) }}>
                  <Text style={styles.cardTitle}>{b.name}</Text>
                  <Text style={styles.cardSub}>Mensual · {cat?.name || ""}</Text>
                </View>
                <Text style={{ fontSize: ufs(14), fontWeight: "800", color: alert ? colors.expenseRed : colors.onSurface }}>
                  {formatCurrency(b.spent)} / {formatCurrency(b.amount_limit)}
                </Text>
              </View>
              <View style={{ marginTop: us(12) }}>
                <ProgressBar progress={p} color={alert ? colors.expenseRed : cat?.color || colors.brandPrimary} height={us(10)} />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: us(6) }}>
                <Text style={styles.small}>Disponible: {formatCurrency(Math.max(0, b.amount_limit - b.spent))}</Text>
                <Text style={styles.small}>{Math.round(p * 100)}% usado</Text>
              </View>
            </View>
          );
        })}
      </ScrollView>

      <Modal visible={modalOpen} transparent animationType="slide" onRequestClose={() => setModalOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, justifyContent: "flex-end", backgroundColor: "#00000055" }}>
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <Text style={styles.title}>Nuevo presupuesto</Text>
            <Text style={styles.label}>Nombre</Text>
            <TextInput value={name} onChangeText={setName} placeholder="Ej. Restaurantes" placeholderTextColor={colors.muted} style={styles.input} />
            <Text style={styles.label}>Límite mensual</Text>
            <TextInput value={limit} onChangeText={setLimit} placeholder="0.00" placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={styles.input} />
            <Text style={styles.label}>Categoría</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: us(10) }}>
              {cats.filter((c: any) => c.type === "expense" && !c.is_group).map((c: any) => (
                <Pressable key={c.id} onPress={() => setCategoryId(c.id)} style={[styles.catChip, categoryId === c.id && { borderColor: c.color, borderWidth: 2 }]}>
                  <IconTile icon={c.icon} tint={c.color} size={us(32)} />
                  <Text style={{ fontSize: ufs(11), color: colors.onSurface, fontWeight: "600", marginTop: us(4) }}>{c.name}</Text>
                </Pressable>
              ))}
            </ScrollView>
            <Pressable testID="save-budget" onPress={saveBudget} style={styles.saveBtn}>
              <Text style={styles.saveText}>Guardar</Text>
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, marginBottom: 12 },
  cardTitle: { fontWeight: "800", color: colors.onSurface, fontSize: 15 },
  cardSub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  small: { color: colors.muted, fontSize: 11 },
  sheet: { backgroundColor: colors.surface, padding: spacing.lg, borderTopLeftRadius: radius.cardLg, borderTopRightRadius: radius.cardLg, paddingBottom: 32 },
  sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  catChip: { alignItems: "center", padding: 8, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, minWidth: 76 },
  saveBtn: { marginTop: 20, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
