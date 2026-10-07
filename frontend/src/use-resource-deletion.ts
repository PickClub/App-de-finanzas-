import { useCallback, useEffect, useRef, useState } from "react";
import { Alert } from "react-native";
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
    Alert.alert("Registro no disponible", "El registro ya no existe. Volverás a su lista.");
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
        .catch(() => Alert.alert("Actualizar datos", "El registro se eliminó, pero no se pudo refrescar la lista."));
      if (exit) exit(); else router.dismissTo(destination);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        unavailable();
      } else {
        let message = error instanceof Error ? error.message : "No se pudo eliminar el registro.";
        if (error instanceof ApiError && error.status === 409) message = error.detail;
        Alert.alert("No se pudo eliminar", message);
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
