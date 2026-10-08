import React, { useEffect, useState } from "react";
import { View, ScrollView, StyleSheet, Alert } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useResourceDeletion } from "@/src/use-resource-deletion";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";

import { us } from "@/src/ui-scale";
import { COLOR_PALETTE } from "@/src/color-palette";
const ICONS = [
  "restaurant-outline", "cart-outline", "pizza-outline", "car-outline",
  "flame-outline", "home-outline", "flash-outline", "call-outline",
  "wifi-outline", "musical-notes-outline", "bag-outline", "medkit-outline",
  "briefcase-outline", "school-outline", "airplane-outline", "cash-outline",
  "star-outline", "gift-outline", "heart-outline", "paw-outline",
];
// Shared 20-color palette; DEFAULT_COLOR keeps this screen's previous default.
const COLORS = COLOR_PALETTE;
const DEFAULT_COLOR = "#FF8A3D";

export default function CategoryForm() {
  const { colors } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const deletion = useResourceDeletion("/categories", [["accounts"], ["transactions"], ["categories"], ["debts"], ["debt-payments"], ["debt"], ["summary"]]);
  const [loadedId, setResourceLoaded] = useState<string>();
  const resourceLoaded = loadedId === params.id;

  const [name, setName] = useState("");
  const [type, setType] = useState<"expense" | "income">("expense");
  const [icon, setIcon] = useState(ICONS[0]);
  const [color, setColor] = useState(DEFAULT_COLOR);

  useEffect(() => {
    if (params.id) {
      api.listCategories().then((all) => {
        const c = all.find((x: any) => x.id === params.id);
        if (!c) { deletion.unavailable(); return; }
        if (c) { setResourceLoaded(params.id); setName(c.name); setType(c.type); setIcon(c.icon); setColor(c.color); }
      }).catch((error) => Alert.alert("No se pudo cargar", error instanceof Error ? error.message : "Inténtalo de nuevo."));
    }
  }, [params.id]);

  const save = async () => {
    if (deletion.locked.current || (params.id && !resourceLoaded)) return;
    if (!name.trim()) return Alert.alert("Falta nombre");
    const payload = { name, type, icon, color };
    if (params.id) await api.updateCategory(params.id as string, payload);
    else await api.createCategory(payload);
    qc.invalidateQueries();
    router.back();
  };

  const remove = async () => {
    if (!params.id) return;
    await deletion.remove(() => api.deleteCategory(params.id as string));
  };

  if (params.id && (!resourceLoaded || deletion.deleted.current)) return <View />;

  return (
    <ScrollView pointerEvents={deletion.busy ? "none" : "auto"} style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: us(12), marginBottom: us(spacing.lg) }}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{params.id ? "Editar" : "Nueva"} categoría</Text>
        {params.id && <Pressable onPress={remove} disabled={deletion.busy} style={styles.backBtn}><Ionicons name="trash-outline" size={us(22)} color={colors.expenseRed} /></Pressable>}
      </View>

      <Text style={styles.label}>Nombre</Text>
      <TextInput value={name} onChangeText={setName} placeholder="Ej. Comida" placeholderTextColor={colors.muted} style={styles.input} />

      <Text style={styles.label}>Tipo</Text>
      <View style={{ flexDirection: "row", gap: us(10) }}>
        {(["expense", "income"] as const).map((t) => (
          <Pressable key={t} onPress={() => setType(t)} style={[styles.typeBtn, type === t && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]}>
            <Text style={{ color: type === t ? "#fff" : colors.onSurface, fontWeight: "700" }}>{t === "expense" ? "Gasto" : "Ingreso"}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Icono</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(10) }}>
        {ICONS.map((ic) => (
          <Pressable key={ic} onPress={() => setIcon(ic)} style={[styles.iconOpt, icon === ic && { borderColor: color, borderWidth: 2 }]}>
            <IconTile icon={ic} tint={color} size={us(36)} />
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Color</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(10) }}>
        {COLORS.map((c) => (
          <Pressable key={c} onPress={() => setColor(c)} style={{ width: us(40), height: us(40), borderRadius: us(20), backgroundColor: c, borderWidth: color === c ? us(3) : 0, borderColor: colors.onSurface }} />
        ))}
      </View>

      <Pressable testID="save-category" onPress={save} style={styles.saveBtn}>
        <Text style={styles.saveText}>Guardar</Text>
      </Pressable>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 16, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  typeBtn: { flex: 1, padding: 12, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  iconOpt: { padding: 4, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  saveBtn: { marginTop: 28, backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
}));
