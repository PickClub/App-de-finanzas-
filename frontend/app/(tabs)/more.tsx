import React from "react";
import { View, Text, Pressable } from "react-native";
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
      <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1, paddingRight: 10 }}>
            <Text style={styles.title}>Más</Text>
            <Text style={styles.subtitle} numberOfLines={2}>
              Todo lo que necesitas para personalizar tu experiencia en MoneyFlow.
            </Text>
          </View>
          <Pressable
            testID="more-profile"
            onPress={() => go("/settings")}
            style={({ pressed }) => [styles.profilePill, pressed && styles.pressed]}
          >
            <View style={styles.avatar}>
              <Ionicons name="person" size={15} color={colors.brandPrimary} />
            </View>
            <View style={{ marginHorizontal: 7 }}>
              <Text style={styles.profileHi}>Hola,</Text>
              <Text style={styles.profileName}>Usuario</Text>
            </View>
            <Ionicons name="chevron-forward" size={15} color={colors.muted} />
          </Pressable>
        </View>

        {/* Premium banner */}
        <Pressable testID="more-premium" style={({ pressed }) => [styles.banner, pressed && styles.pressed]}>
          <View style={styles.bannerIcon}>
            <Ionicons name="ribbon" size={22} color={colors.brandPrimary} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 10 }}>
            <Text style={styles.bannerTitle} numberOfLines={1}>Saca más provecho de MoneyFlow</Text>
            <Text style={styles.bannerSub} numberOfLines={2}>
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
                      <Ionicons name={it.icon as any} size={18} color={it.color} />
                    </View>
                    <Ionicons name="chevron-forward" size={15} color={colors.muted} />
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
              style={({ pressed }) => [styles.appRow, pressed && styles.pressed]}
            >
              <View style={[styles.appIcon, { backgroundColor: it.color + "24" }]}>
                <Ionicons name={it.icon as any} size={17} color={it.color} />
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={styles.appLabel} numberOfLines={1}>{it.label}</Text>
                <Text style={styles.appSub} numberOfLines={1}>{it.subtitle}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              {i < APP.length - 1 && <View style={styles.appDivider} />}
            </Pressable>
          ))}
        </View>

        {/* Suggestion */}
        <Pressable testID="more-suggestion" style={({ pressed }) => [styles.suggestion, pressed && styles.pressed]}>
          <View style={styles.suggIcon}>
            <Ionicons name="bulb-outline" size={20} color={colors.success} />
          </View>
          <View style={{ flex: 1, marginHorizontal: 10 }}>
            <Text style={styles.suggTitle} numberOfLines={1}>¿Tienes alguna sugerencia?</Text>
            <Text style={styles.suggSub} numberOfLines={1}>Nos encantaría escucharla.</Text>
          </View>
          <View style={styles.suggBtn}>
            <Text style={styles.suggBtnText}>Enviar</Text>
          </View>
        </Pressable>
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => ({
  container: { flex: 1, paddingHorizontal: 16, paddingBottom: 10 },
  pressed: { opacity: 0.6 },

  // Header
  header: { flexDirection: "row", alignItems: "flex-start", marginBottom: 10 },
  title: { fontSize: 28, fontWeight: "800", color: colors.onSurface, marginBottom: 2 },
  subtitle: { fontSize: 12.5, color: colors.muted, lineHeight: 17 },
  profilePill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: 6,
    paddingHorizontal: 9,
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  profileHi: { fontSize: 10, color: colors.muted, lineHeight: 12 },
  profileName: { fontSize: 12.5, fontWeight: "700", color: colors.onSurface, lineHeight: 15 },

  // Banner
  banner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandTertiary,
    borderRadius: 20,
    padding: 10,
    marginBottom: 12,
  },
  bannerIcon: {
    width: 40,
    height: 40,
    borderRadius: 14,
    backgroundColor: colors.brandPrimary + "2E",
    alignItems: "center",
    justifyContent: "center",
  },
  bannerTitle: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface },
  bannerSub: { fontSize: 11, color: scheme === "dark" ? colors.muted : colors.onSurfaceTertiary, lineHeight: 14, marginTop: 1, opacity: scheme === "dark" ? 1 : 0.75 },
  bannerBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 9, paddingHorizontal: 13 },
  bannerBtnText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "700" },

  // Section headers
  sectionHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  sectionHint: { fontSize: 11.5, color: colors.muted },

  // Grid (Tu dinero) — flexes to fill remaining height so nothing scrolls
  grid: { flex: 3.6, gap: 10, marginBottom: 12 },
  gridRow: { flex: 1, flexDirection: "row", gap: 10 },
  tile: { flex: 1, borderRadius: 18, paddingVertical: 8, paddingHorizontal: 12, justifyContent: "center", overflow: "hidden" },
  tileTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4, flexShrink: 0 },
  tileIcon: { width: 30, height: 30, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  tileLabel: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface, flexShrink: 0 },
  tileSub: { fontSize: 11, color: colors.muted, lineHeight: 13.5, marginTop: 2, flexShrink: 0 },

  // App list — also flexes to fill
  appCard: {
    flex: 2.7,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 14,
    marginBottom: 12,
    overflow: "hidden",
  },
  appRow: { flex: 1, flexDirection: "row", alignItems: "center" },
  appIcon: { width: 34, height: 34, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  appLabel: { fontSize: 14, fontWeight: "700", color: colors.onSurface, flexShrink: 0 },
  appSub: { fontSize: 11.5, color: colors.muted, marginTop: 1, flexShrink: 0 },
  appDivider: { position: "absolute", left: 44, right: 0, bottom: 0, height: 1, backgroundColor: colors.divider },

  // Suggestion
  suggestion: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.success + (scheme === "dark" ? "1F" : "14"),
    borderRadius: 18,
    padding: 11,
  },
  suggIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.success + "26",
    alignItems: "center",
    justifyContent: "center",
  },
  suggTitle: { fontSize: 13.5, fontWeight: "800", color: colors.onSurface },
  suggSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  suggBtn: { backgroundColor: colors.success + (scheme === "dark" ? "2E" : "1F"), borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: 13 },
  suggBtnText: { color: colors.success, fontSize: 12, fontWeight: "700" },
}));
