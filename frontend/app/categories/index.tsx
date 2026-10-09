import React, { useEffect, useState, useCallback } from "react";
import { View, ScrollView } from "react-native";
import Animated, { FadeIn, FadeOut, LinearTransition } from "react-native-reanimated";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import i18n from "@/src/i18n";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";
import { LockToggle, useLock } from "@/src/lock";
import { catLabel } from "@/src/category-labels";

import { us } from "@/src/ui-scale";

// Groups that also absorb ungrouped / custom categories (e.g. "Motica").
const OTHER_GROUPS = ["Other & Misc", "Other Earnings"];

function chunk3<T>(arr: T[]): T[][] {
  const rows: T[][] = [];
  for (let i = 0; i < arr.length; i += 3) rows.push(arr.slice(i, i + 3));
  return rows;
}

const EXPAND_MS = 280;

export default function Categories() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  // Reuse Home's EXACT identity values (app/(tabs)/index.tsx):
  //   page background sage #E8EFE7 (light) / colors.surface (dark)
  //   forest-green accent #126046 (light) / colors.brandPrimary (dark)
  const accentGreen = scheme === "dark" ? colors.brandPrimary : "#126046";
  const pageBg = scheme === "dark" ? colors.surface : "#E8EFE7";
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { guard } = useLock();
  const isEs = i18n.language.startsWith("es");
  const l10n = (es: string, en: string) => (isEs ? es : en);
  const subLabel = (n: number) =>
    isEs ? `${n} ${n === 1 ? "subcategoría" : "subcategorías"}` : `${n} ${n === 1 ? "subcategory" : "subcategories"}`;

  const q = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const cats: any[] = q.data || [];
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Ensure the grouped hierarchy exists (idempotent) if there are no groups yet.
  const ensuredRef = React.useRef(false);
  useEffect(() => {
    if (!q.isSuccess || ensuredRef.current) return;
    ensuredRef.current = true;
    const hasGroups = cats.some((c) => c.is_group);
    if (cats.length === 0 || !hasGroups) {
      api.initDefaultCategories().then(() => qc.invalidateQueries({ queryKey: ["categories"] })).catch(() => {});
    }
  }, [q.isSuccess, q.data, qc]);

  const restore = async () => {
    await api.initDefaultCategories();
    qc.invalidateQueries({ queryKey: ["categories"] });
  };

  const toggle = useCallback((id: string) => {
    setExpandedId((cur) => (cur === id ? null : id));
  }, []);

  const groupsOf = (type: string) => cats.filter((c) => c.is_group && c.type === type);
  const childrenOf = (group: any) => {
    let ch = cats.filter((c) => !c.is_group && c.parent_id === group.id);
    if (OTHER_GROUPS.includes(group.name)) {
      const ungrouped = cats.filter((c) => !c.is_group && !c.parent_id && c.type === group.type);
      ch = [...ch, ...ungrouped];
    }
    return ch;
  };

  const renderPanel = (group: any) => {
    const kids = childrenOf(group);
    const rows = chunk3(kids);
    return (
      <Animated.View
        key={`panel-${group.id}`}
        testID={`cat-panel-${group.id}`}
        entering={FadeIn.duration(220)}
        exiting={FadeOut.duration(150)}
        layout={LinearTransition.duration(EXPAND_MS)}
        style={styles.panel}
      >
        <Pressable onPress={() => toggle(group.id)} style={styles.panelHeader}>
          <IconTile icon={group.icon} tint={group.color} size={us(34)} />
          <View style={{ flex: 1, marginLeft: us(10) }}>
            <Text style={styles.panelTitle} numberOfLines={1}>{catLabel(group.name, i18n.language)}</Text>
            <Text style={styles.panelCount}>{subLabel(kids.length)}</Text>
          </View>
          <Ionicons name="chevron-up" size={us(20)} color={accentGreen} />
        </Pressable>
        <View style={styles.panelDivider} />
        {rows.map((row, ri) => (
          <View key={ri} style={styles.subRow}>
            {row.map((c) => (
              <Pressable
                key={c.id}
                testID={`cat-item-${c.id}`}
                onPress={guard(() => router.push(`/categories/new?id=${c.id}`))}
                style={styles.subItem}
              >
                <IconTile icon={c.icon} tint={c.color} size={us(40)} />
                <Text style={styles.subName} numberOfLines={1}>{catLabel(c.name, i18n.language)}</Text>
              </Pressable>
            ))}
            {Array.from({ length: 3 - row.length }).map((_, i) => (
              <View key={`sp-${i}`} style={styles.cellSpacer} />
            ))}
          </View>
        ))}
        <Pressable
          testID={`cat-add-sub-${group.id}`}
          onPress={guard(() => router.push(`/categories/new?parent=${group.id}&type=${group.type}`))}
          style={styles.addSub}
        >
          <Ionicons name="add" size={us(16)} color={accentGreen} />
          <Text style={[styles.addSubText, { color: accentGreen }]}>{l10n("Añadir subcategoría", "Add subcategory")}</Text>
        </Pressable>
      </Animated.View>
    );
  };

  const renderSection = (type: string, dotColor: string, title: string) => {
    const groups = groupsOf(type);
    if (groups.length === 0) return null;
    const rows = chunk3(groups);
    return (
      <>
        <View style={styles.sectionHead}>
          <View style={[styles.dot, { backgroundColor: dotColor }]} />
          <Text style={styles.section}>{title}</Text>
          <Text style={styles.count}>{groups.length}</Text>
        </View>
        {rows.map((row, ri) => {
          const expandedInRow = row.find((g) => g.id === expandedId);
          return (
            <React.Fragment key={ri}>
              <Animated.View layout={LinearTransition.duration(EXPAND_MS)} style={styles.gridRow}>
                {row.map((g) => {
                  const active = g.id === expandedId;
                  const kids = childrenOf(g);
                  return (
                    <Pressable
                      key={g.id}
                      testID={`cat-group-${g.id}`}
                      onPress={() => toggle(g.id)}
                      style={styles.gridItem}
                    >
                      <IconTile icon={g.icon} tint={g.color} size={us(48)} />
                      <Text style={styles.name} numberOfLines={1}>{catLabel(g.name, i18n.language)}</Text>
                      <Text style={styles.subCount} numberOfLines={1}>{subLabel(kids.length)}</Text>
                      <Ionicons
                        name={active ? "chevron-up" : "chevron-down"}
                        size={us(13)}
                        color={active ? accentGreen : colors.muted}
                        style={styles.chev}
                      />
                    </Pressable>
                  );
                })}
                {Array.from({ length: 3 - row.length }).map((_, i) => (
                  <View key={`sp-${i}`} style={styles.cellSpacer} />
                ))}
              </Animated.View>
              {expandedInRow ? renderPanel(expandedInRow) : null}
            </React.Fragment>
          );
        })}
      </>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: pageBg }}
      contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(140), paddingHorizontal: us(spacing.lg) }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: us(10), marginBottom: us(spacing.lg) }}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{l10n("Categorías", "Categories")}</Text>
        <LockToggle testID="lock-cats" compact />
        <Pressable testID="add-category" onPress={() => router.push("/categories/new")} style={[styles.backBtn, { backgroundColor: accentGreen, borderColor: accentGreen }]}>
          <Ionicons name="add" size={us(22)} color="#fff" />
        </Pressable>
      </View>

      {renderSection("expense", colors.expenseRed, l10n("Gastos", "Expenses"))}
      <View style={{ height: us(spacing.md) }} />
      {renderSection("income", colors.incomeGreen, l10n("Ingresos", "Income"))}

      <Pressable testID="restore-categories" onPress={restore} style={styles.restoreBtn}>
        <Ionicons name="refresh-outline" size={us(18)} color={colors.brandPrimary} />
        <Text style={styles.restoreText}>{l10n("Restaurar predeterminadas", "Restore defaults")}</Text>
      </Pressable>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  // Reuse Home's exact card language so Categories feels native to the app.
  const isDark = scheme === "dark";
  const cardSurface = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const wallText = isDark ? colors.onSurface : "#15251E";
  const wallMuted = isDark ? colors.muted : "#68746D";
  const wallSub = isDark ? colors.muted : "#8B958F";
  const lineSoft = isDark ? colors.border : "rgba(39,71,56,0.10)";
  const dividerSoft = isDark ? colors.divider : "#E4E7E2";
  const accentGreen = isDark ? colors.brandPrimary : "#126046";
  // Soft diffuse shadows copied from Home (wallet cards + Movimientos card).
  const cardShadow = { shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 2 };
  const panelShadow = { shadowColor: "#274738", shadowOpacity: 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 3 };
  return {
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: cardSurface, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: lineSoft },
  title: { flex: 1, fontSize: 22, fontWeight: "800", color: colors.onSurface },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  section: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  count: { fontSize: 12, fontWeight: "700", color: wallMuted },
  // Main group grid (explicit rows of 3 so expansion never leaves gaps).
  gridRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 12 },
  cellSpacer: { width: "31%" },
  gridItem: { width: "31%", backgroundColor: cardSurface, borderRadius: radius.md, paddingTop: 14, paddingBottom: 12, paddingHorizontal: 8, alignItems: "center", borderWidth: 1, borderColor: lineSoft, ...cardShadow },
  name: { color: wallText, fontWeight: "700", fontSize: 12, marginTop: 8, textAlign: "center" },
  subCount: { color: wallSub, fontWeight: "600", fontSize: 10, marginTop: 3, textAlign: "center" },
  chev: { position: "absolute", top: 8, right: 8 },
  // Expanded panel (soft tinted border of the category color, warm card surface).
  panel: { backgroundColor: cardSurface, borderRadius: radius.cardLg, borderWidth: 1, borderColor: lineSoft, paddingHorizontal: 12, paddingTop: 12, paddingBottom: 6, marginBottom: 12, ...panelShadow },
  panelHeader: { flexDirection: "row", alignItems: "center" },
  panelTitle: { color: wallText, fontWeight: "800", fontSize: 15 },
  panelCount: { color: wallSub, fontWeight: "600", fontSize: 11, marginTop: 2 },
  panelDivider: { height: 1, backgroundColor: dividerSoft, marginTop: 12, marginBottom: 12 },
  subRow: { flexDirection: "row", justifyContent: "space-between" },
  subItem: { width: "31%", backgroundColor: cardSurface, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 6, alignItems: "center", borderWidth: 1, borderColor: lineSoft, marginBottom: 10 },
  subName: { color: wallText, fontWeight: "700", fontSize: 11, marginTop: 6, textAlign: "center" },
  addSub: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8, marginBottom: 4 },
  addSubText: { fontWeight: "800", fontSize: 12.5 },
  restoreBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 8, paddingVertical: 14, borderRadius: radius.pill, borderWidth: 1, borderColor: lineSoft, backgroundColor: cardSurface },
  restoreText: { color: accentGreen, fontWeight: "800", fontSize: 14 },
  };
});
