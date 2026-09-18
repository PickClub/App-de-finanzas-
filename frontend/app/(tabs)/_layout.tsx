import React, { useState } from "react";
import { Tabs, useRouter } from "expo-router";
import { Pressable, StyleSheet, View, Text, Modal, TouchableOpacity } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, makeStyles, radius } from "@/src/theme";

function FabButton({ onPress }: { onPress: () => void }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  return (
    <View pointerEvents="box-none" style={[styles.fabWrap, { bottom: 20 + insets.bottom }]}>
      <Pressable
        testID="fab-add-btn"
        onPress={() => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          onPress();
        }}
        style={({ pressed }) => [styles.fab, pressed && { transform: [{ scale: 0.95 }] }]}
      >
        <Ionicons name="add" size={34} color={colors.onBrandPrimary} />
      </Pressable>
    </View>
  );
}

function QuickMenu({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const router = useRouter();
  const items = [
    { icon: "trending-down-outline", label: "Gasto", color: colors.expenseRed, route: "/transactions/new?type=expense" },
    { icon: "trending-up-outline", label: "Ingreso", color: colors.incomeGreen, route: "/transactions/new?type=income" },
    { icon: "swap-horizontal-outline", label: "Transferencia", color: colors.accountsBlue, route: "/transactions/new?type=transfer" },
    { icon: "card-outline", label: "Crear deuda", color: colors.statsPurple, route: "/debts/new?direction=i_owe" },
    { icon: "hand-left-outline", label: "Registrar préstamo", color: colors.loansYellow, route: "/debts/new?direction=they_owe" },
    { icon: "cash-outline", label: "Pago de deuda", color: colors.brandPrimary, route: "/debts" },
  ];
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <View style={styles.sheetHandle} />
          <Text style={styles.sheetTitle}>Añadir rápido</Text>
          <View style={styles.grid}>
            {items.map((it) => (
              <TouchableOpacity
                key={it.label}
                testID={`quick-${it.label}`}
                style={styles.gridItem}
                onPress={() => {
                  onClose();
                  setTimeout(() => router.push(it.route as any), 100);
                }}
              >
                <View style={[styles.gridIcon, { backgroundColor: it.color + "22" }]}>
                  <Ionicons name={it.icon as any} size={26} color={it.color} />
                </View>
                <Text style={styles.gridLabel}>{it.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const styles = useStyles();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.brandPrimary,
          tabBarInactiveTintColor: colors.muted,
          tabBarStyle: {
            backgroundColor: colors.surfaceSecondary,
            borderTopColor: colors.border,
            borderTopWidth: 1,
          },
          tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
          tabBarItemStyle: { alignSelf: "center" },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "Inicio",
            tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="transactions"
          options={{
            title: "IA",
            tabBarIcon: ({ color, size }) => <Ionicons name="mic" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="fab"
          options={{
            title: "",
            tabBarIcon: () => <View style={{ width: 40, height: 40 }} />,
            tabBarButton: () => <View style={{ flex: 1 }} />,
          }}
        />
        <Tabs.Screen
          name="reports"
          options={{
            title: "Informes",
            tabBarIcon: ({ color, size }) => <Ionicons name="stats-chart" size={size} color={color} />,
          }}
        />
        <Tabs.Screen
          name="more"
          options={{
            title: "Más",
            tabBarIcon: ({ color, size }) => <Ionicons name="grid" size={size} color={color} />,
          }}
        />
      </Tabs>
      <FabButton onPress={() => setMenuOpen(true)} />
      <QuickMenu visible={menuOpen} onClose={() => setMenuOpen(false)} />
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  fabWrap: { position: "absolute", left: 0, right: 0, alignItems: "center" },
  fab: {
    width: 62,
    height: 62,
    borderRadius: 31,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: colors.brandPrimary,
    shadowOpacity: 0.35,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.cardLg,
    borderTopRightRadius: radius.cardLg,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 32,
  },
  sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  sheetTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginBottom: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  gridItem: { width: "31%", alignItems: "center", marginBottom: 20 },
  gridIcon: { width: 60, height: 60, borderRadius: 20, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  gridLabel: { fontSize: 12, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
}));
