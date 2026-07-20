import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Alert, TextInput, Platform, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import * as Sharing from "expo-sharing";
import { File, Paths } from "expo-file-system";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Btn, Badge } from "@/src/components/ui";
import { useAuth } from "@/src/auth";
import * as billing from "@/src/services/billing";
import { ensurePermission as notifPerm, syncAndSchedule, health as notifHealth } from "@/src/services/notifications";

export default function Profile() {
  const insets = useSafeAreaInsets();
  const { signOut, revokeAllSessions, deleteAccount, replayOnboarding, user } = useAuth();
  const [wr, setWr] = useState<any>(null);
  const [loadingWr, setLoadingWr] = useState(false);
  const [plan, setPlan] = useState<billing.BillingStatus | null>(null);
  const [notif, setNotif] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [askDelPw, setAskDelPw] = useState(false);
  const [delPw, setDelPw] = useState("");
  const [delErr, setDelErr] = useState("");

  const load = useCallback(async () => {
    setLoadingWr(true);
    try {
      const [w, p] = await Promise.all([api.get("/weekly-review"), billing.fetchStatus()]);
      setWr(w); setPlan(p);
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

  const router = useRouter();

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
    const isPremium = plan?.plan === "premium";
    const subWarning = isPremium
      ? "\n\nImportant: deleting your Student Assistant account does NOT cancel your Google Play subscription. Cancel it separately in Google Play to stop future charges."
      : "";
    if ((user as any)?.auth_provider === "password") {
      if (isPremium) {
        Alert.alert("You have an active subscription", subWarning.trim(), [
          { text: "Manage subscription", onPress: openManageSubscription },
          { text: "Continue to delete", style: "destructive", onPress: () => setAskDelPw(true) },
          { text: "Cancel", style: "cancel" },
        ]);
      } else { setAskDelPw(true); }
      return;
    }
    Alert.alert("Delete your account?", "This permanently deletes ALL your data — recordings, transcripts, notes, tasks, events, imports and memory. This cannot be undone." + subWarning, [
      { text: "Cancel", style: "cancel" },
      ...(isPremium ? [{ text: "Manage subscription", onPress: openManageSubscription }] : []),
      { text: "Delete account", style: "destructive", onPress: async () => { await deleteAccount(); } },
    ]);
  };

  const openManageSubscription = () => {
    const pkg = plan?.product?.package_name || "com.decisivlabs.studentassistant";
    const sku = plan?.product?.product_id || "student_assistant_premium";
    Linking.openURL(`https://play.google.com/store/account/subscriptions?sku=${sku}&package=${pkg}`);
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
          <Card testID="premium-card" style={{ gap: S.md }}>
            <View style={styles.premRow}>
              <View style={styles.premIcon}><Feather name="zap" size={18} color={C.brand} /></View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: S.sm }}>
                  <Text style={styles.premTitle}>Student Assistant Premium</Text>
                  <Badge label={plan?.plan === "premium" ? "Premium" : "Free"} tone={plan?.plan === "premium" ? "success" : "info"} />
                </View>
                <Text style={styles.premSub}>
                  {plan?.plan === "premium"
                    ? "Your plan is active. Manage or review your subscription."
                    : "Higher monthly AI allowances for lectures, imports and guidance."}
                </Text>
              </View>
            </View>
            <Btn
              label={plan?.plan === "premium" ? "Manage Premium" : "Upgrade to Premium"}
              variant={plan?.plan === "premium" ? "soft" : "primary"}
              icon={plan?.plan === "premium" ? "settings" : "arrow-up-circle"}
              onPress={() => router.push("/premium")}
              testID="premium-open-btn" />
          </Card>
        </View>

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
          <SectionTitle>Calendar</SectionTitle>
          <Card style={{ gap: S.md }}>
            <Text style={styles.body}>Connect the calendar you already use (Google, Microsoft 365, Outlook, Exchange, and others synced to your device). External events appear in Today and drive conflict detection; approved events sync back to your calendar.</Text>
            <Btn label="Connect Calendar" variant="soft" icon="calendar" onPress={() => router.push("/calendar-connect")} testID="cal-btn" />
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
          <Btn label="Diagnostics" variant="soft" icon="activity" onPress={() => router.push("/diagnostics")} testID="diagnostics-btn" />
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
  premRow: { flexDirection: "row", gap: S.md, alignItems: "flex-start" },
  premIcon: { width: 40, height: 40, borderRadius: R.md, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  premTitle: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface },
  premSub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, marginTop: 2, lineHeight: 18 },
});
