import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Platform, Linking, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { useAudioRecorder, useAudioRecorderState, AudioModule, RecordingPresets, setAudioModeAsync } from "expo-audio";
import * as Notifications from "expo-notifications";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn, Loading } from "@/src/components/ui";
import { uploadRecording } from "@/src/services/recordingUpload";

const isWeb = Platform.OS === "web";
const isDevice = Platform.OS === "ios" || Platform.OS === "android";

function fmt(ms: number) {
  const s = Math.floor((ms || 0) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export default function Listen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);

  const [course, setCourse] = useState("");
  const [phase, setPhase] = useState<"idle" | "listening" | "paused" | "processing" | "done">("idle");
  const [sid, setSid] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [summary, setSummary] = useState<any>(null);
  const [err, setErr] = useState("");
  const notifId = useRef<string | null>(null);

  useEffect(() => () => { if (notifId.current) Notifications.dismissNotificationAsync(notifId.current).catch(() => {}); }, []);

  const showOngoing = async () => {
    if (!isDevice) return;
    try {
      notifId.current = await Notifications.scheduleNotificationAsync({
        content: { title: "Listening now", body: "Student Assistant is capturing this session. Tap to return.", sticky: true } as any,
        trigger: null,
      });
    } catch {}
  };
  const clearOngoing = async () => { if (notifId.current) { await Notifications.dismissNotificationAsync(notifId.current).catch(() => {}); notifId.current = null; } };

  const start = async () => {
    setErr(""); setSummary(null);
    try {
      const s = await api.post("/listen/start", { course: course || null });
      setSid(s.id);
      if (isDevice) {
        const cur = await AudioModule.getRecordingPermissionsAsync();
        let granted = cur.granted;
        if (!granted && cur.canAskAgain) granted = (await AudioModule.requestRecordingPermissionsAsync()).granted;
        if (granted) {
          await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true, shouldPlayInBackground: true } as any);
          await recorder.prepareToRecordAsync();
          recorder.record();
          await showOngoing();
        } else {
          setErr("Microphone permission is needed to capture audio. You can still type notes below.");
        }
      }
      setPhase("listening");
    } catch (e: any) { setErr(e?.message || "Could not start."); }
  };

  const pause = async () => { try { recorder.pause?.(); } catch {} await api.post(`/listen/${sid}/pause`, {}).catch(() => {}); setPhase("paused"); };
  const resume = async () => { try { recorder.record(); } catch {} await api.post(`/listen/${sid}/resume`, {}).catch(() => {}); setPhase("listening"); };

  const stop = async () => {
    setPhase("processing");
    await clearOngoing();
    let transcript = manual.trim();
    let audioUri: string | null = null;
    try {
      if (isDevice && state.isRecording) {
        await recorder.stop();
        audioUri = recorder.uri || null;
        if (audioUri) {
          try {
            const res = await uploadRecording(audioUri, { title: "Active Listening", course: course || null, filename: "listen.m4a" });
            if (res?.text) transcript = [transcript, res.text].filter(Boolean).join("\n");
          } catch { /* keep manual transcript; audio stays on device */ }
        }
      }
      const done = await api.post(`/listen/${sid}/stop`, { transcript, audio_uri: audioUri });
      setSummary(done.summary);
      setPhase("done");
    } catch (e: any) {
      setErr(e?.message || "Processing failed. Your session is saved.");
      setPhase("done");
    }
  };

  const undo = async () => { await api.post(`/listen/${sid}/undo`, {}).catch(() => {}); setSummary(null); router.back(); };

  const listening = phase === "listening" || phase === "paused";
  const level = Math.max(0, Math.min(1, ((state.metering ?? -60) + 60) / 60));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Active Listening</Text>
        <Pressable onPress={() => router.back()} testID="listen-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {phase === "idle" ? (
          <>
            <Text style={styles.label}>Course (optional)</Text>
            <TextInput style={styles.input} value={course} onChangeText={setCourse} placeholder="e.g. HIST 210" placeholderTextColor={C.onSurface3} testID="listen-course" />
            <View style={styles.stage}>
              <Pressable style={styles.startBtn} onPress={start} testID="listen-start"><Feather name="radio" size={34} color={C.onBrand} /></Pressable>
              <Text style={styles.note}>You start it. Student Assistant listens, then routes anything you’re asked to do into your AI Inbox for review.</Text>
              {isWeb ? <Text style={styles.note}>Live audio needs the installed app — you can still type what was said below to test the flow.</Text> : null}
            </View>
          </>
        ) : listening ? (
          <View style={styles.stage}>
            <View style={[styles.pulse, phase === "paused" && { backgroundColor: C.onSurface3 }]}><Feather name={phase === "paused" ? "pause" : "radio"} size={30} color={C.onBrand} /></View>
            <Text style={styles.timer} testID="listen-timer">{fmt(state.durationMillis)}</Text>
            <View style={styles.badge}><View style={[styles.dot, { backgroundColor: phase === "paused" ? C.onSurface3 : C.error }]} /><Text style={styles.badgeTxt}>{phase === "paused" ? "Paused" : "Listening now — continues if the screen locks"}</Text></View>
            {isDevice ? (
              <View style={styles.meter}><View style={[styles.meterFill, { width: `${Math.round(level * 100)}%` }]} /></View>
            ) : (
              <TextInput style={[styles.input, { minHeight: 100, textAlignVertical: "top", alignSelf: "stretch" }]} multiline value={manual} onChangeText={setManual} placeholder="Type what was said (web fallback)…" placeholderTextColor={C.onSurface3} testID="listen-manual" />
            )}
            <View style={{ flexDirection: "row", gap: S.sm, alignSelf: "stretch", marginTop: S.lg }}>
              {phase === "paused"
                ? <Btn label="Resume" icon="play" onPress={resume} testID="listen-resume" style={{ flex: 1 }} />
                : <Btn label="Pause" variant="soft" icon="pause" onPress={pause} testID="listen-pause" style={{ flex: 1 }} />}
              <Btn label="Stop" icon="square" onPress={stop} testID="listen-stop" style={{ flex: 1 }} />
            </View>
          </View>
        ) : phase === "processing" ? (
          <View style={styles.stage}><Loading label="Processing session — extracting commitments…" /></View>
        ) : (
          <View style={styles.stage}>
            <View style={styles.doneIcon}><Feather name="check" size={28} color={C.success} /></View>
            <Text style={styles.doneTitle}>Session summary</Text>
            {summary ? (
              <Text style={styles.note}>{summary.items_detected} item(s) detected · {summary.to_inbox} sent to your AI Inbox · {summary.auto_created} auto-created.{summary.ai_error ? `\nAI note: ${summary.ai_error}` : ""}</Text>
            ) : <Text style={styles.note}>Session saved.</Text>}
            <Btn label="Review AI Inbox" icon="inbox" onPress={() => router.replace("/inbox")} style={{ marginTop: S.lg, alignSelf: "stretch" }} testID="listen-inbox" />
            <Btn label="Undo this session" variant="ghost" icon="rotate-ccw" onPress={undo} style={{ marginTop: S.sm, alignSelf: "stretch" }} testID="listen-undo" />
            <Btn label="Done" variant="ghost" onPress={() => router.back()} style={{ alignSelf: "stretch" }} />
          </View>
        )}
        {err ? <Text style={styles.err} testID="listen-error">{err}</Text> : null}
        {isDevice && phase === "idle" ? null : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  label: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface, marginTop: S.md, marginBottom: S.xs },
  input: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  stage: { alignItems: "center", marginTop: S.xxl, gap: S.sm },
  startBtn: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  pulse: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.error, alignItems: "center", justifyContent: "center" },
  timer: { fontFamily: F.display, fontSize: 40, color: C.onSurface, marginTop: S.md },
  badge: { flexDirection: "row", alignItems: "center", gap: S.sm, marginTop: S.xs },
  dot: { width: 8, height: 8, borderRadius: 4 },
  badgeTxt: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  meter: { height: 8, alignSelf: "stretch", backgroundColor: C.surface3, borderRadius: 4, overflow: "hidden", marginTop: S.md },
  meterFill: { height: 8, backgroundColor: C.brand, borderRadius: 4 },
  doneIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  doneTitle: { fontFamily: F.display, fontSize: 20, color: C.onSurface, marginTop: S.sm },
  note: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center", marginTop: S.sm, lineHeight: 19 },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, textAlign: "center", marginTop: S.md },
});
