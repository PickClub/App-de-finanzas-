import React from "react";
import { View, Text, Pressable, ScrollView } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useTheme, makeStyles, radius } from "@/src/theme";

type Tile = {
  icon: string;
  label: string;
  subtitle: string;
  color: string;
  route?: string;
};

export default function More() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const go = (route?: string) => {
    if (route) router.push(route as any);
  };
  // Pastel card fill derived from the module accent — adapts to both themes.
  const tileBg = (c: string) => c + (scheme === "dark" ? "22" : "16");

  const MONEY: Tile[] = [
    { icon: "wallet-outline", label: "Cuentas", subtitle: "Gestiona tus cuentas bancarias y efectivo", color: colors.accountsBlue, route: "/accounts" },
    { icon: "pricetag-outline", label: "Categorías", subtitle: "Personaliza tus ingresos y gastos", color: colors.brandSecondary, route: "/categories" },
    { icon: "pie-chart-outline", label: "Presupuestos", subtitle: "Define límites y controla tus gastos", color: colors.expenseRed, route: "/budgets" },
    { icon: "flag-outline", label: "Metas de ahorro", subtitle: "Establece y sigue tus objetivos", color: colors.savingsTurquoise, route: "/goals" },
    { icon: "cash-outline", label: "Deudas y préstamos", subtitle: "Lleva el control de tus deudas", color: colors.loansYellow, route: "/debts" },
    { icon: "sync-outline", label: "Pagos recurrentes", subtitle: "Administra tus suscripciones", color: colors.statsPurple },
  ];

  const APP: Tile[] = [
    { icon: "settings-outline", label: "Ajustes", subtitle: "Preferencias de la app", color: colors.muted, route: "/settings" },
    { icon: "shield-checkmark-outline", label: "Privacidad y seguridad", subtitle: "Tus datos siempre protegidos", color: colors.accountsBlue },
    { icon: "help-circle-outline", label: "Centro de ayuda", subtitle: "Preguntas frecuentes y soporte", color: colors.success },
    { icon: "star-outline", label: "Califica la app", subtitle: "Tu opinión nos ayuda a mejorar", color: colors.warning },
    { icon: "information-circle-outline", label: "Acerca de MoneyFlow", subtitle: "Versión 1.0.0 · Hecho con amor", color: colors.info },
  ];

  const rows: Tile[][] = [
    [MONEY[0], MONEY[1]],
    [MONEY[2], MONEY[3]],
    [MONEY[4], MONEY[5]],
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + 14, paddingBottom: insets.bottom + 132 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1, paddingRight: 12 }}>
            <Text style={styles.title}>Más</Text>
            <Text style={styles.subtitle}>
              Todo lo que necesitas para personalizar tu experiencia en MoneyFlow.
            </Text>
          </View>
          <Pressable
            testID="more-profile"
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.profilePill, pressed && styles.pressed]}
          >
            <View style={styles.avatar}>
              <Ionicons name="person" size={16} color={colors.brandPrimary} />
            </View>
            <View style={{ marginHorizontal: 8 }}>
              <Text style={styles.profileHi}>Hola,</Text>
              <Text style={styles.profileName}>Usuario</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.muted} />
          </Pressable>
        </View>

        {/* Premium banner */}
        <Pressable testID="more-premium" style={({ pressed }) => [styles.banner, pressed && styles.pressed]}>
          <View style={styles.bannerIcon}>
            <Ionicons name="ribbon" size={26} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 14 }}>
            <Text style={styles.bannerTitle}>Saca más provecho de MoneyFlow</Text>
            <Text style={styles.bannerSub}>
              Descubre funciones premium para alcanzar tus metas más rápido.
            </Text>
          </View>
          <View style={styles.bannerBtn}>
            <Text style={styles.bannerBtnText}>Conocer más</Text>
          </View>
        </Pressable>

        {/* Tu dinero */}
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>Tu dinero</Text>
          <Text style={styles.sectionHint}>Organiza hoy un mejor mañana</Text>
        </View>
        <View style={styles.grid}>
          {rows.map((pair, ri) => (
            <View key={ri} style={styles.gridRow}>
              {pair.map((it) => (
                <Pressable
                  key={it.label}
                  testID={`more-${it.label}`}
                  onPress={() => go(it.route)}
                  style={({ pressed }) => [styles.tile, { backgroundColor: tileBg(it.color) }, pressed && styles.pressed]}
                >
                  <View style={styles.tileTop}>
                    <View style={[styles.tileIcon, { backgroundColor: it.color + "2E" }]}>
                      <Ionicons name={it.icon as any} size={20} color={it.color} />
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </View>
                  <Text style={styles.tileLabel} numberOfLines={1}>{it.label}</Text>
                  <Text style={styles.tileSub} numberOfLines={2}>{it.subtitle}</Text>
                </Pressable>
              ))}
            </View>
          ))}
        </View>

        {/* Aplicación */}
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>Aplicación</Text>
          <Text style={styles.sectionHint}>Personaliza tu experiencia</Text>
        </View>
        <View style={styles.appCard}>
          {APP.map((it, i) => (
            <Pressable
              key={it.label}
              testID={`more-${it.label}`}
              onPress={() => go(it.route)}
              style={({ pressed }) => [styles.appRow, i < APP.length - 1 && styles.appRowBorder, pressed && styles.pressed]}
            >
              <View style={[styles.appIcon, { backgroundColor: it.color + "24" }]}>
                <Ionicons name={it.icon as any} size={19} color={it.color} />
              </View>
              <View style={{ flex: 1, marginLeft: 14 }}>
                <Text style={styles.appLabel} numberOfLines={1}>{it.label}</Text>
                <Text style={styles.appSub} numberOfLines={1}>{it.subtitle}</Text>
              </View>
              <Ionicons name="chevron-forward" size={19} color={colors.muted} />
            </Pressable>
          ))}
        </View>

        {/* Suggestion */}
        <Pressable testID="more-suggestion" style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}>
          <View style={styles.suggIcon}>
            <Ionicons name="bulb-outline" size={22} color={colors.success} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 14 }}>
            <Text style={styles.suggTitle} numberOfLines={2}>¿Tienes alguna sugerencia?</Text>
            <Text style={styles.suggSub} numberOfLines={2}>Nos encantaría escucharla.</Text>
          </View>
          <View style={styles.suggBtn}>
            <Text style={styles.suggBtnText}>Enviar</Text>
          </View>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  container: { paddingHorizontal: 20 },
  pressed: { opacity: 0.65 },

  // Header
  header: { flexDirection: "row", alignItems: "flex-start", marginBottom: 22 },
  title: { fontSize: 30, fontWeight: "800", color: colors.onSurface, marginBottom: 5 },
  subtitle: { fontSize: 13.5, color: colors.muted, lineHeight: 19 },
  profilePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 8,
    paddingHorizontal: 11,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  profileHi: { fontSize: 11, color: colors.muted, lineHeight: 14 },
  profileName: { fontSize: 13.5, fontWeight: "700", color: colors.onSurface, lineHeight: 17 },

  // Banner
  banner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandTertiary,
    borderRadius: 22,
    padding: 16,
    marginBottom: 28,
  },
  bannerIcon: {
    width: 48,
    height: 48,
    borderRadius: 16,
    backgroundColor: colors.brandPrimary + "2E",
    alignItems: "center",
    justifyContent: "center",
  },
  bannerTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface, lineHeight: 20 },
  bannerSub: { fontSize: 12.5, color: scheme === "dark" ? colors.muted : colors.onSurfaceTertiary, lineHeight: 17, marginTop: 4, opacity: scheme === "dark" ? 1 : 0.8 },
  bannerBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: 16 },
  bannerBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "700" },

  // Section headers
  sectionHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginBottom: 14 },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  sectionHint: { fontSize: 12, color: colors.muted },

  // Grid (Tu dinero) — natural, consistent card heights
  grid: { gap: 12, marginBottom: 28 },
  gridRow: { flexDirection: "row", gap: 12 },
  tile: { flex: 1, minHeight: 128, borderRadius: 20, padding: 14, justifyContent: "flex-start" },
  tileTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  tileIcon: { width: 40, height: 40, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  tileLabel: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface, marginBottom: 4 },
  tileSub: { fontSize: 12, color: colors.muted, lineHeight: 16 },

  // App list
  appCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    marginBottom: 28,
    overflow: "hidden",
  },
  appRow: { flexDirection: "row", alignItems: "center", paddingVertical: 15 },
  appRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  appIcon: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  appLabel: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: 3 },
  appSub: { fontSize: 12.5, color: colors.muted, lineHeight: 16 },

  // Suggestion
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.success + (scheme === "dark" ? "1F" : "14"),
    borderRadius: 20,
    padding: 16,
  },
  suggIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.success + "26",
    alignItems: "center",
    justifyContent: "center",
  },
  suggTitle: { fontSize: 14.5, fontWeight: "800", color: colors.onSurface, marginBottom: 3, lineHeight: 19 },
  suggSub: { fontSize: 12.5, color: colors.muted, lineHeight: 16 },
  suggBtn: { backgroundColor: colors.success + (scheme === "dark" ? "2E" : "1F"), borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: 16 },
  suggBtnText: { color: colors.success, fontSize: 13, fontWeight: "700" },
}));
