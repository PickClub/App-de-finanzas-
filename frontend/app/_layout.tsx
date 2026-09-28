import { QueryClientProvider } from "@tanstack/react-query";
// Use the official native stack from expo-router. The native stack drives its
// slide animation on the native side, so it does not intercept the vertical
// touches of ScrollViews on Android (unlike the JS stack's horizontal pan).
import { Stack } from "expo-router";
import { useEffect } from "react";
import { StatusBar } from "react-native";
import * as Font from "expo-font";
import * as SplashScreen from "expo-splash-screen";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { ThemeProvider, useTheme } from "@/src/theme";
import { LockProvider } from "@/src/lock";
import { LanguageProvider } from "@/src/i18n";

// Prewarm the icon fonts so bundled routes have icons on first render.
import "@react-native-vector-icons/ionicons";

SplashScreen.preventAutoHideAsync().catch(() => {});

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
      <LanguageProvider>
        <ThemeProvider>
          <ThemedApp />
        </ThemeProvider>
      </LanguageProvider>
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
                  // Native Expo Router Stack transition: pushed screens rise
                  // subtly from the bottom and fade in (Android/Expo Go native).
                  animation: "fade_from_bottom",
                  gestureEnabled: true,
                  fullScreenGestureEnabled: false,
                }}
              />
            </LockProvider>
          </BottomSheetModalProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
