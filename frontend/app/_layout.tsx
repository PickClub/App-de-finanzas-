import { QueryClientProvider } from "@tanstack/react-query";
// Use expo-router's JavaScript stack layout so we can define a precise,
// navigation-level transition (short horizontal slide + subtle fade). The
// default `Stack` from "expo-router" is the native-stack whose presets cannot
// express a custom ~24px slide + fade + ease-out curve.
import { Stack } from "expo-router/build/layouts/JSStack";
import { useEffect } from "react";
import { Easing, LogBox, StatusBar, Text as RNText } from "react-native";
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

// ---------------------------------------------------------------------------
// Premium, controlled navigation transition (normal screens).
// ~220ms, ease-out timing, applied at the navigation level (screen card).
// Forward: incoming screen starts ~24px to the right and fades in as it
// settles to its final position. Back: React Navigation drives the same
// interpolator in reverse (progress 1 -> 0), so the leaving screen slides
// back to the right and fades out — the exact inverse. No spring, no bounce,
// no zoom/scale, no large full-screen slide. Transform + opacity only, which
// run on the native driver for 60fps performance.
// ---------------------------------------------------------------------------
const TRANSITION_SPEC = {
  animation: "timing" as const,
  config: { duration: 220, easing: Easing.out(Easing.ease) },
};

const smoothSlideFade = ({ current }: any) => ({
  cardStyle: {
    opacity: current.progress.interpolate({
      inputRange: [0, 1],
      outputRange: [0, 1],
    }),
    transform: [
      {
        translateX: current.progress.interpolate({
          inputRange: [0, 1],
          outputRange: [24, 0],
        }),
      },
    ],
  },
});

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
                  cardStyle: { backgroundColor: colors.surface },
                  // Preserve swipe-back / back gestures (horizontal).
                  gestureEnabled: true,
                  gestureDirection: "horizontal",
                  // Keep the transition clean: no leading-edge shadow / dark
                  // overlay on the underlying screen during the slide.
                  cardShadowEnabled: false,
                  cardOverlayEnabled: false,
                  // Premium short slide + subtle fade, ~220ms ease-out.
                  transitionSpec: { open: TRANSITION_SPEC, close: TRANSITION_SPEC },
                  cardStyleInterpolator: smoothSlideFade,
                }}
              />
            </LockProvider>
          </BottomSheetModalProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
