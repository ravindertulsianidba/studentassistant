import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useFonts } from "expo-font";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/auth";
import { wireHandlers, syncAndSchedule } from "@/src/services/notifications";

// Disable logbox errors etc so that users can see the app
// and agent works as expected.
LogBox.ignoreAllLogs(true);

// Keep the native splash visible from cold start until icon fonts register.
// Required because @expo/vector-icons' componentDidMount fallback fires
// Font.loadAsync against a broken vendor path if any <Icon> mounts before
// the family is registered — which throws on Android Expo Go.
SplashScreen.preventAutoHideAsync();

function RootNav() {
  const { ready, user } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => { wireHandlers(); }, []);

  // On sign-in (and every cold start with a session) rebuild the local
  // notification schedule from the server — this restores reminders after reboot.
  useEffect(() => {
    if (user) { syncAndSchedule().catch(() => {}); }
  }, [user]);

  useEffect(() => {
    if (!ready) return;
    SplashScreen.hideAsync();
    const publicRoutes = ["login", "verify-email", "reset-password"];
    const onPublic = publicRoutes.includes(segments[0] as string);
    if (!user && !onPublic) router.replace("/login");
    else if (user && segments[0] === "login") router.replace("/(tabs)");
  }, [ready, user, segments]);

  if (!ready) return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="verify-email" />
      <Stack.Screen name="reset-password" />
      <Stack.Screen name="(tabs)" />
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
