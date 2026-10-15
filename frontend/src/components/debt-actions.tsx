import React, { useEffect, useRef, useState } from "react";
import { View } from "react-native";
import { useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api, ApiError } from "@/src/api";
import { useTranslation } from "@/src/i18n";
import { localizedError } from "@/src/i18n/errors";
import { useTheme, makeStyles } from "@/src/theme";
import { AppSheet } from "./sheets";
import { Pressable } from "./pressable";
import { Text } from "./typography";
import { us } from "@/src/ui-scale";

export function DebtActions({ debt, onClose, onDeleted }: {
  debt: any; onClose: () => void; onDeleted?: () => void;
}) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const styles = useStyles();
  const router = useRouter();
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleted, setDeleted] = useState(false);
  const processing = useRef(false);
  const confirmed = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const close = () => { if (!processing.current) onClose(); };
  const remove = async () => {
    if (!confirming || processing.current || confirmed.current) return;
    processing.current = true; setBusy(true); setError("");
    try {
      const result = await api.deleteDebt(debt.id);
      if (result?.ok !== true) throw new Error(t("errors.requestFailed"));
      confirmed.current = true;
      onDeleted?.();
      qc.setQueryData(["debts"], (rows: any[] | undefined) => rows?.filter(row => row.id !== debt.id));
      qc.removeQueries({ queryKey: ["debt", debt.id], exact: true });
      qc.removeQueries({ queryKey: ["debt-payments", debt.id], exact: true });
      if (mounted.current) setDeleted(true);
      await Promise.all([["debts"], ["summary"], ["transactions"], ["accounts"]]
        .map(queryKey => qc.invalidateQueries({ queryKey, refetchType: "all" })));
      if (mounted.current) onClose();
    } catch (failure) {
      if (mounted.current) setError(confirmed.current ? t("debts.deleteRefreshFailed")
        : failure instanceof ApiError && failure.status === 409 ? t("debts.deleteLinked") : localizedError(failure));
    } finally {
      processing.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  return <AppSheet visible onClose={close} testID="debt-actions-sheet">
    <View style={styles.body}>
      <Text style={styles.title}>{confirming ? t("ui.delete_debt") : debt.name}</Text>
      {!confirming ? <>
        <Pressable testID="debt-action-edit" style={styles.row} onPress={() => {
          if (processing.current) return;
          processing.current = true;
          onClose(); router.push({ pathname: "/debts/new", params: { id: debt.id } });
        }}>
          <Ionicons name="pencil-outline" size={us(20)} color={colors.onSurface} /><Text style={styles.label}>{t("ui.edit")}</Text>
        </Pressable>
        <Pressable testID="debt-action-delete" style={styles.row} onPress={() => setConfirming(true)}>
          <Ionicons name="trash-outline" size={us(20)} color={colors.expenseRed} /><Text style={[styles.label, { color: colors.expenseRed }]}>{t("ui.delete")}</Text>
        </Pressable>
      </> : <>
        <Text style={styles.description}>{deleted ? t("debts.deleteCompleted") : t("debts.deleteConfirmation", { name: debt.name })}</Text>
        {!!error && <Text testID="debt-delete-error" accessibilityRole="alert" style={[styles.description, { color: colors.expenseRed }]}>{error}</Text>}
        {!deleted && <Pressable testID="debt-delete-confirm" disabled={busy} onPress={() => { void remove(); }} style={[styles.confirm, { backgroundColor: colors.expenseRed, opacity: busy ? 0.6 : 1 }]}>
          <Text style={{ color: colors.onBrandPrimary, fontWeight: "700" }}>{busy ? t("ui.loading") : t("ui.delete")}</Text>
        </Pressable>}
      </>}
      <Pressable testID="debt-actions-cancel" disabled={busy} onPress={close} style={styles.row}>
        <Text style={styles.label}>{deleted ? t("common.close") : t("common.cancel")}</Text>
      </Pressable>
    </View>
  </AppSheet>;
}

const useStyles = makeStyles(colors => ({
  body: { paddingVertical: 8 },
  title: { fontSize: 19, fontWeight: "800", color: colors.onSurface, marginBottom: 12 },
  row: { minHeight: 48, flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 10 },
  label: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  description: { fontSize: 14, color: colors.muted, marginVertical: 10 },
  confirm: { minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 999, marginTop: 12 },
}));
