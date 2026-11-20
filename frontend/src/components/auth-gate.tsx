import { resumeDeletedJournals } from "@/src/private-journal";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { ActivityIndicator, KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import * as Linking from "expo-linking";
import { accountFormFromLink, type AccountForm } from "@/src/account-links";
import { SafeAreaView } from "react-native-safe-area-context";
import { Pressable } from "@/src/components/pressable";
import { useTranslation } from "@/src/i18n";
import { useTheme } from "@/src/theme";
import { AuthSessionError, authState, restoreAuth, signIn, subscribeAuth, redeemAccountCode } from "@/src/auth-session";

export function AuthGate({ children }: { children: ReactNode }) {
  const session = useSyncExternalStore(subscribeAuth, authState);
  const { colors } = useTheme();
  const [linkedForm, setLinkedForm] = useState<AccountForm>("login");
  useEffect(() => {
    let active = true;
    const select = (url: string | null) => {
      const form = accountFormFromLink(url);
      if (active && form) setLinkedForm(form);
    };
    void Linking.getInitialURL().then(select).catch(() => {});
    const listener = Linking.addEventListener("url", event => select(event.url));
    void resumeDeletedJournals().catch(() => {});
    void restoreAuth();
    return () => { active = false; listener.remove(); };
  }, []);
  if (session.status === "loading") {
    return <View style={[styles.loading, { backgroundColor: colors.pageBackground }]}>
      <ActivityIndicator color={colors.primaryAction} />
    </View>;
  }
  if (session.status === "signed-in") {
    return <View key={session.identity?.user_id} style={styles.fill}>{children}</View>;
  }
  return <SignIn deletion={session.deletion} linkedForm={linkedForm} removalUnconfirmed={session.removalUnconfirmed} />;
}

function SignIn({ removalUnconfirmed, linkedForm, deletion }: { removalUnconfirmed?: boolean; linkedForm: AccountForm; deletion?: "confirmed" | "device-pending" }) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [form, setForm] = useState<AccountForm>(linkedForm);
  const [code, setCode] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [completed, setCompleted] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<"invalid" | "unavailable">();
  useEffect(() => { setForm(linkedForm); setCode(""); setPassword(""); setConfirmation(""); setCompleted(false); setError(undefined); }, [linkedForm]);
  async function submit() {
    if (busy || !password || (form === "login" && !email.trim())) return;
    if (form !== "login" && (password !== confirmation || !code.trim())) { setError("invalid"); return; }
    setBusy(true);
    setError(undefined);
    try {
      if (form === "login") await signIn(email, password);
      else {
        await redeemAccountCode(form, code.trim(), password);
        setCode(""); setCompleted(true); setForm("login");
      }
    } catch (reason) {
      setError(reason instanceof AuthSessionError && reason.reason === "invalid" ? "invalid" : "unavailable");
    } finally {
      setPassword("");
      setConfirmation("");
      setBusy(false);
    }
  }
  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: colors.pageBackground }]}>
      <KeyboardAvoidingView style={styles.fill} behavior="height">
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.body}>
          <Text style={[styles.title, { color: colors.primaryAction }]}>{t("auth.brand")}</Text>
          {form === "login" && <><Text style={[styles.label, { color: colors.onSurface }]}>{t("auth.email")}</Text>
          <TextInput accessibilityLabel={t("auth.email")} autoCapitalize="none" autoCorrect={false}
            autoComplete="email" keyboardType="email-address" value={email} onChangeText={setEmail}
            style={[styles.input, { color: colors.onSurface, borderColor: colors.primaryAction }]} /></>}
          {form !== "login" && <>
            <Text style={[styles.label, { color: colors.onSurface }]}>{t(form === "invite" ? "auth.invitationCode" : "auth.recoveryCode")}</Text>
            <Text style={{ color: colors.onSurface }}>{t("auth.operatorCodeHelp")}</Text>
            <TextInput accessibilityLabel={t("auth.accountCode")} autoCapitalize="none" autoCorrect={false}
              secureTextEntry autoComplete="off" importantForAutofill="no" value={code} onChangeText={setCode} maxLength={64}
              style={[styles.input, { color: colors.onSurface, borderColor: colors.primaryAction }]} />
            <Text style={{ color: colors.onSurface }}>{t("auth.passwordPolicy")}</Text>
          </>}
          <Text style={[styles.label, { color: colors.onSurface }]}>{t("auth.password")}</Text>
          <TextInput accessibilityLabel={t("auth.password")} autoComplete={form === "login" ? "current-password" : "new-password"} secureTextEntry
            maxLength={256}
            value={password} onChangeText={setPassword} onSubmitEditing={() => void submit()}
            style={[styles.input, { color: colors.onSurface, borderColor: colors.primaryAction }]} />
          {form !== "login" && <TextInput accessibilityLabel={t("auth.confirmPassword")} secureTextEntry
            autoComplete="new-password" value={confirmation} onChangeText={setConfirmation} maxLength={256}
            style={[styles.input, { color: colors.onSurface, borderColor: colors.primaryAction }]} />}
          {completed && <Text accessibilityLiveRegion="polite" style={{ color: colors.onSurface }}>{t("auth.accountReady")}</Text>}
          {deletion && <Text accessibilityLiveRegion="polite" style={{ color: colors.onSurface }}>
            {t(deletion === "confirmed" ? "accountDeletion.confirmed" : "accountDeletion.devicePending")}
          </Text>}
          {removalUnconfirmed && <Text accessibilityLiveRegion="polite" style={{ color: colors.onSurface }}>
            {t("auth.signOutUnconfirmed")}
          </Text>}
          {error && <Text accessibilityLiveRegion="polite" style={{ color: colors.onSurface }}>
            {error === "invalid" ? t(form === "login" ? "auth.invalid" : "auth.codeInvalid") : t("auth.unavailable")}
          </Text>}
          <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy }}
            disabled={busy} onPress={() => void submit()}
            style={[styles.button, { backgroundColor: colors.primaryAction }]}>
            <Text style={styles.buttonLabel}>{busy ? t("auth.signingIn") : t(form === "login" ? "auth.signIn" : "auth.setPassword")}</Text>
          </Pressable>
          {(["login", "invite", "recover"] as const).filter(option => option !== form).map(option => (
            <Pressable key={option} accessibilityRole="button" disabled={busy} onPress={() => {
              setForm(option); setCode(""); setPassword(""); setConfirmation(""); setError(undefined); setCompleted(false);
            }} style={styles.button}>
              <Text style={{ color: colors.primaryAction }}>{t(option === "login" ? "auth.backToSignIn" : option === "invite" ? "auth.useInvitation" : "auth.recoverAccount")}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  loading: { flex: 1, justifyContent: "center", alignItems: "center" },
  body: { flexGrow: 1, justifyContent: "center", padding: 28, gap: 12 },
  title: { fontFamily: "AuthMontserratBold", fontSize: 34, marginBottom: 20 },
  label: { fontFamily: "AuthMontserratBold", fontSize: 14 },
  input: { fontFamily: "AuthMontserrat", borderWidth: 1, borderRadius: 12, padding: 12, minHeight: 48 },
  button: { borderRadius: 12, padding: 14, alignItems: "center", marginTop: 8 },
  buttonLabel: { fontFamily: "AuthMontserratBold", color: "#fff" },
});
