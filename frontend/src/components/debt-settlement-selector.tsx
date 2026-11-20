import React from "react";
import { View } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import { useTheme } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { us } from "@/src/ui-scale";

export type SettlementSource = "account" | "external";

export function DebtSettlementSelector({ value, onChange, incoming, disabled = false }: {
  value?: SettlementSource;
  onChange: (value: SettlementSource) => void;
  incoming: boolean;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  return (
    <View style={{ gap: us(8), marginBottom: us(12) }}>
      <Text style={{ fontSize: us(13), fontWeight: "600", color: colors.muted }}>
        {t(incoming ? "debts.receiptDestination" : "debts.paymentSource")}
      </Text>
      <View style={{ flexDirection: "row", gap: us(8) }}>
        {(["account", "external"] as const).map(option => (
          <Pressable key={option} testID={`settlement-${option}`}
            accessibilityRole="radio" accessibilityState={{ checked: value === option, disabled }}
            disabled={disabled} onPress={() => onChange(option)}
            style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: us(6),
              padding: us(10), borderRadius: us(12), borderWidth: 1,
              borderColor: value === option ? colors.primaryAction : colors.border,
              backgroundColor: colors.surfaceSecondary }}>
            <Ionicons name={option === "account" ? "wallet-outline" : "exit-outline"}
              size={us(18)} color={colors.primaryAction} />
            <Text style={{ flexShrink: 1, fontSize: us(13), fontWeight: "600", color: colors.onSurface }}>
              {t(option === "account" ? "debts.accountSettlement" :
                incoming ? "debts.externalReceipt" : "debts.externalPayment")}
            </Text>
          </Pressable>
        ))}
      </View>
      {value === "external" && <Text style={{ fontSize: us(12), color: colors.muted }}>
        {t(incoming ? "debts.externalReceiptExplanation" : "debts.externalPaymentExplanation")}
      </Text>}
    </View>
  );
}
