import React, { useCallback, useState } from "react";
import { View, ScrollView, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt, formatDateTime } from "@/src/format";
import { ProgressBar } from "@/src/components/ProgressBar";
import { ConfirmSheet } from "@/src/components/sheets";
import { FOREST, useMontserrat, statusColor, budgetLabel, pastel, shortDate } from "@/src/budgets/shared";

import { us } from "@/src/ui-scale";

export default function BudgetDetail() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id, y, m } = useLocalSearchParams<{ id: string; y?: string; m?: string }>();
  const now = new Date();
  const year = Number(y) || now.getFullYear();
  const month = Number(m) || now.getMonth() + 1;
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const q = useQuery({ queryKey: ["budget-detail", id, year, month], queryFn: () => api.budgetDetail(id as string, year, month) });
  const { refetch } = q;
  useFocusEffect(useCallback(() => { refetch(); }, [refetch]));

  const b = q.data;
  const cat = b?.category;
  const base = cat?.color || colors.brandPrimary;
  const barColor = b ? statusColor(b.status, base, colors) : base;
  const over = (b?.available ?? 0) < 0;

  const doDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await api.deleteBudget(id as string);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["budgets-overview"] }),
        qc.invalidateQueries({ queryKey: ["budgets"] }),
      ]);
      setConfirmDel(false);
      router.back();
    } catch {
      setDeleting(false);
    }
  };

  const periodText = b
    ? `${t(`budgets.${b.period}`)}${b.window_start ? ` · ${shortDate(b.window_start, i18n.language)} – ${shortDate(b.window_end, i18n.language)}` : ""}`
    : "";

  const InfoRow = ({ icon, label, value, color }: { icon: string; label: string; value: string; color?: string }) => (
    <View style={styles.infoRow}>
      <View style={[styles.infoIcon, { backgroundColor: colors.incomeGreen + "1F" }]}>
        <Ionicons name={icon as any} size={us(16)} color={forest} />
      </View>
      <Text style={styles.infoLbl}>{label}</Text>
      <Text style={[styles.infoVal, color ? { color } : null]} numberOfLines={2}>{value}</Text>
    </View>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(60), paddingHorizontal: us(spacing.lg) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable testID="budget-detail-back" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title} numberOfLines={1}>{t("budgets.detail")}</Text>
        </View>

        {q.isLoading ? (
          <ActivityIndicator color={colors.incomeGreen} style={{ marginTop: us(40) }} />
        ) : !b ? (
          <Text style={styles.muted}>{t("budgets.notFound")}</Text>
        ) : (
          <>
            <View style={styles.hero} testID="budget-detail-hero">
              <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={[styles.catIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(cat?.icon || "pie-chart-outline") as any} size={us(24)} color={base} />
                </View>
                <View style={{ flex: 1, marginLeft: us(12) }}>
                  <Text style={[styles.heroTitle, mont()]} numberOfLines={1}>{budgetLabel(b, cat, i18n.language)}</Text>
                  <View style={[styles.statusPill, { backgroundColor: barColor + "22" }]}>
                    <Text style={[styles.statusText, { color: b.status === "normal" ? forest : barColor }]} testID="budget-detail-status">
                      {b.active ? t(`budgets.status_${b.status}`) : t("budgets.inactive")}
                    </Text>
                  </View>
                </View>
              </View>
              <Text style={styles.heroAmount}>
                <Text style={[styles.heroStrong, mont(true), over && { color: colors.expenseRed }]}>{formatCurrencyInt(b.spent)}</Text>
                {" / "}{formatCurrencyInt(b.amount_limit)}
              </Text>
              <View style={{ marginVertical: us(8) }}>
                <ProgressBar progress={b.amount_limit > 0 ? b.spent / b.amount_limit : 0} color={barColor} height={us(9)} trackColor={base + "1F"} />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={styles.small}>{t("budgets.pctUsed", { pct: Math.round(b.pct ?? 0) })}</Text>
                <Text style={[styles.small, over && { color: colors.expenseRed, fontWeight: "700" }]}>
                  {over ? t("budgets.exceededN", { amount: formatCurrencyInt(-b.available) }) : t("budgets.availableN", { amount: formatCurrencyInt(b.available) })}
                </Text>
              </View>
            </View>

            <View style={styles.card}>
              <InfoRow icon="flag-outline" label={t("budgets.limitConfigured")} value={formatCurrencyInt(b.amount_limit)} />
              <InfoRow icon="trending-down-outline" label={t("budgets.spentAcc")} value={formatCurrencyInt(b.spent)} color={colors.expenseRed} />
              <InfoRow icon="wallet-outline" label={over ? t("budgets.exceededLbl") : t("budgets.availableLbl")} value={formatCurrencyInt(Math.abs(b.available))} color={over ? colors.expenseRed : forest} />
              <InfoRow icon="calendar-outline" label={t("budgets.period")} value={periodText} />
              <InfoRow icon="pulse-outline" label={t("budgets.statusLbl")} value={b.active ? t(`budgets.status_${b.status}`) : t("budgets.inactive")} />
              <InfoRow icon="notifications-outline" label={t("budgets.alertsLbl")} value={b.alerts_enabled === false ? t("budgets.alertsOff") : t("budgets.alertsAt", { pct: b.alert_threshold || 80 })} />
            </View>

            <Text style={[styles.section, mont()]}>{t("budgets.movements")}</Text>
            <View style={styles.card}>
              {(b.transactions || []).length === 0 ? (
                <Text style={[styles.muted, { paddingVertical: us(14) }]}>{t("budgets.noMovements")}</Text>
              ) : (
                b.transactions.map((tx: any, i: number) => (
                  <Pressable
                    key={tx.id}
                    testID={`budget-tx-${tx.id}`}
                    onPress={() => router.push(`/transactions/${tx.id}` as any)}
                    style={[styles.txRow, i < b.transactions.length - 1 && styles.txBorder]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.txName} numberOfLines={1}>{tx.name}</Text>
                      <Text style={styles.small}>{formatDateTime(tx.date)}</Text>
                    </View>
                    <Text style={[styles.txAmt, { color: colors.expenseRed }]}>-{formatCurrencyInt(tx.amount)}</Text>
                    <Ionicons name="chevron-forward" size={us(16)} color={colors.muted} style={{ marginLeft: us(6) }} />
                  </Pressable>
                ))
              )}
            </View>

            <View style={{ flexDirection: "row", gap: us(12), marginTop: us(18) }}>
              <Pressable testID="budget-edit" onPress={() => router.push(`/budgets/new?id=${b.id}` as any)} style={[styles.actionBtn, { backgroundColor: forest }]}>
                <Ionicons name="create-outline" size={us(18)} color="#fff" />
                <Text style={styles.actionText}>{t("common.edit")}</Text>
              </Pressable>
              <Pressable testID="budget-delete" onPress={() => setConfirmDel(true)} style={[styles.actionBtn, { backgroundColor: colors.expenseRed + "1A" }]}>
                <Ionicons name="trash-outline" size={us(18)} color={colors.expenseRed} />
                <Text style={[styles.actionText, { color: colors.expenseRed }]}>{t("common.delete")}</Text>
              </Pressable>
            </View>
          </>
        )}
      </ScrollView>

      <ConfirmSheet
        visible={confirmDel}
        onClose={() => setConfirmDel(false)}
        icon="trash-outline"
        accent={colors.expenseRed}
        title={t("budgets.deleteTitle")}
        description={t("budgets.deleteDesc")}
        confirmLabel={t("common.delete")}
        onConfirm={doDelete}
        destructive
        confirmTestID="confirm-delete-budget"
      />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  muted: { color: colors.muted, fontSize: 13, textAlign: "center" },
  hero: { borderRadius: radius.cardLg, padding: 16, borderWidth: 1, borderColor: colors.border, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  catIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  heroTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  statusPill: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 3, borderRadius: radius.pill, marginTop: 4 },
  statusText: { fontSize: 11.5, fontWeight: "700" },
  heroAmount: { fontSize: 14, color: colors.muted, marginTop: 14 },
  heroStrong: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  small: { fontSize: 11.5, color: colors.muted },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginTop: 12 },
  infoRow: { flexDirection: "row", alignItems: "center", paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: colors.divider },
  infoIcon: { width: 32, height: 32, borderRadius: 10, alignItems: "center", justifyContent: "center", marginRight: 10 },
  infoLbl: { flex: 1, fontSize: 13, color: colors.muted },
  infoVal: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, maxWidth: "55%", textAlign: "right" },
  section: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: 20 },
  txRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12 },
  txBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  txName: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  txAmt: { fontSize: 14, fontWeight: "800" },
  actionBtn: { flex: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", paddingVertical: 14, borderRadius: radius.pill },
  actionText: { color: "#fff", fontWeight: "800", fontSize: 14.5 },
}));
