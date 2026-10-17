import React, { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/src/api";
import { useTranslation } from "@/src/i18n";
import { localizedError } from "@/src/i18n/errors";
import { useTheme } from "@/src/theme";
import { MoneyFlowConfirmDialog } from "./interaction-system";

export function DebtActions({ debt, visible, onClose, onDeleted }: {
  debt: any; visible: boolean; onClose: () => void; onDeleted?: () => void;
}) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleted, setDeleted] = useState(false);
  const processing = useRef(false);
  const confirmed = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const remove = async () => {
    if (!visible || processing.current || confirmed.current) return;
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

  const dismiss = () => { if (!processing.current) onClose(); };
  return <MoneyFlowConfirmDialog
    visible={visible}
    onClose={dismiss}
    icon="trash-outline"
    accent={colors.expenseRed}
    title={t("ui.delete_debt")}
    description={deleted ? t("debts.deleteCompleted") : t("debts.deleteConfirmation", { name: debt.name })}
    confirmLabel={t("ui.delete")}
    confirmTestID="debt-delete-confirm"
    destructive
    busy={busy}
    error={error}
    hideConfirm={deleted}
    cancelLabel={deleted ? t("common.close") : t("common.cancel")}
    cancelTestID="debt-actions-cancel"
    onConfirm={remove}
  />;
}
