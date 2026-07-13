import { Tabs, useRouter } from "expo-router";
import { Pressable, View, StyleSheet } from "react-native";
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { C, F, shadow } from "@/src/theme";

function CaptureButton() {
  const router = useRouter();
  return (
    <View style={styles.fabWrap} pointerEvents="box-none">
      <Pressable
        testID="capture-fab"
        onPress={() => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          router.push("/quick-capture");
        }}
        style={({ pressed }) => [styles.fab, pressed && { transform: [{ scale: 0.95 }] }]}
      >
        <Feather name="plus" size={26} color={C.onBrand} />
      </Pressable>
    </View>
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.inverse,
        tabBarInactiveTintColor: C.onSurface3,
        tabBarStyle: styles.bar,
        tabBarLabelStyle: { fontFamily: F.bodyMed, fontSize: 11 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Today", tabBarIcon: ({ color }) => <Feather name="home" size={22} color={color} /> }} />
      <Tabs.Screen name="timeline" options={{ title: "Timeline", tabBarIcon: ({ color }) => <Feather name="clock" size={22} color={color} /> }} />
      <Tabs.Screen name="capture" options={{ title: "", tabBarButton: () => <CaptureButton /> }} />
      <Tabs.Screen name="review" options={{ title: "Review", tabBarIcon: ({ color }) => <Feather name="inbox" size={22} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: "You", tabBarIcon: ({ color }) => <Feather name="user" size={22} color={color} /> }} />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  bar: { height: 64, paddingBottom: 8, paddingTop: 8, backgroundColor: C.surface2, borderTopColor: C.border },
  fabWrap: { flex: 1, alignItems: "center" },
  fab: { position: "absolute", bottom: 4, width: 56, height: 56, borderRadius: 28, backgroundColor: C.brand, alignItems: "center", justifyContent: "center", ...shadow, shadowOpacity: 0.2, elevation: 6 },
});
