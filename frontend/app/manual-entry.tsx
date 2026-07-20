import { useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn } from "@/src/components/ui";

type Kind = "task" | "event" | "reminder" | "note";
const KINDS: { key: Kind; label: string; icon: any }[] = [
  { key: "task", label: "Task", icon: "check-square" },
  { key: "event", label: "Event", icon: "calendar" },
  { key: "reminder", label: "Reminder", icon: "bell" },
  { key: "note", label: "Note", icon: "file-text" },
];
const PRIORITIES = ["low", "normal", "high"];

function toIso(date: string, time: string): string | null {
  const d = (date || "").trim();
  if (!d) return null;
  const t = (time || "").trim() || "09:00";
  return `${d}T${t.length === 5 ? t : "09:00"}:00`;
}

export default function ManualEntry() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  // Prefilled context (e.g. after an AI failure) is preserved and reused here.
  const params = useLocalSearchParams<{ kind?: string; title?: string; text?: string; course?: string; date?: string; time?: string }>();

  const [kind, setKind] = useState<Kind>((params.kind as Kind) || "task");
  const [title, setTitle] = useState(String(params.title || ""));
  const [course, setCourse] = useState(String(params.course || ""));
  const [date, setDate] = useState(String(params.date || ""));
  const [time, setTime] = useState(String(params.time || ""));
  const [priority, setPriority] = useState("normal");
  const [location, setLocation] = useState("");
  const [recurring, setRecurring] = useState(false);
  const [addReminder, setAddReminder] = useState(false);
  const [notes, setNotes] = useState(String(params.text || ""));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  const submit = async () => {
    setErr("");
    if (!title.trim()) { setErr("Please enter a title."); return; }
    if (kind === "reminder" && !date.trim()) { setErr("Please choose a date for the reminder."); return; }
    setBusy(true);
    try {
      if (kind === "task") {
        const due = toIso(date, time);
        const task = await api.post("/tasks", { title: title.trim(), course: course.trim() || null, due, priority, category: "general" });
        if (addReminder && due) {
          try { await api.post("/reminders", { title: title.trim(), remind_at: due, ref_type: "task", ref_id: task.id }); } catch {}
        }
      } else if (kind === "event") {
        const start = toIso(date, time);
        await api.post("/events", { title: title.trim(), event_type: "personal", course: course.trim() || null, start, location: location.trim() || null, recurring, notes: notes.trim() || null });
      } else if (kind === "reminder") {
        const when = toIso(date, time);
        await api.post("/reminders", { title: title.trim(), remind_at: when, body: notes.trim() || null, ref_type: "manual" });
      } else {
        await api.post("/notes", { title: title.trim(), course: course.trim() || null, body: notes.trim() || null });
      }
      setDone(true);
    } catch (e: any) {
      setErr(e?.message || "Could not save. Please try again.");
    } finally { setBusy(false); }
  };

  if (done) {
    return (
      <View style={[styles.root, { paddingTop: insets.top + S.xl }]}>
        <View style={styles.doneWrap}>
          <Feather name="check-circle" size={44} color={C.success} />
          <Text style={styles.doneTxt}>Saved</Text>
          <Btn label="Add another" variant="soft" icon="plus" onPress={() => { setDone(false); setTitle(""); setNotes(""); setDate(""); setTime(""); setLocation(""); }} style={{ marginTop: S.lg }} />
          <Btn label="Done" variant="primary" onPress={() => router.back()} style={{ marginTop: S.sm }} testID="manual-done" />
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Add manually</Text>
        <Pressable onPress={() => router.back()} testID="manual-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
        <Text style={styles.hint}>No AI needed — this always works, even offline or after your free AI allowance is used.</Text>

        <View style={styles.kindRow}>
          {KINDS.map((k) => (
            <Pressable key={k.key} testID={`manual-kind-${k.key}`} onPress={() => setKind(k.key)}
              style={[styles.kindChip, kind === k.key && styles.kindChipSel]}>
              <Feather name={k.icon} size={16} color={kind === k.key ? C.onBrand : C.onSurface2} />
              <Text style={[styles.kindTxt, kind === k.key && styles.kindTxtSel]}>{k.label}</Text>
            </Pressable>
          ))}
        </View>

        <Field label="Title" required>
          <TextInput testID="manual-title" style={styles.input} value={title} onChangeText={setTitle}
            placeholder={kind === "note" ? "Note title" : "What is it?"} placeholderTextColor={C.onSurface3} />
        </Field>

        {kind !== "note" && (
          <Field label="Course">
            <TextInput testID="manual-course" style={styles.input} value={course} onChangeText={setCourse}
              placeholder="e.g. CS101 (optional)" placeholderTextColor={C.onSurface3} />
          </Field>
        )}

        {kind !== "note" && (
          <View style={styles.row}>
            <Field label={kind === "reminder" ? "Date (required)" : "Date"} style={{ flex: 1 }}>
              <TextInput testID="manual-date" style={styles.input} value={date} onChangeText={setDate}
                placeholder="YYYY-MM-DD" placeholderTextColor={C.onSurface3} />
            </Field>
            <Field label="Time" style={{ flex: 1 }}>
              <TextInput testID="manual-time" style={styles.input} value={time} onChangeText={setTime}
                placeholder="HH:MM" placeholderTextColor={C.onSurface3} />
            </Field>
          </View>
        )}

        {kind === "task" && (
          <>
            <Field label="Priority">
              <View style={styles.segRow}>
                {PRIORITIES.map((p) => (
                  <Pressable key={p} testID={`manual-priority-${p}`} onPress={() => setPriority(p)}
                    style={[styles.seg, priority === p && styles.segSel]}>
                    <Text style={[styles.segTxt, priority === p && styles.segTxtSel]}>{p}</Text>
                  </Pressable>
                ))}
              </View>
            </Field>
            <Toggle label="Remind me at the due time" value={addReminder} onToggle={() => setAddReminder((v) => !v)} testID="manual-reminder-toggle" />
          </>
        )}

        {kind === "event" && (
          <>
            <Field label="Location">
              <TextInput testID="manual-location" style={styles.input} value={location} onChangeText={setLocation}
                placeholder="Room / place (optional)" placeholderTextColor={C.onSurface3} />
            </Field>
            <Toggle label="Repeats weekly" value={recurring} onToggle={() => setRecurring((v) => !v)} testID="manual-recurring-toggle" />
          </>
        )}

        <Field label={kind === "note" ? "Note" : "Notes"}>
          <TextInput testID="manual-notes" style={[styles.input, styles.multiline]} value={notes} onChangeText={setNotes}
            multiline placeholder={kind === "note" ? "Write your note…" : "Extra details (optional)"} placeholderTextColor={C.onSurface3} />
        </Field>

        {err ? <Text style={styles.err} testID="manual-error">{err}</Text> : null}

        <Btn label={busy ? "Saving…" : "Save"} icon="check" onPress={submit} testID="manual-submit" style={{ marginTop: S.lg }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({ label, required, children, style }: any) {
  return (
    <View style={[{ marginTop: S.md }, style]}>
      <Text style={styles.label}>{label}{required ? <Text style={{ color: C.error }}> *</Text> : null}</Text>
      {children}
    </View>
  );
}

function Toggle({ label, value, onToggle, testID }: any) {
  return (
    <Pressable testID={testID} onPress={onToggle} style={styles.toggleRow}>
      <Text style={styles.toggleLabel}>{label}</Text>
      <View style={[styles.toggle, value && styles.toggleOn]}>
        <View style={[styles.knob, value && styles.knobOn]} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  hint: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, lineHeight: 19, marginBottom: S.md },
  kindRow: { flexDirection: "row", flexWrap: "wrap", gap: S.sm },
  kindChip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: S.md, paddingVertical: S.sm, borderRadius: R.pill, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface2 },
  kindChipSel: { backgroundColor: C.brand, borderColor: C.brand },
  kindTxt: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2 },
  kindTxtSel: { color: C.onBrand },
  label: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface3, marginBottom: 6 },
  input: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  multiline: { minHeight: 90, textAlignVertical: "top" },
  row: { flexDirection: "row", gap: S.sm },
  segRow: { flexDirection: "row", gap: S.sm },
  seg: { flex: 1, paddingVertical: S.sm, borderRadius: R.md, borderWidth: 1, borderColor: C.border, alignItems: "center", backgroundColor: C.surface2 },
  segSel: { backgroundColor: C.brand, borderColor: C.brand },
  segTxt: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2, textTransform: "capitalize" },
  segTxtSel: { color: C.onBrand },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: S.md, paddingVertical: S.xs },
  toggleLabel: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface, flex: 1 },
  toggle: { width: 46, height: 28, borderRadius: 14, backgroundColor: C.border, padding: 3, justifyContent: "center" },
  toggleOn: { backgroundColor: C.brand },
  knob: { width: 22, height: 22, borderRadius: 11, backgroundColor: C.onBrand },
  knobOn: { alignSelf: "flex-end" },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, marginTop: S.md, textAlign: "center" },
  doneWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: S.lg },
  doneTxt: { fontFamily: F.display, fontSize: 22, color: C.onSurface, marginTop: S.md },
});
