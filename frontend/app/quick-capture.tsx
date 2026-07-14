import { useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ScrollView, KeyboardAvoidingView, Platform, Alert, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import { useAudioRecorder, AudioModule, RecordingPresets, setAudioModeAsync } from "expo-audio";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn, Loading, Badge } from "@/src/components/ui";

const KIND_LABEL: any = { event: "Calendar event", task: "Task", reminder: "Reminder", followup: "Follow-up" };
const SUGGESTIONS = [
  "I'll finish my sociology assignment Friday",
  "I have a lab Tuesday at 2pm in room B12",
  "Remind me to email Professor Lee tomorrow",
  "Call my group member about the project",
];

export default function Capture() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [err, setErr] = useState("");
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const toggleMic = async () => {
    setErr("");
    if (Platform.OS === "web") { setErr("Voice recording needs the installed app."); return; }
    if (recording) { await stopAndTranscribe(); return; }
    const cur = await AudioModule.getRecordingPermissionsAsync();
    let granted = cur.granted;
    if (!granted && cur.canAskAgain) granted = (await AudioModule.requestRecordingPermissionsAsync()).granted;
    if (!granted) {
      Alert.alert("Microphone needed", "Allow microphone access to dictate your commitment.", [
        { text: "Cancel", style: "cancel" },
        { text: "Open settings", onPress: () => Linking.openSettings() },
      ]);
      return;
    }
    try {
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true } as any);
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (e: any) { setErr(e?.message || "Could not start recording."); }
  };

  const stopAndTranscribe = async () => {
    setRecording(false);
    setTranscribing(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error("No audio was recorded.");
      const form = new FormData();
      form.append("file", { uri, name: "voice.m4a", type: "audio/m4a" } as any);
      form.append("title", "Voice capture");
      const res = await fetch(`${api.base}/transcribe`, { method: "POST", headers: { ...api.authHeader() } as any, body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Transcription failed.");
      setText((p) => (p ? p + " " : "") + (data.text || "").trim());
    } catch (e: any) { setErr(e?.message || "Transcription failed. Please type instead."); }
    finally { setTranscribing(false); }
  };

  const submit = async () => {
    if (!text.trim()) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setLoading(true);
    try { setResult(await api.post("/capture", { text })); } catch (e) {} finally { setLoading(false); }
  };

  const pickDocument = async () => {
    setErr("");
    const r = await DocumentPicker.getDocumentAsync({
      type: ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"],
      copyToCacheDirectory: true,
    });
    if (r.canceled || !r.assets?.[0]) return;
    const a = r.assets[0];
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", { uri: a.uri, name: a.name, type: a.mimeType || "application/octet-stream" } as any);
      const res = await fetch(`${api.base}/import/file`, { method: "POST", headers: { ...api.authHeader() } as any, body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");
      setResult({ committed: [], review: data.review || [],
        docType: data.ai_extracted ? "document" : "document · text saved (AI extraction pending)" });
    } catch (e: any) { setErr(e.message || "Upload failed"); } finally { setLoading(false); }
  };

  const pickFile = async (fromCamera: boolean) => {
    const perm = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const r = fromCamera
      ? await ImagePicker.launchCameraAsync({ base64: true, quality: 0.6 })
      : await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.6, mediaTypes: "images" });
    if (r.canceled || !r.assets?.[0]?.base64) return;
    setLoading(true);
    try {
      const res = await api.post("/import", { image_base64: `data:image/jpeg;base64,${r.assets[0].base64}` });
      setResult({ committed: [], review: res.review, docType: res.doc_type });
    } catch (e) {} finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Capture</Text>
        <Pressable onPress={() => router.back()} testID="capture-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {!result ? (
          <>
            <Text style={styles.prompt}>What's on your mind? I'll organize it.</Text>
            <View style={styles.inputWrap}>
              <TextInput
                testID="capture-input"
                style={styles.input}
                placeholder="Speak or type a commitment…"
                placeholderTextColor={C.onSurface3}
                multiline
                autoFocus
                value={text}
                onChangeText={setText}
              />
              <Pressable style={[styles.mic, recording && styles.micActive]} onPress={toggleMic} testID="capture-mic" disabled={transcribing}>
                <Feather name={recording ? "square" : "mic"} size={20} color={C.onBrand} />
              </Pressable>
            </View>
            {recording ? <Text style={styles.recTxt} testID="capture-listening">● Listening… tap the square to stop.</Text> : null}
            {transcribing ? <Text style={styles.hint}>Transcribing your voice…</Text> : null}
            {err && !result ? <Text style={styles.errTxt} testID="capture-mic-error">{err}</Text> : null}

            <Text style={styles.tryLabel}>Try</Text>
            {SUGGESTIONS.map((s) => (
              <Pressable key={s} style={styles.sugg} onPress={() => setText(s)}>
                <Feather name="corner-down-right" size={14} color={C.brand} />
                <Text style={styles.suggTxt}>{s}</Text>
              </Pressable>
            ))}

            {loading ? <Loading label="Analyzing intent…" /> : <Btn label="Capture" icon="zap" onPress={submit} testID="capture-submit" style={{ marginTop: S.lg }} />}

            {!loading ? (
              <>
                <View style={styles.orRow}><View style={styles.hr} /><Text style={styles.or}>or capture anything</Text><View style={styles.hr} /></View>
                <View style={styles.attachRow}>
                  <Btn label="Photo" variant="soft" icon="camera" onPress={() => pickFile(true)} testID="capture-photo" style={{ flex: 1 }} />
                  <Btn label="Gallery" variant="soft" icon="image" onPress={() => pickFile(false)} testID="capture-file" style={{ flex: 1 }} />
                </View>
                <Btn label="Document (PDF / DOCX / TXT)" variant="soft" icon="file" onPress={pickDocument} testID="capture-document" style={{ marginTop: S.sm }} />
                {err ? <Text style={styles.errTxt} testID="capture-error">{err}</Text> : null}
                <Text style={styles.hintSmall}>Add a schedule, syllabus, email, or slide — I'll figure out what it is.</Text>
              </>
            ) : null}
          </>
        ) : (
          <>
            <View style={styles.done}><Feather name="check-circle" size={40} color={C.success} /></View>
            {result.docType ? <Text style={styles.docType}>Detected: {result.docType}</Text> : null}
            {result.committed?.length ? (
              <>
                <Text style={styles.resHead}>Added for you</Text>
                {result.committed.map((c: any, i: number) => (
                  <View key={i} style={styles.resCard} testID={`committed-${i}`}>
                    <Badge label={c.type === "event" ? "Calendar" : "Task"} tone="success" />
                    <Text style={styles.resTitle}>{c.title}</Text>
                  </View>
                ))}
              </>
            ) : null}
            {result.review?.length ? (
              <>
                <Text style={styles.resHead}>Needs your review</Text>
                {result.review.map((r: any, i: number) => (
                  <View key={i} style={styles.resCard}>
                    <Badge label={KIND_LABEL[r.item?.kind] || "Item"} tone="warning" />
                    <Text style={styles.resTitle}>{r.item?.title}</Text>
                  </View>
                ))}
              </>
            ) : null}
            {!result.committed?.length && !result.review?.length ? (
              <Text style={styles.prompt}>I couldn't detect a commitment. Try rephrasing.</Text>
            ) : null}
            <Btn label="Capture something else" variant="soft" icon="plus" onPress={() => { setText(""); setResult(null); }} style={{ marginTop: S.lg }} />
            {result.review?.length ? <Btn label="Open AI Inbox" variant="ghost" icon="inbox" onPress={() => { router.back(); router.push("/inbox"); }} style={{ marginTop: S.sm }} /> : null}
            <Btn label="Done" variant="primary" onPress={() => router.back()} style={{ marginTop: S.sm }} testID="capture-done" />
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  prompt: { fontFamily: F.bodyMed, fontSize: 16, color: C.onSurface2, marginBottom: S.lg, lineHeight: 22 },
  inputWrap: { position: "relative" },
  input: { minHeight: 120, backgroundColor: C.surface2, borderRadius: R.lg, borderWidth: 1, borderColor: C.border, padding: S.lg, paddingRight: 60, fontFamily: F.body, fontSize: 16, color: C.onSurface, textAlignVertical: "top" },
  mic: { position: "absolute", right: S.md, bottom: S.md, width: 44, height: 44, borderRadius: 22, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  micActive: { backgroundColor: C.error },
  recTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, marginTop: S.sm },
  hint: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: S.sm },
  tryLabel: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface3, marginTop: S.xl, marginBottom: S.sm },
  sugg: { flexDirection: "row", alignItems: "center", gap: S.sm, paddingVertical: S.sm },
  suggTxt: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, flex: 1 },
  done: { alignItems: "center", marginVertical: S.lg },
  resHead: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface3, marginTop: S.md, marginBottom: S.sm },
  resCard: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, marginBottom: S.sm, gap: 6 },
  resTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  orRow: { flexDirection: "row", alignItems: "center", gap: S.md, marginTop: S.lg },
  hr: { flex: 1, height: 1, backgroundColor: C.border },
  or: { fontFamily: F.bodyMed, fontSize: 12, color: C.onSurface3 },
  attachRow: { flexDirection: "row", gap: S.sm, marginTop: S.md },
  hintSmall: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: S.sm, textAlign: "center" },
  docType: { fontFamily: F.bodyBold, fontSize: 14, color: C.brand, textAlign: "center", marginBottom: S.sm, textTransform: "capitalize" },
  errTxt: { fontFamily: F.bodyMed, fontSize: 12, color: C.error, textAlign: "center", marginTop: S.sm },
});
