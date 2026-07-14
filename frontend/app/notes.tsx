import { useState, useEffect } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Btn, Loading, SectionTitle } from "@/src/components/ui";

export default function Notes() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const [list, setList] = useState<any[]>([]);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [title, setTitle] = useState("");
  const [course, setCourse] = useState("");
  const [transcript, setTranscript] = useState("");
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<any>(null);

  const loadList = async () => { try { setList(await api.get("/notes")); } catch (e) {} };
  useEffect(() => { loadList(); }, []);

  const generate = async () => {
    if (!transcript.trim() || !title.trim()) return;
    setLoading(true);
    try {
      const n = await api.post("/notes/generate", { title, course: course || null, transcript });
      setNote(n); setMode("list"); loadList();
      setTitle(""); setCourse(""); setTranscript("");
    } catch (e) {} finally { setLoading(false); }
  };

  const openNote = async (nid: string) => { setNote(await api.get(`/notes/${nid}`)); };
  useEffect(() => { if (id) openNote(id); }, [id]);

  const sn = note?.study_notes || {};

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>{note ? "Study Notes" : "Lecture Notes"}</Text>
        <Pressable onPress={() => note ? setNote(null) : router.back()} testID="notes-close" hitSlop={10}>
          <Feather name={note ? "arrow-left" : "x"} size={24} color={C.onSurface2} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {note ? (
          <>
            <Text style={styles.noteTitle}>{note.title}</Text>
            {note.course ? <Text style={styles.noteCourse}>{note.course}</Text> : null}
            <NoteSection icon="book-open" title="Overview" text={sn.overview} />
            <NoteList icon="key" title="Key concepts" items={sn.key_concepts} />
            <NoteDefs items={sn.definitions} />
            <NoteList icon="layers" title="Examples" items={sn.examples} />
            <NoteList icon="git-merge" title="Relationships" items={sn.relationships} />
            <NoteList icon="star" title="Professor emphasis" items={sn.professor_emphasis} />
            <NoteList icon="calendar" title="Important dates" items={sn.important_dates} />
            <NoteList icon="target" title="Likely exam topics" items={sn.likely_exam_topics} />
            <NoteList icon="check-square" title="Action items" items={sn.action_items} />
            <NoteList icon="refresh-cw" title="Review recommendations" items={sn.review_recommendations} />
          </>
        ) : mode === "create" ? (
          <>
            <Text style={styles.label}>Title</Text>
            <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="e.g. Intro to Sociology — Lecture 4" placeholderTextColor={C.onSurface3} testID="notes-title" />
            <Text style={styles.label}>Course (optional)</Text>
            <TextInput style={styles.input} value={course} onChangeText={setCourse} placeholder="e.g. SOC 101" placeholderTextColor={C.onSurface3} testID="notes-course" />
            <Text style={styles.label}>Lecture transcript</Text>
            <TextInput style={[styles.input, styles.area]} value={transcript} onChangeText={setTranscript} placeholder="Paste your lecture transcript or notes here…" placeholderTextColor={C.onSurface3} multiline testID="notes-transcript" />
            {loading ? <Loading label="Reorganizing into study notes…" /> : <Btn label="Generate study notes" icon="zap" onPress={generate} testID="notes-generate" style={{ marginTop: S.md }} />}
          </>
        ) : (
          <>
            <Btn label="New study notes" icon="plus" onPress={() => setMode("create")} testID="notes-new" />
            <View style={{ height: S.lg }} />
            <SectionTitle>Your notes</SectionTitle>
            {list.length ? list.map((n) => (
              <Pressable key={n.id} onPress={() => openNote(n.id)} testID={`note-${n.id}`}>
                <Card style={styles.noteRow}>
                  <View style={styles.noteIcon}><Feather name="file-text" size={16} color={C.onBrand3} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{n.title}</Text>
                    <Text style={styles.rowSub}>{n.course || "General"}</Text>
                  </View>
                  <Feather name="chevron-right" size={18} color={C.onSurface3} />
                </Card>
              </Pressable>
            )) : <Text style={styles.empty}>No notes yet. Create your first set of AI study notes.</Text>}
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function NoteSection({ icon, title, text }: any) {
  if (!text) return null;
  return (
    <View style={styles.sec}>
      <View style={styles.secHead}><Feather name={icon} size={15} color={C.brand} /><Text style={styles.secTitle}>{title}</Text></View>
      <Text style={styles.secBody}>{text}</Text>
    </View>
  );
}
function NoteList({ icon, title, items }: any) {
  if (!items?.length) return null;
  return (
    <View style={styles.sec}>
      <View style={styles.secHead}><Feather name={icon} size={15} color={C.brand} /><Text style={styles.secTitle}>{title}</Text></View>
      {items.map((it: string, i: number) => <View key={i} style={styles.li}><Text style={styles.bullet}>•</Text><Text style={styles.secBody}>{it}</Text></View>)}
    </View>
  );
}
function NoteDefs({ items }: any) {
  if (!items?.length) return null;
  return (
    <View style={styles.sec}>
      <View style={styles.secHead}><Feather name="bookmark" size={15} color={C.brand} /><Text style={styles.secTitle}>Definitions</Text></View>
      {items.map((d: any, i: number) => <Text key={i} style={styles.secBody}><Text style={styles.term}>{d.term}: </Text>{d.definition}</Text>)}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  label: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface, marginTop: S.md, marginBottom: S.xs },
  input: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  area: { minHeight: 160, textAlignVertical: "top" },
  empty: { fontFamily: F.body, fontSize: 14, color: C.onSurface3, marginTop: S.md },
  noteRow: { flexDirection: "row", alignItems: "center", gap: S.md, marginBottom: S.sm, padding: S.md },
  noteIcon: { width: 34, height: 34, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  rowSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  noteTitle: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  noteCourse: { fontFamily: F.bodyMed, fontSize: 13, color: C.brand, marginTop: 2, marginBottom: S.sm },
  sec: { marginTop: S.lg },
  secHead: { flexDirection: "row", alignItems: "center", gap: S.sm, marginBottom: S.sm },
  secTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  secBody: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, lineHeight: 21, flex: 1 },
  li: { flexDirection: "row", gap: S.sm, marginBottom: 4 },
  bullet: { fontFamily: F.body, fontSize: 14, color: C.brand },
  term: { fontFamily: F.bodyBold, color: C.onSurface },
});
