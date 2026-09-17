import { QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { useEffect } from "react";
import { LogBox, StatusBar, Text as RNText } from "react-native";
import * as Font from "expo-font";
import * as SplashScreen from "expo-splash-screen";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { ThemeProvider, useTheme } from "@/src/theme";
import { LockProvider } from "@/src/lock";

LogBox.ignoreAllLogs(true);

// Prewarm the icon fonts so bundled routes have icons on first render.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import "@react-native-vector-icons/ionicons";

SplashScreen.preventAutoHideAsync().catch(() => {});

// Apply the app font as the default for every <Text> in the tree, once.
const AnyText: any = RNText;
if (!AnyText.__moneyflowFontPatched) {
  AnyText.__moneyflowFontPatched = true;
  const prev = AnyText.render;
  AnyText.defaultProps = AnyText.defaultProps || {};
  AnyText.defaultProps.style = [
    { fontFamily: "SpaceGrotesk" },
    AnyText.defaultProps.style,
  ];
  // Keep render for future-proofing (some libs replace defaultProps).
  if (prev && !AnyText.__origRender) AnyText.__origRender = prev;
}

export default function RootLayout() {
  const [loaded] = Font.useFonts({
    SpaceGrotesk: require("../assets/fonts/SpaceGrotesk-Variable.ttf"),
  });

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync().catch(() => {});
  }, [loaded]);

  if (!loaded) return null;

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ThemedApp />
      </ThemeProvider>
    </ErrorBoundary>
  );
}

function ThemedApp() {
  const { scheme, colors } = useTheme();
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.surface }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <BottomSheetModalProvider>
            <LockProvider>
              <StatusBar barStyle={scheme === "dark" ? "light-content" : "dark-content"} backgroundColor={colors.surface} />
              <Stack
                screenOptions={{
                  headerShown: false,
                  contentStyle: { backgroundColor: colors.surface },
                  // Forward (push): slide the new screen in from the right — kept as-is
                  // but made noticeably faster/snappier. Native-stack automatically plays
                  // the REVERSE of this on pop (current screen slides out to the right and
                  // the previous screen is revealed), so back navigation gets its own clean
                  // reverse transition instead of re-using the forward-entry animation.
                  animation: "slide_from_right",
                  animationDuration: 160,
                  // Replaced screens should animate like a pop (return) so we never flash a
                  // forward-entry on top of an existing screen.
                  animationTypeForReplace: "pop",
                  gestureEnabled: true,
                }}
              />
            </LockProvider>
          </BottomSheetModalProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
