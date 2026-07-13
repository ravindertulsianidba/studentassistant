import { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn, Chip, Loading, Badge } from "@/src/components/ui";

const KINDS = [
  { key: "schedule", label: "Class schedule", icon: "grid" },
  { key: "syllabus", label: "Syllabus", icon: "book" },
  { key: "email", label: "Email", icon: "mail" },
];

export default function ImportScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [kind, setKind] = useState("schedule");
  const [img, setImg] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const pick = async (fromCamera: boolean) => {
    const perm = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = fromCamera
      ? await ImagePicker.launchCameraAsync({ base64: true, quality: 0.6 })
      : await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.6, mediaTypes: "images" });
    if (!res.canceled && res.assets?.[0]?.base64) {
      setImg(`data:image/jpeg;base64,${res.assets[0].base64}`);
      setResult(null);
    }
  };

  const submit = async () => {
    if (!img) return;
    setLoading(true);
    try { setResult(await api.post("/import", { image_base64: img, kind })); } catch (e) {} finally { setLoading(false); }
  };

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Import</Text>
        <Pressable onPress={() => router.back()} testID="import-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }}>
        <Text style={styles.label}>What are you importing?</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: S.sm, paddingVertical: S.sm }}>
          {KINDS.map((k) => <Chip key={k.key} label={k.label} active={kind === k.key} onPress={() => setKind(k.key)} testID={`import-kind-${k.key}`} />)}
        </ScrollView>

        {img ? (
          <Image source={{ uri: img }} style={styles.preview} contentFit="cover" />
        ) : (
          <View style={styles.dropzone} testID="import-dropzone">
            <Feather name="image" size={30} color={C.brand} />
            <Text style={styles.dzText}>Add a screenshot or photo of your {KINDS.find(k => k.key === kind)?.label.toLowerCase()}</Text>
          </View>
        )}

        <View style={styles.pickRow}>
          <Btn label="Camera" variant="soft" icon="camera" onPress={() => pick(true)} testID="import-camera" style={{ flex: 1 }} />
          <Btn label="Gallery" variant="soft" icon="image" onPress={() => pick(false)} testID="import-gallery" style={{ flex: 1 }} />
        </View>

        {loading ? <Loading label="Extracting details…" /> : img && !result ? (
          <Btn label="Extract items" icon="zap" onPress={submit} testID="import-extract" style={{ marginTop: S.md }} />
        ) : null}

        {result ? (
          <View style={{ marginTop: S.lg }}>
            <View style={styles.done}><Feather name="check-circle" size={36} color={C.success} /></View>
            <Text style={styles.resHead}>{result.review?.length || 0} items detected — sent to Review Queue</Text>
            {result.review?.map((r: any, i: number) => (
              <View key={i} style={styles.resCard} testID={`import-item-${i}`}>
                <Badge label={r.item?.kind === "event" ? "Event" : "Task"} tone="info" />
                <Text style={styles.resTitle}>{r.item?.title}</Text>
              </View>
            ))}
            <Btn label="Review & confirm" icon="inbox" onPress={() => { router.back(); router.push("/(tabs)/review"); }} style={{ marginTop: S.md }} testID="import-goto-review" />
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  label: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface, marginBottom: S.xs },
  dropzone: { height: 180, borderRadius: R.lg, borderWidth: 2, borderColor: C.border, borderStyle: "dashed", alignItems: "center", justifyContent: "center", gap: S.sm, marginTop: S.sm, padding: S.lg },
  dzText: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center" },
  preview: { height: 200, borderRadius: R.lg, marginTop: S.sm },
  pickRow: { flexDirection: "row", gap: S.sm, marginTop: S.md },
  done: { alignItems: "center", marginBottom: S.sm },
  resHead: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface, marginBottom: S.md, textAlign: "center" },
  resCard: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, marginBottom: S.sm, gap: 6 },
  resTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
});
