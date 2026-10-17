import { Alert } from "@/src/components/interaction-system";
import { tr } from "@/src/i18n";
import { localizedError } from "@/src/i18n/errors";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, type Href } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "./api";

// Only deletion lifecycle: keep resource-specific operations and finance on their screens/API.
export function useResourceDeletion(destination: Href, queryKeys: string[][], exit?: () => void) {
  const router = useRouter();
  const qc = useQueryClient();
  const locked = useRef(false);
  const deleted = useRef(false);
  const [busy, setBusy] = useState(false);
  const unavailable = useCallback(() => {
    if (deleted.current) return;
    locked.current = true;
    deleted.current = true;
    setBusy(true);
    Alert.alert(tr("ui.record_unavailable"), localizedError(tr("ui.this_record_no_longer_exists_returning_to_the_list")));
    if (exit) exit(); else router.dismissTo(destination);
  }, [router, destination, exit]);
  const remove = async (operation: () => Promise<unknown>) => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    try {
      await operation();
      deleted.current = true;
      void Promise.all(queryKeys.map((queryKey) => qc.invalidateQueries({ queryKey, refetchType: "all" })))
        .catch(() => Alert.alert(tr("ui.refresh_data"), localizedError(tr("ui.the_record_was_deleted_but_the_list_could_not_refresh"))));
      if (exit) exit(); else router.dismissTo(destination);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        unavailable();
      } else {
        let message = error instanceof Error ? error.message : "No se pudo eliminar el registro.";
        if (error instanceof ApiError && error.status === 409) message = error.detail;
        Alert.alert(tr("ui.could_not_delete"), localizedError(message));
      }
    } finally {
      if (!deleted.current) { locked.current = false; setBusy(false); }
    }
  };
  return { busy, locked, deleted, remove, unavailable };
}

export function useMissingResource(missing: boolean, unavailable: () => void) {
  useEffect(() => { if (missing) unavailable(); }, [missing, unavailable]);
}
