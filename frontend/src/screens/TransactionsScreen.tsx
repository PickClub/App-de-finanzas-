import React, { useMemo, useState } from "react";
import { View, Text, ScrollView, TextInput, StyleSheet, FlatList, Pressable, Modal, KeyboardAvoidingView, Platform } from "react-native";
import { useQuery } from "@tanstack/react-query";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatCurrency, formatDate } from "@/src/format";
import { IconTile, Chip } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";

const TYPE_FILTERS = [
  { id: "all", label: "Todos" },
  { id: "income", label: "Ingresos" },
  { id: "expense", label: "Gastos" },
  { id: "transfer", label: "Transferencias" },
  { id: "debt_payment", label: "Pagos deuda" },
];

const DATE_RANGES = [
  { id: "all", label: "Cualquier fecha", days: null as number | null },
  { id: "7d", label: "Últimos 7 días", days: 7 },
  { id: "30d", label: "Últimos 30 días", days: 30 },
  { id: "90d", label: "Últimos 3 meses", days: 90 },
  { id: "365d", label: "Último año", days: 365 },
  { id: "month", label: "Este mes", days: 0 },
];

export default function Transactions() {
  const { colors } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { guard } = useLock();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [accountId, setAccountId] = useState<string | undefined>();
  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState("all");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const txQ = useQuery({ queryKey: ["transactions"], queryFn: api.listTransactions });
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const accQ = useQuery({ queryKey: ["accounts"], queryFn: api.listAccounts });

  const cats: any[] = catQ.data || [];
  const accs: any[] = accQ.data || [];
  const catById = Object.fromEntries(cats.map((c) => [c.id, c]));
  const accById = Object.fromEntries(accs.map((a) => [a.id, a]));

  const activeAdvanced = (accountId ? 1 : 0) + (categoryId ? 1 : 0) + (dateRange !== "all" ? 1 : 0);

  const data = useMemo(() => {
    let items: any[] = txQ.data || [];
    if (filter !== "all") items = items.filter((t) => t.type === filter);
    if (accountId) items = items.filter((t) => t.account_id === accountId || t.to_account_id === accountId);
    if (categoryId) items = items.filter((t) => t.category_id === categoryId);
    if (dateRange !== "all") {
      const now = new Date();
      const range = DATE_RANGES.find((r) => r.id === dateRange);
      let cutoff = 0;
      if (range?.id === "month") {
        cutoff = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
      } else if (range?.days) {
        cutoff = Date.now() - range.days * 86400000;
      }
      items = items.filter((t) => new Date(t.date).getTime() >= cutoff);
    }
    if (q.trim()) items = items.filter((t) => t.name.toLowerCase().includes(q.toLowerCase()));
    return items;
  }, [txQ.data, filter, accountId, categoryId, dateRange, q]);

  const clearAll = () => {
    setAccountId(undefined);
    setCategoryId(undefined);
    setDateRange("all");
  };

  const rangeLabel = DATE_RANGES.find((r) => r.id === dateRange)?.label;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <Text style={styles.title}>Movimientos</Text>
          <LockToggle testID="lock-tx" compact />
          <Pressable
            testID="open-filters"
            onPress={() => setFiltersOpen(true)}
            style={styles.filterBtn}
          >
            <Ionicons name="options-outline" size={18} color={colors.onSurface} />
            {activeAdvanced > 0 && (
              <View style={styles.badge}>
                <Text style={styles.badgeText}>{activeAdvanced}</Text>
              </View>
            )}
          </Pressable>
        </View>
        <View style={styles.searchWrap}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            testID="search-input"
            value={q}
            onChangeText={setQ}
            placeholder="Buscar movimiento…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
          />
          {q.length > 0 && (
            <Pressable onPress={() => setQ("")} hitSlop={8}>
              <Ionicons name="close-circle" size={18} color={colors.muted} />
            </Pressable>
          )}
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: 8 }}
          style={{ marginTop: spacing.md, height: 44 }}
        >
          {TYPE_FILTERS.map((f) => (
            <Chip
              key={f.id}
              label={f.label}
              active={filter === f.id}
              onPress={() => setFilter(f.id)}
              testID={`chip-${f.id}`}
            />
          ))}
        </ScrollView>

        {activeAdvanced > 0 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: 8 }}
            style={{ marginTop: 6, height: 40 }}
          >
            {accountId && (
              <ActiveTag
                testID="active-account"
                icon="card-outline"
                color={accById[accountId]?.color || colors.accountsBlue}
                label={accById[accountId]?.name || "Cuenta"}
                onRemove={() => setAccountId(undefined)}
              />
            )}
            {categoryId && (
              <ActiveTag
                testID="active-category"
                icon="pricetag-outline"
                color={catById[categoryId]?.color || colors.brandPrimary}
                label={catById[categoryId]?.name || "Categoría"}
                onRemove={() => setCategoryId(undefined)}
              />
            )}
            {dateRange !== "all" && (
              <ActiveTag
                testID="active-date"
                icon="calendar-outline"
                color={colors.statsPurple}
                label={rangeLabel || ""}
                onRemove={() => setDateRange("all")}
              />
            )}
            <Pressable testID="clear-filters" onPress={clearAll} style={styles.clearBtn}>
              <Text style={{ color: colors.brandPrimary, fontWeight: "700", fontSize: 12 }}>Limpiar</Text>
            </Pressable>
          </ScrollView>
        )}
      </View>

      <FlatList
        data={data}
        keyExtractor={(i) => i.id}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}
        ListEmptyComponent={
          <View style={{ alignItems: "center", padding: spacing.xxl }}>
            <Ionicons name="documents-outline" size={48} color={colors.muted} />
            <Text style={{ color: colors.muted, marginTop: 10 }}>Sin movimientos</Text>
          </View>
        }
        renderItem={({ item }) => {
          const cat = catById[item.category_id];
          const acc = accById[item.account_id];
          const isIncome = item.type === "income" || item.type === "loan_received";
          const isTransfer = item.type === "transfer";
          const sign = isTransfer ? "" : isIncome ? "+" : "-";
          const color = isTransfer ? colors.accountsBlue : isIncome ? colors.incomeGreen : colors.expenseRed;
          const iconName =
            cat?.icon ||
            (isTransfer ? "swap-horizontal-outline" : isIncome ? "trending-up-outline" : "trending-down-outline");
          const tint = cat?.color || color;
          return (
            <Pressable
              testID={`tx-${item.id}`}
              onPress={guard(() => router.push(`/transactions/new?id=${item.id}`))}
              style={styles.row}
            >
              <IconTile icon={iconName} tint={tint} size={44} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.name}>{item.name}</Text>
                <Text style={styles.sub}>
                  {cat?.name || item.type} {acc ? `· ${acc.name}` : ""} · {formatDate(item.date)}
                </Text>
              </View>
              <Text style={{ color, fontWeight: "800", fontSize: 15 }}>
                {sign}{formatCurrency(item.amount)}
              </Text>
            </Pressable>
          );
        }}
      />

      {/* Filters Modal */}
      <Modal visible={filtersOpen} transparent animationType="slide" onRequestClose={() => setFiltersOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.modalWrap}>
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Filtros</Text>
              <Pressable onPress={() => setFiltersOpen(false)} testID="close-filters" hitSlop={8}>
                <Ionicons name="close" size={24} color={colors.onSurface} />
              </Pressable>
            </View>

            <ScrollView contentContainerStyle={{ paddingBottom: 20 }}>
              <Text style={styles.sheetLabel}>Cuenta</Text>
              <View style={styles.optRow}>
                <FilterPill
                  label="Todas"
                  active={!accountId}
                  onPress={() => setAccountId(undefined)}
                  testID="filter-acc-all"
                />
                {accs.map((a: any) => (
                  <FilterPill
                    key={a.id}
                    label={a.name}
                    color={a.color}
                    icon={a.icon}
                    active={accountId === a.id}
                    onPress={() => setAccountId(a.id)}
                    testID={`filter-acc-${a.id}`}
                  />
                ))}
              </View>

              <Text style={styles.sheetLabel}>Categoría</Text>
              <View style={styles.optRow}>
                <FilterPill
                  label="Todas"
                  active={!categoryId}
                  onPress={() => setCategoryId(undefined)}
                  testID="filter-cat-all"
                />
                {cats.map((c: any) => (
                  <FilterPill
                    key={c.id}
                    label={c.name}
                    color={c.color}
                    icon={c.icon}
                    active={categoryId === c.id}
                    onPress={() => setCategoryId(c.id)}
                    testID={`filter-cat-${c.id}`}
                  />
                ))}
              </View>

              <Text style={styles.sheetLabel}>Fecha</Text>
              <View style={styles.optRow}>
                {DATE_RANGES.map((r) => (
                  <FilterPill
                    key={r.id}
                    label={r.label}
                    active={dateRange === r.id}
                    onPress={() => setDateRange(r.id)}
                    testID={`filter-date-${r.id}`}
                  />
                ))}
              </View>
            </ScrollView>

            <View style={styles.footerRow}>
              <Pressable testID="filters-clear" onPress={clearAll} style={styles.footerGhost}>
                <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Limpiar</Text>
              </Pressable>
              <Pressable testID="filters-apply" onPress={() => setFiltersOpen(false)} style={styles.footerApply}>
                <Text style={{ color: "#fff", fontWeight: "800" }}>Aplicar</Text>
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

function ActiveTag({
  label, color, icon, onRemove, testID,
}: { label: string; color: string; icon: string; onRemove: () => void; testID?: string }) {
  const { colors } = useTheme();
  const styles = useStyles();
  return (
    <View testID={testID} style={[styles.activeTag, { borderColor: color + "80", backgroundColor: color + "1A" }]}>
      <Ionicons name={icon as any} size={13} color={color} />
      <Text style={{ color: colors.onSurface, fontWeight: "700", fontSize: 12 }}>{label}</Text>
      <Pressable onPress={onRemove} hitSlop={8}>
        <Ionicons name="close-circle" size={16} color={color} />
      </Pressable>
    </View>
  );
}

function FilterPill({
  label, active, onPress, color, icon, testID,
}: { label: string; active?: boolean; onPress: () => void; color?: string; icon?: string; testID?: string }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const bg = active ? (color || colors.brandPrimary) : colors.surfaceSecondary;
  const fg = active ? "#fff" : colors.onSurface;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: bg, borderColor: active ? bg : colors.border }]}
    >
      {icon && <Ionicons name={icon as any} size={13} color={fg} />}
      <Text style={{ color: fg, fontWeight: "700", fontSize: 12 }}>{label}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  title: { fontSize: 24, fontWeight: "800", color: colors.onSurface, flex: 1 },
  filterBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  badge: {
    position: "absolute", top: -2, right: -2,
    minWidth: 18, height: 18, borderRadius: 9,
    backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center",
    paddingHorizontal: 5,
  },
  badgeText: { color: "#fff", fontSize: 10, fontWeight: "800" },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 8,
    marginTop: 12,
  },
  searchInput: { flex: 1, paddingVertical: 10, color: colors.onSurface, fontSize: 14 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: 10,
  },
  name: { fontWeight: "700", color: colors.onSurface, fontSize: 14 },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  activeTag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexShrink: 0,
  },
  clearBtn: {
    paddingHorizontal: 10, paddingVertical: 6, alignItems: "center", justifyContent: "center",
    flexShrink: 0,
  },
  modalWrap: { flex: 1, justifyContent: "flex-end", backgroundColor: "#00000055" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.cardLg,
    borderTopRightRadius: radius.cardLg,
    padding: spacing.lg,
    maxHeight: "85%",
  },
  sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  sheetTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  sheetLabel: {
    fontSize: 12, fontWeight: "700", color: colors.muted,
    textTransform: "uppercase", letterSpacing: 0.5,
    marginTop: 16, marginBottom: 10,
  },
  optRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  footerRow: { flexDirection: "row", gap: 10, marginTop: 12 },
  footerGhost: {
    flex: 1, padding: 14, borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary, alignItems: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  footerApply: {
    flex: 2, padding: 14, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary, alignItems: "center",
  },
}));
