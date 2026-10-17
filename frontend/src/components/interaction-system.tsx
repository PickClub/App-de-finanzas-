import React, { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { AccessibilityInfo, ActivityIndicator, findNodeHandle, Keyboard, KeyboardAvoidingView, Modal, Platform, ScrollView, StyleSheet, View, useWindowDimensions, type StyleProp, type ViewStyle } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { usePathname } from "expo-router";
import { useFonts } from "expo-font";
import Animated, { Easing, ReduceMotion, runOnJS, useAnimatedStyle, useReducedMotion, useSharedValue, withTiming } from "react-native-reanimated";
import { useTranslation } from "@/src/i18n";
import { localizedError } from "@/src/i18n/errors";
import { useTheme } from "@/src/theme";
import { Pressable } from "./pressable";
import { Text } from "./typography";
import { Alert, interactions, placeContextMenu, type AnchorRect, type ContextAction, type AlertButton } from "./interaction-state";
export { Alert } from "./interaction-state";
export type { ContextAction } from "./interaction-state";

function focusView(view: View | null) {
  if (!view) return;
  const handle = findNodeHandle(view);
  if (handle) AccessibilityInfo.setAccessibilityFocus(handle);
}
function useInteractionFonts() {
  const [ready] = useFonts({
    "MoneyFlowDialog-Regular": require("../../assets/fonts/Montserrat-Regular.ttf"),
    "MoneyFlowDialog-Bold": require("../../assets/fonts/Montserrat-Bold.ttf"),
  });
  return ready ? { regular: { fontFamily: "MoneyFlowDialog-Regular" }, bold: { fontFamily: "MoneyFlowDialog-Bold", fontWeight: undefined } } : { regular: {}, bold: { fontWeight: "700" as const } };
}

export function ContextActionsTrigger({ actions, testID, style, iconColor, iconSize = 20, disabled, accessibilityLabel }: {
  actions: ContextAction[]; testID?: string; style?: StyleProp<ViewStyle>; iconColor?: string; iconSize?: number; disabled?: boolean; accessibilityLabel?: string;
}) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const owner = useId();
  const trigger = useRef<View>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; interactions.clearMenu(owner); }; }, [owner]);
  return <Pressable ref={trigger} testID={testID} accessibilityRole="button" accessibilityLabel={accessibilityLabel || t("ui.more_options")} disabled={disabled || !actions.length} style={style || styles.trigger} onPress={event => {
    event.stopPropagation?.();
    if (disabled) return;
    trigger.current?.measureInWindow((x, y, width, height) => {
      if (alive.current) interactions.openMenu(owner, { x, y, width, height }, actions, () => { if (alive.current) focusView(trigger.current); });
    });
  }}><Ionicons name="ellipsis-horizontal" size={iconSize} color={iconColor || colors.onSurface} /></Pressable>;
}

function MenuOverlay() {
  const { menu } = useSyncExternalStore(interactions.subscribe, interactions.getSnapshot);
  const { colors } = useTheme();
  const { t } = useTranslation();
  const fonts = useInteractionFonts();
  const insets = useSafeAreaInsets();
  const window = useWindowDimensions();
  const pathname = usePathname();
  const root = useRef<View>(null);
  const card = useRef<View>(null);
  const [viewport, setViewport] = useState<AnchorRect | null>(null);
  const [keyboardTop, setKeyboardTop] = useState<number | null>(null);
  const progress = useSharedValue(0);
  const animatedMenu = useRef<number | null>(null);
  useEffect(() => { interactions.clearMenu(); }, [pathname]);
  useEffect(() => {
    const show = Keyboard.addListener("keyboardDidShow", e => setKeyboardTop(e.endCoordinates.screenY));
    const hide = Keyboard.addListener("keyboardDidHide", () => setKeyboardTop(null));
    return () => { show.remove(); hide.remove(); };
  }, []);
  const bottomClearance = ["/", "/more", "/notes", "/reports", "/transactions"].includes(pathname) ? 88 : 0;
  const placement = menu && viewport ? placeContextMenu(menu.anchor, viewport, insets, keyboardTop, window.fontScale, menu.actions.length, bottomClearance) : null;
  const finishClose = (id: number) => {
    const operation = interactions.finishMenuClose(id);
    if (operation) {
      try { Promise.resolve(operation()).catch(error => Alert.alert(t("common.error"), localizedError(error))); }
      catch (error) { Alert.alert(t("common.error"), localizedError(error)); }
    }
  };
  useEffect(() => {
    if (!menu || !placement) { progress.value = 0; return; }
    if (menu.closing) progress.value = withTiming(0, { duration: 130, easing: Easing.in(Easing.cubic), reduceMotion: ReduceMotion.System }, done => { if (done) runOnJS(finishClose)(menu.id); });
    else {
      if (animatedMenu.current !== menu.id) { progress.value = 0; animatedMenu.current = menu.id; }
      progress.value = withTiming(1, { duration: 190, easing: Easing.out(Easing.cubic), reduceMotion: ReduceMotion.System });
    }
    // Repositioning does not restart the opening animation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [menu?.id, menu?.closing, !!placement]);
  const animation = useAnimatedStyle(() => ({ opacity: progress.value, transform: [{ translateY: (1 - progress.value) * (placement?.upward ? 8 : -8) }] }));
  useEffect(() => {
    if (menu && viewport && !placement) interactions.clearMenu(menu.owner);
  }, [menu, viewport, placement]);
  if (!menu) return null;
  // The transparent native window is an overlay host; only the anchored card is a menu.
  // It also keeps menus above existing native Notes modals without clipping list rows.
  return <Modal transparent visible animationType="none" statusBarTranslucent onRequestClose={() => interactions.closeMenu()}>
    <View ref={root} style={styles.overlay} onLayout={() => root.current?.measureInWindow((x, y, width, height) => {
      if ([x, y, width, height].every(Number.isFinite) && width > 0 && height > 0) setViewport({ x, y, width, height });
    })}>
      <Pressable testID="context-menu-backdrop" accessible={false} style={StyleSheet.absoluteFill} onPress={() => interactions.closeMenu()} />
      {placement && <Animated.View ref={card} onLayout={() => focusView(card.current)} accessibilityViewIsModal testID="context-actions-menu" style={[styles.menu, { left: placement.x, top: placement.y, width: placement.width, maxHeight: placement.height, backgroundColor: colors.surfaceSecondary, borderColor: colors.border }, animation]}>
        <ScrollView style={{ maxHeight: placement.height }} contentContainerStyle={styles.menuContent} showsVerticalScrollIndicator nestedScrollEnabled keyboardShouldPersistTaps="handled">
          {menu.actions.map(action => <Pressable key={action.id} testID={`context-action-${action.id}`} accessibilityRole="menuitem" accessibilityState={{ disabled: !!action.disabled || menu.closing }} disabled={action.disabled || menu.closing} onPress={() => interactions.selectMenuAction(menu.id, action.id)} style={[styles.menuItem, { opacity: action.disabled ? 0.45 : 1 }]}>
            <Ionicons name={action.icon as any} size={20} color={action.destructive ? colors.expenseRed : colors.onSurface} />
            <Text style={[styles.menuLabel, fonts.regular, { color: action.destructive ? colors.expenseRed : colors.onSurface }]}>{action.label}</Text>
          </Pressable>)}
        </ScrollView>
      </Animated.View>}
    </View>
  </Modal>;
}

type DialogProps = {
  visible: boolean; onClose: () => void; icon: string; accent?: string; title: string; description?: string;
  confirmLabel: string; onConfirm: () => unknown; destructive?: boolean; confirmTestID?: string; busy?: boolean;
  error?: string; children?: React.ReactNode; hideConfirm?: boolean; cancelLabel?: string; cancelTestID?: string;
};
function DialogSurface({ title, description, icon, accent, error, children, buttons, busy, onClose }: {
  title: string; description?: string; icon: string; accent: string; error?: string; children?: React.ReactNode;
  buttons: { id: string; label: string; onPress: () => void; destructive?: boolean; primary?: boolean; color?: string }[]; busy: boolean; onClose: () => void;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const fonts = useInteractionFonts();
  const titleRef = useRef<View>(null);
  const reduceMotion = useReducedMotion();
  return <Modal transparent visible animationType={reduceMotion ? "none" : "fade"} statusBarTranslucent onRequestClose={() => { if (!busy) onClose(); }}>
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "ios" ? "padding" : "height"}>
    <View style={[styles.dialogOverlay, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16, paddingLeft: insets.left + 20, paddingRight: insets.right + 20 }]}>
      <Pressable accessible={false} testID="dialog-backdrop" style={StyleSheet.absoluteFill} onPress={() => { if (!busy) onClose(); }} />
      <View accessibilityViewIsModal style={[styles.dialog, { backgroundColor: colors.surfaceSecondary, borderColor: colors.border }]}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.dialogContent}>
          <View style={[styles.dialogIcon, { backgroundColor: accent + "1F" }]}><Ionicons name={icon as any} size={30} color={accent} /></View>
          <View ref={titleRef} onLayout={() => focusView(titleRef.current)} accessible><Text accessibilityRole="header" style={[styles.dialogTitle, fonts.bold, { color: colors.onSurface }]}>{title}</Text></View>
          {!!description && <Text style={[styles.dialogDescription, fonts.regular, { color: colors.muted }]}>{description}</Text>}
          {!!error && <Text testID="dialog-error" accessibilityRole="alert" style={[styles.dialogDescription, fonts.regular, { color: colors.expenseRed }]}>{error}</Text>}
          {children}
          <View style={styles.dialogButtons}>
            {buttons.map(button => <Pressable key={button.id} testID={button.id} accessibilityRole="button" accessibilityState={{ disabled: busy, busy: busy && !!button.primary }} disabled={busy} onPress={button.onPress} style={[styles.dialogButton, { backgroundColor: button.primary ? button.destructive ? colors.expenseRed : button.color || accent : colors.surfaceTertiary, opacity: busy ? 0.6 : 1 }]}>
              {busy && button.primary ? <ActivityIndicator color={button.destructive ? colors.onError : colors.onSuccess} /> : <Text style={[styles.buttonLabel, fonts.bold, { color: button.primary ? button.destructive ? colors.onError : colors.onSuccess : button.destructive ? colors.expenseRed : colors.onSurface }]}>{button.label}</Text>}
            </Pressable>)}
          </View>
        </ScrollView>
      </View>
    </View>
    </KeyboardAvoidingView>
  </Modal>;
}

export function MoneyFlowConfirmDialog(props: DialogProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const working = useRef(false);
  const [pending, setPending] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const busy = !!props.busy || pending;
  const closeIfIdle = () => { if (!props.busy && !working.current) props.onClose(); };
  if (!props.visible) return null;
  return <DialogSurface title={props.title} description={props.description} icon={props.icon} accent={props.destructive ? colors.expenseRed : props.accent || colors.incomeGreen} error={props.error} busy={busy} onClose={closeIfIdle} buttons={[
    ...props.hideConfirm ? [] : [{ id: props.confirmTestID || "confirm-primary", label: props.confirmLabel, primary: true, destructive: props.destructive, color: props.destructive ? colors.expenseRed : colors.incomeGreen, onPress: async () => {
      if (props.busy || working.current) return;
      working.current = true; setPending(true);
      try { await props.onConfirm(); }
      catch (error) { Alert.alert(t("common.error"), localizedError(error)); }
      finally { working.current = false; if (active.current) setPending(false); }
    } }],
    { id: props.cancelTestID || "confirm-cancel", label: props.cancelLabel || t("common.cancel"), onPress: closeIfIdle },
  ]}>{props.children}</DialogSurface>;
}

function AlertOverlay() {
  const { alert } = useSyncExternalStore(interactions.subscribe, interactions.getSnapshot);
  const { colors } = useTheme();
  const { t } = useTranslation();
  if (!alert) return null;
  const buttons: AlertButton[] = alert.buttons?.length ? alert.buttons : [{}];
  const destructive = buttons.some(button => button.style === "destructive");
  return <DialogSurface title={alert.title} description={alert.message} icon={destructive ? "trash-outline" : "information-circle-outline"} accent={destructive ? colors.expenseRed : colors.incomeGreen} busy={alert.busy} onClose={() => interactions.dismissAlert(alert.id)} buttons={buttons.map((button, index) => ({
    id: `alert-action-${index}`, label: button.text || t("common.close"), destructive: button.style === "destructive", primary: button.style !== "cancel", color: button.style === "destructive" ? colors.expenseRed : colors.incomeGreen,
    onPress: async () => {
      if (!interactions.claimAlert(alert.id)) return;
      try { await button.onPress?.(); }
      catch (error) { Alert.alert(t("common.error"), localizedError(error)); }
      finally { interactions.finishAlert(alert.id); }
    },
  }))} />;
}

export function InteractionProvider({ children }: { children: React.ReactNode }) {
  return <>{children}<MenuOverlay /><AlertOverlay /></>;
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  trigger: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  overlay: { flex: 1 },
  menu: { position: "absolute", borderRadius: 18, borderWidth: 1, overflow: "hidden", shadowColor: "#123D2E", shadowOpacity: 0.12, shadowRadius: 12, shadowOffset: { width: 0, height: 4 }, elevation: 12 },
  menuContent: { paddingVertical: 6 },
  menuItem: { minHeight: 48, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 16, paddingVertical: 10 },
  menuLabel: { fontSize: 14, flex: 1, flexShrink: 1, lineHeight: 20 },
  dialogOverlay: { flex: 1, backgroundColor: "rgba(16,40,29,0.28)", alignItems: "center", justifyContent: "center" },
  dialog: { width: "100%", maxWidth: 380, maxHeight: "90%", borderRadius: 24, borderWidth: 1, shadowColor: "#123D2E", shadowOpacity: 0.12, shadowRadius: 16, shadowOffset: { width: 0, height: 5 }, elevation: 12 },
  dialogContent: { padding: 24, alignItems: "center" },
  dialogIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  dialogTitle: { fontSize: 19, fontWeight: "700", textAlign: "center" },
  dialogDescription: { fontSize: 14, lineHeight: 21, textAlign: "center", marginTop: 10 },
  dialogButtons: { alignSelf: "stretch", gap: 10, marginTop: 22 },
  dialogButton: { minHeight: 48, borderRadius: 24, paddingHorizontal: 16, paddingVertical: 12, alignItems: "center", justifyContent: "center" },
  buttonLabel: { fontSize: 15, textAlign: "center", fontWeight: "700" },
});
