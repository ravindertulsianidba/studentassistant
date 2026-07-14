import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Btn, Badge } from "@/src/components/ui";
import { useAuth } from "@/src/auth";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { signOut, deleteAccount, user } = useAuth();
  const [wr, setWr] = useState<any>(null);
  const [loadingWr, setLoadingWr] = useState(false);

  const loadWeekly = useCallback(async () => {
    setLoadingWr(true);
    try { setWr(await api.get("/weekly-review")); } catch (e) {} finally { setLoadingWr(false); }
  }, []);
  useFocusEffect(useCallback(() => { loadWeekly(); }, [loadWeekly]));

  const exportData = async () => {
    const d = await api.get("/export");
    Alert.alert("Data ready", `Your data: ${d.tasks.length} tasks, ${d.events.length} events, ${d.notes.length} notes, ${d.timeline.length} timeline entries. In a build this exports to a file.`);
  };
  const wipe = () => {
    Alert.alert("Delete your account?", "This permanently deletes ALL your data — recordings, transcripts, notes, tasks, events, imports and memory. This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete account", style: "destructive", onPress: async () => { await deleteAccount(); } },
    ]);
  };

  const rv = wr?.review || {};
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingTop: insets.top + S.lg, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.sub}>{user?.email ? `Signed in as ${user.email}` : "Weekly review, privacy & your data"}</Text>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Weekly review</SectionTitle>
          <Card testID="weekly-card" style={{ gap: S.md }}>
            {loadingWr ? <Text style={styles.body}>Analyzing your week…</Text> : (
              <>
                <View style={styles.rowBetween}>
                  <Text style={styles.body}>{rv.summary || "No upcoming items this week."}</Text>
                </View>
                {rv.workload ? <Badge label={`Workload: ${rv.workload}`} tone={rv.workload === "heavy" ? "error" : rv.workload === "moderate" ? "warning" : "success"} /> : null}
                {rv.busy_days?.length ? <Text style={styles.meta}>Busy days: {rv.busy_days.join(", ")}</Text> : null}
                {rv.recommendations?.map((r: string, i: number) => (
                  <View key={i} style={styles.recRow}><Feather name="arrow-right" size={14} color={C.brand} /><Text style={styles.rec}>{r}</Text></View>
                ))}
                <Text style={styles.meta}>{wr?.upcoming?.length || 0} items due in the next 7 days</Text>
              </>
            )}
          </Card>
        </View>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Privacy & data</SectionTitle>
          <Card style={{ gap: S.md }}>
            <PrivacyRow icon="mic" title="Recording is always visible" text="You'll always see a clear indicator when recording, with one-tap stop." />
            <PrivacyRow icon="shield" title="Nothing is shared automatically" text="The AI never sends emails or shares data. You approve every action." />
            <PrivacyRow icon="lock" title="You own your data" text="Export or delete everything at any time." />
          </Card>
          <View style={{ height: S.md }} />
          <Btn label="Export my data" variant="soft" icon="download" onPress={exportData} testID="export-btn" />
          <View style={{ height: S.sm }} />
          <Btn label="Sign out" variant="ghost" icon="log-out" onPress={signOut} testID="signout-btn" />
          <View style={{ height: S.sm }} />
          <Btn label="Delete my account" variant="ghost" icon="trash-2" onPress={wipe} testID="wipe-btn" />
        </View>
      </ScrollView>
    </View>
  );
}

function PrivacyRow({ icon, title, text }: any) {
  return (
    <View style={styles.pRow}>
      <View style={styles.pIcon}><Feather name={icon} size={16} color={C.onBrand3} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.pTitle}>{title}</Text>
        <Text style={styles.pText}>{text}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, marginTop: 2 },
  body: { fontFamily: F.body, fontSize: 14, color: C.onSurface, flex: 1, lineHeight: 20 },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between" },
  recRow: { flexDirection: "row", gap: S.sm, alignItems: "flex-start" },
  rec: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, flex: 1 },
  pRow: { flexDirection: "row", gap: S.md, alignItems: "flex-start" },
  pIcon: { width: 34, height: 34, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  pTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  pText: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
});
