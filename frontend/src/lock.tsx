import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Animated, Easing, StyleSheet, View, type GestureResponderEvent } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import { useTheme, makeStyles, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";

import { us } from "@/src/ui-scale";
type LockContextValue = {
  locked: boolean;
  toggle: () => void;
  setLocked: (v: boolean) => void;
  /**
   * Wrap a Pressable's onPress. When unlocked, calls fn(e). When locked, cancels
   * the action, plays a warning haptic and emits a small flash at the touch point.
   */
  guard: <T extends (e?: GestureResponderEvent) => any>(fn: T) => (e?: GestureResponderEvent) => void;
};

const LockContext = createContext<LockContextValue>({
  locked: false,
  toggle: () => {},
  setLocked: () => {},
  guard: (fn) => (e) => fn(e),
});

type Flash = { id: number; x: number; y: number };

const STORAGE_KEY = "edit-lock";

export function LockProvider({ children }: { children: React.ReactNode }) {
  const [locked, setLockedState] = useState(false);
  const [flashes, setFlashes] = useState<Flash[]>([]);
  const nextId = useRef(1);

  useEffect(() => {
    (async () => {
      const v = await storage.getItem<boolean>(STORAGE_KEY, false);
      if (v) setLockedState(true);
    })();
  }, []);

  const setLocked = useCallback((v: boolean) => {
    setLockedState(v);
    storage.setItem(STORAGE_KEY, v);
    Haptics.selectionAsync().catch(() => {});
  }, []);

  const toggle = useCallback(() => setLocked(!locked), [locked, setLocked]);

  const spawn = useCallback((x: number, y: number) => {
    const id = nextId.current++;
    setFlashes((prev) => [...prev, { id, x, y }]);
    setTimeout(() => setFlashes((prev) => prev.filter((f) => f.id !== id)), 700);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
  }, []);

  const guard = useCallback(
    <T extends (e?: GestureResponderEvent) => any>(fn: T) =>
      (e?: GestureResponderEvent) => {
        if (locked) {
          const x = e?.nativeEvent?.pageX ?? 200;
          const y = e?.nativeEvent?.pageY ?? 300;
          spawn(x, y);
          return;
        }
        fn(e);
      },
    [locked, spawn],
  );

  const value = useMemo(() => ({ locked, setLocked, toggle, guard }), [locked, setLocked, toggle, guard]);

  return (
    <LockContext.Provider value={value}>
      {children}
      <FlashLayer flashes={flashes} />
    </LockContext.Provider>
  );
}

export function useLock() {
  return useContext(LockContext);
}

function FlashLayer({ flashes }: { flashes: Flash[] }) {
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {flashes.map((f) => (
        <FlashDot key={f.id} x={f.x} y={f.y} />
      ))}
    </View>
  );
}

function FlashDot({ x, y }: { x: number; y: number }) {
  const { colors } = useTheme();
  const scale = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(1)).current;
  const inner = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(scale, { toValue: 1, duration: 500, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
      Animated.timing(opacity, { toValue: 0, duration: 620, easing: Easing.in(Easing.quad), useNativeDriver: true }),
      Animated.sequence([
        Animated.timing(inner, { toValue: 1, duration: 140, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        Animated.timing(inner, { toValue: 0, duration: 260, easing: Easing.in(Easing.cubic), useNativeDriver: true }),
      ]),
    ]).start();
  }, [scale, opacity, inner]);

  const SIZE = us(84);
  return (
    <View
      pointerEvents="none"
      style={{
        position: "absolute",
        left: x - SIZE / 2,
        top: y - SIZE / 2,
        width: SIZE,
        height: SIZE,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Animated.View
        style={{
          position: "absolute",
          width: SIZE,
          height: SIZE,
          borderRadius: SIZE / 2,
          backgroundColor: colors.brandPrimary + "22",
          borderWidth: 2,
          borderColor: colors.brandPrimary,
          transform: [{ scale }],
          opacity,
        }}
      />
      <Animated.View
        style={{
          width: us(22),
          height: us(22),
          borderRadius: us(11),
          backgroundColor: colors.brandPrimary,
          alignItems: "center",
          justifyContent: "center",
          transform: [{ scale: inner.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1.1] }) }],
          opacity,
        }}
      >
        <Ionicons name="lock-closed" size={us(12)} color="#fff" />
      </Animated.View>
    </View>
  );
}

export function LockToggle({ testID, compact }: { testID?: string; compact?: boolean }) {
  const { colors } = useTheme();
  const styles = useStyles();
  const { locked, toggle } = useLock();
  return (
    <Pressable
      testID={testID || "lock-toggle"}
      onPress={toggle}
      hitSlop={8}
      style={[
        styles.toggle,
        compact && { paddingHorizontal: us(8), height: us(30) },
        locked ? styles.toggleOn : styles.toggleOff,
      ]}
    >
      <Ionicons
        name={locked ? "lock-closed" : "lock-open-outline"}
        size={us(compact ? 14 : 15)}
        color={locked ? "#fff" : colors.onSurface}
      />
      {!compact && (
        <Text style={[styles.toggleText, { color: locked ? "#fff" : colors.onSurface }]}>
          {locked ? "Bloqueado" : "Editable"}
        </Text>
      )}
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  toggle: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    height: 32,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  toggleOff: {
    backgroundColor: colors.surfaceSecondary,
    borderColor: colors.border,
  },
  toggleOn: {
    backgroundColor: colors.brandPrimary,
    borderColor: colors.brandPrimary,
  },
  toggleText: { fontSize: 12, fontWeight: "700" },
}));
