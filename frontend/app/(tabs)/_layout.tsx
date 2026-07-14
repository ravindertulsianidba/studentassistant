import { Tabs, useRouter } from "expo-router";
import { Pressable, View, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { C, F, shadow } from "@/src/theme";

function CaptureButton({ bottom }: { bottom: number }) {
  const router = useRouter();
  return (
    <View style={styles.fabWrap} pointerEvents="box-none">
      <Pressable
        testID="capture-fab"
        onPress={() => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          router.push("/quick-capture");
        }}
        style={({ pressed }) => [styles.fab, { bottom: bottom + 4 }, pressed && { transform: [{ scale: 0.95 }] }]}
      >
        <Feather name="plus" size={26} color={C.onBrand} />
      </Pressable>
    </View>
  );
}

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  // Lift the whole bar above the Android gesture/nav buttons (and iOS home indicator).
  const bottomInset = Math.max(insets.bottom, 8);
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.inverse,
        tabBarInactiveTintColor: C.onSurface3,
        tabBarStyle: [styles.bar, { height: 60 + bottomInset, paddingBottom: bottomInset }],
        tabBarLabelStyle: { fontFamily: F.bodyMed, fontSize: 11 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Today", tabBarIcon: ({ color }) => <Feather name="home" size={22} color={color} /> }} />
      <Tabs.Screen name="timeline" options={{ title: "Memory", tabBarIcon: ({ color }) => <Feather name="database" size={22} color={color} /> }} />
      <Tabs.Screen name="capture" options={{ title: "", tabBarButton: () => <CaptureButton bottom={bottomInset} /> }} />
      <Tabs.Screen name="courses" options={{ title: "Courses", tabBarIcon: ({ color }) => <Feather name="book" size={22} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: "Settings", tabBarIcon: ({ color }) => <Feather name="settings" size={22} color={color} /> }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: { paddingTop: 8, backgroundColor: C.surface2, borderTopColor: C.border },
  fabWrap: { flex: 1, alignItems: "center" },
  fab: { position: "absolute", width: 56, height: 56, borderRadius: 28, backgroundColor: C.brand, alignItems: "center", justifyContent: "center", ...shadow, shadowOpacity: 0.2, elevation: 6 },
});
