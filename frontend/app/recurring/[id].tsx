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
import { ConfirmSheet } from "@/src/components/sheets";
import { catLabel } from "@/src/category-labels";
import { FOREST, useMontserrat, pastel, deepen, safeHex, longDate, statusTint } from "@/src/recurring/shared";

import { us } from "@/src/ui-scale";

export default function RecurringDetail() {
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
  const [confirm, setConfirm] = useState<null | "delete" | "end" | { undo: string }>(null);
  const [busy, setBusy] = useState(false);

  const q = useQuery({ queryKey: ["rp-detail", id], queryFn: () => api.rpGet(id as string) });
  const occ = useInfiniteQuery({
    queryKey: ["rp-occ", id],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => api.rpOccurrences(id as string, pageParam as number, 12),
    getNextPageParam: (last: any) => (last?.has_more ? last.offset + last.limit : undefined),
  });
  const { refetch } = q;
  const refetchOcc = occ.refetch;
  useFocusEffect(useCallback(() => { refetch(); refetchOcc(); }, [refetch, refetchOcc]));

  const r = q.data;
  const items: any[] = (occ.data?.pages || []).flatMap((p: any) => p.items || []);
  const base = safeHex(r?.color);
  const strong = deepen(base, isDark);
  const todayIso = new Date().toISOString().slice(0, 10);
  const oldestOverdue = [...items].reverse().find((o) => o.status === "overdue");
  const payTarget = oldestOverdue || r?.next_due;

  const refreshAll = () => Promise.all([["rp-overview"], ["rp-detail"], ["rp-occ"], ["accounts"], ["transactions"], ["summary"]].map((k) => qc.invalidateQueries({ queryKey: k })));

  const openPay = (o: any) => router.push(`/recurring/pay?id=${id}&due=${o.due_date}&exp=${o.expected}&rem=${o.remaining}` as any);

  const doAction = async (action: "pause" | "resume" | "end") => {
    if (busy) return;
    setBusy(true);
    try { await api.rpAction(id as string, action); await refreshAll(); } finally { setBusy(false); setConfirm(null); }
  };
  const onConfirm = async () => {
    if (busy || !confirm) return;
    if (confirm === "end") return doAction("end");
    setBusy(true);
    try {
      if (confirm === "delete") {
        await api.rpDelete(id as string);
        qc.removeQueries({ queryKey: ["rp-detail", id] });
        await qc.invalidateQueries({ queryKey: ["rp-overview"] });
        setConfirm(null);
        router.back();
        return;
      }
      await api.rpDeletePayment(confirm.undo);
      await refreshAll();
      setConfirm(null);
    } finally { setBusy(false); }
  };

  const Info = ({ icon, label, value, color, testID }: { icon: string; label: string; value: string; color?: string; testID?: string }) => (
    <View style={styles.infoRow}>
      <View style={[styles.infoIcon, { backgroundColor: base + "1F" }]}>
        <Ionicons name={icon as any} size={us(16)} color={strong} />
      </View>
      <Text style={styles.infoLbl}>{label}</Text>
      <Text style={[styles.infoVal, color ? { color } : null]} numberOfLines={2} testID={testID}>{value}</Text>
    </View>
  );

  const stateTint = r?.state === "active" ? colors.incomeGreen : r?.state === "paused" ? colors.brandSecondary : colors.muted;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(60), paddingHorizontal: us(spacing.lg) }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
          <Pressable testID="rp-detail-back" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title} numberOfLines={1}>{t("rp.detail")}</Text>
        </View>

        {q.isLoading ? <ActivityIndicator color={colors.incomeGreen} style={{ marginTop: us(40) }} /> : !r ? (
          <Text style={styles.muted}>{t("rp.loadError")}</Text>
        ) : (
          <>
            <View style={styles.hero}>
              <LinearGradient colors={pastel(base, isDark)} start={{ x: 1, y: 0 }} end={{ x: 0, y: 1 }} style={styles.fill} pointerEvents="none" />
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <View style={[styles.heroIcon, { backgroundColor: base + "29" }]}>
                  <Ionicons name={(r.icon || "receipt-outline") as any} size={us(26)} color={strong} />
                </View>
                <View style={{ flex: 1, marginLeft: us(12) }}>
                  <Text style={[styles.heroTitle, mont()]} numberOfLines={1}>{r.name}</Text>
                  <View style={[styles.pill, { backgroundColor: stateTint + "24" }]}>
                    <Text style={[styles.pillText, { color: deepen(stateTint, isDark, 0.15) }]} testID="rp-detail-state">{t(`rp.st_${r.state}`)}</Text>
                  </View>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[styles.heroAmount, mont(true), { color: strong }]} testID="rp-detail-amount">{formatCurrencyInt(r.amount)}</Text>
                  <Text style={styles.small}>{t(`rp.f_${r.frequency}`)}{r.variable ? ` · ${t("rp.variable")}` : ""}</Text>
                </View>
              </View>
            </View>

            {r.state !== "ended" && payTarget ? (
              <Pressable testID="rp-register-pay" onPress={() => openPay(payTarget)} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary }]}>
                <Ionicons name="checkmark-done" size={us(18)} color="#fff" />
                <Text style={styles.primaryText}>{t("rp.registerPay")} · {longDate(payTarget.due_date, i18n.language)}</Text>
              </Pressable>
            ) : null}

            <View style={styles.card}>
              <Info icon="calendar-outline" label={t("rp.nextDue")} testID="rp-detail-next"
                value={r.next_due ? `${longDate(r.next_due.due_date, i18n.language)}` : t("rp.noNext")} />
              <Info icon="wallet-outline" label={t("rp.account")} value={r.account?.name || t("rp.none")} />
              <Info icon="pricetag-outline" label={t("rp.category")} value={r.category ? catLabel(r.category.name, i18n.language) : t("rp.none")} />
              <Info icon="checkmark-done-outline" label={t("rp.paidTotal")} value={formatCurrencyInt(r.paid_total)} color={forest} testID="rp-detail-paid-total" />
              <Info icon="notifications-outline" label={t("rp.reminder")} value={t(`rp.r_${r.reminder_days ?? "none"}`)} />
              {r.end_date ? <Info icon="flag-outline" label={t("rp.endDate")} value={longDate(r.end_date, i18n.language)} /> : null}
              {r.notes ? <Info icon="document-text-outline" label={t("rp.description")} value={r.notes} /> : null}
            </View>

            <Text style={[styles.section, mont()]}>{t("rp.history")}</Text>
            <View style={styles.card} testID="rp-history">
              {occ.isLoading ? <ActivityIndicator color={colors.incomeGreen} style={{ paddingVertical: us(14) }} /> : items.length === 0 ? (
                <Text style={[styles.muted, { paddingVertical: us(14) }]}>{t("rp.noHistory")}</Text>
              ) : items.map((o: any, i: number) => {
                const st = o.partial ? "partial" : o.status;
                const tint = statusTint(o.status, colors);
                const future = o.due_date > todayIso;
                return (
                  <View key={o.due_date} testID={`rp-occ-${o.due_date}`} style={[styles.occRow, i < items.length - 1 && styles.border]}>
                    <View style={{ flexDirection: "row", alignItems: "center" }}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.occDate}>{longDate(o.due_date, i18n.language)}</Text>
                        <Text style={styles.small}>
                          {formatCurrencyInt(o.paid)} / {formatCurrencyInt(o.expected)}{future && o.status !== "paid" ? ` · ${t("rp.forecast")}` : ""}
                        </Text>
                      </View>
                      <View style={[styles.pill, { backgroundColor: tint + "22", marginTop: 0 }]}>
                        <Text style={[styles.pillText, { color: deepen(tint, isDark, 0.15) }]}>{t(`rp.st_${st}`)}</Text>
                      </View>
                      {o.status !== "paid" && r.state !== "ended" ? (
                        <Pressable testID={`rp-occ-pay-${o.due_date}`} onPress={() => openPay(o)} hitSlop={8} style={styles.occPay}>
                          <Ionicons name="add-circle-outline" size={us(22)} color={forest} />
                        </Pressable>
                      ) : null}
                    </View>
                    {(o.records || []).map((rec: any) => (
                      <View key={rec.id} style={styles.recRow} testID={`rp-rec-${rec.id}`}>
                        <Ionicons name={rec.mode === "expense" ? "card-outline" : rec.mode === "link" ? "link-outline" : "bookmark-outline"} size={us(14)} color={colors.muted} />
                        <Text style={[styles.small, { flex: 1 }]} numberOfLines={1}>
                          {t(`rp.${rec.mode}`)} · {formatDateTime(rec.date)}{rec.notes ? ` · ${rec.notes}` : ""}
                        </Text>
                        <Text style={[styles.recAmt, { color: forest }]}>{formatCurrencyInt(rec.amount)}</Text>
                        <Pressable testID={`rp-undo-${rec.id}`} onPress={() => setConfirm({ undo: rec.id })} hitSlop={8} style={{ marginLeft: us(8) }}>
                          <Ionicons name="arrow-undo-outline" size={us(16)} color={colors.expenseRed} />
                        </Pressable>
                      </View>
                    ))}
                  </View>
                );
              })}
              {occ.hasNextPage ? (
                <Pressable testID="rp-history-more" onPress={() => occ.fetchNextPage()} style={styles.moreBtn}>
                  {occ.isFetchingNextPage ? <ActivityIndicator color={forest} /> : <Text style={[styles.moreText, { color: forest }]}>{t("rp.loadMore")}</Text>}
                </Pressable>
              ) : null}
            </View>

            <View style={styles.actions}>
              <Pressable testID="rp-edit" onPress={() => router.push(`/recurring/new?id=${r.id}` as any)} style={[styles.actBtn, { backgroundColor: forest }]}>
                <Ionicons name="create-outline" size={us(17)} color="#fff" />
                <Text style={styles.actText}>{t("rp.edit")}</Text>
              </Pressable>
              {r.state === "active" ? (
                <Pressable testID="rp-pause" disabled={busy} onPress={() => doAction("pause")} style={[styles.actBtn, styles.outline]}>
                  <Ionicons name="pause-outline" size={us(17)} color={forest} />
                  <Text style={[styles.actText, { color: forest }]}>{t("rp.pause")}</Text>
                </Pressable>
              ) : r.state === "paused" ? (
                <Pressable testID="rp-resume" disabled={busy} onPress={() => doAction("resume")} style={[styles.actBtn, styles.outline]}>
                  <Ionicons name="play-outline" size={us(17)} color={forest} />
                  <Text style={[styles.actText, { color: forest }]}>{t("rp.resume")}</Text>
                </Pressable>
              ) : null}
            </View>
            <View style={styles.actions}>
              {r.state !== "ended" ? (
                <Pressable testID="rp-end" onPress={() => setConfirm("end")} style={[styles.actBtn, styles.outline]}>
                  <Ionicons name="stop-circle-outline" size={us(17)} color={colors.onSurface} />
                  <Text style={[styles.actText, { color: colors.onSurface }]}>{t("rp.end")}</Text>
                </Pressable>
              ) : null}
              <Pressable testID="rp-delete" onPress={() => setConfirm("delete")} style={[styles.actBtn, { backgroundColor: colors.expenseRed + "1A" }]}>
                <Ionicons name="trash-outline" size={us(17)} color={colors.expenseRed} />
                <Text style={[styles.actText, { color: colors.expenseRed }]}>{t("rp.delete")}</Text>
              </Pressable>
            </View>
          </>
        )}
      </ScrollView>

      <ConfirmSheet
        visible={confirm !== null}
        onClose={() => setConfirm(null)}
        icon={confirm === "end" ? "stop-circle-outline" : confirm === "delete" ? "trash-outline" : "arrow-undo-outline"}
        accent={colors.expenseRed}
        title={confirm === "end" ? t("rp.endTitle") : confirm === "delete" ? t("rp.deleteTitle") : t("rp.undoTitle")}
        description={confirm === "end" ? t("rp.endDesc") : confirm === "delete" ? t("rp.deleteDesc") : t("rp.undoDesc")}
        confirmLabel={confirm === "end" ? t("rp.end") : confirm === "delete" ? t("rp.delete") : t("rp.undo")}
        onConfirm={onConfirm}
        destructive
        confirmTestID="rp-confirm"
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
  heroAmount: { fontSize: 20, fontWeight: "800" },
  pill: { alignSelf: "flex-start", paddingHorizontal: 9, paddingVertical: 2, borderRadius: radius.pill, marginTop: 4 },
  pillText: { fontSize: 11, fontWeight: "700" },
  small: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
  primaryBtn: { flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", minHeight: 50, marginTop: 12, borderRadius: radius.pill, paddingHorizontal: 16 },
  primaryText: { color: "#fff", fontWeight: "800", fontSize: 14.5 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, marginTop: 12 },
  infoRow: { flexDirection: "row", alignItems: "center", paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: colors.divider },
  infoIcon: { width: 32, height: 32, borderRadius: 10, alignItems: "center", justifyContent: "center", marginRight: 10 },
  infoLbl: { flex: 1, fontSize: 13, color: colors.muted },
  infoVal: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, maxWidth: "55%", textAlign: "right" },
  section: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: 20 },
  occRow: { paddingVertical: 11 },
  border: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  occDate: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface },
  occPay: { marginLeft: 8, minWidth: 32, minHeight: 32, alignItems: "center", justifyContent: "center" },
  recRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6, paddingLeft: 4 },
  recAmt: { fontSize: 12.5, fontWeight: "800" },
  moreBtn: { paddingVertical: 14, alignItems: "center" },
  moreText: { fontWeight: "800", fontSize: 13.5 },
  actions: { flexDirection: "row", gap: 10, marginTop: 12 },
  actBtn: { flex: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", minHeight: 48, borderRadius: radius.pill },
  outline: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  actText: { color: "#fff", fontWeight: "800", fontSize: 14 },
}));
