import React from "react";
import { View, Text, ScrollView, Pressable, StyleSheet } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { useTranslation } from "@/src/i18n";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

export default function Accounts() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const accs: any[] = accQ.data || [];
  const total = accs.reduce((s, a) => s + a.current_balance, 0);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140 }}
    >
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("accounts.title")}</Text>
        <LockToggle testID="lock-accounts" compact />
        <Pressable testID="add-account" onPress={() => router.push("/accounts/new")} style={[styles.backBtn, { backgroundColor: colors.brandPrimary }]}>
          <Ionicons name="add" size={22} color="#fff" />
        </Pressable>
      </View>

      <View style={styles.totalCard}>
        <Text style={{ color: colors.muted, fontWeight: "700", fontSize: 12, textTransform: "uppercase" }}>{t("accounts.totalBalance")}</Text>
        <Text style={styles.totalAmount}>{formatCurrency(total)}</Text>
      </View>

      <View style={{ paddingHorizontal: spacing.lg, gap: 10 }}>
        {accs.map((a) => (
          <Pressable
            testID={`account-${a.id}`}
            key={a.id}
            onPress={guard(() => router.push(`/accounts/new?id=${a.id}`))}
            style={styles.row}
          >
            <IconTile icon={a.icon} tint={a.color} size={48} />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.name}>{a.name}</Text>
              <Text style={styles.sub}>{t(`accounts.types.${a.type}`, { defaultValue: a.type })}</Text>
            </View>
            <Text style={styles.balance}>{formatCurrency(a.current_balance)}</Text>
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: 12 },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 22, fontWeight: "800", color: colors.onSurface },
  totalCard: {
    marginHorizontal: spacing.lg, marginVertical: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  totalAmount: { fontSize: 32, fontWeight: "800", color: colors.onSurface, marginTop: 6 },
  row: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  name: { fontWeight: "700", color: colors.onSurface, fontSize: 15 },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  balance: { fontWeight: "800", color: colors.onSurface, fontSize: 16 },
}));
