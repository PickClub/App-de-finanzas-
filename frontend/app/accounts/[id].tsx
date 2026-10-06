import React, { useMemo } from "react";
import { View, ScrollView, Platform, ActivityIndicator } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";
import { formatCurrencyInt, formatDateLong } from "@/src/format";
import { IconTile } from "@/src/components/ui";

import { us } from "@/src/ui-scale";
// Mirror the Home square-card color logic so the detail accents match the card
// EXACTLY (legacy name overrides on light; raw stored color otherwise). This is
// a presentation-only helper — it reads the account's REAL stored color.
const HOME_ACCOUNT_COLORS: Record<string, string> = {
  "chase checking": "#0C5C46",
  efectivo: "#C6952C",
  ahorros: "#176F78",
  "cuenta 2": "#678E58",
  "cuenta 6": "#E2763E",
};
function accountColor(a: any, scheme: string): string {
  if (!a) return "#4C83EA";
  if (scheme === "dark") return a.color || "#4C83EA";
  const key = (a.name || "").trim().toLowerCase();
  return HOME_ACCOUNT_COLORS[key] || a.color || "#4C83EA";
}
const ACCOUNT_ICON: Record<string, string> = {
  cash: "cash-outline",
  checking: "card-outline",
  savings: "wallet-outline",
  credit_card: "card-outline",
  wallet: "phone-portrait-outline",
  other: "ellipsis-horizontal-outline",
};

function InfoRow({ styles, tileBg, iconColor, icon, label, value, rightNode }: any) {
  return (
    <View style={styles.infoRow}>
      <View style={[styles.infoTile, { backgroundColor: tileBg }]}>
        <Ionicons name={icon} size={us(18)} color={iconColor} />
      </View>
      <Text style={styles.infoLabel}>{label}</Text>
      {rightNode ? rightNode : <Text style={styles.infoValue}>{value}</Text>}
    </View>
  );
}

export default function AccountDetail() {
  const { colors, scheme } = useTheme();
  const { t } = useTranslation();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  // Reuse the SAME react-query sources the rest of the app uses (single source
  // of truth). No new data layer, no mutations here — read-only preview.
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });
  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });

  const account = useMemo(
    () => (accountsQ.data || []).find((a: any) => a.id === params.id),
    [accountsQ.data, params.id],
  );
  const forest = scheme === "dark" ? colors.incomeGreen : "#126046";
  const ac = accountColor(account, scheme);

  // Movements belonging to THIS account (either side of a transfer).
  const catById = useMemo(() => {
    const cats: any[] = catsQ.data || [];
    return Object.fromEntries(cats.map((c: any) => [c.id, c]));
  }, [catsQ.data]);
  const accountTx = useMemo(() => {
    const all: any[] = txQ.data || [];
    return all
      .filter((x: any) => x.account_id === params.id || x.to_account_id === params.id)
      .slice(0, 3);
  }, [txQ.data, params.id]);

  if (!account) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top + us(8) }}>
        <View style={styles.headerRow}>
          <Pressable testID="acc-detail-back" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
        </View>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          {accountsQ.isLoading ? (
            <ActivityIndicator color={forest} />
          ) : (
            <Text style={{ color: colors.muted }}>{t("accounts.noAccounts")}</Text>
          )}
        </View>
      </View>
    );
  }

  const iconName = account.icon || ACCOUNT_ICON[account.type] || "wallet-outline";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + us(8),
          paddingBottom: insets.bottom + us(28),
          paddingHorizontal: us(spacing.lg),
        }}
        showsVerticalScrollIndicator={false}
      >
        {/* 1. Header */}
        <View style={styles.headerRow}>
          <Pressable testID="acc-detail-back" onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1 }} />
        </View>

        {/* Identity */}
        <View style={styles.identityRow}>
          <View style={[styles.identityIcon, { backgroundColor: ac }]}>
            <Ionicons name={iconName as any} size={us(30)} color="#fff" />
          </View>
          <View style={{ flex: 1, marginLeft: us(16), minWidth: 0 }}>
            <Text style={styles.accName}>{account.name}</Text>
            <View style={styles.typeRow}>
              <View style={[styles.typeDot, { backgroundColor: ac }]} />
              <Text style={styles.typeLabel}>{t(`accounts.types.${account.type}`)}</Text>
            </View>
          </View>
        </View>

        {/* 2. Current balance */}
        <View style={[styles.card, styles.balanceCard]}>
          <View style={[styles.balanceGlow, { backgroundColor: ac + "14" }]} pointerEvents="none" />
          <Ionicons name="wallet-outline" size={us(92)} color={ac} style={styles.balanceWallet} />
          <Text style={styles.balanceLabel}>{t("accounts.currentBalance")}</Text>
          <Text style={styles.balanceValue} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.5}>
            {formatCurrencyInt(account.current_balance || 0)}
          </Text>
        </View>

        {/* 3. Account information */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{t("accounts.accountInfo")}</Text>
          <InfoRow
            styles={styles}
            tileBg={colors.incomeGreen + "1A"}
            iconColor={forest}
            icon="wallet-outline"
            label={t("accounts.type")}
            value={t(`accounts.types.${account.type}`)}
          />
          <View style={styles.infoDivider} />
          <InfoRow
            styles={styles}
            tileBg={colors.incomeGreen + "1A"}
            iconColor={forest}
            icon="color-palette-outline"
            label={t("accounts.color")}
            rightNode={<View style={[styles.colorDot, { backgroundColor: ac }]} />}
          />
          <View style={styles.infoDivider} />
          <InfoRow
            styles={styles}
            tileBg={colors.incomeGreen + "1A"}
            iconColor={forest}
            icon="cash-outline"
            label={t("accounts.initialBalance")}
            value={formatCurrencyInt(account.initial_balance || 0)}
          />
        </View>

        {/* 4. Recent movements */}
        <View style={styles.card}>
          <View style={styles.mrHead}>
            <Text style={styles.cardTitle}>{t("transactions.recent")}</Text>
            <Pressable
              testID="acc-see-all"
              onPress={() => router.push("/(tabs)/transactions")}
              style={[styles.seePill, { backgroundColor: forest + "14" }]}
              hitSlop={8}
            >
              <Text style={[styles.seeText, { color: forest }]}>{t("common.seeAll")}</Text>
              <Ionicons name="chevron-forward" size={us(14)} color={forest} />
            </Pressable>
          </View>
          {accountTx.length === 0 && <Text style={styles.emptyTx}>{t("home.noMovements")}</Text>}
          {accountTx.map((item: any, idx: number) => {
            const cat = catById[item.category_id];
            const isIncome = item.type === "income" || item.type === "loan_received";
            const isTransfer = item.type === "transfer";
            const amtColor = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
            const sign = isTransfer ? "" : isIncome ? "+" : "-";
            const ic = cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
            const tint = cat?.color || amtColor;
            return (
              <View key={item.id}>
                {idx > 0 && <View style={styles.infoDivider} />}
                <Pressable
                  testID={`acc-tx-${item.id}`}
                  onPress={() => router.push(`/transactions/${item.id}`)}
                  style={styles.txRow}
                >
                  <IconTile icon={ic} tint={tint} size={us(36)} />
                  <View style={{ flex: 1, marginLeft: us(10), minWidth: 0 }}>
                    <Text style={styles.txName}>{item.name}</Text>
                    <Text style={styles.txDate}>{formatDateLong(item.date)}</Text>
                  </View>
                  <Text style={[styles.txAmount, { color: amtColor }]}>
                    {sign}{formatCurrencyInt(item.amount)}
                  </Text>
                  <Ionicons name="chevron-forward" size={us(15)} color={colors.muted} style={{ marginLeft: us(4) }} />
                </Pressable>
              </View>
            );
          })}
        </View>

        {/* 5. Edit account -> existing edit form (unchanged logic/route) */}
        <Pressable
          testID="acc-edit"
          onPress={() => router.push(`/accounts/new?id=${account.id}`)}
          style={[styles.editBtn, { backgroundColor: ac }]}
        >
          <Ionicons name="create-outline" size={us(20)} color="#fff" />
          <Text style={styles.editText}>{t("accounts.editAccount")}</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  headerRow: { flexDirection: "row", alignItems: "center", minHeight: 40, marginBottom: 6 },
  backBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  identityRow: { flexDirection: "row", alignItems: "center", marginTop: 6 },
  identityIcon: {
    width: 64,
    height: 64,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    ...Platform.select({
      ios: { shadowColor: "#000", shadowOpacity: scheme === "dark" ? 0.3 : 0.08, shadowRadius: 8, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 3 },
      default: {},
    }),
  },
  accName: { fontSize: 26, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.6 },
  typeRow: { flexDirection: "row", alignItems: "center", marginTop: 7, gap: 7 },
  typeDot: { width: 9, height: 9, borderRadius: 4.5 },
  typeLabel: { fontSize: 14, color: colors.muted, fontWeight: "600" },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 18,
    marginTop: 16,
    ...Platform.select({
      ios: { shadowColor: "#000", shadowOpacity: scheme === "dark" ? 0.22 : 0.04, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 1 },
      default: {},
    }),
  },
  balanceCard: { marginTop: 18, overflow: "hidden", paddingVertical: 22 },
  balanceGlow: { position: "absolute", right: -30, top: -30, width: 170, height: 170, borderRadius: 85 },
  balanceWallet: { position: "absolute", right: 16, bottom: 10, opacity: scheme === "dark" ? 0.16 : 0.12 },
  balanceLabel: { fontSize: 14, color: colors.muted, fontWeight: "600" },
  balanceValue: { fontSize: 40, fontWeight: "800", color: colors.onSurface, letterSpacing: -1, marginTop: 4 },
  cardTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.3, marginBottom: 6 },
  infoRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12 },
  infoTile: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  infoLabel: { flex: 1, marginLeft: 14, fontSize: 15, color: colors.muted, fontWeight: "600" },
  infoValue: { fontSize: 15, fontWeight: "800", color: colors.onSurface, maxWidth: 170, textAlign: "right" },
  colorDot: { width: 26, height: 26, borderRadius: 13 },
  infoDivider: { height: 1, backgroundColor: colors.divider, marginLeft: 54 },
  mrHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 2 },
  seePill: { flexDirection: "row", alignItems: "center", gap: 2, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14 },
  seeText: { fontSize: 13, fontWeight: "700" },
  emptyTx: { color: colors.muted, textAlign: "center", paddingVertical: 16, fontSize: 13 },
  txRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12 },
  txName: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  txDate: { fontSize: 12.5, color: colors.muted, marginTop: 2, fontWeight: "500" },
  txAmount: { fontSize: 15, fontWeight: "800" },
  editBtn: {
    marginTop: 22,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 16,
    borderRadius: radius.pill,
    ...Platform.select({
      ios: { shadowColor: "#000", shadowOpacity: scheme === "dark" ? 0.3 : 0.12, shadowRadius: 10, shadowOffset: { width: 0, height: 5 } },
      android: { elevation: 3 },
      default: {},
    }),
  },
  editText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
