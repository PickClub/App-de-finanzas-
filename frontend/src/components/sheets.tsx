import React, { useEffect, useRef, useState } from "react";
import { View, Modal, Animated, Easing, StyleSheet, Dimensions } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, radius, spacing } from "@/src/theme";

import { us, scaleStyles } from "@/src/ui-scale";
import { MoneyFlowConfirmDialog } from "./interaction-system";
const { height: SCREEN_H } = Dimensions.get("window");

/**
 * One consistent bottom-sheet primitive used by every transaction action.
 * Warm cream surface, large rounded top corners, subtle border + soft shadow,
 * gray drag indicator. Animates: slide up + fade in / slide down + fade out.
 * No bouncing (cubic easing).
 */
export function AppSheet({
  visible,
  onClose,
  children,
  testID,
}: {
  visible: boolean;
  onClose: () => void;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  const ty = useRef(new Animated.Value(SCREEN_H)).current;
  const op = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      requestAnimationFrame(() => {
        Animated.parallel([
          Animated.timing(op, { toValue: 1, duration: 180, useNativeDriver: true }),
          Animated.timing(ty, { toValue: 0, duration: 260, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        ]).start();
      });
    } else if (mounted) {
      Animated.parallel([
        Animated.timing(op, { toValue: 0, duration: 150, useNativeDriver: true }),
        Animated.timing(ty, { toValue: SCREEN_H, duration: 200, easing: Easing.in(Easing.cubic), useNativeDriver: true }),
      ]).start(() => setMounted(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  if (!mounted) return null;

  return (
    <Modal transparent visible animationType="none" onRequestClose={onClose} statusBarTranslucent>
      <View style={s.root}>
        <Animated.View style={[s.backdrop, { opacity: op }]}>
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} testID="sheet-backdrop" />
        </Animated.View>
        <Animated.View
          testID={testID}
          style={[
            s.sheet,
            {
              backgroundColor: colors.surface,
              borderColor: colors.border,
              paddingBottom: insets.bottom + us(spacing.lg),
              transform: [{ translateY: ty }],
            },
          ]}
        >
          <View style={[s.grip, { backgroundColor: colors.borderStrong }]} />
          {children}
        </Animated.View>
      </View>
    </Modal>
  );
}

/** Compatibility name: existing handlers now use the unified centered dialog. */
export function ConfirmSheet(props: React.ComponentProps<typeof MoneyFlowConfirmDialog>) {
  return <MoneyFlowConfirmDialog {...props} />;
}

const s = StyleSheet.create(scaleStyles({
  root: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFill, backgroundColor: "rgba(20,16,12,0.45)" },
  sheet: {
    borderTopLeftRadius: radius.cardLg,
    borderTopRightRadius: radius.cardLg,
    borderWidth: 1,
    paddingTop: 10,
    paddingHorizontal: spacing.lg,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: -8 },
    elevation: 24,
  },
  grip: { alignSelf: "center", width: 40, height: 5, borderRadius: 3, marginBottom: 14 },
}));
