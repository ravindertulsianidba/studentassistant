import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, FlatList } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
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

export default function Timeline() {
  const insets = useSafeAreaInsets();
  const [filter, setFilter] = useState("all");
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (f: string) => {
    setLoading(true);
    try { setItems(await api.get(`/timeline?kind=${f}`)); } catch (e) {} finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(filter); }, [filter, load]));

  const fmt = (s: string) => new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.md }]}>
        <Text style={styles.title}>Timeline</Text>
        <Text style={styles.sub}>Your searchable academic memory</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipsRow}
          contentContainerStyle={{ gap: S.sm, paddingHorizontal: S.lg, paddingVertical: S.md }}>
          {FILTERS.map((f) => (
            <Chip key={f.key} label={f.label} active={filter === f.key} onPress={() => setFilter(f.key)} testID={`filter-${f.key}`} />
          ))}
        </ScrollView>
      </View>

      {loading ? <Loading /> : items.length === 0 ? (
        <Empty icon="clock" title="Your academic memory is ready to be written." sub="Captures, notes, and events will appear here." />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.id}
          contentContainerStyle={{ padding: S.lg, paddingBottom: 120 }}
          showsVerticalScrollIndicator={false}
          renderItem={({ item }) => (
            <View style={styles.node} testID={`timeline-${item.id}`}>
              <View style={styles.line}>
                <View style={styles.dotWrap}><Feather name={KIND_ICON[item.kind] || "circle"} size={13} color={C.brand} /></View>
                <View style={styles.connector} />
              </View>
              <View style={styles.nodeCard}>
                <Text style={styles.nodeTitle} numberOfLines={2}>{item.title}</Text>
                {item.subtitle ? <Text style={styles.nodeSub}>{item.subtitle}</Text> : null}
                <Text style={styles.nodeTime}>{fmt(item.ts)}{item.course ? ` · ${item.course}` : ""}</Text>
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { backgroundColor: C.surface2, borderBottomWidth: 1, borderBottomColor: C.border },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface, paddingHorizontal: S.lg },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, paddingHorizontal: S.lg, marginTop: 2 },
  chipsRow: { marginTop: S.xs },
  node: { flexDirection: "row", gap: S.md },
  line: { alignItems: "center", width: 30 },
  dotWrap: { width: 30, height: 30, borderRadius: 15, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  connector: { flex: 1, width: 2, backgroundColor: C.border, marginVertical: 2 },
  nodeCard: { flex: 1, backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, marginBottom: S.md },
  nodeTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  nodeSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface2, marginTop: 2 },
  nodeTime: { fontFamily: F.body, fontSize: 11, color: C.onSurface3, marginTop: 6 },
});
