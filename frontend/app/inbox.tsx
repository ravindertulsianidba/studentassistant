import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Btn, Loading, Empty, Badge } from "@/src/components/ui";

const CONF: any = {
  high: { label: "High confidence", tone: "success" },
  medium: { label: "Needs review", tone: "warning" },
  low: { label: "Low confidence", tone: "error" },
};

export default function Inbox() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [edits, setEdits] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try { setItems(await api.get("/review")); } catch (e) {} finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const act = async (rid: string, action: string, item: any) => {
    Haptics.notificationAsync(action === "approve" ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
    setItems((p) => p.filter((x) => x.id !== rid));
    const edited = edits[rid] && edits[rid] !== item.title ? { title: edits[rid] } : undefined;
    await api.post(`/review/${rid}/action`, { action, edited });
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>AI Inbox</Text>
          <Text style={styles.sub}>Review what your assistant detected before it’s saved.</Text>
        </View>
        <View style={styles.close} onTouchEnd={() => router.back()}>
          <Feather name="x" size={22} color={C.onSurface2} testID="inbox-close" />
        </View>
      </View>
      {loading ? <Loading /> : items.length === 0 ? (
        <Empty icon="check-circle" title="All caught up." sub="No suggestions to review." testID="inbox-empty" />
      ) : (
        <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} showsVerticalScrollIndicator={false}>
          {items.map((r) => {
            const it = r.item || {};
            const cl = CONF[r.confidence_label] || CONF.medium;
            return (
              <Card key={r.id} style={{ marginBottom: S.md, gap: S.md }} testID={`inbox-${r.id}`}>
                <View style={styles.rowBetween}>
                  <Badge label={cl.label} tone={cl.tone} />
                  <Text style={styles.conf}>{Math.round((r.confidence || 0) * 100)}%</Text>
                </View>
                <Text style={styles.detected}>{r.detected || it.title}</Text>
                <TextInput
                  testID={`inbox-title-${r.id}`}
                  style={styles.input}
                  defaultValue={it.title}
                  onChangeText={(v) => setEdits((p) => ({ ...p, [r.id]: v }))}
                />
                {it.datetime ? <Text style={styles.meta}><Feather name="calendar" size={12} />  {new Date(it.datetime).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Text> : null}
                {it.course ? <Text style={styles.meta}><Feather name="book" size={12} />  {it.course}</Text> : null}
                <Text style={styles.source}>{r.suggestion || "Add item"} · from {r.source}</Text>
                <View style={styles.actions}>
                  <Btn label="Delete" variant="ghost" icon="trash-2" onPress={() => act(r.id, "delete", it)} testID={`inbox-delete-${r.id}`} style={{ flex: 1 }} />
                  <Btn label="Ignore" variant="ghost" icon="x" onPress={() => act(r.id, "ignore", it)} testID={`inbox-ignore-${r.id}`} style={{ flex: 1 }} />
                  <Btn label="Approve" variant="primary" icon="check" onPress={() => act(r.id, "approve", it)} testID={`inbox-approve-${r.id}`} style={{ flex: 1.3 }} />
                </View>
              </Card>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "flex-start", padding: S.lg, backgroundColor: C.surface2, borderBottomWidth: 1, borderBottomColor: C.border },
  close: { padding: 4 },
  title: { fontFamily: F.display, fontSize: 24, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, marginTop: 2 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  conf: { fontFamily: F.displayMed, fontSize: 13, color: C.onSurface3 },
  detected: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2 },
  input: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface, backgroundColor: C.surface3, borderRadius: R.sm, padding: S.md },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface2 },
  source: { fontFamily: F.body, fontSize: 11, color: C.onSurface3 },
  actions: { flexDirection: "row", gap: S.sm, marginTop: S.xs },
});
