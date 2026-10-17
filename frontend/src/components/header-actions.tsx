import React from "react";
import { ActivityIndicator, StyleSheet, View, type StyleProp, type ViewStyle } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useTranslation } from "@/src/i18n";
import { useTheme } from "@/src/theme";
import { Pressable } from "./pressable";

type MoneyFlowHeaderActionsProps = {
  onBack: () => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
  saveDisabled?: boolean;
  backTestID?: string;
  saveTestID?: string;
  backAccessibilityLabel?: string;
  saveAccessibilityLabel?: string;
  beforeActions?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** Shared upper-right navigation/save controls; screen handlers retain ownership of operations. */
export function MoneyFlowHeaderActions({
  onBack,
  onSave,
  saving = false,
  saveDisabled = false,
  backTestID,
  saveTestID,
  backAccessibilityLabel,
  saveAccessibilityLabel,
  beforeActions,
  style,
}: MoneyFlowHeaderActionsProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  return (
    <View style={[styles.group, style]}>
      {beforeActions}
      <Pressable
        testID={backTestID}
        accessibilityRole="button"
        accessibilityLabel={backAccessibilityLabel || t("common.back")}
        onPress={onBack}
        style={({ pressed }) => [styles.button, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }, pressed && styles.pressed]}
      >
        <Ionicons name="arrow-back" size={20} color={colors.onSurface} />
      </Pressable>
      {onSave ? (
        <Pressable
          testID={saveTestID}
          accessibilityRole="button"
          accessibilityLabel={saveAccessibilityLabel || t("headerActions.saveChanges")}
          accessibilityState={{ disabled: saveDisabled || saving, busy: saving }}
          disabled={saveDisabled || saving}
          onPress={() => { void onSave(); }}
          style={({ pressed }) => [styles.button, styles.saveButton, { backgroundColor: colors.primaryAction, opacity: saveDisabled ? 0.5 : 1 }, (pressed || saving) && styles.pressed]}
        >
          {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Ionicons name="arrow-forward" size={20} color="#FFFFFF" />}
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 8, marginLeft: "auto" },
  button: { width: 44, height: 44, borderRadius: 14, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  saveButton: { borderColor: "transparent" },
  pressed: { opacity: 0.72 },
});
