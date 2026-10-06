import React from "react";
import { View } from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { makeStyles, radius, spacing } from "@/src/theme";

import { us } from "@/src/ui-scale";
// NOTE: The previous "Movimientos" list screen has been preserved verbatim at
// `@/src/screens/TransactionsScreen` so its functionality can be reused later.
// This route now presents the new voice-entry "IA" screen (UI only).

const WAVE_BARS = [10, 18, 28, 20, 34, 20, 28, 18, 10];

export default function IA() {
  const styles = useStyles();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.container, { paddingTop: insets.top + us(24) }]}>
      {/* Heading */}
      <Text style={styles.title}>Registra con IA</Text>
      <Text style={styles.subtitle}>Dime un gasto o ingreso</Text>

      {/* Microphone — main action */}
      <View style={styles.micArea}>
        <View style={styles.halo} />
        <View style={[styles.ring, styles.ringOuter]} />
        <View style={[styles.ring, styles.ringMid]} />
        <Pressable
          testID="ia-mic-btn"
          onPress={() => {}}
          style={({ pressed }) => [styles.micButton, pressed && { transform: [{ scale: 0.96 }] }]}
        >
          <Ionicons name="mic" size={us(52)} color="#fff" />
        </Pressable>
      </View>

      {/* Elegant audio waveform */}
      <View style={styles.wave}>
        {WAVE_BARS.map((h, i) => (
          <View key={i} style={[styles.waveBar, { height: us(h) }]} />
        ))}
      </View>

      <Text style={styles.tapHint}>Toca para hablar</Text>

      {/* Example card */}
      <View style={styles.exampleCard}>
        <Text style={styles.exampleLabel}>Puedes decir algo como:</Text>
        <Text style={styles.exampleText}>
          “Gasté $47 en Walmart en comida con mi tarjeta Chase”
        </Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  // Match the Accounts/Home screen system: same wall + premium green family.
  const isDark = scheme === "dark";
  const wall = isDark ? colors.surface : "#E8EFE7"; // Home/Accounts wall
  const green = isDark ? "#2CA079" : "#126046"; // Home/Accounts premium green
  return {
  container: {
    flex: 1,
    backgroundColor: wall,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
  },
  title: {
    fontSize: 26,
    fontWeight: "800",
    color: colors.onSurface,
    textAlign: "center",
    marginTop: spacing.sm,
  },
  subtitle: {
    fontSize: 15,
    color: colors.muted,
    textAlign: "center",
    marginTop: 6,
  },
  micArea: {
    width: 260,
    height: 260,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.xxxl,
  },
  // Extremely soft coral glow behind the button
  halo: {
    position: "absolute",
    width: 236,
    height: 236,
    borderRadius: 999,
    backgroundColor: green + "0D",
  },
  // Very subtle concentric circles
  ring: {
    position: "absolute",
    borderRadius: 999,
    borderWidth: 1,
  },
  ringOuter: {
    width: 236,
    height: 236,
    borderColor: green + "1F",
  },
  ringMid: {
    width: 184,
    height: 184,
    borderColor: green + "33",
  },
  micButton: {
    width: 128,
    height: 128,
    borderRadius: 64,
    backgroundColor: green,
    alignItems: "center",
    justifyContent: "center",
    // Soft green shadow/glow — same premium green family as the Home/Accounts screen
    shadowColor: green,
    shadowOpacity: 0.35,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 10 },
    elevation: 12,
  },
  wave: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    height: 40,
    marginTop: spacing.lg,
  },
  waveBar: {
    width: 3.5,
    borderRadius: 2,
    backgroundColor: green + "66",
  },
  tapHint: {
    fontSize: 14,
    fontWeight: "600",
    color: colors.muted,
    marginTop: spacing.md,
  },
  exampleCard: {
    marginTop: spacing.xxxl,
    width: "100%",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    // Soft card shadow, consistent with the app's cards
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
  exampleLabel: {
    fontSize: 12,
    color: colors.muted,
    fontWeight: "600",
    marginBottom: 6,
  },
  exampleText: {
    fontSize: 15,
    color: colors.onSurface,
    fontWeight: "600",
    lineHeight: 21,
  },
  };
});
