import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Loading, Empty } from "@/src/components/ui";

export default function Courses() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [courses, setCourses] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setCourses(await api.get("/courses")); } catch (e) {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.md }]}>
        <Text style={styles.title}>Courses</Text>
        <Text style={styles.sub}>Everything organized by course</Text>
      </View>
      {loading ? <Loading /> : courses.length === 0 ? (
        <Empty icon="book" title="No courses yet." sub="Import a schedule or capture something with a course name." testID="courses-empty" />
      ) : (
        <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
          {courses.map((c) => (
            <Pressable key={c.name} onPress={() => router.push(`/course/${encodeURIComponent(c.name)}`)} testID={`course-${c.name}`}>
              <Card style={styles.card}>
                <View style={styles.badge}><Text style={styles.badgeTxt}>{c.name.slice(0, 2).toUpperCase()}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{c.name}</Text>
                  <Text style={styles.meta}>{c.open_tasks} tasks · {c.events} events · {c.notes} notes</Text>
                </View>
                <Feather name="chevron-right" size={20} color={C.onSurface3} />
              </Card>
            </Pressable>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { padding: S.lg, backgroundColor: C.surface2, borderBottomWidth: 1, borderBottomColor: C.border },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, marginTop: 2 },
  card: { flexDirection: "row", alignItems: "center", gap: S.md, marginBottom: S.md },
  badge: { width: 44, height: 44, borderRadius: R.md, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  badgeTxt: { fontFamily: F.display, fontSize: 15, color: C.onBrand },
  name: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
});
