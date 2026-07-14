import { useState, useEffect } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Loading } from "@/src/components/ui";

const ICON: any = { class: "book-open", lab: "activity", exam: "edit-3", meeting: "users", study: "book", personal: "star", assignment: "file-text" };

export default function CourseWorkspace() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { name } = useLocalSearchParams<{ name: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { setData(await api.get(`/courses/${encodeURIComponent(name)}`)); } catch (e) {} finally { setLoading(false); }
    })();
  }, [name]);

  const fmt = (s?: string) => s ? new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Pressable onPress={() => router.back()} testID="course-close" hitSlop={10}><Feather name="arrow-left" size={24} color={C.onSurface2} /></Pressable>
        <Text style={styles.title}>{name}</Text>
        <View style={{ width: 24 }} />
      </View>
      {loading ? <Loading /> : (
        <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} showsVerticalScrollIndicator={false}>
          <View style={styles.stats}>
            <Stat v={data?.tasks?.length || 0} l="Tasks" />
            <Stat v={data?.events?.length || 0} l="Events" />
            <Stat v={data?.notes?.length || 0} l="Notes" />
          </View>

          <Section title="Schedule">
            {data?.events?.length ? data.events.map((e: any) => (
              <Card key={e.id} style={styles.row}>
                <View style={styles.iconChip}><Feather name={ICON[e.event_type] || "calendar"} size={15} color={C.onBrand3} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rTitle}>{e.title}</Text>
                  <Text style={styles.rSub}>{[e.event_type, e.location, e.start ? fmt(e.start) : null].filter(Boolean).join(" · ")}</Text>
                </View>
              </Card>
            )) : <Empty t="No events yet." />}
          </Section>

          <Section title="Assignments & tasks">
            {data?.tasks?.length ? data.tasks.map((t: any) => (
              <Card key={t.id} style={styles.row}>
                <Feather name={t.status === "done" ? "check-circle" : "circle"} size={16} color={t.status === "done" ? C.success : C.borderStrong} />
                <View style={{ flex: 1 }}>
                  <Text style={[styles.rTitle, t.status === "done" && styles.done]}>{t.title}</Text>
                  <Text style={styles.rSub}>{t.due ? `Due ${fmt(t.due)}` : t.category}{t.entity ? ` · ${t.entity}` : ""}</Text>
                </View>
              </Card>
            )) : <Empty t="No tasks yet." />}
          </Section>

          <Section title="Study notes">
            {data?.notes?.length ? data.notes.map((n: any) => (
              <Pressable key={n.id} onPress={() => router.push({ pathname: "/notes", params: { id: n.id } })}>
                <Card style={styles.row}>
                  <View style={styles.iconChip}><Feather name="file-text" size={15} color={C.onBrand3} /></View>
                  <Text style={[styles.rTitle, { flex: 1 }]}>{n.title}</Text>
                  <Feather name="chevron-right" size={18} color={C.onSurface3} />
                </Card>
              </Pressable>
            )) : <Empty t="No study notes yet." />}
          </Section>

          <Section title="Memory">
            {data?.memory?.length ? data.memory.slice(0, 20).map((m: any) => (
              <View key={m.id} style={styles.memRow}>
                <View style={styles.dot} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.rTitle} numberOfLines={1}>{m.title}</Text>
                  {m.subtitle ? <Text style={styles.rSub}>{m.subtitle}</Text> : null}
                </View>
              </View>
            )) : <Empty t="No memory yet." />}
          </Section>
        </ScrollView>
      )}
    </View>
  );
}

function Stat({ v, l }: any) { return <View style={styles.stat}><Text style={styles.statV}>{v}</Text><Text style={styles.statL}>{l}</Text></View>; }
function Section({ title, children }: any) { return <View style={{ marginTop: S.xl }}><SectionTitle>{title}</SectionTitle>{children}</View>; }
function Empty({ t }: any) { return <Text style={styles.empty}>{t}</Text>; }

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 20, color: C.onSurface },
  stats: { flexDirection: "row", gap: S.sm },
  stat: { flex: 1, backgroundColor: C.surface2, borderRadius: R.md, padding: S.md, alignItems: "center", borderWidth: 1, borderColor: C.border },
  statV: { fontFamily: F.display, fontSize: 22, color: C.brand },
  statL: { fontFamily: F.body, fontSize: 11, color: C.onSurface3, marginTop: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: S.md, marginBottom: S.sm, padding: S.md },
  iconChip: { width: 32, height: 32, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  rTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  rSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  done: { textDecorationLine: "line-through", color: C.onSurface3 },
  memRow: { flexDirection: "row", gap: S.md, alignItems: "center", paddingVertical: S.sm, paddingLeft: S.xs },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.brand },
  empty: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, paddingVertical: S.sm },
});
