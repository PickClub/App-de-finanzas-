import React from "react";
import { View, ScrollView, Platform } from "react-native";
import Svg, { Path } from "react-native-svg";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, spacing } from "@/src/theme";
import { formatCurrency } from "@/src/format";
import { useTranslation } from "@/src/i18n";
import { LockToggle, useLock } from "@/src/lock";

import { us } from "@/src/ui-scale";

// Local visual identity (same light-mode values as Home and the redesigned forms).
// Dark mode falls back to the global dark theme tokens.
function listPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    dark,
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    forest: dark ? colors.incomeGreen : "#126046",
    ink: dark ? colors.onSurface : "#123D2E",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    muted: dark ? colors.muted : "#7A847E",
    border: dark ? colors.border : "rgba(39,71,56,0.08)",
    deco: dark ? colors.incomeGreen : "#9DBBA4",
  };
}

export default function Accounts() {
  const { colors, scheme } = useTheme();
  const pal = listPalette(colors, scheme);
  const { t } = useTranslation();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const accs: any[] = accQ.data || [];
  const total = accs.reduce((s, a) => s + a.current_balance, 0);

  const shadow = pal.dark ? null : styles.softShadow;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: pal.bg }}
      contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(40) }}
    >
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={[styles.circleBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
          <Ionicons name="chevron-back" size={us(24)} color={pal.ink} />
        </Pressable>
        <Text style={[styles.title, { color: pal.dark ? colors.onSurface : pal.ink }]} numberOfLines={1}>{t("accounts.title")}</Text>
        <View style={[styles.circleBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
          <LockToggle testID="lock-accounts" compact />
        </View>
        <Pressable testID="add-account" onPress={() => router.push("/accounts/new")} style={[styles.circleBtn, styles.addBtn, { backgroundColor: pal.dark ? pal.forest : pal.ink, borderColor: "transparent" }, shadow]}>
          <Ionicons name="add" size={us(26)} color={pal.dark ? colors.onSuccess : "#fff"} />
        </Pressable>
      </View>

      <View style={[styles.totalCard, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
        <Svg width={us(190)} height={us(70)} viewBox="0 0 190 70" style={styles.totalDeco} pointerEvents="none">
          <Path d="M10 70 C 30 36, 70 26, 104 40 C 120 46, 128 70, 128 70 Z" fill={pal.deco} opacity={pal.dark ? 0.1 : 0.14} />
          <Path d="M80 70 C 104 30, 150 18, 190 30 L 190 70 Z" fill={pal.deco} opacity={pal.dark ? 0.12 : 0.18} />
        </Svg>
        <View style={[styles.totalIcon, { backgroundColor: pal.mint }]}>
          <Ionicons name="wallet-outline" size={us(30)} color={pal.forest} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.totalLabel, { color: pal.muted }]}>{t("accounts.totalBalance")}</Text>
          <Text style={[styles.totalAmount, { color: pal.dark ? colors.onSurface : pal.ink }]} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>{formatCurrency(total)}</Text>
        </View>
      </View>

      <View style={{ paddingHorizontal: us(spacing.lg), gap: us(10) }}>
        {accs.map((a) => (
          <Pressable
            testID={`account-${a.id}`}
            key={a.id}
            onPress={guard(() => router.push(`/accounts/new?id=${a.id}`))}
            style={({ pressed }) => [styles.row, { backgroundColor: pal.card, borderColor: pal.border }, shadow, pressed && { opacity: 0.88 }]}
          >
            <View style={[styles.stripe, { backgroundColor: a.color }]} />
            <View style={[styles.accIcon, { backgroundColor: (a.color || pal.forest) + (pal.dark ? "2E" : "22") }]}>
              <Ionicons name={(a.icon || "wallet-outline") as any} size={us(24)} color={a.color || pal.forest} />
            </View>
            <View style={{ flex: 1, minWidth: 0, marginLeft: us(12) }}>
              <Text style={[styles.name, { color: pal.dark ? colors.onSurface : pal.ink }]} numberOfLines={1}>{a.name}</Text>
              <Text style={[styles.sub, { color: pal.muted }]} numberOfLines={1}>{t(`accounts.types.${a.type}`, { defaultValue: a.type })}</Text>
            </View>
            <Text style={[styles.balance, { color: pal.dark ? colors.onSurface : pal.ink }]} numberOfLines={1}>{formatCurrency(a.current_balance)}</Text>
            <Ionicons name="chevron-forward" size={us(18)} color={pal.muted} style={{ marginLeft: us(6) }} />
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles(() => ({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: 12, marginBottom: 14 },
  circleBtn: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  addBtn: { width: 48, height: 48, borderRadius: 24 },
  title: { flex: 1, fontSize: 24, fontWeight: "800", letterSpacing: -0.3 },
  softShadow: Platform.select({
    web: { boxShadow: "0px 2px 10px rgba(18,96,70,0.06)" } as any,
    default: { shadowColor: "#126046", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  }),
  totalCard: {
    flexDirection: "row", alignItems: "center", gap: 16,
    marginHorizontal: spacing.lg, marginBottom: 14,
    borderRadius: 22, padding: 16, borderWidth: 1, overflow: "hidden",
  },
  totalDeco: { position: "absolute", right: 0, bottom: 0 },
  totalIcon: { width: 64, height: 64, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  totalLabel: { fontWeight: "600", fontSize: 12, textTransform: "uppercase", letterSpacing: 0.6 },
  totalAmount: { fontSize: 30, fontWeight: "800", marginTop: 4, letterSpacing: -0.5 },
  row: {
    flexDirection: "row", alignItems: "center",
    borderRadius: 20, paddingVertical: 14, paddingLeft: 16, paddingRight: 12,
    borderWidth: 1, overflow: "hidden", minHeight: 76,
  },
  stripe: { position: "absolute", left: 0, top: 0, bottom: 0, width: 4 },
  accIcon: { width: 50, height: 50, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  name: { fontWeight: "700", fontSize: 16 },
  sub: { fontSize: 13, marginTop: 2 },
  balance: { fontWeight: "800", fontSize: 17, marginLeft: 8, flexShrink: 0 },
}));
