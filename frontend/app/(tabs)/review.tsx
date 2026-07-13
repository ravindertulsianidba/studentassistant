import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import * as Haptics from "expo-haptics";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Btn, Loading, Empty, Badge } from "@/src/components/ui";

const KIND_LABEL: any = { event: "Calendar event", task: "Task", reminder: "Reminder", followup: "Follow-up" };

export default function Review() {
  const insets = useSafeAreaInsets();
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
      <View style={[styles.header, { paddingTop: insets.top + S.md }]}>
        <Text style={styles.title}>Review Queue</Text>
        <Text style={styles.sub}>Approve, edit, or ignore AI suggestions before they're added.</Text>
      </View>
      {loading ? <Loading /> : items.length === 0 ? (
        <Empty icon="check-circle" title="All caught up." sub="No items to review." testID="review-empty" />
      ) : (
        <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
          {items.map((r) => {
            const it = r.item || {};
            const conf = Math.round((r.confidence || 0) * 100);
            return (
              <Card key={r.id} style={{ marginBottom: S.md, gap: S.md }} testID={`review-${r.id}`}>
                <View style={styles.rowBetween}>
                  <Badge label={KIND_LABEL[it.kind] || "Item"} tone="info" />
                  <Text style={styles.conf}>{conf}% sure</Text>
                </View>
                <TextInput
                  testID={`review-title-${r.id}`}
                  style={styles.input}
                  defaultValue={it.title}
                  onChangeText={(v) => setEdits((p) => ({ ...p, [r.id]: v }))}
                />
                {it.datetime ? <Text style={styles.meta}><Feather name="calendar" size={12} /> {new Date(it.datetime).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</Text> : null}
                {r.source ? <Text style={styles.source}>From: {r.source}</Text> : null}
                <View style={styles.actions}>
                  <Btn label="Ignore" variant="ghost" icon="x" onPress={() => act(r.id, "ignore", it)} testID={`ignore-${r.id}`} style={{ flex: 1 }} />
                  <Btn label="Approve" variant="primary" icon="check" onPress={() => act(r.id, "approve", it)} testID={`approve-${r.id}`} style={{ flex: 1 }} />
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
  header: { padding: S.lg, backgroundColor: C.surface2, borderBottomWidth: 1, borderBottomColor: C.border },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, marginTop: 2 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  conf: { fontFamily: F.bodyMed, fontSize: 12, color: C.onSurface3 },
  input: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface, backgroundColor: C.surface3, borderRadius: R.sm, padding: S.md },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface2 },
  source: { fontFamily: F.body, fontSize: 11, color: C.onSurface3 },
  actions: { flexDirection: "row", gap: S.sm, marginTop: S.xs },
});
