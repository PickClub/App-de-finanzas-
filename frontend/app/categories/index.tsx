import React, { useEffect } from "react";
import { View, ScrollView, Pressable, StyleSheet } from "react-native";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

export default function Categories() {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { guard } = useLock();
  const q = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const cats: any[] = q.data || [];

  // Ensure the default catalog exists (idempotent) if there are no categories.
  const ensuredRef = React.useRef(false);
  useEffect(() => {
    if (q.isSuccess && cats.length === 0 && !ensuredRef.current) {
      ensuredRef.current = true;
      api.initDefaultCategories().then(() => qc.invalidateQueries({ queryKey: ["categories"] })).catch(() => {});
    }
  }, [q.isSuccess, cats.length, qc]);

  const restore = async () => {
    await api.initDefaultCategories();
    qc.invalidateQueries({ queryKey: ["categories"] });
  };

  const expense = cats.filter((c) => c.type === "expense");
  const income = cats.filter((c) => c.type === "income");

  const renderGrid = (list: any[]) => (
    <View style={styles.grid}>
      {list.map((c) => (
        <Pressable
          key={c.id}
          testID={`cat-item-${c.id}`}
          onPress={guard(() => router.push(`/categories/new?id=${c.id}`))}
          style={styles.gridItem}
        >
          <IconTile icon={c.icon} tint={c.color} size={52} />
          <Text style={styles.name}>{c.name}</Text>
        </Pressable>
      ))}
    </View>
  );

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140, paddingHorizontal: spacing.lg }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginBottom: spacing.lg }}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Categorías</Text>
        <LockToggle testID="lock-cats" compact />
        <Pressable testID="add-category" onPress={() => router.push("/categories/new")} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
          <Ionicons name="add" size={22} color="#fff" />
        </Pressable>
      </View>

      {expense.length > 0 && (
        <>
          <View style={styles.sectionHead}>
            <View style={[styles.dot, { backgroundColor: colors.expenseRed }]} />
            <Text style={styles.section}>Gastos</Text>
            <Text style={styles.count}>{expense.length}</Text>
          </View>
          {renderGrid(expense)}
        </>
      )}

      {income.length > 0 && (
        <>
          <View style={[styles.sectionHead, { marginTop: spacing.md }]}>
            <View style={[styles.dot, { backgroundColor: colors.incomeGreen }]} />
            <Text style={styles.section}>Ingresos</Text>
            <Text style={styles.count}>{income.length}</Text>
          </View>
          {renderGrid(income)}
        </>
      )}

      <Pressable testID="restore-categories" onPress={restore} style={styles.restoreBtn}>
        <Ionicons name="refresh-outline" size={18} color={colors.brandPrimary} />
        <Text style={styles.restoreText}>Restaurar predeterminadas</Text>
      </Pressable>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 22, fontWeight: "800", color: colors.onSurface },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  section: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  count: { fontSize: 12, fontWeight: "700", color: colors.muted },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  gridItem: { width: "31%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, paddingVertical: 14, paddingHorizontal: 8, alignItems: "center", borderWidth: 1, borderColor: colors.border, marginBottom: 12 },
  name: { color: colors.onSurface, fontWeight: "700", fontSize: 12, marginTop: 8, textAlign: "center" },
  restoreBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 8, paddingVertical: 14, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  restoreText: { color: colors.brandPrimary, fontWeight: "800", fontSize: 14 },
}));
