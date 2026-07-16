import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect, useRef } from "react";
import { LogBox, AppState } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts } from "expo-font";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/auth";
import { wireHandlers, syncAndSchedule } from "@/src/services/notifications";
import { fullSync as calendarFullSync } from "@/src/services/calendar";
import { registerBackgroundSync } from "@/src/services/background";

// Disable logbox errors etc so that users can see the app
// and agent works as expected.
LogBox.ignoreAllLogs(true);

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
SplashScreen.preventAutoHideAsync();

function RootNav() {
  const { ready, user, onboarded } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => { wireHandlers(); registerBackgroundSync(); }, []);

  const appState = useRef(AppState.currentState);
  useEffect(() => {
    if (user) {
      syncAndSchedule().catch(() => {});
      calendarFullSync().catch(() => {});
    }
  }, [user]);

  // Foreground re-sync: when the app returns to the active state (also covers "after
  // permissions restored" and "after external change" once the user reopens the app).
  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (appState.current.match(/inactive|background/) && next === "active" && user) {
        calendarFullSync().catch(() => {});
        syncAndSchedule().catch(() => {});
      }
      appState.current = next;
    });
    return () => sub.remove();
  }, [user]);

  useEffect(() => {
    if (!ready) return;
    SplashScreen.hideAsync();
    const publicRoutes = ["login", "verify-email", "reset-password"];
    const onPublic = publicRoutes.includes(segments[0] as string);
    const onOnboarding = segments[0] === "onboarding";
    if (!user && !onPublic) { router.replace("/login"); return; }
    if (user && !onboarded && !onOnboarding) { router.replace("/onboarding"); return; }
    if (user && onboarded && (segments[0] === "login" || onOnboarding)) router.replace("/(tabs)");
  }, [ready, user, onboarded, segments]);

  if (!ready) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="verify-email" />
      <Stack.Screen name="reset-password" />
      <Stack.Screen name="onboarding" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="calendar-connect" options={{ presentation: "modal" }} />
      <Stack.Screen name="listen" options={{ presentation: "modal" }} />
      <Stack.Screen name="diagnostics" options={{ presentation: "modal" }} />
      <Stack.Screen name="quick-capture" options={{ presentation: "modal" }} />
      <Stack.Screen name="notes" options={{ presentation: "modal" }} />
      <Stack.Screen name="record" options={{ presentation: "modal" }} />
      <Stack.Screen name="item-detail" options={{ presentation: "modal" }} />
      <Stack.Screen name="search" options={{ presentation: "modal" }} />
      <Stack.Screen name="inbox" options={{ presentation: "modal" }} />
      <Stack.Screen name="course/[name]" options={{ presentation: "modal" }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [iconsLoaded, iconErr] = useIconFonts();
  const [fontsLoaded, fontErr] = useFonts({
    "SpaceGrotesk-Bold": require("../assets/fonts/SpaceGrotesk-Bold.ttf"),
    SpaceGrotesk: require("../assets/fonts/SpaceGrotesk-Medium.ttf"),
    Manrope: require("../assets/fonts/Manrope-Regular.ttf"),
    "Manrope-Medium": require("../assets/fonts/Manrope-Medium.ttf"),
    "Manrope-Bold": require("../assets/fonts/Manrope-Bold.ttf"),
  });

  const fontsReady = (iconsLoaded || iconErr) && (fontsLoaded || fontErr);
  if (!fontsReady) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AuthProvider>
          <RootNav />
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
