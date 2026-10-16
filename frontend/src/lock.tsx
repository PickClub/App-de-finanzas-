import React from "react";
import type { GestureResponderEvent } from "react-native";

// Compatibility boundary for existing callers after removing the optional UI edit lock.
// Authentication and financial validation are independent of this presentation feature.
export function LockProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function useLock() {
  return {
    guard: <T extends (e?: GestureResponderEvent) => any>(fn: T) => fn,
  };
}
