import React, { useEffect, useState } from "react";
import { Alert, View, ScrollView, StyleSheet } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeMode } from "@/src/theme";
import { useTranslation, useLang, type Lang } from "@/src/i18n";
import { AppSheet } from "@/src/components/sheets";

import { us, ufs } from "@/src/ui-scale";
const CURRENCIES = ["USD", "EUR", "MXN", "COP", "ARS", "CLP"];

export default function Settings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { colors, mode, setMode } = useTheme();
  const { t } = useTranslation();
  const { lang, setLang } = useLang();
  const styles = useStyles();
  const q = useQuery({ queryKey: ["user"], queryFn: api.getUser });

  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [langOpen, setLangOpen] = useState(false);

  const THEMES: { id: ThemeMode; label: string; icon: string }[] = [
    { id: "light", label: t("settings.themeLight"), icon: "sunny-outline" },
    { id: "dark", label: t("settings.themeDark"), icon: "moon-outline" },
    { id: "system", label: t("settings.themeSystem"), icon: "phone-portrait-outline" },
  ];
  const LANGUAGES: { id: Lang; label: string }[] = [
    { id: "es", label: t("settings.spanish") },
    { id: "en", label: t("settings.english") },
  ];

  useEffect(() => {
    if (q.data) { setName(q.data.name || ""); setCurrency(q.data.currency || "USD"); }
  }, [q.data]);

  const save = async () => {
    await api.updateUser({ name, currency });
    qc.invalidateQueries({ queryKey: ["user"] });
    router.back();
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("settings.title")}</Text>
      </View>

      <Text style={styles.label}>{t("settings.name")}</Text>
      <TextInput value={name} onChangeText={setName} placeholder={t("settings.namePlaceholder")} placeholderTextColor={colors.muted} style={styles.input} />

      <Text style={styles.label}>{t("settings.currency")}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(8) }}>
        {CURRENCIES.map((c) => (
          <Pressable key={c} onPress={() => setCurrency(c)} style={[styles.currency, currency === c && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]}>
            <Text style={{ color: currency === c ? "#fff" : colors.onSurface, fontWeight: "700" }}>{c}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>{t("settings.appearance")}</Text>
      <View style={{ flexDirection: "row", gap: us(8) }}>
        {THEMES.map((t) => {
          const active = mode === t.id;
          return (
            <Pressable
              key={t.id}
              testID={`theme-${t.id}`}
              onPress={() => setMode(t.id)}
              style={[
                styles.themeBtn,
                active && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
              ]}
            >
              <Ionicons
                name={t.icon as any}
                size={us(18)}
                color={active ? "#fff" : colors.onSurface}
              />
              <Text
                style={{
                  color: active ? "#fff" : colors.onSurface,
                  fontWeight: "700",
                  marginTop: us(4),
                  fontSize: ufs(12),
                }}
              >
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <Text style={styles.label}>{t("settings.language")}</Text>
      <Pressable testID="language-row" onPress={() => setLangOpen(true)} style={styles.langRow}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(12) }}>
          <Ionicons name="language-outline" size={us(20)} color={colors.onSurface} />
          <Text style={styles.langRowLabel}>{t("settings.language")}</Text>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: us(6) }}>
          <Text style={styles.langRowValue}>{lang === "es" ? t("settings.spanish") : t("settings.english")}</Text>
          <Ionicons name="chevron-forward" size={us(18)} color={colors.muted} />
        </View>
      </Pressable>

      <Pressable testID="save-settings" onPress={save} style={styles.saveBtn}>
        <Text style={styles.saveText}>{t("common.save")}</Text>
      </Pressable>

      <Pressable
        testID="reseed"
        onPress={async () => {
          try {
            await api.seed();
            qc.invalidateQueries();
          } catch (error) {
            Alert.alert("Error", error instanceof Error ? error.message : String(error));
          }
        }}
        style={[styles.saveBtn, { marginTop: us(12), backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border }]}
      >
        <Text style={[styles.saveText, { color: colors.onSurface }]}>{t("settings.restoreSampleData")}</Text>
      </Pressable>

      <AppSheet visible={langOpen} onClose={() => setLangOpen(false)} testID="language-sheet">
        <Text style={styles.sheetTitle}>{t("settings.chooseLanguage")}</Text>
        {LANGUAGES.map((l) => {
          const active = lang === l.id;
          return (
            <Pressable
              key={l.id}
              testID={`language-option-${l.id}`}
              onPress={() => { setLang(l.id); setLangOpen(false); }}
              style={styles.langOption}
            >
              <Text style={[styles.langOptionText, active && { color: colors.brandPrimary, fontWeight: "800" }]}>{l.label}</Text>
              {active && <Ionicons name="checkmark" size={us(20)} color={colors.brandPrimary} />}
            </Pressable>
          );
        })}
      </AppSheet>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  currency: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  themeBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  saveBtn: { marginTop: 28, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  langRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.surfaceSecondary, paddingHorizontal: 14, paddingVertical: 14,
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  langRowLabel: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  langRowValue: { fontSize: 14, fontWeight: "600", color: colors.muted },
  sheetTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginBottom: 8, marginTop: 2 },
  langOption: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: colors.divider,
  },
  langOptionText: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
}));
