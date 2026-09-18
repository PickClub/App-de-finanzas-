import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, Pressable, TextInput, StyleSheet, Alert } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";
import { AppSheet, ConfirmSheet } from "@/src/components/sheets";
import { formatCurrency } from "@/src/format";

const TYPE_LABEL: Record<string, string> = {
  income: "Ingreso",
  expense: "Gasto",
  transfer: "Transferencia",
  debt_payment: "Pago de deuda",
  loan_received: "Préstamo recibido",
  loan_given: "Préstamo otorgado",
};

function fmtDateTime(iso: string, withYear = false): string {
  try {
    const d = new Date(iso);
    const opts: any = withYear
      ? { day: "2-digit", month: "short", year: "numeric" }
      : { day: "2-digit", month: "short" };
    const date = d.toLocaleDateString("es-ES", opts).replace(".", "");
    let h = d.getHours();
    const m = d.getMinutes().toString().padStart(2, "0");
    const ampm = h >= 12 ? "p.m." : "a.m.";
    h = h % 12;
    if (h === 0) h = 12;
    const sep = withYear ? " · " : ", ";
    return `${date}${sep}${h}:${m} ${ampm}`;
  } catch {
    return "";
  }
}

export default function TransactionDetail() {
  const { colors } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const tx = useMemo(() => (txQ.data || []).find((t: any) => t.id === params.id), [txQ.data, params.id]);
  const cat = useMemo(() => (catQ.data || []).find((c: any) => c.id === tx?.category_id), [catQ.data, tx]);
  const account = useMemo(() => (accQ.data || []).find((a: any) => a.id === tx?.account_id), [accQ.data, tx]);

  // Sheets
  const [moreOpen, setMoreOpen] = useState(false);
  const [confirmEdit, setConfirmEdit] = useState(false);
  const [confirmDup, setConfirmDup] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [catOpen, setCatOpen] = useState(false);
  const [soon, setSoon] = useState<{ title: string; desc: string; icon: string; accent: string } | null>(null);

  // Cambiar categoría state
  const [catSearch, setCatSearch] = useState("");
  const [pickedCat, setPickedCat] = useState<string | undefined>();
  const catList = useMemo(() => {
    const all = (catQ.data || []).filter((c: any) => (tx?.type === "income" ? c.type === "income" : c.type === "expense"));
    const q = catSearch.trim().toLowerCase();
    return q ? all.filter((c: any) => c.name.toLowerCase().includes(q)) : all;
  }, [catQ.data, tx, catSearch]);

  if (!tx) {
    return (
      <View style={[styles.screen, { paddingTop: insets.top + 8 }]}>
        <View style={styles.header}>
          <Pressable testID="back-btn" onPress={() => router.back()} style={styles.circleBtn}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.headerTitle}>Detalle del movimiento</Text>
          <View style={styles.circleBtn} />
        </View>
        <Text style={{ color: colors.muted, textAlign: "center", marginTop: 40 }}>
          {txQ.isLoading ? "Cargando…" : "Movimiento no encontrado"}
        </Text>
      </View>
    );
  }

  const isIncome = tx.type === "income" || tx.type === "loan_received";
  const isTransfer = tx.type === "transfer";
  const amtColor = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
  const sign = isTransfer ? "" : isIncome ? "+" : "-";
  const badgeColor = amtColor;
  const iconName = cat?.icon || (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
  const iconTint = cat?.color || amtColor;

  // --- Actions (reuse existing update/delete/create logic) ---
  const doEdit = () => {
    setConfirmEdit(false);
    router.push(`/transactions/new?id=${tx.id}`);
  };
  const doDuplicate = () => {
    setConfirmDup(false);
    router.push(`/transactions/new?dupFrom=${tx.id}`);
  };
  const doDelete = async () => {
    try {
      await api.deleteTransaction(tx.id);
      qc.invalidateQueries();
      setConfirmDel(false);
      router.back();
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  };
  const saveCategory = async () => {
    if (!pickedCat) return;
    try {
      await api.updateTransaction(tx.id, {
        name: tx.name,
        amount: tx.amount,
        type: tx.type,
        date: tx.date,
        category_id: pickedCat,
        account_id: tx.account_id,
        to_account_id: tx.to_account_id,
        debt_id: tx.debt_id,
        notes: tx.notes,
      });
      qc.invalidateQueries();
      setCatOpen(false);
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  };

  const openCategorySheet = () => {
    setPickedCat(tx.category_id);
    setCatSearch("");
    setMoreOpen(false);
    setTimeout(() => setCatOpen(true), 180);
  };

  const menu = [
    { key: "edit", icon: "create-outline", label: "Editar movimiento", tint: colors.brandSecondary, onPress: () => afterMenu(() => setConfirmEdit(true)) },
    { key: "dup", icon: "copy-outline", label: "Duplicar movimiento", tint: colors.accountsBlue, onPress: () => afterMenu(() => setConfirmDup(true)) },
    { key: "recur", icon: "sync-outline", label: "Hacer recurrente", tint: colors.incomeGreen, onPress: () => afterMenu(() => setSoon({ title: "Hacer recurrente", desc: "Muy pronto podrás configurar la frecuencia y una fecha de inicio para automatizar este movimiento.", icon: "sync-outline", accent: colors.incomeGreen })) },
    { key: "receipt", icon: "attach-outline", label: "Añadir comprobante", tint: colors.statsPurple, onPress: () => afterMenu(() => setSoon({ title: "Añadir comprobante", desc: "Muy pronto podrás subir una foto o documento del comprobante de este movimiento.", icon: "attach-outline", accent: colors.statsPurple })) },
    { key: "category", icon: "pricetag-outline", label: "Cambiar categoría", tint: colors.brandSecondary, onPress: openCategorySheet },
  ];

  function afterMenu(fn: () => void) {
    setMoreOpen(false);
    setTimeout(fn, 180);
  }

  return (
    <View style={[styles.screen, { paddingTop: insets.top + 8 }]}>
      {/* Header */}
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.circleBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Detalle del movimiento</Text>
        <Pressable testID="more-btn" onPress={() => setMoreOpen(true)} style={styles.circleBtn}>
          <Ionicons name="ellipsis-horizontal" size={20} color={colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        {/* Summary card */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryTop}>
            <IconTile icon={iconName} tint={iconTint} size={48} />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.summaryName} numberOfLines={2}>{tx.name}</Text>
              <Text style={styles.summaryDate}>{fmtDateTime(tx.date)}</Text>
            </View>
          </View>
          <View style={styles.summaryBottom}>
            <View style={[styles.badge, { backgroundColor: badgeColor + "1A" }]}>
              <Text style={[styles.badgeText, { color: badgeColor }]}>{TYPE_LABEL[tx.type] || tx.type}</Text>
            </View>
            <Text style={[styles.summaryAmount, { color: amtColor }]}>{sign}{formatCurrency(tx.amount)}</Text>
          </View>
        </View>

        {/* Info card */}
        <View style={styles.infoCard}>
          <InfoRow
            icon="pricetag-outline"
            tint={cat?.color || colors.brandSecondary}
            label="Categoría"
            value={cat?.name || "Sin categoría"}
            onPress={openCategorySheet}
            styles={styles}
            colors={colors}
          />
          <View style={styles.rowDivider} />
          <InfoRow
            icon={account?.icon || "card-outline"}
            tint={account?.color || colors.accountsBlue}
            label="Cuenta"
            value={account?.name || "Sin cuenta"}
            styles={styles}
            colors={colors}
          />
          <View style={styles.rowDivider} />
          <InfoRow
            icon="calendar-outline"
            tint={colors.brandSecondary}
            label="Fecha y hora"
            value={fmtDateTime(tx.date, true)}
            styles={styles}
            colors={colors}
          />
          <View style={styles.rowDivider} />
          <InfoRow
            icon="document-text-outline"
            tint={colors.statsPurple}
            label="Descripción"
            value={tx.name}
            styles={styles}
            colors={colors}
          />
          <View style={styles.rowDivider} />
          <InfoRow
            icon="create-outline"
            tint={colors.muted}
            label="Notas"
            value={tx.notes && tx.notes.trim() ? tx.notes : "Sin notas"}
            styles={styles}
            colors={colors}
          />
        </View>

        {/* Registered note */}
        <View style={styles.noteBox}>
          <View style={[styles.noteIcon, { backgroundColor: colors.statsPurple + "1A" }]}>
            <Ionicons name="information-circle-outline" size={18} color={colors.statsPurple} />
          </View>
          <Text style={styles.noteText}>Este movimiento ya está registrado en tus saldos y estadísticas.</Text>
        </View>
      </ScrollView>

      {/* ===== Más opciones menu ===== */}
      <AppSheet visible={moreOpen} onClose={() => setMoreOpen(false)} testID="more-sheet">
        <Text style={styles.sheetTitle}>Más opciones</Text>
        <View style={{ marginTop: 6 }}>
          {menu.map((m) => (
            <Pressable key={m.key} testID={`menu-${m.key}`} onPress={m.onPress} style={styles.menuRow}>
              <View style={[styles.menuIcon, { backgroundColor: m.tint + "1A" }]}>
                <Ionicons name={m.icon as any} size={19} color={m.tint} />
              </View>
              <Text style={styles.menuLabel}>{m.label}</Text>
              <Ionicons name="chevron-forward" size={17} color={colors.muted} />
            </Pressable>
          ))}
          <View style={styles.menuSeparator} />
          <Pressable testID="menu-delete" onPress={() => afterMenu(() => setConfirmDel(true))} style={styles.menuRow}>
            <View style={[styles.menuIcon, { backgroundColor: colors.expenseRed + "1A" }]}>
              <Ionicons name="trash-outline" size={19} color={colors.expenseRed} />
            </View>
            <Text style={[styles.menuLabel, { color: colors.expenseRed }]}>Eliminar movimiento</Text>
            <Ionicons name="chevron-forward" size={17} color={colors.expenseRed + "99"} />
          </Pressable>
        </View>
        <Pressable onPress={() => setMoreOpen(false)} style={[styles.cancelRow, { backgroundColor: colors.surfaceTertiary }]}>
          <Text style={styles.cancelRowText}>Cancelar</Text>
        </Pressable>
      </AppSheet>

      {/* ===== Confirmations ===== */}
      <ConfirmSheet
        visible={confirmEdit}
        onClose={() => setConfirmEdit(false)}
        icon="create-outline"
        accent={colors.brandPrimary}
        title="¿Editar este movimiento?"
        description="Podrás modificar el monto, categoría, cuenta y demás información de este movimiento."
        confirmLabel="Editar"
        confirmTestID="confirm-edit"
        onConfirm={doEdit}
      />
      <ConfirmSheet
        visible={confirmDup}
        onClose={() => setConfirmDup(false)}
        icon="copy-outline"
        accent={colors.brandPrimary}
        title="¿Duplicar este movimiento?"
        description="Se creará un nuevo movimiento con la misma información. Podrás revisarlo antes de guardarlo."
        confirmLabel="Duplicar"
        confirmTestID="confirm-dup"
        onConfirm={doDuplicate}
      />
      <ConfirmSheet
        visible={confirmDel}
        onClose={() => setConfirmDel(false)}
        icon="trash-outline"
        accent={colors.expenseRed}
        destructive
        title="¿Eliminar este movimiento?"
        description="Esta acción eliminará permanentemente este movimiento y puede afectar tus saldos y estadísticas."
        confirmLabel="Eliminar"
        confirmTestID="confirm-delete"
        onConfirm={doDelete}
      />
      {soon && (
        <ConfirmSheet
          visible={!!soon}
          onClose={() => setSoon(null)}
          icon={soon.icon}
          accent={soon.accent}
          title={soon.title}
          description={soon.desc}
          confirmLabel="Entendido"
          onConfirm={() => setSoon(null)}
        />
      )}

      {/* ===== Cambiar categoría ===== */}
      <AppSheet visible={catOpen} onClose={() => setCatOpen(false)} testID="category-sheet">
        <View style={{ alignItems: "center" }}>
          <View style={[styles.confirmIconSm, { backgroundColor: colors.brandSecondary + "1F" }]}>
            <Ionicons name="pricetag-outline" size={24} color={colors.brandSecondary} />
          </View>
          <Text style={styles.catTitle}>Cambiar categoría</Text>
          <Text style={styles.catSubtitle}>Selecciona una nueva categoría para este movimiento.</Text>
        </View>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={colors.muted} />
          <TextInput
            testID="cat-search"
            value={catSearch}
            onChangeText={setCatSearch}
            placeholder="Buscar categoría…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
          />
        </View>
        <ScrollView style={{ maxHeight: 260, marginTop: 8 }} keyboardShouldPersistTaps="handled">
          {catList.map((c: any) => {
            const selected = pickedCat === c.id;
            return (
              <Pressable
                key={c.id}
                testID={`pick-cat-${c.id}`}
                onPress={() => setPickedCat(c.id)}
                style={[styles.catRow, selected && { backgroundColor: c.color + "14" }]}
              >
                <IconTile icon={c.icon} tint={c.color} size={34} />
                <Text style={styles.catRowText}>{c.name}</Text>
                {selected && <Ionicons name="checkmark-circle" size={20} color={colors.incomeGreen} />}
              </Pressable>
            );
          })}
          {catList.length === 0 && (
            <Text style={{ color: colors.muted, textAlign: "center", padding: 16 }}>Sin resultados</Text>
          )}
        </ScrollView>
        <Pressable
          testID="save-category"
          onPress={saveCategory}
          disabled={!pickedCat}
          style={[styles.saveBtn, { backgroundColor: colors.brandPrimary, opacity: pickedCat ? 1 : 0.5 }]}
        >
          <Text style={styles.saveText}>Guardar</Text>
        </Pressable>
      </AppSheet>
    </View>
  );
}

function InfoRow({
  icon,
  tint,
  label,
  value,
  onPress,
  styles,
  colors,
}: any) {
  const body = (
    <>
      <View style={[styles.infoIcon, { backgroundColor: tint + "1A" }]}>
        <Ionicons name={icon} size={17} color={tint} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={styles.infoLabel}>{label}</Text>
        <Text style={styles.infoValue} numberOfLines={2}>{value}</Text>
      </View>
      {onPress && <Ionicons name="chevron-forward" size={17} color={colors.muted} />}
    </>
  );
  if (onPress) {
    return (
      <Pressable onPress={onPress} style={styles.infoRow}>
        {body}
      </Pressable>
    );
  }
  return <View style={styles.infoRow}>{body}</View>;
}

const useStyles = makeStyles((colors) => ({
  screen: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: 12 },
  circleBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  headerTitle: { flex: 1, fontSize: 17, fontWeight: "800", color: colors.onSurface },

  summaryCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border,
    shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  summaryTop: { flexDirection: "row", alignItems: "center" },
  summaryName: { fontSize: 16, fontWeight: "800", color: colors.onSurface, letterSpacing: -0.3 },
  summaryDate: { fontSize: 12.5, color: colors.muted, marginTop: 3 },
  summaryBottom: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 16 },
  badge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  badgeText: { fontSize: 12.5, fontWeight: "800" },
  summaryAmount: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },

  infoCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.cardLg, paddingHorizontal: spacing.lg,
    borderWidth: 1, borderColor: colors.border, marginTop: spacing.md,
    shadowColor: "#000", shadowOpacity: 0.04, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  infoRow: { flexDirection: "row", alignItems: "center", paddingVertical: 14 },
  infoIcon: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  infoLabel: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  infoValue: { fontSize: 14.5, color: colors.onSurface, fontWeight: "700", marginTop: 2 },
  rowDivider: { height: 1, backgroundColor: colors.divider, marginLeft: 50 },

  noteBox: {
    flexDirection: "row", alignItems: "center", marginTop: spacing.md,
    backgroundColor: colors.statsPurple + "12", borderRadius: radius.lg, padding: 12,
    borderWidth: 1, borderColor: colors.statsPurple + "26",
  },
  noteIcon: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", marginRight: 10 },
  noteText: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 17 },

  // Sheet menu
  sheetTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginBottom: 4 },
  menuRow: { flexDirection: "row", alignItems: "center", paddingVertical: 11 },
  menuIcon: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center", marginRight: 14 },
  menuLabel: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  menuSeparator: { height: 1, backgroundColor: colors.divider, marginVertical: 6 },
  cancelRow: { marginTop: 12, paddingVertical: 15, borderRadius: radius.pill, alignItems: "center" },
  cancelRowText: { fontWeight: "800", fontSize: 15.5, color: colors.onSurface },

  // Category sheet
  confirmIconSm: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center", marginBottom: 10 },
  catTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  catSubtitle: { fontSize: 13, color: colors.muted, marginTop: 4, textAlign: "center", paddingHorizontal: 10 },
  searchBox: {
    flexDirection: "row", alignItems: "center", gap: 8, marginTop: 16,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, paddingHorizontal: 14, height: 44,
    borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface, paddingVertical: 0 },
  catRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 9, paddingHorizontal: 8, borderRadius: radius.lg },
  catRowText: { flex: 1, fontSize: 14.5, fontWeight: "700", color: colors.onSurface },
  saveBtn: { marginTop: 14, paddingVertical: 15, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 15.5 },
}));
