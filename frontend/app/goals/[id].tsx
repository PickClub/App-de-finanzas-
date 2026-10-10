import React, { useCallback, useState } from "react";
import { View, ScrollView, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt, formatDateTime } from "@/src/format";
import { ProgressBar } from "@/src/components/ProgressBar";
import { ConfirmSheet } from "@/src/components/sheets";
import { FOREST, useMontserrat, pastel, deepen, safeHex, longDate } from "@/src/goals/shared";

import { us } from "@/src/ui-scale";

const PAGE = 20;

export default function GoalDetail() {
  const { colors, scheme } = useTheme();
  const isDark = scheme === "dark";
  const forest = isDark ? colors.incomeGreen : FOREST;
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { t, i18n } = useTranslation();
  const mont = useMontserrat();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const q = useQuery({ queryKey: ["goal-detail", id], queryFn: () => api.getGoal(id as string) });
  const hist = useInfiniteQuery({
    queryKey: ["goal-contribs", id],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => api.listGoalContributions(id as string, pageParam as number, PAGE),
    getNextPageParam: (last: any) => (last?.has_more ? last.offset + last.limit : undefined),
  });
  const { refetch } = q;
  const refetchHist = hist.refetch;
  useFocusEffect(useCallback(() => { refetch(); refetchHist(); }, [refetch, refetchHist]));

  const g = q.data;
  const items: any[] = (hist.data?.pages || []).flatMap((p: any) => p.items || []);
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const accName = (aid?: string | null) => (accountsQ.data || []).find((a: any) => a.id === aid)?.name;

  const base = safeHex(g?.color);
  const strong = deepen(base, isDark);

  const doDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await api.deleteGoal(id as string);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["goals-overview"] }),
        qc.invalidateQueries({ queryKey: ["goals"] }),
      ]);
      qc.removeQueries({ queryKey: ["goal-detail", id] });
      setConfirmDel(false);
      router.back();
    } catch {
      setDeleting(false);
    }
  };

  const InfoRow = ({ icon, label, value, color, testID }: { icon: string; label: string; value: string; color?: string; testID?: string }) => (
    <View style={styles.infoRow}>
      <View style={[styles.infoIcon, { backgroundColor: base + "1F" }]}>
        <Ionicons name={icon as any} size={us(16)} color={strong} />
      </View>
      <Text style={styles.infoLbl}>{label}</Text>
      <Text style={[styles.infoVal, color ? { color } : null]} numberOfLines={2} testID={testID}>{value}</Text>
    </View>
  );

  const recommendedText = !g ? "" : g.completed
    ? t("goals.reached")
    : g.overdue ? t("goals.overdue")
    : g.monthly_recommended ? t("goals.recommendedVal", { amount: formatCurrencyInt(g.monthly_recommended) }) : "—";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(60), paddingHorizontal: us(spacing.lg) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable testID="goal-detail-back" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title} numberOfLines={1}>{t("goals.detail")}</Text>
        </View>

        {q.isLoading ? (
          <ActivityIndicator color={colors.incomeGreen} style={{ marginTop: us(40) }} />
        ) : !g ? (
          <Text style={styles.muted}>{t("goals.notFound")}</Text>
        ) : (
          <>
            <View style={styles.hero} testID="goal-detail-hero">
              <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={[styles.heroIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(g.icon || "flag") as any} size={us(26)} color={strong} />
                </View>
                <View style={{ flex: 1, marginLeft: us(12) }}>
                  <Text style={[styles.heroTitle, mont()]} numberOfLines={1}>{g.name}</Text>
                  <View style={[styles.statusPill, { backgroundColor: (g.completed ? colors.brandSecondary : base) + "26" }]}>
                    {g.completed ? <Ionicons name="trophy" size={us(12)} color={deepen(colors.brandSecondary, isDark, 0.1)} /> : null}
                    <Text style={[styles.statusText, { color: g.completed ? deepen(colors.brandSecondary, isDark, 0.1) : strong }]} testID="goal-detail-status">
                      {g.completed ? t("goals.completedBadge") : t("goals.inProgress")}
                    </Text>
                  </View>
                </View>
              </View>
              <View style={styles.heroAmountRow}>
                <Text style={styles.heroAmount}>
                  <Text style={[styles.heroStrong, mont(true), { color: strong }]} testID="goal-detail-saved">{formatCurrencyInt(g.current_amount)}</Text>
                  {" / "}{formatCurrencyInt(g.target_amount)}
                </Text>
                <Text style={styles.heroPct} testID="goal-detail-pct">{Math.floor(g.pct ?? 0)}%</Text>
              </View>
              <View style={{ marginVertical: us(8) }}>
                <ProgressBar progress={(g.pct ?? 0) / 100} color={base} height={us(10)} trackColor={base + "26"} />
              </View>
              <Text style={styles.small}>{t("goals.remainingN", { amount: formatCurrencyInt(g.remaining) })}</Text>
            </View>

            <View style={{ flexDirection: "row", gap: us(10), marginTop: us(12) }}>
              <Pressable
                testID="goal-detail-add"
                onPress={() => router.push(`/goals/contribute?id=${g.id}&kind=deposit` as any)}
                style={({ pressed }) => [styles.actionBtn, { backgroundColor: colors.brandPrimary }, pressed && { opacity: 0.8 }]}
              >
                <Ionicons name="add" size={us(18)} color="#fff" />
                <Text style={styles.actionText}>{t("goals.addSaving")}</Text>
              </Pressable>
              <Pressable
                testID="goal-detail-withdraw"
                disabled={g.current_amount <= 0}
                onPress={() => router.push(`/goals/contribute?id=${g.id}&kind=withdrawal` as any)}
                style={({ pressed }) => [styles.actionBtn, styles.outlineBtn, g.current_amount <= 0 && { opacity: 0.5 }, pressed && { opacity: 0.8 }]}
              >
                <Ionicons name="remove" size={us(18)} color={forest} />
                <Text style={[styles.actionText, { color: forest }]}>{t("goals.withdraw")}</Text>
              </Pressable>
            </View>

            <View style={styles.card}>
              <InfoRow icon="flag-outline" label={t("goals.targetAmount")} value={formatCurrencyInt(g.target_amount)} />
              <InfoRow icon="wallet-outline" label={t("goals.totalSaved")} value={formatCurrencyInt(g.current_amount)} color={strong} />
              <InfoRow icon="hourglass-outline" label={t("goals.remaining")} value={formatCurrencyInt(g.remaining)} testID="goal-detail-remaining" />
              <InfoRow icon="calendar-outline" label={t("goals.targetDate")} value={g.target_date ? longDate(g.target_date, i18n.language) : t("goals.noTargetDate")} />
              <InfoRow icon="trending-up-outline" label={t("goals.recommended")} value={recommendedText} color={g.overdue && !g.completed ? colors.expenseRed : undefined} testID="goal-detail-recommended" />
              <InfoRow icon="card-outline" label={t("goals.account")} value={g.account?.name || t("goals.noAccount")} />
            </View>

            <Text style={[styles.section, mont()]}>{t("goals.history")}</Text>
            <View style={styles.card} testID="goal-history">
              {hist.isLoading ? (
                <ActivityIndicator color={colors.incomeGreen} style={{ paddingVertical: us(14) }} />
              ) : items.length === 0 && !(g.initial_amount > 0) ? (
                <Text style={[styles.muted, { paddingVertical: us(14) }]}>{t("goals.noHistory")}</Text>
              ) : (
                <>
                  {items.map((c: any, i: number) => {
                    const dep = c.kind === "deposit";
                    const acc = accName(c.account_id);
                    return (
                      <View key={c.id} testID={`goal-contrib-${c.id}`} style={[styles.txRow, styles.txBorder]}>
                        <View style={[styles.txIcon, { backgroundColor: (dep ? colors.incomeGreen : colors.expenseRed) + "1F" }]}>
                          <Ionicons name={dep ? "arrow-down" : "arrow-up"} size={us(15)} color={dep ? forest : colors.expenseRed} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.txName} numberOfLines={1}>
                            {c.notes || (dep ? t("goals.deposit") : t("goals.withdrawal"))}
                          </Text>
                          <Text style={styles.small} numberOfLines={1}>
                            {formatDateTime(c.date)}{acc ? ` · ${acc}` : ""}{c.real_movement ? ` · ${t("goals.realTag")}` : ""}
                          </Text>
                        </View>
                        <Text style={[styles.txAmt, { color: dep ? forest : colors.expenseRed }]}>
                          {dep ? "+" : "-"}{formatCurrencyInt(c.amount)}
                        </Text>
                      </View>
                    );
                  })}
                  {hist.hasNextPage ? (
                    <Pressable testID="goal-history-more" onPress={() => hist.fetchNextPage()} style={styles.moreBtn}>
                      {hist.isFetchingNextPage ? <ActivityIndicator color={forest} /> : <Text style={[styles.moreText, { color: forest }]}>{t("goals.loadMore")}</Text>}
                    </Pressable>
                  ) : g.initial_amount > 0 ? (
                    <View style={styles.txRow} testID="goal-contrib-initial">
                      <View style={[styles.txIcon, { backgroundColor: base + "1F" }]}>
                        <Ionicons name="flag" size={us(14)} color={strong} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.txName}>{t("goals.initialEntry")}</Text>
                        {g.created_at ? <Text style={styles.small}>{formatDateTime(g.created_at)}</Text> : null}
                      </View>
                      <Text style={[styles.txAmt, { color: forest }]}>+{formatCurrencyInt(g.initial_amount)}</Text>
                    </View>
                  ) : null}
                </>
              )}
            </View>

            <View style={{ flexDirection: "row", gap: us(12), marginTop: us(18) }}>
              <Pressable testID="goal-edit" onPress={() => router.push(`/goals/new?id=${g.id}` as any)} style={[styles.actionBtn, { backgroundColor: forest }]}>
                <Ionicons name="create-outline" size={us(18)} color="#fff" />
                <Text style={styles.actionText}>{t("common.edit")}</Text>
              </Pressable>
              <Pressable testID="goal-delete" onPress={() => setConfirmDel(true)} style={[styles.actionBtn, { backgroundColor: colors.expenseRed + "1A" }]}>
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
        title={t("goals.deleteTitle")}
        description={t("goals.deleteDesc")}
        confirmLabel={t("common.delete")}
        onConfirm={doDelete}
        destructive
        confirmTestID="confirm-delete-goal"
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
  heroIcon: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  heroTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 3, borderRadius: radius.pill, marginTop: 4 },
  statusText: { fontSize: 11.5, fontWeight: "700" },
  heroAmountRow: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", marginTop: 14 },
  heroAmount: { flexShrink: 1, fontSize: 14, color: colors.onSurface },
  heroStrong: { fontSize: 22, fontWeight: "800" },
  heroPct: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  small: { fontSize: 11.5, color: colors.muted },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginTop: 12 },
  infoRow: { flexDirection: "row", alignItems: "center", paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: colors.divider },
  infoIcon: { width: 32, height: 32, borderRadius: 10, alignItems: "center", justifyContent: "center", marginRight: 10 },
  infoLbl: { flex: 1, fontSize: 13, color: colors.muted },
  infoVal: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, maxWidth: "55%", textAlign: "right" },
  section: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: 20 },
  txRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 10 },
  txBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  txIcon: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  txName: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  txAmt: { fontSize: 14, fontWeight: "800" },
  moreBtn: { paddingVertical: 14, alignItems: "center" },
  moreText: { fontWeight: "800", fontSize: 13.5 },
  actionBtn: { flex: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", paddingVertical: 14, minHeight: 48, borderRadius: radius.pill },
  outlineBtn: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  actionText: { color: "#fff", fontWeight: "800", fontSize: 14.5 },
}));
