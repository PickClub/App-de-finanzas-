import React from "react";
import { Pressable, View } from "react-native";
import { Text } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useTheme, radius } from "@/src/theme";

export function IconTile({
  icon,
  tint,
  size = 44,
  iconSize,
}: {
  icon: string;
  tint: string;
  size?: number;
  iconSize?: number;
}) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 3,
        backgroundColor: tint + "26",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Ionicons name={icon as any} size={iconSize || size * 0.55} color={tint} />
    </View>
  );
}

export function Chip({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active?: boolean;
  onPress?: () => void;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={{
        height: 36,
        paddingHorizontal: 16,
        borderRadius: radius.pill,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: active ? colors.brandPrimary : colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: active ? colors.brandPrimary : colors.border,
        flexShrink: 0,
      }}
    >
      <Text
        style={{
          color: active ? colors.onBrandPrimary : colors.onSurface,
          fontSize: 13,
          fontWeight: "600",
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}
