/** Presentation state only: never owns financial operations, records or retries. */
export type ContextAction = {
  id: string;
  label: string;
  icon: string;
  destructive?: boolean;
  disabled?: boolean;
  onPress: () => unknown;
};
export type AnchorRect = { x: number; y: number; width: number; height: number };
export type AlertButton = { text?: string; style?: "default" | "cancel" | "destructive"; onPress?: () => unknown };
export type AlertOptions = { cancelable?: boolean; onDismiss?: () => void; userInterfaceStyle?: string };
type Menu = { id: number; owner: string; anchor: AnchorRect; actions: ContextAction[]; closing: boolean; selected?: string; restoreFocus?: () => void };
type AlertRequest = { id: number; title: string; message?: string; buttons?: AlertButton[]; options?: AlertOptions; busy: boolean };
type Snapshot = { menu: Menu | null; alert: AlertRequest | null; queue: AlertRequest[] };

export function createInteractionStore() {
  let snapshot: Snapshot = { menu: null, alert: null, queue: [] };
  let nextId = 1;
  const listeners = new Set<() => void>();
  const publish = (next: Snapshot) => { snapshot = next; listeners.forEach(listener => listener()); };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    openMenu(owner: string, anchor: AnchorRect, actions: ContextAction[], restoreFocus?: () => void) {
      if (snapshot.alert || snapshot.menu?.closing || !actions.length || !Object.values(anchor).every(Number.isFinite) || anchor.width <= 0 || anchor.height <= 0) return;
      publish({ ...snapshot, menu: { id: nextId++, owner, anchor, actions: [...actions], closing: false, restoreFocus } });
    },
    closeMenu(owner?: string) {
      const menu = snapshot.menu;
      if (!menu || menu.closing || owner && menu.owner !== owner) return;
      publish({ ...snapshot, menu: { ...menu, closing: true } });
    },
    selectMenuAction(id: number, actionId: string) {
      const menu = snapshot.menu;
      if (!menu || menu.id !== id || menu.closing || !menu.actions.some(action => action.id === actionId && !action.disabled)) return;
      publish({ ...snapshot, menu: { ...menu, closing: true, selected: actionId } });
    },
    finishMenuClose(id: number) {
      const menu = snapshot.menu;
      if (!menu || menu.id !== id || !menu.closing) return;
      const action = menu.actions.find(action => action.id === menu.selected && !action.disabled);
      publish({ ...snapshot, menu: null });
      menu.restoreFocus?.();
      return action?.onPress;
    },
    clearMenu(owner?: string) {
      if (snapshot.menu && (!owner || snapshot.menu.owner === owner)) publish({ ...snapshot, menu: null });
    },
    alert(title: string, message?: string, buttons?: AlertButton[], options?: AlertOptions) {
      const request = { id: nextId++, title, message, buttons, options, busy: false };
      publish(snapshot.alert
        ? { ...snapshot, queue: [...snapshot.queue, request] }
        : { ...snapshot, menu: null, alert: request });
    },
    claimAlert(id: number) {
      if (snapshot.alert?.id !== id || snapshot.alert.busy) return false;
      publish({ ...snapshot, alert: { ...snapshot.alert, busy: true } });
      return true;
    },
    finishAlert(id: number) {
      if (snapshot.alert?.id !== id) return;
      const [next, ...queue] = snapshot.queue;
      publish({ ...snapshot, alert: next || null, queue });
    },
    dismissAlert(id: number) {
      const current = snapshot.alert;
      if (current?.id !== id || current.busy || !current.options?.cancelable) return;
      const [next, ...queue] = snapshot.queue;
      publish({ ...snapshot, alert: next || null, queue });
      current.options.onDismiss?.();
    },
  };
}

export const interactions = createInteractionStore();
// Callback-compatible replacement for application-owned React Native alerts.
export const Alert = { alert: interactions.alert };

export function placeContextMenu(anchor: AnchorRect, viewport: AnchorRect, insets: { top: number; bottom: number; left: number; right: number }, keyboardTop: number | null, fontScale: number, actionCount: number, bottomClearance = 0) {
  if (![...Object.values(anchor), ...Object.values(viewport), ...Object.values(insets), fontScale, actionCount].every(Number.isFinite) || viewport.width <= 0 || viewport.height <= 0) return null;
  const gap = 8;
  const left = insets.left + gap, right = viewport.width - insets.right - gap;
  const top = insets.top + gap;
  const bottom = Math.min(viewport.height - insets.bottom - gap - bottomClearance, keyboardTop === null ? Infinity : keyboardTop - viewport.y - gap);
  const width = Math.min(Math.max(210, 210 * fontScale), 280, right - left);
  const estimatedHeight = Math.min(304, actionCount * Math.max(48, 48 * fontScale) + 12);
  const anchorTop = anchor.y - viewport.y, anchorBottom = anchorTop + anchor.height;
  const belowStart = Math.max(anchorBottom + gap, top);
  const aboveEnd = Math.min(anchorTop - gap, bottom);
  const below = bottom - belowStart, above = aboveEnd - top;
  const upward = below < estimatedHeight && above > below;
  const height = Math.min(estimatedHeight, Math.max(0, upward ? above : below));
  if (width <= 0 || height < 44) return null;
  return {
    x: Math.min(Math.max(anchor.x - viewport.x + anchor.width - width, left), right - width),
    y: upward ? aboveEnd - height : belowStart,
    width, height, upward,
  };
}
