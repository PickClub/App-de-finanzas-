import React, { useEffect, useState } from "react";
import { View, ScrollView, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useAccountDeletionExit } from "@/src/account-deletion-navigation";
import { useResourceDeletion } from "@/src/use-resource-deletion";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { useTranslation } from "@/src/i18n";

import { us } from "@/src/ui-scale";
import { COLOR_PALETTE } from "@/src/color-palette";

// Local visual identity (same light-mode values used by Home / Nueva deuda:
// sage background, warm-white cards, forest green, mint badges). Dark mode
// falls back to the global dark theme tokens.
function formPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    dark,
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    field: dark ? colors.surface : "#FFFFFF",
    forest: dark ? colors.incomeGreen : "#126046",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    mintSoft: dark ? colors.incomeGreen + "14" : "#EEF5EF",
    onSurface: dark ? colors.onSurface : "#15251E",
    muted: dark ? colors.muted : "#68746D",
    border: dark ? colors.border : "rgba(39,71,56,0.10)",
  };
}

// Visual-only accent per account type (internal ids/icons unchanged).
const TYPE_ACCENT: Record<string, { light: string; dark: string }> = {
  cash: { light: "#126046", dark: "#37C08D" },
  checking: { light: "#4C83EA", dark: "#6D9BFF" },
  savings: { light: "#8F5BE8", dark: "#A57DFF" },
  credit_card: { light: "#FF8A3D", dark: "#FF9C5A" },
  wallet: { light: "#29C4A9", dark: "#3ED4B9" },
  other: { light: "#8E8883", dark: "#9E9791" },
};
const TYPE_IDS = [
  { id: "cash", icon: "cash-outline" },
  { id: "checking", icon: "card-outline" },
  { id: "savings", icon: "wallet-outline" },
  { id: "credit_card", icon: "card-outline" },
  { id: "wallet", icon: "phone-portrait-outline" },
  { id: "other", icon: "ellipsis-horizontal-outline" },
];
// Shared 20-color palette; DEFAULT_COLOR keeps this screen's previous default.
const COLORS = COLOR_PALETTE;
const DEFAULT_COLOR = "#4C83EA";

export default function AccountForm() {
  const { colors, scheme } = useTheme();
  const { t, i18n } = useTranslation();
  const styles = useStyles();
  const pal = formPalette(colors, scheme);
  const isEn = (i18n?.language || "es").startsWith("en");
  const [saving, setSaving] = useState(false);
  const savingRef = React.useRef(false);
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const exitAfterRemoval = useAccountDeletionExit(params.id);
  const deletion = useResourceDeletion("/accounts", [["accounts"], ["transactions"], ["categories"], ["debts"], ["debt-payments"], ["debt"], ["summary"]], exitAfterRemoval);
  const [loadedId, setResourceLoaded] = useState<string>();
  const resourceLoaded = loadedId === params.id;

  const [name, setName] = useState("");
  const [type, setType] = useState("cash");
  const [balance, setBalance] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [icon, setIcon] = useState("wallet-outline");

  useEffect(() => {
    if (params.id) {
      api.listAccounts().then((all) => {
        const a = all.find((x: any) => x.id === params.id);
        if (!a) { deletion.unavailable(); return; }
        if (a) {
          setResourceLoaded(params.id);
          setName(a.name);
          setType(a.type);
          setBalance(String(a.initial_balance));
          setColor(a.color);
          setIcon(a.icon);
        }
      }).catch((error) => Alert.alert("No se pudo cargar", error instanceof Error ? error.message : "Inténtalo de nuevo."));
    }
  }, [params.id]);

  const save = async () => {
    if (deletion.locked.current || (params.id && !resourceLoaded)) return;
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
    if (savingRef.current) return; // prevent duplicate saves
    savingRef.current = true;
    setSaving(true);
    try {
      if (params.id) await api.updateAccount(params.id as string, payload);
      else await api.createAccount(payload);
      qc.invalidateQueries();
      router.back();
    } catch (error) {
      // Keep the entered data; just report the error.
      Alert.alert(isEn ? "Could not save" : "No se pudo guardar", error instanceof Error ? error.message : (isEn ? "Please try again." : "Inténtalo de nuevo."));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!params.id) return;
    await deletion.remove(() => api.deleteAccount(params.id as string));
  };

  if (params.id && (!resourceLoaded || deletion.deleted.current)) return <View />;

  const shadow = pal.dark ? null : styles.softShadow;
  const cardStyle = [styles.card, { backgroundColor: pal.card, borderColor: pal.border }, shadow];

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: pal.bg }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
    <ScrollView pointerEvents={deletion.busy ? "none" : "auto"} keyboardShouldPersistTaps="handled" style={{ flex: 1, backgroundColor: pal.bg }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(32), paddingHorizontal: us(spacing.lg) }}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={[styles.backBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
          <Ionicons name="chevron-back" size={us(24)} color={pal.forest} />
        </Pressable>
        <Text style={[styles.title, { color: pal.dark ? pal.onSurface : pal.forest }]} numberOfLines={1}>{params.id ? t("accounts.editAccount") : t("accounts.newAccount")}</Text>
        {params.id && (
          <Pressable onPress={remove} disabled={deletion.busy} style={[styles.backBtn, { backgroundColor: pal.card, borderColor: pal.border }, shadow]}>
            <Ionicons name="trash-outline" size={us(22)} color={colors.expenseRed} />
          </Pressable>
        )}
      </View>

      {/* Nombre de la cuenta */}
      <View style={[cardStyle, styles.fieldRow]}>
        <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
          <Ionicons name="document-text-outline" size={us(24)} color={pal.forest} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.label, { color: pal.muted }]}>{isEn ? "Account name" : "Nombre de la cuenta"}</Text>
          <TextInput testID="acc-name" value={name} onChangeText={setName} placeholder={isEn ? "e.g. My Chase account" : "Ej. Mi cuenta Chase"} placeholderTextColor={pal.muted} style={[styles.input, { backgroundColor: pal.field, borderColor: pal.border, color: pal.onSurface }]} />
        </View>
      </View>

      {/* Saldo inicial */}
      <View style={[cardStyle, styles.fieldRow]}>
        <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
          <Ionicons name="logo-usd" size={us(26)} color={pal.forest} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.label, { color: pal.muted }]}>{t("accounts.initialBalance")}</Text>
          <View style={[styles.amountBox, { backgroundColor: pal.field, borderColor: pal.border }]}>
            <Text style={[styles.amountText, { color: pal.forest }]}>$</Text>
            <TextInput testID="acc-balance" value={balance} onChangeText={setBalance} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={pal.forest + "99"} style={[styles.amountText, styles.amountInput, { color: pal.forest }]} />
          </View>
        </View>
      </View>

      {/* Tipo de cuenta */}
      <View style={cardStyle}>
        <Text style={[styles.label, styles.sectionLabel, { color: pal.muted }]}>{isEn ? "Account type" : "Tipo de cuenta"}</Text>
        <View style={styles.grid}>
          {TYPE_IDS.map((ty) => {
            const sel = type === ty.id;
            const acc = TYPE_ACCENT[ty.id]?.[pal.dark ? "dark" : "light"] || pal.forest;
            return (
              <Pressable
                key={ty.id}
                testID={`acc-type-${ty.id}`}
                accessibilityRole="radio"
                accessibilityState={{ selected: sel }}
                onPress={() => { setType(ty.id); setIcon(ty.icon); }}
                style={[styles.typeItem, { backgroundColor: sel ? pal.mintSoft : pal.card, borderColor: sel ? pal.forest : pal.border, borderWidth: sel ? 1.5 : 1 }]}
              >
                <View style={[styles.typeIcon, { backgroundColor: acc + (pal.dark ? "29" : "1F") }]}>
                  <Ionicons name={ty.icon as any} size={us(22)} color={acc} />
                </View>
                <Text style={[styles.typeText, { color: pal.onSurface }]} numberOfLines={1}>{t(`accounts.types.${ty.id}`)}</Text>
                {sel && (
                  <View style={[styles.check, { backgroundColor: pal.forest }]}>
                    <Ionicons name="checkmark" size={us(16)} color="#fff" />
                  </View>
                )}
              </Pressable>
            );
          })}
        </View>
      </View>

      {/* Color de la cuenta */}
      <View style={cardStyle}>
        <Text style={[styles.label, styles.sectionLabel, { color: pal.muted }]}>{isEn ? "Account color" : "Color de la cuenta"}</Text>
        <View style={styles.swatches}>
          {COLORS.map((c) => {
            const sel = color === c;
            return (
              <Pressable key={c} testID={`acc-color-${c}`} accessibilityRole="radio" accessibilityState={{ selected: sel }} onPress={() => setColor(c)} style={[styles.swatchRing, { borderColor: sel ? pal.forest : "transparent" }]}>
                <View style={[styles.swatch, { backgroundColor: c }]}>
                  {sel && <Ionicons name="checkmark" size={us(22)} color="#fff" />}
                </View>
              </Pressable>
            );
          })}
        </View>
      </View>

      <Pressable testID="save-account" onPress={save} disabled={saving} style={[styles.saveBtn, { backgroundColor: pal.forest, opacity: saving ? 0.7 : 1 }, shadow]}>
        <Text style={[styles.saveText, { color: pal.dark ? colors.onSuccess : "#fff" }]}>{isEn ? "Save account" : "Guardar cuenta"}</Text>
      </Pressable>
    </ScrollView>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles(() => ({
  header: { flexDirection: "row", alignItems: "center", gap: 14, marginBottom: 16 },
  backBtn: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  title: { flex: 1, fontSize: 24, fontWeight: "800" },
  softShadow: Platform.select({
    web: { boxShadow: "0px 2px 10px rgba(18,96,70,0.06)" } as any,
    default: { shadowColor: "#126046", shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  }),
  card: { borderRadius: 22, borderWidth: 1, padding: 14, marginBottom: 12 },
  fieldRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  fieldIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center" },
  label: { fontSize: 12, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 8 },
  sectionLabel: { marginLeft: 2, marginBottom: 10 },
  input: { fontSize: 15, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 16, borderWidth: 1 },
  amountBox: { flexDirection: "row", alignItems: "center", borderRadius: 16, borderWidth: 1, paddingHorizontal: 14, minHeight: 56 },
  amountText: { fontSize: 28, fontWeight: "800" },
  amountInput: { flex: 1, marginLeft: 8, paddingVertical: 6, minWidth: 0, ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as any) : null) },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10 },
  typeItem: { width: "48.5%", flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 10, paddingVertical: 10, borderRadius: 18, minHeight: 60 },
  typeIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  typeText: { flex: 1, fontSize: 14, fontWeight: "600" },
  check: { width: 26, height: 26, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  swatches: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  swatchRing: { width: 48, height: 48, borderRadius: 24, borderWidth: 3, alignItems: "center", justifyContent: "center" },
  swatch: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  saveBtn: { marginTop: 8, marginHorizontal: 4, minHeight: 56, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  saveText: { fontWeight: "800", fontSize: 17 },
}));
