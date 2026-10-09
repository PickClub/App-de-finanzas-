import React, { useMemo, useRef, useState } from "react";
import { View, ScrollView, Alert, KeyboardAvoidingView, Platform, Keyboard } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing } from "react-native-reanimated";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { IconTile } from "@/src/components/ui";
import { AppSheet } from "@/src/components/sheets";

import { us, ufs } from "@/src/ui-scale";
import { COLOR_PALETTE } from "@/src/color-palette";

// Same light-mode identity values used by Home (sage background, warm white
// cards, forest green, mint badges). Local to this form; dark mode keeps the
// global dark theme (forest -> incomeGreen, as this file already did).
function formPalette(colors: any, scheme: string) {
  const dark = scheme === "dark";
  return {
    bg: dark ? colors.surface : "#E8EFE7",
    card: dark ? colors.surfaceSecondary : "#FCFCF8",
    field: dark ? colors.surface : "#FFFFFF",
    forest: dark ? colors.incomeGreen : "#126046",
    mint: dark ? colors.incomeGreen + "1F" : "#DCE9DD",
    onSurface: dark ? colors.onSurface : "#15251E",
    muted: dark ? colors.muted : "#68746D",
    border: dark ? colors.border : "rgba(39,71,56,0.10)",
  };
}

// Optional section card: closed by default, opens/closes independently with a
// light height + chevron animation. Children stay mounted, so values persist.
function Collapsible({
  testID,
  icon,
  title,
  summary,
  pal,
  styles,
  children,
}: {
  testID: string;
  icon: string;
  title: string;
  summary?: string;
  pal: ReturnType<typeof formPalette>;
  styles: any;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const progress = useSharedValue(0);
  const contentH = useSharedValue(0);
  const toggle = () => {
    Keyboard.dismiss();
    const next = !open;
    setOpen(next);
    progress.value = withTiming(next ? 1 : 0, { duration: 240, easing: Easing.out(Easing.cubic) });
  };
  const bodyStyle = useAnimatedStyle(() => ({ height: contentH.value * progress.value, opacity: progress.value }));
  const chevStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${progress.value * 180}deg` }] }));
  return (
    <View style={styles.card}>
      <Pressable testID={testID} onPress={toggle} style={styles.collHeader} accessibilityRole="button" accessibilityState={{ expanded: open }}>
        <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
          <Ionicons name={icon as any} size={us(20)} color={pal.forest} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.collTitle}>{title}</Text>
          <Text style={[styles.collSub, !!summary && { color: pal.forest }]} numberOfLines={1}>
            {summary || "Opcional"}
          </Text>
        </View>
        <Animated.View style={chevStyle}>
          <Ionicons name="chevron-down" size={us(20)} color={pal.onSurface} />
        </Animated.View>
      </Pressable>
      <Animated.View style={[{ overflow: "hidden" }, bodyStyle]} pointerEvents={open ? "auto" : "none"}>
        <View style={styles.collBody} onLayout={(e) => { contentH.value = e.nativeEvent.layout.height; }}>
          {children}
        </View>
      </Animated.View>
    </View>
  );
}
// Shared 20-color palette; DEFAULT_COLOR keeps this screen's previous default.
const COLORS = COLOR_PALETTE;
const DEFAULT_COLOR = "#F5B83B";
const ICONS = ["cash-outline", "card-outline", "car-outline", "home-outline", "person-outline", "briefcase-outline", "gift-outline"];
const FREQ = [
  { id: "weekly", label: "Semanal" },
  { id: "biweekly", label: "Quincenal" },
  { id: "monthly", label: "Mensual" },
  { id: "none", label: "Sin frecuencia" },
];

// Visual-only selection card used on the first step of "Nueva deuda".
// It is fully pressable and runs a light 1 -> 0.96 -> 1 scale response, then
// calls the SAME handler the old big button used (no logic/route change).
function SelectCard({
  testID,
  title,
  subtitle,
  arrowIcon,
  accent,
  circleBg,
  bandBg,
  styles,
  onPress,
}: {
  testID: string;
  title: string;
  subtitle: string;
  arrowIcon: string;
  accent: string;
  circleBg: string;
  bandBg: string;
  styles: any;
  onPress: () => void;
}) {
  const scale = useSharedValue(1);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      onPressIn={() => {
        scale.value = withTiming(0.96, { duration: 90, easing: Easing.out(Easing.quad) });
      }}
      onPressOut={() => {
        scale.value = withTiming(1, { duration: 140, easing: Easing.out(Easing.quad) });
      }}
      style={{ flex: 1 }}
    >
      <Animated.View style={[styles.selCard, aStyle]}>
        <View style={[styles.selBand, { backgroundColor: bandBg }]} pointerEvents="none" />
        <Ionicons name="wallet-outline" size={us(58)} color={accent} style={styles.selBandIcon} />
        <View style={[styles.selCircle, { backgroundColor: circleBg }]}>
          <Ionicons name={arrowIcon as any} size={us(28)} color={accent} />
        </View>
        <Text style={styles.selCardTitle}>{title}</Text>
        <Text style={styles.selCardSub}>{subtitle}</Text>
      </Animated.View>
    </Pressable>
  );
}

export default function NewDebt() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const params = useLocalSearchParams<{ direction?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();

  // Forest green accent, consistent with Home (hardcoded brand green on light,
  // brightened green on dark). Used only for the decorative selection screen.
  const forest = scheme === "dark" ? colors.incomeGreen : "#126046";

  const [direction, setDirection] = useState<string>(params.direction || "");
  const [step2, setStep2] = useState(!!params.direction);
  const [name, setName] = useState("");
  const [person, setPerson] = useState("");
  const [amount, setAmount] = useState("");
  const [minPay, setMinPay] = useState("");
  const [frequency, setFrequency] = useState("monthly");
  const [interest, setInterest] = useState("");
  const [notes] = useState("");
  const [color, setColor] = useState(DEFAULT_COLOR);
  const [icon, setIcon] = useState(ICONS[0]);
  // Optional category (existing Debt.category_id field). Notes are no longer
  // shown in this form; the value is still sent unchanged (empty for new debts).
  const [categoryId, setCategoryId] = useState<string | undefined>();
  const [catSheet, setCatSheet] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const pal = useMemo(() => formPalette(colors, scheme), [colors, scheme]);
  const catQ = useQuery({ queryKey: ["categories"], queryFn: api.listCategories });
  const cats = (catQ.data || []).filter((c: any) => c.type === "expense" && !c.is_group);
  const selCat = cats.find((c: any) => c.id === categoryId);

  const save = async () => {
    if (savingRef.current) return;
    const amt = parseFloat(amount);
    if (!name.trim() || !amt) return Alert.alert("Completa nombre y monto");
    savingRef.current = true;
    setSaving(true);
    try {
      await api.createDebt({
        name,
        direction,
        person,
        original_amount: amt,
        minimum_payment: parseFloat(minPay) || 0,
        payment_frequency: frequency,
        interest_rate: parseFloat(interest) || 0,
        notes,
        color,
        icon,
        category_id: categoryId,
      });
      qc.invalidateQueries();
      // Reuse the existing list; replace only when opened directly from Home.
      router.dismissTo("/debts");
    } catch (e: any) {
      savingRef.current = false;
      setSaving(false);
      Alert.alert("Error", e?.message || "No se pudo guardar la deuda");
    }
  };

  if (!step2) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface, paddingTop: insets.top + us(8) }}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={us(24)} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Nueva deuda</Text>
          <View style={{ width: us(40) }} />
        </View>
        <View style={styles.selWrap}>
          <View style={[styles.selIconTile, { backgroundColor: colors.incomeGreen + "1A" }]}>
            <Ionicons name="wallet-outline" size={us(28)} color={forest} />
          </View>
          <Text style={styles.selHeading}>¿Qué quieres registrar?</Text>
          <Text style={styles.selSubheading}>Selecciona el tipo de deuda</Text>
          <View style={styles.selRow}>
            <SelectCard
              testID="dir-i-owe"
              title="Yo debo"
              subtitle={"Dinero que debo\npagar"}
              arrowIcon="arrow-down"
              accent={colors.expenseRed}
              circleBg={colors.expenseRed + "1A"}
              bandBg={colors.expenseRed + "0F"}
              styles={styles}
              onPress={() => { setDirection("i_owe"); setStep2(true); }}
            />
            <SelectCard
              testID="dir-they-owe"
              title="Me deben"
              subtitle={"Dinero por\ncobrar"}
              arrowIcon="arrow-up"
              accent={forest}
              circleBg={colors.incomeGreen + "1A"}
              bandBg={colors.incomeGreen + "0F"}
              styles={styles}
              onPress={() => { setDirection("they_owe"); setStep2(true); }}
            />
          </View>
        </View>
      </View>
    );
  }

  const iOwe = direction === "i_owe";
  const freqLabel = FREQ.find((f) => f.id === frequency)?.label;
  const minSummary = parseFloat(minPay) > 0 ? minPay : "";
  const freqSummary = frequency !== "monthly" ? freqLabel : "";
  const intSummary = parseFloat(interest) > 0 ? `${interest} %` : "";

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: pal.bg }}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(spacing.lg), paddingHorizontal: us(spacing.lg), gap: us(10) }}
      >
        <View style={[styles.headerRow, { marginBottom: us(spacing.xs) }]}>
          <Pressable onPress={() => router.back()} style={[styles.backBtn, { backgroundColor: pal.card, borderColor: pal.border }]}>
            <Ionicons name="chevron-back" size={us(24)} color={pal.onSurface} />
          </Pressable>
          <Text style={[styles.title, { color: pal.onSurface }]}>{iOwe ? "Yo debo" : "Me deben"}</Text>
          <View style={{ width: us(40) }} />
        </View>

        {/* B. Debt name */}
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Nombre de la deuda</Text>
          <View style={styles.fieldRow}>
            <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
              <Ionicons name="document-text-outline" size={us(20)} color={pal.forest} />
            </View>
            <TextInput testID="debt-name" value={name} onChangeText={setName} placeholder="Ej. Tarjeta Chase" placeholderTextColor={pal.muted} style={styles.fieldInput} />
          </View>
        </View>

        {/* C. Person */}
        <View style={styles.card}>
          <Text style={styles.cardLabel}>{iOwe ? "A quién debo" : "Quién me debe"}</Text>
          <View style={styles.fieldRow}>
            <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
              <Ionicons name="person-outline" size={us(20)} color={pal.forest} />
            </View>
            <TextInput testID="debt-person" value={person} onChangeText={setPerson} placeholder="Nombre de la persona o entidad" placeholderTextColor={pal.muted} style={styles.fieldInput} />
          </View>
        </View>

        {/* D. Total amount + category */}
        <View style={styles.pairRow}>
          <View style={[styles.card, { flex: 1.1, minWidth: 0 }]}>
            <Text style={styles.cardLabel}>Monto total</Text>
            <View style={styles.fieldRow}>
              <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
                <Ionicons name="cash-outline" size={us(20)} color={pal.forest} />
              </View>
              <TextInput
                testID="debt-amount"
                value={amount}
                onChangeText={setAmount}
                keyboardType="decimal-pad"
                placeholder="0.00"
                placeholderTextColor={pal.muted}
                style={[styles.fieldInput, styles.amountInput]}
              />
            </View>
          </View>
          <Pressable
            testID="debt-pick-category"
            onPress={() => { Keyboard.dismiss(); setCatSheet(true); }}
            style={({ pressed }) => [styles.card, { flex: 1, minWidth: 0 }, pressed && styles.pressed]}
          >
            <Text style={styles.cardLabel}>Categoría</Text>
            <View style={styles.catRow}>
              {selCat ? (
                <IconTile icon={selCat.icon} tint={selCat.color} size={us(40)} />
              ) : (
                <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
                  <Ionicons name="pricetag-outline" size={us(20)} color={pal.forest} />
                </View>
              )}
              <Text style={[styles.catName, !selCat && { color: pal.muted }]} numberOfLines={2}>
                {selCat ? selCat.name : "Sin categoría"}
              </Text>
              <Ionicons name="chevron-forward" size={us(18)} color={pal.onSurface} />
            </View>
          </Pressable>
        </View>

        {/* Optional sections (closed by default) */}
        <Collapsible testID="toggle-min-pay" icon="cash-outline" title="Pago mínimo" summary={minSummary} pal={pal} styles={styles}>
          <TextInput
            testID="debt-min-pay"
            value={minPay}
            onChangeText={setMinPay}
            keyboardType="decimal-pad"
            placeholder="0.00"
            placeholderTextColor={pal.muted}
            style={[styles.innerInput, styles.amountInput]}
          />
        </Collapsible>

        <Collapsible testID="toggle-frequency" icon="calendar-outline" title="Frecuencia de pago" summary={freqSummary} pal={pal} styles={styles}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(8) }}>
            {FREQ.map((f) => {
              const sel = frequency === f.id;
              return (
                <Pressable
                  key={f.id}
                  testID={`freq-${f.id}`}
                  onPress={() => setFrequency(f.id)}
                  style={[styles.freqChip, sel && { backgroundColor: pal.mint, borderColor: pal.forest }]}
                >
                  <Text style={{ color: sel ? pal.forest : pal.onSurface, fontWeight: "700", fontSize: ufs(12) }}>{f.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </Collapsible>

        <Collapsible testID="toggle-interest" icon="trending-up-outline" title="Interés (%)" summary={intSummary} pal={pal} styles={styles}>
          <View style={[styles.innerInputRow]}>
            <TextInput
              testID="debt-interest"
              value={interest}
              onChangeText={setInterest}
              keyboardType="decimal-pad"
              placeholder="0"
              placeholderTextColor={pal.muted}
              style={[styles.innerInputFlat, styles.amountInput]}
            />
            <Text style={styles.percentSuffix}>%</Text>
          </View>
        </Collapsible>

        {/* Icon + color personalization */}
        <View style={styles.card}>
          <Text style={styles.cardLabel}>Icono</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: us(10), paddingVertical: us(2) }}>
            {ICONS.map((ic) => (
              <Pressable key={ic} testID={`debt-icon-${ic}`} onPress={() => setIcon(ic)} style={[styles.iconOpt, icon === ic && { borderColor: color, borderWidth: 2 }]}>
                <IconTile icon={ic} tint={color} size={us(34)} />
              </Pressable>
            ))}
          </ScrollView>
          <Text style={[styles.cardLabel, { marginTop: us(12) }]}>Color</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: us(10), paddingVertical: us(2) }}>
            {COLORS.map((c) => (
              <Pressable
                key={c}
                testID={`debt-color-${c}`}
                onPress={() => setColor(c)}
                style={[styles.colorRing, { borderColor: color === c ? pal.onSurface : "transparent" }]}
              >
                <View style={[styles.colorDot, { backgroundColor: c }]} />
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + us(12), backgroundColor: pal.bg }]}>
        <Pressable
          testID="save-debt"
          onPress={save}
          disabled={saving}
          style={({ pressed }) => [styles.saveBtn, { backgroundColor: pal.forest }, (pressed || saving) && { opacity: 0.85 }]}
        >
          <Text style={styles.saveText}>{saving ? "Guardando…" : "Guardar deuda"}</Text>
        </Pressable>
      </View>

      <AppSheet visible={catSheet} onClose={() => setCatSheet(false)} testID="debt-category-sheet">
        <View style={styles.sheetHeader}>
          <Text style={styles.sheetTitle}>Categoría</Text>
          <Pressable testID="debt-category-close" onPress={() => setCatSheet(false)} style={styles.sheetClose}>
            <Ionicons name="close" size={us(20)} color={pal.onSurface} />
          </Pressable>
        </View>
        <ScrollView style={{ maxHeight: us(420) }} contentContainerStyle={{ paddingHorizontal: us(spacing.lg), gap: us(6), paddingBottom: us(8) }}>
          <Pressable
            testID="debt-cat-none"
            onPress={() => { setCategoryId(undefined); setCatSheet(false); }}
            style={({ pressed }) => [styles.sheetRow, !categoryId && { backgroundColor: pal.mint }, pressed && styles.pressed]}
          >
            <View style={[styles.fieldIcon, { backgroundColor: pal.mint }]}>
              <Ionicons name="remove-circle-outline" size={us(20)} color={pal.forest} />
            </View>
            <Text style={styles.sheetRowText}>Sin categoría</Text>
            <View style={[styles.radio, !categoryId && { borderColor: pal.forest }]}>
              {!categoryId && <View style={[styles.radioDot, { backgroundColor: pal.forest }]} />}
            </View>
          </Pressable>
          {cats.length === 0 && <Text style={styles.sheetEmpty}>No hay categorías disponibles</Text>}
          {cats.map((c: any) => {
            const sel = c.id === categoryId;
            return (
              <Pressable
                key={c.id}
                testID={`debt-cat-${c.id}`}
                onPress={() => { setCategoryId(c.id); setCatSheet(false); }}
                style={({ pressed }) => [styles.sheetRow, sel && { backgroundColor: (c.color || pal.forest) + "1A" }, pressed && styles.pressed]}
              >
                <IconTile icon={c.icon} tint={c.color} size={us(40)} />
                <Text style={styles.sheetRowText}>{c.name}</Text>
                <View style={[styles.radio, sel && { borderColor: c.color || pal.forest }]}>
                  {sel && <View style={[styles.radioDot, { backgroundColor: c.color || pal.forest }]} />}
                </View>
              </Pressable>
            );
          })}
        </ScrollView>
      </AppSheet>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  const p = formPalette(colors, scheme);
  return {
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: spacing.lg },
  backBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { flex: 1, fontSize: 20, fontWeight: "800", color: colors.onSurface },
  // --- First step: debt-type selection (visual redesign) ---
  selWrap: { paddingHorizontal: spacing.lg, flex: 1, justifyContent: "center", paddingBottom: 48 },
  selIconTile: { alignSelf: "center", width: 60, height: 60, borderRadius: 18, alignItems: "center", justifyContent: "center", marginBottom: 18 },
  selHeading: { fontSize: 24, fontWeight: "800", color: colors.onSurface, textAlign: "center", letterSpacing: -0.5 },
  selSubheading: { fontSize: 14, color: colors.muted, textAlign: "center", marginTop: 6, fontWeight: "500" },
  selRow: { flexDirection: "row", gap: 14, marginTop: 28 },
  selCard: {
    flex: 1,
    minHeight: 208,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.cardLg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingTop: 26,
    paddingHorizontal: 14,
    alignItems: "center",
    overflow: "hidden",
    ...Platform.select({
      ios: { shadowColor: "#000", shadowOpacity: scheme === "dark" ? 0.25 : 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 4 } },
      android: { elevation: 2 },
      default: {},
    }),
  },
  selBand: { position: "absolute", left: 0, right: 0, bottom: 0, height: 92, borderTopLeftRadius: 78, borderTopRightRadius: 14 },
  selBandIcon: { position: "absolute", right: 8, bottom: 6, opacity: scheme === "dark" ? 0.14 : 0.1 },
  selCircle: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 16 },
  selCardTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  selCardSub: { fontSize: 13, color: colors.muted, textAlign: "center", marginTop: 6, fontWeight: "500", lineHeight: 18 },
  label: { color: colors.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", marginTop: 14, marginBottom: 8, letterSpacing: 0.5 },
  input: { fontSize: 15, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, padding: 14, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  freqChip: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  iconOpt: { padding: 4, borderRadius: 14, borderWidth: 1, borderColor: p.border, backgroundColor: p.field },
  saveBtn: { backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.pill, alignItems: "center" },
  saveText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  // --- Step 2: redesigned form ---
  card: {
    backgroundColor: p.card, borderRadius: radius.lg, borderWidth: 1, borderColor: p.border, padding: 12,
    ...Platform.select({
      ios: { shadowColor: "#274738", shadowOpacity: scheme === "dark" ? 0.2 : 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 3 } },
      android: { elevation: 1 },
      default: {},
    }),
  },
  cardLabel: { color: p.muted, fontSize: 12, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 },
  fieldRow: {
    flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: p.field,
    borderRadius: radius.md, borderWidth: 1, borderColor: p.border, paddingHorizontal: 6, paddingVertical: 6,
  },
  fieldIcon: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  fieldInput: { flex: 1, minWidth: 0, fontSize: 15, color: p.onSurface, paddingVertical: 8 },
  amountInput: { fontSize: 26, fontWeight: "800", color: p.onSurface },
  pairRow: { flexDirection: "row", gap: 10 },
  pressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  catRow: { flexDirection: "row", alignItems: "center", gap: 8, minHeight: 54 },
  catName: { flex: 1, minWidth: 0, fontSize: 15, fontWeight: "600", color: p.onSurface },
  collHeader: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: 48 },
  collTitle: { fontSize: 15, fontWeight: "700", color: p.onSurface },
  collSub: { fontSize: 13, color: p.muted, marginTop: 2, fontWeight: "500" },
  collBody: { position: "absolute", top: 0, left: 0, right: 0, paddingTop: 12 },
  innerInput: {
    backgroundColor: p.field, borderRadius: radius.md, borderWidth: 1, borderColor: p.border,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  innerInputRow: {
    flexDirection: "row", alignItems: "center", backgroundColor: p.field, borderRadius: radius.md,
    borderWidth: 1, borderColor: p.border, paddingHorizontal: 14,
  },
  innerInputFlat: { flex: 1, minWidth: 0, paddingVertical: 10 },
  percentSuffix: { fontSize: 20, fontWeight: "800", color: p.muted, marginLeft: 6 },
  colorRing: { width: 42, height: 42, borderRadius: 21, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  colorDot: { width: 32, height: 32, borderRadius: 16 },
  footer: { paddingHorizontal: spacing.lg, paddingTop: 10 },
  sheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: 10, marginTop: 4 },
  sheetTitle: { fontSize: 20, fontWeight: "800", color: p.onSurface },
  sheetClose: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: p.mint },
  sheetRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 8, paddingHorizontal: 8, borderRadius: radius.lg },
  sheetRowText: { flex: 1, minWidth: 0, fontSize: 16, fontWeight: "600", color: p.onSurface },
  sheetEmpty: { fontSize: 13, color: p.muted, paddingVertical: 12, paddingHorizontal: 8 },
  radio: { width: 24, height: 24, borderRadius: 12, borderWidth: 2, borderColor: p.border, alignItems: "center", justifyContent: "center" },
  radioDot: { width: 12, height: 12, borderRadius: 6 },
  };
});
