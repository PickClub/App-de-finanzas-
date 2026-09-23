import React, { useEffect, useState } from "react";
import { View, Text, TextInput, ScrollView, Pressable, StyleSheet, Alert } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { IconTile } from "@/src/components/ui";

const TYPE_IDS = [
  { id: "cash", icon: "cash-outline" },
  { id: "checking", icon: "card-outline" },
  { id: "savings", icon: "wallet-outline" },
  { id: "credit_card", icon: "card-outline" },
  { id: "wallet", icon: "phone-portrait-outline" },
  { id: "other", icon: "ellipsis-horizontal-outline" },
];
const COLORS = ["#4C83EA", "#2FA47C", "#FF654A", "#F5B83B", "#8F5BE8", "#29C4A9", "#D95345", "#FF8A3D"];

export default function AccountForm() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const [name, setName] = useState("");
  const [type, setType] = useState("cash");
  const [balance, setBalance] = useState("");
  const [color, setColor] = useState(COLORS[0]);
  const [icon, setIcon] = useState("wallet-outline");

  useEffect(() => {
    if (params.id) {
      api.listAccounts().then((all) => {
        const a = all.find((x: any) => x.id === params.id);
        if (a) {
          setName(a.name);
          setType(a.type);
          setBalance(String(a.initial_balance));
          setColor(a.color);
          setIcon(a.icon);
        }
      });
    }
  }, [params.id]);

  const save = async () => {
    if (!name.trim()) {
      Alert.alert(t("errors.nameRequired"));
      return;
    }
    const payload = {
      name,
      type,
      initial_balance: parseFloat(balance) || 0,
      color,
      icon,
      currency: "USD",
    };
    if (params.id) await api.updateAccount(params.id as string, payload);
    else await api.createAccount(payload);
    qc.invalidateQueries();
    router.back();
  };

  const remove = async () => {
    if (!params.id) return;
    await api.deleteAccount(params.id as string);
    qc.invalidateQueries();
    router.back();
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 140, paddingHorizontal: spacing.lg }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg }}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{params.id ? t("accounts.editAccount") : t("accounts.newAccount")}</Text>
        {params.id && (
          <Pressable onPress={remove} style={styles.backBtn}>
            <Ionicons name="trash-outline" size={22} color={colors.expenseRed} />
          </Pressable>
        )}
      </View>

      <Text style={styles.label}>{t("accounts.name")}</Text>
      <TextInput testID="acc-name" value={name} onChangeText={setName} placeholder={t("accounts.namePlaceholder")} placeholderTextColor={colors.muted} style={styles.input} />

      <Text style={styles.label}>{t("accounts.initialBalance")}</Text>
      <TextInput testID="acc-balance" value={balance} onChangeText={setBalance} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={colors.muted} style={styles.input} />

      <Text style={styles.label}>{t("accounts.type")}</Text>
      <View style={styles.grid}>
        {TYPE_IDS.map((ty) => (
          <Pressable key={ty.id} onPress={() => { setType(ty.id); setIcon(ty.icon); }} style={[styles.gridItem, type === ty.id && { borderColor: color, borderWidth: 2 }]}>
            <IconTile icon={ty.icon} tint={color} size={38} />
            <Text style={{ color: colors.onSurface, fontWeight: "600", marginTop: 6, fontSize: 12 }}>{t(`accounts.types.${ty.id}`)}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>{t("accounts.color")}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        {COLORS.map((c) => (
          <Pressable key={c} onPress={() => setColor(c)} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: c, borderWidth: color === c ? 3 : 0, borderColor: colors.onSurface }} />
        ))}
      </View>

      <Pressable testID="save-account" onPress={save} style={styles.saveBtn}>
        <Text style={styles.saveText}>{t("common.save")}</Text>
      </Pressable>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  gridItem: { width: "31%", padding: 12, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  saveBtn: { marginTop: 28, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
