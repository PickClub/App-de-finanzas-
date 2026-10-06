import React from "react";
import { View, ScrollView, StyleSheet, Alert } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrencyInt, formatDateLong } from "@/src/format";
import { ProgressRing } from "@/src/components/ProgressRing";
import { IconTile } from "@/src/components/ui";

import { us, ufs } from "@/src/ui-scale";
export default function DebtDetail() {
  const { colors } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const debtQ = useQuery({ queryKey: ["debt", params.id], queryFn: () => api.getDebt(params.id as string), enabled: !!params.id });
  const paysQ = useQuery({ queryKey: ["debt-payments", params.id], queryFn: () => api.listDebtPayments(params.id as string), enabled: !!params.id });

  const d = debtQ.data;
  if (!d) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  const progress = d.original_amount > 0 ? d.total_paid / d.original_amount : 0;
  const remove = () => {
    Alert.alert("Eliminar deuda", "¿Estás seguro?", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Eliminar",
        style: "destructive",
        onPress: async () => {
          await api.deleteDebt(d.id);
          qc.invalidateQueries();
          router.back();
        },
      },
    ]);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140) }}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{d.name}</Text>
        <Pressable onPress={remove} style={styles.backBtn}>
          <Ionicons name="trash-outline" size={us(22)} color={colors.expenseRed} />
        </Pressable>
      </View>

      <View style={[styles.hero, { backgroundColor: d.color + "22" }]}>
        <ProgressRing progress={progress} color={d.color} size={us(140)} stroke={us(14)}>
          <View style={{ alignItems: "center" }}>
            <Text style={{ color: colors.muted, fontSize: ufs(12), fontWeight: "600" }}>Pagado</Text>
            <Text style={{ color: colors.onSurface, fontSize: ufs(22), fontWeight: "800" }}>
              {Math.round(progress * 100)}%
            </Text>
          </View>
        </ProgressRing>
        <View style={{ flexDirection: "row", marginTop: us(16), alignItems: "center", gap: us(10) }}>
          <IconTile icon={d.icon} tint={d.color} size={us(36)} />
          <Text style={{ fontSize: ufs(15), color: colors.onSurface, fontWeight: "700" }}>
            {d.direction === "i_owe" ? "Yo debo a " : "Me debe "} {d.person || ""}
          </Text>
        </View>
      </View>

      <View style={styles.cards}>
        <View style={styles.cardCol}>
          <Text style={styles.cardLabel}>Original</Text>
          <Text style={styles.cardVal}>{formatCurrencyInt(d.original_amount)}</Text>
        </View>
        <View style={styles.cardCol}>
          <Text style={styles.cardLabel}>Pendiente</Text>
          <Text style={[styles.cardVal, { color: colors.expenseRed }]}>{formatCurrencyInt(d.remaining_amount)}</Text>
        </View>
        <View style={styles.cardCol}>
          <Text style={styles.cardLabel}>Pagado</Text>
          <Text style={[styles.cardVal, { color: colors.statsPurple }]}>{formatCurrencyInt(d.total_paid)}</Text>
        </View>
      </View>

      <View style={styles.infoCard}>
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Pago mínimo</Text>
          <Text style={styles.infoVal}>{formatCurrencyInt(d.minimum_payment)}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Frecuencia</Text>
          <Text style={styles.infoVal}>{d.payment_frequency}</Text>
        </View>
        <View style={styles.divider} />
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Interés</Text>
          <Text style={styles.infoVal}>{d.interest_rate}%</Text>
        </View>
        {d.due_date && (
          <>
            <View style={styles.divider} />
            <View style={styles.infoRow}>
              <Text style={styles.infoLabel}>Próximo vencimiento</Text>
              <Text style={styles.infoVal}>{formatDateLong(d.due_date)}</Text>
            </View>
          </>
        )}
        <View style={styles.divider} />
        <View style={styles.infoRow}>
          <Text style={styles.infoLabel}>Estado</Text>
          <View style={[styles.badge, { backgroundColor: d.status === "paid" ? colors.incomeGreen + "22" : colors.brandPrimary + "22" }]}>
            <Text style={{ color: d.status === "paid" ? colors.incomeGreen : colors.brandPrimary, fontWeight: "800", fontSize: ufs(12) }}>
              {d.status === "paid" ? "PAGADA ✓" : "ACTIVA"}
            </Text>
          </View>
        </View>
      </View>

      <Pressable
        testID="pay-btn"
        disabled={d.status === "paid"}
        onPress={() => router.push(`/debts/${d.id}/pay`)}
        style={[styles.payBtn, d.status === "paid" && { opacity: 0.5 }]}
      >
        <Ionicons name="add-circle-outline" size={us(22)} color="#fff" />
        <Text style={styles.payText}>Registrar pago</Text>
      </Pressable>

      <View style={{ paddingHorizontal: us(spacing.lg), marginTop: us(spacing.xl) }}>
        <Text style={{ fontSize: ufs(16), fontWeight: "800", color: colors.onSurface, marginBottom: us(10) }}>Historial de pagos</Text>
        <View style={styles.historyCard}>
          {(paysQ.data || []).map((p: any) => (
            <View key={p.id} style={styles.histRow}>
              <Ionicons name="checkmark-circle" size={us(22)} color={colors.incomeGreen} />
              <View style={{ flex: 1, marginLeft: us(10) }}>
                <Text style={{ fontWeight: "700", color: colors.onSurface }}>{formatCurrencyInt(p.amount)}</Text>
                <Text style={{ color: colors.muted, fontSize: ufs(12) }}>{formatDateLong(p.date)}</Text>
              </View>
            </View>
          ))}
          {(!paysQ.data || paysQ.data.length === 0) && (
            <Text style={{ color: colors.muted, textAlign: "center", padding: us(16) }}>Sin pagos registrados</Text>
          )}
        </View>
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "700", color: colors.onSurface, letterSpacing: -0.3 },
  hero: { marginHorizontal: spacing.lg, borderRadius: radius.cardLg, padding: spacing.xl, alignItems: "center" },
  cards: { flexDirection: "row", paddingHorizontal: spacing.lg, marginTop: spacing.md, gap: 10 },
  cardCol: {
    flex: 1,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  cardLabel: { fontSize: 12, color: colors.muted, fontWeight: "400" },
  cardVal: { fontSize: 17, fontWeight: "600", color: colors.onSurface, marginTop: 4, letterSpacing: -0.3 },
  infoCard: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  infoRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8 },
  infoLabel: { color: colors.muted, fontWeight: "400", fontSize: 13 },
  infoVal: { color: colors.onSurface, fontWeight: "600", fontSize: 13 },
  divider: { height: 1, backgroundColor: colors.divider },
  badge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill },
  payBtn: { flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", marginHorizontal: spacing.lg, marginTop: spacing.lg, padding: 16, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  payText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  historyCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  histRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10 },
}));
