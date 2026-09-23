import React, { useEffect, useRef, useState } from "react";
import { View, Text, Pressable, Modal, Animated, Easing, StyleSheet, Dimensions } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";

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
              paddingBottom: insets.bottom + spacing.lg,
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

/**
 * Consistent confirmation sheet. Only the icon / accent / title / description /
 * primary action change between the different flows.
 */
export function ConfirmSheet({
  visible,
  onClose,
  icon,
  accent,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive,
  confirmTestID,
}: {
  visible: boolean;
  onClose: () => void;
  icon: string;
  accent: string;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  destructive?: boolean;
  confirmTestID?: string;
}) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const main = destructive ? colors.expenseRed : accent;
  return (
    <AppSheet visible={visible} onClose={onClose} testID="confirm-sheet">
      <View style={s.confirmBody}>
        <View style={[s.confirmIcon, { backgroundColor: main + "1F" }]}>
          <Ionicons name={icon as any} size={30} color={main} />
        </View>
        <Text style={[s.confirmTitle, { color: colors.onSurface }]}>{title}</Text>
        <Text style={[s.confirmDesc, { color: colors.muted }]}>{description}</Text>
        <Pressable testID={confirmTestID || "confirm-primary"} onPress={onConfirm} style={[s.primaryBtn, { backgroundColor: main }]}>
          <Text style={s.primaryText}>{confirmLabel}</Text>
        </Pressable>
        <Pressable onPress={onClose} style={[s.cancelBtn, { backgroundColor: colors.surfaceTertiary }]}>
          <Text style={[s.cancelText, { color: colors.onSurface }]}>{t("common.cancel")}</Text>
        </Pressable>
      </View>
    </AppSheet>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(20,16,12,0.45)" },
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
  confirmBody: { alignItems: "center", paddingHorizontal: spacing.xs, paddingTop: 6 },
  confirmIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  confirmTitle: { fontSize: 19, fontWeight: "800", textAlign: "center", letterSpacing: -0.3 },
  confirmDesc: { fontSize: 13.5, textAlign: "center", marginTop: 8, lineHeight: 19, paddingHorizontal: 6 },
  primaryBtn: { alignSelf: "stretch", marginTop: 22, paddingVertical: 15, borderRadius: radius.pill, alignItems: "center" },
  primaryText: { color: "#fff", fontWeight: "800", fontSize: 15.5 },
  cancelBtn: { alignSelf: "stretch", marginTop: 10, paddingVertical: 15, borderRadius: radius.pill, alignItems: "center" },
  cancelText: { fontWeight: "800", fontSize: 15.5 },
});
