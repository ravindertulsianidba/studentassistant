import { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform, Share, Alert, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import * as Calendar from "expo-calendar";
import Constants from "expo-constants";
import { AudioModule } from "expo-audio";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Btn, Badge } from "@/src/components/ui";
import { health as notifHealth, sendTestNotification } from "@/src/services/notifications";
import { GOOGLE_WEB_CLIENT_ID, nativeModuleAvailable, signInWithGoogle } from "@/src/services/googleSignin";

const isDevice = Platform.OS === "ios" || Platform.OS === "android";
const TZ = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return "UTC"; } })();

function Row({ label, value, tone }: { label: string; value: any; tone?: any }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      {tone ? <Badge label={String(value)} tone={tone} /> : <Text style={styles.rowVal}>{value ?? "—"}</Text>}
    </View>
  );
}

export default function Diagnostics() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [d, setD] = useState<any>(null);
  const [dev, setDev] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState("");
  const [log, setLog] = useState<string>("");
  const [bundle, setBundle] = useState<any>(null);
  const [bundleText, setBundleText] = useState("");

  const load = useCallback(async () => {
    let mic = "unavailable", notif = "unavailable", cal = "unavailable", scheduled = 0;
    if (isDevice) {
      try { mic = (await AudioModule.getRecordingPermissionsAsync()).granted ? "granted" : "denied"; } catch {}
      try { const h = await notifHealth(); notif = h.permission; scheduled = h.scheduledOnDevice; } catch {}
      try { cal = (await Calendar.getCalendarPermissionsAsync()).granted ? "granted" : "denied"; } catch {}
      api.post("/diagnostics/device-state", { mic_permission: mic, notif_permission: notif }).catch(() => {});
    }
    setDev({ mic, notif, cal, scheduled });
    try { setD(await api.get(`/diagnostics?tz=${encodeURIComponent(TZ)}`)); } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const run = async (key: string, fn: () => Promise<string>) => {
    setRunning(key); setLog("");
    try { setLog(await fn()); } catch (e: any) { setLog("✕ " + (e?.message || "failed")); }
    finally { setRunning(""); load(); }
  };

  const testNotif = () => run("notif", async () => { const r = await sendTestNotification(); return r.ok ? "✓ Notification scheduled (arrives in ~2s)" : "✕ " + r.reason; });
  const testBackend = () => run("backend", async () => { const r = await api.post("/diagnostics/test-backend", {}); return r.ok ? "✓ Backend reachable" : "✕ Backend error"; });
  const testAI = () => run("ai", async () => { const r = await api.post("/diagnostics/test-ai", {}); return r.ok ? `✓ AI OK (${r.latency_ms}ms, ${r.provider})` : "✕ " + (r.error || "AI unavailable"); });
  const testCalRead = () => run("calread", async () => { const r = await api.post("/diagnostics/test-calendar-read", {}); return r.connected ? `✓ ${r.external_events_mirrored} event(s) mirrored. ${r.note}` : "✕ No calendar connected"; });
  const retry = () => run("retry", async () => { const r = await api.post("/diagnostics/retry-jobs", {}); return `✓ Requeued ${r.uploads_requeued} upload(s), ${r.reminders_requeued} reminder(s)`; });
  const testGoogle = () => run("google", async () => {
    // Sanitized Google Sign-In self-check. NEVER logs the ID token contents.
    const mod = nativeModuleAvailable();
    const webCfg = !!GOOGLE_WEB_CLIENT_ID;
    const lines = [
      `${mod ? "✓" : "✕"} Native Google module ${mod ? "available" : "unavailable (needs installed build)"}`,
      `${webCfg ? "✓" : "✕"} Web client ID ${webCfg ? "configured" : "missing"}`,
    ];
    if (!mod || !webCfg) return lines.join("\n");
    try {
      const { idToken } = await signInWithGoogle();
      lines.push(`✓ ID token received (len ${idToken.length})`);
      const r = await api.post("/auth/google", { id_token: idToken });
      lines.push(`${r?.access_token ? "✓" : "✕"} Backend audience accepted (verified vs Web client ID)`);
      lines.push(`${r?.access_token ? "✓" : "✕"} Application session created`);
    } catch (e: any) {
      lines.push(`✕ ${String(e?.message || e)}`);
    }
    return lines.join("\n");
  });
  const testMic = () => run("mic", async () => {
    if (!isDevice) return "✕ Microphone works in the installed app, not the web preview.";
    const cur = await AudioModule.getRecordingPermissionsAsync();
    let granted = cur.granted;
    if (!granted && cur.canAskAgain) granted = (await AudioModule.requestRecordingPermissionsAsync()).granted;
    return granted ? "✓ Microphone permission granted" : "✕ Microphone permission denied";
  });
  const testEvent = () => run("event", async () => {
    if (!isDevice) return "✕ Calendar writes work in the installed app, not the web preview.";
    const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
    const w = cals.find((c: any) => c.allowsModifications);
    if (!w) return "✕ No writable calendar available";
    const id = await Calendar.createEventAsync(w.id, { title: "Student Assistant test", startDate: new Date(Date.now() + 36e5), endDate: new Date(Date.now() + 72e5) });
    await Calendar.deleteEventAsync(id);
    return "✓ Created and deleted a test event";
  });
  const exportReport = () => run("export", async () => {
    const rep = await api.get(`/diagnostics/report?tz=${encodeURIComponent(TZ)}`);
    await Share.share({ message: JSON.stringify(rep, null, 2) });
    return "✓ Diagnostic report shared";
  });

  const openSupportBundle = async () => {
    setRunning("bundle"); setLog("");
    try {
      const b = await api.get(`/diagnostics/support-bundle?tz=${encodeURIComponent(TZ)}`);
      const enriched = {
        app_version: Constants.expoConfig?.version ?? "unknown",
        platform: Platform.OS,
        os_version: String(Platform.Version),
        permissions: { microphone: dev.mic, notifications: dev.notif, calendar: dev.cal },
        ...b,
      };
      setBundle(enriched);
      setBundleText(JSON.stringify(enriched, null, 2));
    } catch (e: any) { setLog("✕ " + (e?.message || "Could not build support bundle")); }
    finally { setRunning(""); }
  };
  const shareBundle = async () => { await Share.share({ message: bundleText }); setBundle(null); };

  const tone = (ok: boolean) => (ok ? "success" : "error");
  const permTone = (p: string) => (p === "granted" ? "success" : p === "unavailable" ? "info" : "warning");

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="diag-back"><Feather name="x" size={22} color={C.onSurface} /></Pressable>
        <Text style={styles.hTitle}>Diagnostics</Text>
        <Pressable onPress={load} hitSlop={10} testID="diag-refresh"><Feather name="refresh-cw" size={18} color={C.onSurface2} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: insets.bottom + S.xl }} showsVerticalScrollIndicator={false}>
        {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xl }} /> : d ? (
          <>
            <SectionTitle>System</SectionTitle>
            <Card>
              <Row label="Authentication" value={d.auth.ok ? "Signed in" : "No"} tone={tone(d.auth.ok)} />
              <Row label="Backend" value={d.backend.ok ? "Reachable" : "Down"} tone={tone(d.backend.ok)} />
              <Row label="AI provider" value={`${d.ai_provider.provider}${d.ai_provider.configured ? "" : " (not configured)"}`} tone={tone(d.ai_provider.configured)} />
              <Row label="Timezone" value={d.timezone} />
            </Card>

            <SectionTitle>Notifications & reminders</SectionTitle>
            <Card>
              <Row label="Notification permission" value={dev.notif} tone={permTone(dev.notif)} />
              <Row label="Scheduled on device" value={dev.scheduled} />
              <Row label="Scheduled (server)" value={d.notifications.scheduled} />
              <Row label="Failed reminders" value={d.notifications.failed} tone={d.notifications.failed ? "warning" : "success"} />
            </Card>

            <SectionTitle>Calendar</SectionTitle>
            <Card>
              <Row label="Connection" value={d.calendar.status} tone={d.calendar.connected ? "success" : "info"} />
              <Row label="Permission (device)" value={dev.cal} tone={permTone(dev.cal)} />
              <Row label="Last sync" value={d.calendar.last_sync ? new Date(d.calendar.last_sync).toLocaleString() : "Never"} />
              <Row label="Failures" value={d.calendar.failures} tone={d.calendar.failures ? "warning" : "success"} />
              <Row label="Pending confirmations" value={d.calendar.pending_confirmations} tone={d.calendar.pending_confirmations ? "warning" : "success"} />
            </Card>

            <SectionTitle>Capture & processing</SectionTitle>
            <Card>
              <Row label="Microphone permission" value={dev.mic} tone={permTone(dev.mic)} />
              <Row label="Active Listening" value={d.active_listening.status} />
              <Row label="Recording" value={d.recording.active ? "Active" : "Idle"} />
              <Row label="Pending uploads" value={d.uploads.pending} />
              <Row label="Failed uploads" value={d.uploads.failed} tone={d.uploads.failed ? "warning" : "success"} />
              <Row label="Pending jobs" value={d.processing.pending_jobs} />
              <Row label="Last transcription" value={d.last_transcription ? new Date(d.last_transcription).toLocaleString() : "—"} />
              <Row label="Last study notes" value={d.last_study_notes ? new Date(d.last_study_notes).toLocaleString() : "—"} />
            </Card>

            <SectionTitle>Safe actions</SectionTitle>
            {log ? <Text style={styles.log} testID="diag-log">{log}</Text> : null}
            <View style={styles.actions}>
              <Btn label="Test notification" variant="soft" icon="bell" onPress={testNotif} testID="diag-test-notif" />
              <Btn label="Test backend" variant="soft" icon="server" onPress={testBackend} testID="diag-test-backend" />
              <Btn label="Test AI provider" variant="soft" icon="cpu" onPress={testAI} testID="diag-test-ai" />
              <Btn label="Test calendar read" variant="soft" icon="calendar" onPress={testCalRead} testID="diag-test-calread" />
              <Btn label="Create & delete test event" variant="soft" icon="plus-square" onPress={testEvent} testID="diag-test-event" />
              <Btn label="Test microphone" variant="soft" icon="mic" onPress={testMic} testID="diag-test-mic" />
              <Btn label="Test Google Sign-In" variant="soft" icon="log-in" onPress={testGoogle} testID="diag-test-google" />
              <Btn label="Retry failed jobs" variant="soft" icon="rotate-cw" onPress={retry} testID="diag-retry" />
              <Btn label="Export diagnostic report" variant="soft" icon="download" onPress={exportReport} testID="diag-export" />
              <Btn label="Copy Support Bundle" variant="soft" icon="clipboard" onPress={openSupportBundle} testID="diag-support-bundle" />
            </View>
            {running ? <View style={styles.runRow}><ActivityIndicator color={C.brand} /><Text style={styles.note}>Running {running}…</Text></View> : null}
          </>
        ) : <Text style={styles.note}>Could not load diagnostics.</Text>}
      </ScrollView>

      <Modal visible={!!bundle} animationType="slide" transparent onRequestClose={() => setBundle(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.modalCard, { paddingBottom: insets.bottom + S.lg }]}>
            <View style={styles.modalHead}>
              <Text style={styles.hTitle}>Support bundle preview</Text>
              <Pressable onPress={() => setBundle(null)} hitSlop={10} testID="bundle-cancel"><Feather name="x" size={22} color={C.onSurface} /></Pressable>
            </View>
            <Text style={styles.note}>Review what will be shared. This contains only IDs, status codes and timestamps — no passwords, tokens, audio, transcripts, documents, or email content.</Text>
            <ScrollView style={styles.bundleBox}><Text style={styles.bundleTxt} testID="bundle-preview">{bundleText}</Text></ScrollView>
            <View style={styles.actions}>
              <Btn label="Share via device" icon="share-2" onPress={shareBundle} testID="bundle-share" />
              <Btn label="Cancel" variant="ghost" onPress={() => setBundle(null)} testID="bundle-cancel-btn" />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  hTitle: { fontFamily: F.display, fontSize: 18, color: C.onSurface },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: S.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border },
  rowLabel: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, flex: 1 },
  rowVal: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface },
  actions: { gap: S.sm },
  log: { fontFamily: F.bodyMed, fontSize: 13, color: C.onSurface, backgroundColor: C.surface3, padding: S.md, borderRadius: R.md, marginBottom: S.md },
  runRow: { flexDirection: "row", alignItems: "center", gap: S.sm, marginTop: S.md },
  note: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center", marginTop: S.sm },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: C.surface, borderTopLeftRadius: R.lg, borderTopRightRadius: R.lg, padding: S.lg, maxHeight: "85%" },
  modalHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: S.sm },
  bundleBox: { backgroundColor: C.surface3, borderRadius: R.md, padding: S.md, marginVertical: S.md, maxHeight: 360 },
  bundleTxt: { fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }), fontSize: 11, color: C.onSurface2 },
});
