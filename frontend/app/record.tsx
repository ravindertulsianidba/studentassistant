import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Platform, Linking, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import {
  useAudioRecorder, useAudioRecorderState, AudioModule, RecordingPresets, setAudioModeAsync,
} from "expo-audio";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn, Loading } from "@/src/components/ui";
import { uploadRecording } from "@/src/services/recordingUpload";

const isWeb = Platform.OS === "web";

function fmt(ms: number) {
  const s = Math.floor((ms || 0) / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export default function Record() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);

  const [title, setTitle] = useState("Lecture");
  const [course, setCourse] = useState("");
  const [perm, setPerm] = useState<"unknown" | "granted" | "denied" | "blocked">("unknown");
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading" | "done" | "generating">("idle");
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [err, setErr] = useState("");
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    (async () => {
      if (isWeb) return;
      const cur = await AudioModule.getRecordingPermissionsAsync();
      setPerm(cur.granted ? "granted" : "unknown");
    })();
  }, []);

  const askPermission = async () => {
    const cur = await AudioModule.getRecordingPermissionsAsync();
    if (cur.granted) { setPerm("granted"); return true; }
    if (!cur.canAskAgain) { setPerm("blocked"); return false; }
    const req = await AudioModule.requestRecordingPermissionsAsync();
    if (req.granted) { setPerm("granted"); return true; }
    setPerm(req.canAskAgain ? "denied" : "blocked");
    return false;
  };

  const start = async () => {
    setErr("");
    if (isWeb) { setErr("Recording needs the installed app (not the web preview)."); return; }
    if (!(await askPermission())) return;
    try {
      // Keep recording alive in background / when the screen locks.
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true, shouldPlayInBackground: true } as any);
      await recorder.prepareToRecordAsync();
      recorder.record();
      setPhase("recording");
    } catch (e: any) {
      setErr(e?.message || "Could not start recording.");
    }
  };

  const stopAndUpload = async () => {
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) { setErr("No audio captured."); setPhase("idle"); return; }
      setPhase("uploading");
      const res = await uploadRecording(
        uri, { title: title || "Lecture", course: course || null, filename: "lecture.m4a" },
        (done, total) => setProgress({ done, total }));
      setResult(res);
      setPhase("done");
    } catch (e: any) {
      setErr(e?.message || "Upload failed. Your recording is still on the device — try again.");
      setPhase("idle");
    }
  };

  const generateNotes = async () => {
    if (!result?.text) return;
    setPhase("generating");
    try {
      const n = await api.post("/notes/generate", { title: title || "Lecture", course: course || null, transcript: result.text });
      router.replace({ pathname: "/notes", params: { id: n.id } });
    } catch (e: any) {
      setErr(e?.message || "Could not generate notes (AI may be unavailable).");
      setPhase("done");
    }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Record lecture</Text>
        <Pressable onPress={() => router.back()} testID="record-close" hitSlop={10}>
          <Feather name="x" size={24} color={C.onSurface2} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        <Text style={styles.label}>Title</Text>
        <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="e.g. Sociology — Lecture 4"
          placeholderTextColor={C.onSurface3} editable={phase === "idle"} testID="record-title" />
        <Text style={styles.label}>Course (optional)</Text>
        <TextInput style={styles.input} value={course} onChangeText={setCourse} placeholder="e.g. SOC 101"
          placeholderTextColor={C.onSurface3} editable={phase === "idle"} testID="record-course" />

        <View style={styles.stage}>
          {phase === "recording" ? (
            <>
              <View style={styles.pulse}><Feather name="mic" size={30} color={C.onBrand} /></View>
              <Text style={styles.timer} testID="record-timer">{fmt(state.durationMillis)}</Text>
              <View style={styles.recBadge}><View style={styles.recDot} /><Text style={styles.recTxt}>Recording — keeps going if the screen locks</Text></View>
              <Btn label="Stop & transcribe" icon="square" onPress={stopAndUpload} testID="record-stop" style={{ marginTop: S.lg, alignSelf: "stretch" }} />
            </>
          ) : phase === "uploading" ? (
            <>
              <Loading label={`Uploading… chunk ${progress.done}/${progress.total || "?"}`} />
              <Text style={styles.note}>Large lectures upload in chunks with automatic retry. Your recording stays on the device until this finishes.</Text>
            </>
          ) : phase === "generating" ? (
            <Loading label="Creating study notes…" />
          ) : phase === "done" ? (
            <>
              <View style={styles.doneIcon}><Feather name="check" size={28} color={C.success} /></View>
              <Text style={styles.doneTitle}>Transcribed</Text>
              <Text style={styles.note} numberOfLines={4}>{result?.text}</Text>
              <Btn label="Generate study notes" icon="zap" onPress={generateNotes} style={{ marginTop: S.lg, alignSelf: "stretch" }} testID="record-generate" />
              <Btn label="Done" variant="ghost" onPress={() => router.back()} style={{ marginTop: S.sm, alignSelf: "stretch" }} />
            </>
          ) : (
            <>
              <Pressable style={styles.recordBtn} onPress={start} testID="record-start">
                <Feather name="mic" size={34} color={C.onBrand} />
              </Pressable>
              <Text style={styles.note}>Tap to start recording your lecture.</Text>
              {perm === "blocked" ? (
                <Btn label="Open settings to allow the microphone" variant="soft" icon="settings"
                  onPress={() => Linking.openSettings()} style={{ marginTop: S.md }} testID="record-settings" />
              ) : null}
              {isWeb ? <Text style={styles.note}>Recording works in the installed app, not the web preview.</Text> : null}
            </>
          )}
          {err ? <Text style={styles.err} testID="record-error">{err}</Text> : null}
        </View>
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
  recordBtn: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  pulse: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.error, alignItems: "center", justifyContent: "center" },
  timer: { fontFamily: F.display, fontSize: 40, color: C.onSurface, marginTop: S.md },
  recBadge: { flexDirection: "row", alignItems: "center", gap: S.sm, marginTop: S.xs },
  recDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: C.error },
  recTxt: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  doneIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  doneTitle: { fontFamily: F.display, fontSize: 20, color: C.onSurface, marginTop: S.sm },
  note: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center", marginTop: S.sm, lineHeight: 19 },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, textAlign: "center", marginTop: S.md },
});
