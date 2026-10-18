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
  title?: React.ReactNode;
  trailingContent?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** Shared header row: Back stays left, while contextual and Save actions stay right. */
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
  title,
  trailingContent,
  style,
}: MoneyFlowHeaderActionsProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  return (
    <View style={[styles.group, style]}>
      <Pressable
        testID={backTestID}
        accessibilityRole="button"
        accessibilityLabel={backAccessibilityLabel || t("common.back")}
        onPress={onBack}
        style={({ pressed }) => [styles.button, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }, pressed && styles.pressed]}
      >
        <Ionicons name="arrow-back" size={20} color={colors.onSurface} />
      </Pressable>
      {title != null && <View style={styles.title}>{title}</View>}
      <View style={styles.trailing}>
        {trailingContent}
        {beforeActions}
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
            {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Ionicons name="checkmark" size={20} color="#FFFFFF" />}
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: { width: "100%", flexDirection: "row", alignItems: "center", gap: 8 },
  title: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center" },
  trailing: { flexDirection: "row", alignItems: "center", gap: 8, marginLeft: "auto" },
  button: { width: 44, height: 44, borderRadius: 14, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  saveButton: { borderColor: "transparent" },
  pressed: { opacity: 0.72 },
});
