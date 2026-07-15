import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Alert, TextInput, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";
import { Feather } from "@expo/vector-icons";
import * as Sharing from "expo-sharing";
import { File, Paths } from "expo-file-system";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Btn, Badge } from "@/src/components/ui";
import { useAuth } from "@/src/auth";
import { ensurePermission as notifPerm, syncAndSchedule, health as notifHealth } from "@/src/services/notifications";
import { syncPending as calSync } from "@/src/services/calendar";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { signOut, revokeAllSessions, deleteAccount, replayOnboarding, user } = useAuth();
  const [wr, setWr] = useState<any>(null);
  const [loadingWr, setLoadingWr] = useState(false);
  const [usage, setUsage] = useState<any>(null);
  const [capInput, setCapInput] = useState("");
  const [notif, setNotif] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [askDelPw, setAskDelPw] = useState(false);
  const [delPw, setDelPw] = useState("");
  const [delErr, setDelErr] = useState("");

  const load = useCallback(async () => {
    setLoadingWr(true);
    try {
      const [w, u] = await Promise.all([api.get("/weekly-review"), api.get("/ai-usage")]);
      setWr(w); setUsage(u); setCapInput(String(u.limit));
    } catch (e) {} finally { setLoadingWr(false); }
    try { setNotif(await notifHealth()); } catch {}
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const enableReminders = async () => {
    setBusy("notif");
    try {
      const p = await notifPerm();
      if (!p.granted) {
        Alert.alert("Reminders need permission",
          Platform.OS === "web" ? "Reminders work in the installed app, not the web preview."
            : "Enable notifications in Settings to get reminders and daily briefings.");
      } else {
        const r = await syncAndSchedule();
        Alert.alert("Reminders on", `Scheduled ${r.scheduled} reminder(s) and ${r.routines} routine(s).`);
      }
      setNotif(await notifHealth());
    } catch (e: any) { Alert.alert("Couldn't set up reminders", e?.message || "Try again."); }
    finally { setBusy(""); }
  };

  const syncCalendar = async () => {
    setBusy("cal");
    try {
      const r = await calSync();
      Alert.alert("Calendar sync",
        Platform.OS === "web" ? "Calendar writes work in the installed app, not the web preview."
          : `Added ${r.created} event(s). ${r.failed ? r.failed + " failed. " : ""}${r.skipped ? r.skipped + " skipped (no date)." : ""}`);
    } catch (e: any) { Alert.alert("Calendar sync failed", e?.message || "Try again."); }
    finally { setBusy(""); }
  };

  const saveCap = async () => {
    const n = parseInt(capInput, 10);
    if (isNaN(n) || n < 0) { Alert.alert("Enter a number", "Use 0 for unlimited."); return; }
    try {
      await fetch(`${api.base}/prefs`, { method: "PUT", headers: { "Content-Type": "application/json", ...api.authHeader() } as any, body: JSON.stringify({ daily_ai_limit: n }) });
      setUsage(await api.get("/ai-usage"));
      Alert.alert("Saved", n === 0 ? "Daily AI limit removed (unlimited)." : `Daily AI limit set to ${n} requests.`);
    } catch (e: any) { Alert.alert("Couldn't save", e?.message || "Try again."); }
  };

  const exportData = async () => {
    setBusy("export");
    try {
      const d = await api.get("/export");
      const json = JSON.stringify(d, null, 2);
      if (Platform.OS === "web" || !(await Sharing.isAvailableAsync())) {
        Alert.alert("Data ready", `Export contains ${d.tasks?.length || 0} tasks, ${d.events?.length || 0} events, ${d.notes?.length || 0} notes, ${d.reminders?.length || 0} reminders. Sharing needs the installed app.`);
      } else {
        const f = new File(Paths.cache, `student-assistant-export-${Date.now()}.json`);
        f.create({ overwrite: true });
        f.write(json);
        await Sharing.shareAsync(f.uri, { mimeType: "application/json", dialogTitle: "Export your data" });
      }
    } catch (e: any) { Alert.alert("Export failed", e?.message || "Try again."); }
    finally { setBusy(""); }
  };

  const wipe = () => {
    if ((user as any)?.auth_provider === "password") { setAskDelPw(true); return; }
    Alert.alert("Delete your account?", "This permanently deletes ALL your data — recordings, transcripts, notes, tasks, events, imports and memory. This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete account", style: "destructive", onPress: async () => { await deleteAccount(); } },
    ]);
  };

  const confirmDeletePw = async () => {
    setDelErr("");
    try { await deleteAccount(delPw); }
    catch (e: any) { setDelErr(e.message || "Incorrect password."); }
  };

  const revokeAll = () => {
    Alert.alert("Sign out of all devices?", "This signs you out everywhere and invalidates every active session. You'll need to sign in again.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out everywhere", style: "destructive", onPress: async () => { await revokeAllSessions(); } },
    ]);
  };

  const rv = wr?.review || {};
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingTop: insets.top + S.lg, paddingBottom: 120 }} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Settings</Text>
        <Text style={styles.sub}>{user?.email ? `Signed in as ${user.email}` : "Reminders, calendar, privacy & your data"}</Text>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Reminders & routines</SectionTitle>
          <Card style={{ gap: S.md }}>
            <Text style={styles.body}>Get notified before classes and deadlines, plus your daily briefing, evening review and weekly review.</Text>
            {notif ? (
              <Text style={styles.meta}>Permission: {notif.permission} · {notif.scheduledOnDevice} scheduled on device</Text>
            ) : null}
            <Btn label="Enable / refresh reminders" variant="soft" icon="bell" onPress={enableReminders} testID="notif-btn" />
          </Card>
        </View>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Device calendar</SectionTitle>
          <Card style={{ gap: S.md }}>
            <Text style={styles.body}>Add your classes and deadlines to your phone's calendar. Duplicates are avoided automatically.</Text>
            <Btn label="Sync to device calendar" variant="soft" icon="calendar" onPress={syncCalendar} testID="cal-btn" />
          </Card>
        </View>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Weekly review</SectionTitle>
          <Card testID="weekly-card" style={{ gap: S.md }}>
            {loadingWr ? <Text style={styles.body}>Analyzing your week…</Text> : (
              <>
                <Text style={styles.body}>{rv.summary || "No upcoming items this week."}</Text>
                {rv.workload ? <Badge label={`Workload: ${rv.workload}`} tone={rv.workload === "heavy" ? "error" : rv.workload === "moderate" ? "warning" : "success"} /> : null}
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
          <Btn label="Replay intro" variant="soft" icon="play-circle" onPress={replayOnboarding} testID="replay-intro-btn" />
          <View style={{ height: S.sm }} />
          <Btn label="Sign out" variant="ghost" icon="log-out" onPress={signOut} testID="signout-btn" />
          <View style={{ height: S.sm }} />
          <Btn label="Sign out of all devices" variant="ghost" icon="shield-off" onPress={revokeAll} testID="revoke-all-btn" />
          <View style={{ height: S.sm }} />
          <Btn label="Delete my account" variant="ghost" icon="trash-2" onPress={wipe} testID="wipe-btn" />
          {askDelPw ? (
            <Card style={{ gap: S.sm, marginTop: S.sm }}>
              <Text style={styles.body}>Confirm your password to permanently delete your account.</Text>
              {delErr ? <Text style={{ fontFamily: F.bodyMed, fontSize: 13, color: C.error }}>{delErr}</Text> : null}
              <TextInput style={styles.capInput} placeholder="Password" placeholderTextColor={C.onSurface3}
                secureTextEntry autoCapitalize="none" value={delPw} onChangeText={setDelPw} testID="del-password" />
              <Btn label="Confirm delete" variant="ghost" icon="trash-2" onPress={confirmDeletePw} testID="confirm-del-btn" />
            </Card>
          ) : null}
        </View>

        <View style={{ marginTop: S.xl }}>
          <SectionTitle>Advanced · cost protection</SectionTitle>
          <Card style={{ gap: S.md }}>
            <Text style={styles.body}>Daily AI request cap. This limits how many AI actions run per day to protect API costs. Use 0 for unlimited.</Text>
            {usage ? <Text style={styles.meta}>Today: {usage.used} used{usage.unlimited ? "" : ` · ${usage.remaining} left of ${usage.limit}`}</Text> : null}
            <View style={styles.capRow}>
              <TextInput style={styles.capInput} value={capInput} onChangeText={setCapInput} keyboardType="number-pad" testID="cap-input" />
              <Btn label="Save limit" variant="soft" icon="save" onPress={saveCap} testID="cap-save" style={{ flex: 1 }} />
            </View>
          </Card>
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
  body: { fontFamily: F.body, fontSize: 14, color: C.onSurface, lineHeight: 20 },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  recRow: { flexDirection: "row", gap: S.sm, alignItems: "flex-start" },
  rec: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, flex: 1 },
  pRow: { flexDirection: "row", gap: S.md, alignItems: "flex-start" },
  pIcon: { width: 34, height: 34, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  pTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  pText: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  capRow: { flexDirection: "row", gap: S.sm, alignItems: "center" },
  capInput: { width: 90, backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.borderStrong, padding: S.md, fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface, textAlign: "center" },
});
