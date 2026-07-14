import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, FlatList, TextInput, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Chip, Loading, Empty } from "@/src/components/ui";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "capture", label: "Captures" },
  { key: "task", label: "Tasks" },
  { key: "event", label: "Events" },
  { key: "note", label: "Notes" },
  { key: "import", label: "Imports" },
];
const KIND_ICON: any = { capture: "mic", task: "check-square", event: "calendar", note: "file-text", import: "upload" };

export default function Memory() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [course, setCourse] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [courses, setCourses] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (f: string, c: string | null, query: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ kind: f });
      if (c) params.append("course", c);
      if (query.trim()) params.append("q", query.trim());
      const [mem, cs] = await Promise.all([api.get(`/timeline?${params.toString()}`), api.get("/courses")]);
      setItems(mem); setCourses(cs);
    } catch (e) {} finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(filter, course, q); }, [filter, course, q, load]));

  const fmt = (s: string) => new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

  const jump = (item: any) => {
    if (item.kind === "note" && item.ref_id) router.push({ pathname: "/notes", params: { id: item.ref_id } });
    else if (item.course) router.push(`/course/${encodeURIComponent(item.course)}`);
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.md }]}>
        <Text style={styles.title}>Memory</Text>
        <Text style={styles.sub}>Everything your assistant knows</Text>
        <View style={styles.searchBar}>
          <Feather name="search" size={16} color={C.onSurface3} />
          <TextInput
            testID="memory-search"
            style={styles.searchInput}
            placeholder="Search your academic memory…"
            placeholderTextColor={C.onSurface3}
            value={q}
            onChangeText={setQ}
            returnKeyType="search"
          />
          {q ? <Pressable onPress={() => setQ("")}><Feather name="x-circle" size={16} color={C.onSurface3} /></Pressable> : null}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          {FILTERS.map((f) => <Chip key={f.key} label={f.label} active={filter === f.key} onPress={() => setFilter(f.key)} testID={`filter-${f.key}`} />)}
        </ScrollView>
        {courses.length ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipsBottom}>
            <Chip label="All courses" active={!course} onPress={() => setCourse(null)} testID="course-all" />
            {courses.map((c) => <Chip key={c.name} label={c.name} active={course === c.name} onPress={() => setCourse(c.name)} testID={`course-chip-${c.name}`} />)}
          </ScrollView>
        ) : null}
      </View>

      {loading ? <Loading /> : items.length === 0 ? (
        <Empty icon="database" title="Your academic memory is ready to be written." sub="Captures, notes, imports, and events appear here." />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: S.lg, paddingBottom: 120 }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => {
            const canJump = (item.kind === "note" && item.ref_id) || item.course;
            return (
              <Pressable onPress={() => jump(item)} disabled={!canJump} style={styles.node} testID={`memory-${item.id}`}>
                <View style={styles.line}>
                  <View style={styles.dotWrap}><Feather name={KIND_ICON[item.kind] || "circle"} size={13} color={C.brand} /></View>
                  <View style={styles.connector} />
                </View>
                <View style={styles.nodeCard}>
                  <Text style={styles.nodeTitle} numberOfLines={2}>{item.title}</Text>
                  {item.subtitle ? <Text style={styles.nodeSub}>{item.subtitle}</Text> : null}
                  <View style={styles.nodeFoot}>
                    <Text style={styles.nodeTime}>{fmt(item.ts)}{item.course ? ` · ${item.course}` : ""}</Text>
                    {canJump ? <Feather name="corner-up-right" size={13} color={C.brand} /> : null}
                  </View>
                </View>
              </Pressable>
            );
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { backgroundColor: C.surface2, borderBottomWidth: 1, borderBottomColor: C.border, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface, paddingHorizontal: S.lg },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, paddingHorizontal: S.lg, marginTop: 2 },
  searchBar: { flexDirection: "row", alignItems: "center", gap: S.sm, backgroundColor: C.surface3, marginHorizontal: S.lg, marginTop: S.md, paddingHorizontal: S.md, borderRadius: R.pill, height: 44 },
  searchInput: { flex: 1, fontFamily: F.body, fontSize: 14, color: C.onSurface },
  chips: { gap: S.sm, paddingHorizontal: S.lg, paddingVertical: S.md },
  chipsBottom: { gap: S.sm, paddingHorizontal: S.lg, paddingBottom: S.xs },
  node: { flexDirection: "row", gap: S.md },
  line: { alignItems: "center", width: 30 },
  dotWrap: { width: 30, height: 30, borderRadius: 15, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  connector: { flex: 1, width: 2, backgroundColor: C.border, marginVertical: 2 },
  nodeCard: { flex: 1, backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, marginBottom: S.md },
  nodeTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  nodeSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface2, marginTop: 2 },
  nodeFoot: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  nodeTime: { fontFamily: F.body, fontSize: 11, color: C.onSurface3 },
});
