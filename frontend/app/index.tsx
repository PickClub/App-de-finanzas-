import React from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { Redirect } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/src/api";
import { useTheme, makeStyles } from "@/src/theme";

export default function Index() {
  const { colors } = useTheme();
  const styles = useStyles();
  // Load the profile without creating or replacing financial data.
  const { isLoading } = useQuery({
    queryKey: ["user"],
    queryFn: api.getUser,
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  return <Redirect href="/(tabs)" />;
}

const useStyles = makeStyles((colors) => ({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
}));
