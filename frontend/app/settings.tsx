import { localizedError } from "@/src/i18n/errors";
import { useTranslation, useLang, type Lang } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import React, { useRef, useState } from "react";
import { Animated, Platform, View, useWindowDimensions } from "react-native";
import { useReducedMotion } from "react-native-reanimated";
import { Alert } from "@/src/components/interaction-system";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing, type ThemeMode } from "@/src/theme";
import { useFonts } from "expo-font";
import { AppSheet, type SheetOrigin } from "@/src/components/sheets";
import { us } from "@/src/ui-scale";

const CURRENCIES = ["USD", "EUR", "MXN", "COP", "ARS", "CLP"];
const CURRENCY_SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", MXN: "$", COP: "$", ARS: "$", CLP: "$" };
const currencyLabel = (value: string) => CURRENCY_SYMBOLS[value] ? `${value} (${CURRENCY_SYMBOLS[value]})` : value;
const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export default function Settings() {
  const [fontsLoaded, fontError] = useFonts({
    ProfileMontserratRegular: require("../assets/fonts/Montserrat-Regular.ttf"),
    ProfileMontserratBold: require("../assets/fonts/Montserrat-Bold.ttf"),
  });
  const insets = useSafeAreaInsets();
  const { width, fontScale } = useWindowDimensions();
  const inlineAppearance = width >= 380 && fontScale <= 1.15;
  const router = useRouter();
  const qc = useQueryClient();
  const { colors, mode, setMode } = useTheme();
  const { t } = useTranslation();
  const { lang, setLang } = useLang();
  const styles = useStyles();
  const q = useQuery({ queryKey: ["user"], queryFn: api.getUser });
  const [editor, setEditor] = useState<"name" | "currency" | null>(null);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const [langOpen, setLangOpen] = useState(false);
  const [languageSaving, setLanguageSaving] = useState(false);
  const languageBusy = useRef(false);
  const restoring = useRef(false);
  const reduceMotion = useReducedMotion();
  const themeScaleRef = useRef<Record<ThemeMode, Animated.Value> | null>(null);
  if (!themeScaleRef.current) themeScaleRef.current = { light: new Animated.Value(1), dark: new Animated.Value(1), system: new Animated.Value(1) };
  const themeScales = themeScaleRef.current;
  const currencyRow = useRef<View>(null);
  const languageRow = useRef<View>(null);
  const nameRow = useRef<View>(null);
  const editorField = useRef<"name" | "currency">("currency");
  const selectorRequest = useRef(0);
  const [editorOrigin, setEditorOrigin] = useState<SheetOrigin>();
  const [languageOrigin, setLanguageOrigin] = useState<SheetOrigin>();
  const animateThemePress = (theme: ThemeMode, pressed: boolean) => {
    const scale = themeScales[theme];
    scale.stopAnimation();
    if (reduceMotion) { scale.setValue(1); return; }
    Animated.spring(scale, { toValue: pressed ? 0.95 : 1, useNativeDriver: Platform.OS !== "web", speed: pressed ? 50 : 20, bounciness: pressed ? 0 : 12 }).start();
  };
  const openSelector = (field: "name" | "currency" | "language") => {
    const request = ++selectorRequest.current;
    const trigger = field === "name" ? nameRow.current : field === "currency" ? currencyRow.current : languageRow.current;
    const open = (origin?: SheetOrigin) => {
      if (field === "language") { setLanguageOrigin(origin); setLangOpen(true); }
      else openEditor(field, origin);
    };
    if (!trigger) { open(); return; }
    trigger.measureInWindow((x, y, width, height) => {
      if (request !== selectorRequest.current) return;
      if ((field === "name" ? nameRow.current : field === "currency" ? currencyRow.current : languageRow.current) !== trigger) return;
      open([x, y, width, height].every(Number.isFinite) && width > 0 && height > 0 ? { x: x + width / 2, y: y + height / 2 } : undefined);
    });
  };

  const THEMES: { id: ThemeMode; label: string }[] = [
    { id: "light", label: t("settings.themeLight") },
    { id: "dark", label: t("settings.themeDark") },
    { id: "system", label: t("settings.themeSystem") },
  ];
  const LANGUAGES: { id: Lang; label: string }[] = [
    { id: "en-US", label: t("settings.english") },
    { id: "es", label: t("settings.spanish") },
  ];
  const openEditor = (field: "name" | "currency", origin?: SheetOrigin) => {
    setEditorOrigin(origin);
    // Keep the name input and keyboard mounted throughout the exit transition.
    editorField.current = field;
    setName(q.data?.name ?? "");
    setCurrency(q.data?.currency ?? "USD");
    setEditor(field);
  };
  const closeEditor = () => { if (!busy.current) setEditor(null); };
  const save = async () => {
    if (!editor || busy.current) return;
    busy.current = true;
    setSaving(true);
    try {
      // Send only the edited field; never overwrite an unrelated preference.
      const user = await api.updateUser(editor === "name" ? { name } : { currency });
      qc.setQueryData(["user"], user);
      void qc.invalidateQueries({ queryKey: ["user"] });
      setEditor(null);
    } catch (error) {
      Alert.alert(t("common.error"), localizedError(error instanceof Error ? error.message : String(error)));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };
  const confirmRestore = () => Alert.alert(t("settings.restoreSampleData"), t("settings.restoreConfirmation"), [
    { text: t("common.cancel"), style: "cancel" },
    { text: t("common.confirm"), style: "destructive", onPress: async () => {
      if (restoring.current) return;
      restoring.current = true;
      try { await api.seed(); void qc.invalidateQueries(); }
      catch (error) { Alert.alert(t("common.error"), localizedError(error instanceof Error ? error.message : String(error))); }
      finally { restoring.current = false; }
    } },
  ]);

  const row = (id: string, icon: string, label: string, value?: string, onPress?: () => void, divider = false) => (
    <Pressable ref={id === "profile-name" ? nameRow : id === "currency-row" ? currencyRow : id === "language-row" ? languageRow : undefined} testID={id} accessibilityRole={onPress ? "button" : "text"} accessibilityLabel={value ? `${label}: ${value}` : label}
      disabled={!onPress} onPress={onPress} style={styles.row}>
      {divider && <View pointerEvents="none" style={styles.divider} />}
      <Ionicons name={icon as any} size={us(20)} color={colors.identityAccent} />
      <Text style={styles.rowLabel}>{label}</Text>
      {value !== undefined && <Text style={styles.rowValue} numberOfLines={1}>{value}</Text>}
      {onPress && <Ionicons name="chevron-forward" size={us(16)} color={colors.muted} />}
    </Pressable>
  );
  const email = typeof q.data?.email === "string" ? q.data.email.trim() : "";

  if (!fontsLoaded) return <View style={{ flex: 1, backgroundColor: colors.pageBackground, paddingTop: insets.top + us(16), paddingHorizontal: us(spacing.lg) }}>
    <MoneyFlowHeaderActions onBack={() => router.back()} />
    <Text>{fontError ? t("settings.loadError") : t("common.loading")}</Text>
  </View>;

  return (
    <ElasticScrollView {...NATIVE_VERTICAL_SCROLL} keyboardShouldPersistTaps="handled" style={{ flex: 1, backgroundColor: colors.pageBackground }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: insets.bottom + us(100), paddingHorizontal: us(spacing.lg) }}>
      <View style={styles.header}>
        <MoneyFlowHeaderActions title={<Text style={[styles.title, { flex: 1 }]}>{t("settings.profileTitle")}</Text>} onBack={() => router.back()} />
      </View>

      {!q.data ? <View style={styles.card}>
        <Text style={styles.status}>{q.isError ? t("settings.loadError") : t("common.loading")}</Text>
        {q.isError && <Pressable testID="profile-retry" onPress={() => { void q.refetch(); }} style={styles.saveBtn}><Text style={styles.saveText}>{t("settings.retry")}</Text></Pressable>}
      </View> : <>
        <View style={[styles.card, styles.profile]}>
          <View style={styles.avatar}>
            <Ionicons name="person-outline" size={us(32)} color="#FFFFFF" />
            <Pressable testID="profile-edit" accessibilityLabel={t("settings.editName")} onPress={() => openEditor("name")} style={styles.editIcon}>
              <Ionicons name="create-outline" size={us(17)} color={colors.identityAccent} />
            </Pressable>
          </View>
          <View style={styles.userInfo}>
            <Text style={styles.userName}>{q.data.name}</Text>
            {email !== "" && <Text testID="profile-email" style={styles.email}>{email}</Text>}
          </View>

        </View>

        <Text style={styles.section}>{t("settings.personalInformation")}</Text>
        <View style={styles.card}>
          {row("profile-name", "person-outline", t("settings.name"), q.data.name, () => openSelector("name"))}
          {email !== "" && row("profile-email-row", "mail-outline", t("settings.email"), email, undefined, true)}
        </View>

        <Text style={styles.section}>{t("settings.preferences")}</Text>
        <View style={styles.card}>
          {row("currency-row", "cash-outline", t("settings.currency"), currencyLabel(q.data.currency || "USD"), () => openSelector("currency"))}
          <View testID="profile-appearance" style={[styles.appearance, inlineAppearance && styles.appearanceInline]}>
            <View pointerEvents="none" style={styles.divider} />
            <View style={styles.appearanceLabel}><Ionicons name="sunny-outline" size={us(20)} color={colors.identityAccent} /><Text style={styles.rowLabel}>{t("settings.appearance")}</Text></View>
            <View accessibilityRole="radiogroup" style={[styles.segment, inlineAppearance && { flex: 1 }]}>
              {THEMES.map(theme => <AnimatedPressable key={theme.id} testID={`theme-${theme.id}`} accessibilityRole="radio" accessibilityState={{ checked: mode === theme.id }} onPressIn={() => animateThemePress(theme.id, true)} onPressOut={() => animateThemePress(theme.id, false)} onPress={() => setMode(theme.id)} style={[styles.themeBtn, mode === theme.id && styles.selected, { transform: [{ scale: themeScales[theme.id] }] }]}>
                <Text style={[styles.themeText, mode === theme.id && styles.selectedText]}>{theme.label}</Text>
              </AnimatedPressable>)}
            </View>
          </View>
          {row("language-row", "language-outline", t("settings.language"), lang === "es" ? t("settings.spanish") : t("settings.english"), () => openSelector("language"), true)}
        </View>
      </>}

      <Text style={styles.section}>{t("settings.dataStorage")}</Text>
      <View style={styles.card}>
        <Pressable testID="reseed" accessibilityRole="button" onPress={confirmRestore} style={styles.row}>
          <Ionicons name="server-outline" size={us(20)} color={colors.identityAccent} />
          <Text style={[styles.rowLabel, { flex: 1 }]}>{t("settings.restoreSampleData")}</Text>
          <Ionicons name="chevron-forward" size={us(16)} color={colors.muted} />
        </Pressable>
      </View>

      <AppSheet visible={editor !== null} onClose={closeEditor} testID="profile-editor" origin={editorOrigin}>
        <Text style={styles.sheetTitle}>{editorField.current === "name" ? t("settings.editName") : t("settings.currency")}</Text>
        {editorField.current === "name" ? <TextInput testID="profile-name-input" accessibilityLabel={t("settings.name")} value={name} onChangeText={setName} editable={!saving} placeholder={t("settings.namePlaceholder")} placeholderTextColor={colors.muted} style={styles.input} /> : <View style={styles.currencyOptions}>
          {CURRENCIES.map(c => <Pressable key={c} testID={`currency-${c}`} accessibilityRole="radio" accessibilityState={{ checked: currency === c }} disabled={saving} onPress={() => setCurrency(c)} style={[styles.currency, currency === c && styles.selected]}><Text style={[styles.rowLabel, currency === c && styles.selectedText]}>{currencyLabel(c)}</Text></Pressable>)}
        </View>}
        <View style={styles.editorActions}>
          <Pressable testID="profile-editor-cancel" disabled={saving} onPress={closeEditor} style={styles.cancelBtn}><Text style={styles.rowLabel}>{t("common.cancel")}</Text></Pressable>
          <Pressable testID="save-settings" disabled={saving} accessibilityState={{ disabled: saving }} onPress={save} style={styles.saveBtn}><Text style={styles.saveText}>{saving ? t("common.loading") : t("common.save")}</Text></Pressable>
        </View>
      </AppSheet>

      <AppSheet visible={langOpen} onClose={() => { if (!languageBusy.current) setLangOpen(false); }} testID="language-sheet" origin={languageOrigin}>
        <Text style={styles.sheetTitle}>{t("settings.chooseLanguage")}</Text>
        {LANGUAGES.map(l => <Pressable key={l.id} testID={`language-option-${l.id}`} disabled={languageSaving} accessibilityRole="radio" accessibilityState={{ checked: lang === l.id, disabled: languageSaving }}
          onPress={async () => {
            if (languageBusy.current) return;
            languageBusy.current = true; setLanguageSaving(true);
            try { await setLang(l.id); setLangOpen(false); }
            catch { Alert.alert(t("common.error"), t("errors.languagePreference")); }
            finally { languageBusy.current = false; setLanguageSaving(false); }
          }} style={styles.langOption}>
          <Text style={[styles.rowLabel, lang === l.id && { color: colors.identityAccent }]}>{l.label}</Text>
          {lang === l.id && <Ionicons name="checkmark" size={us(20)} color={colors.identityAccent} />}
        </Pressable>)}
      </AppSheet>
    </ElasticScrollView>
  );
}

const useStyles = makeStyles(colors => ({
  header: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 16 },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { fontFamily: "ProfileMontserratBold", flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, borderWidth: 1, borderColor: colors.identityAccent + "14", paddingHorizontal: 16 },
  profile: { flexDirection: "row", alignItems: "center", gap: 20, paddingVertical: 18 },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.identityAccent, alignItems: "center", justifyContent: "center" },
  userInfo: { flex: 1, minWidth: 0 },
  userName: { fontFamily: "ProfileMontserratBold", fontSize: 18, fontWeight: "700", color: colors.onSurface, flexShrink: 1 },
  email: { fontFamily: "ProfileMontserratRegular", fontSize: 12, color: colors.muted, marginTop: 4 },
  editIcon: { position: "absolute", bottom: -3, right: -5, width: 30, height: 30, borderRadius: 15, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  section: { fontFamily: "ProfileMontserratBold", fontSize: 11, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.7, marginTop: 20, marginBottom: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 56, paddingVertical: 14 },
  divider: { position: "absolute", left: 32, right: 0, top: 0, height: 1, backgroundColor: colors.divider, opacity: 0.65 },
  rowLabel: { fontFamily: "ProfileMontserratBold", color: colors.onSurface, fontSize: 13, fontWeight: "600", flexShrink: 1 },
  rowValue: { fontFamily: "ProfileMontserratRegular", color: colors.muted, fontSize: 12, flex: 1, textAlign: "right", minWidth: 0 },
  appearance: { paddingVertical: 12, gap: 10 },
  appearanceInline: { flexDirection: "row", alignItems: "center", gap: 12 },
  appearanceLabel: { flexDirection: "row", alignItems: "center", gap: 12, flexShrink: 0 },
  segment: { flexDirection: "row", minWidth: 0, gap: 4 },
  themeBtn: { flex: 1, minHeight: 44, justifyContent: "center", alignItems: "center", borderRadius: radius.pill, paddingHorizontal: 6, paddingVertical: 6, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  themeText: { fontFamily: "ProfileMontserratBold", fontSize: 11.5, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
  selected: { backgroundColor: colors.identityAccent, borderColor: colors.identityAccent },
  selectedText: { color: "#FFFFFF" },
  sheetTitle: { fontFamily: "ProfileMontserratBold", fontSize: 18, fontWeight: "700", color: colors.onSurface, marginBottom: 12 },
  input: { fontFamily: "ProfileMontserratRegular", fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, minHeight: 48 },
  currencyOptions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  currency: { paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.md, backgroundColor: colors.pageBackground, minHeight: 44 },
  editorActions: { flexDirection: "row", gap: 12, marginTop: 16 },
  saveBtn: { flexGrow: 1, backgroundColor: colors.primaryAction, padding: 12, borderRadius: radius.md, alignItems: "center", minHeight: 44 },
  cancelBtn: { flexGrow: 1, backgroundColor: colors.secondaryActionBackground, padding: 12, borderRadius: radius.md, alignItems: "center", minHeight: 44 },
  saveText: { fontFamily: "ProfileMontserratBold", color: "#FFFFFF", fontSize: 14, fontWeight: "700" },
  langOption: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, paddingVertical: 16, minHeight: 48, borderBottomWidth: 1, borderBottomColor: colors.divider },
  status: { fontFamily: "ProfileMontserratRegular", color: colors.muted, paddingVertical: 16, fontSize: 14 },
}));
