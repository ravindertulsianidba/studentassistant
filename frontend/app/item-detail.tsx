import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Platform, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import DateTimePicker from "@react-native-community/datetimepicker";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Btn } from "@/src/components/ui";

const CATEGORIES = ["task", "assignment", "reminder", "followup", "exam"];
const EVENT_TYPES = ["class", "lab", "exam", "meeting", "study", "personal"];

export default function ItemDetail() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ type: string; data: string }>();
  const type = params.type === "event" ? "event" : "task";
  const initial = (() => { try { return JSON.parse(params.data as string); } catch { return {}; } })();

  const dateField = type === "event" ? "start" : "due";
  const [title, setTitle] = useState(initial.title || "");
  const [when, setWhen] = useState<Date | null>(initial[dateField] ? new Date(initial[dateField]) : null);
  const [priority, setPriority] = useState(initial.priority || "normal");
  const [category, setCategory] = useState(initial.category || "task");
  const [eventType, setEventType] = useState(initial.event_type || "personal");
  const [location, setLocation] = useState(initial.location || "");
  const [status, setStatus] = useState(initial.status || "open");
  const [picker, setPicker] = useState<null | "date" | "time">(null);
  const [saving, setSaving] = useState(false);

  const onPick = (_: any, sel?: Date) => {
    if (Platform.OS === "android") setPicker(null);
    if (!sel) return;
    if (picker === "date") {
      const base = when || new Date();
      const d = new Date(sel); d.setHours(base.getHours(), base.getMinutes(), 0, 0);
      setWhen(d);
      if (Platform.OS === "android") setTimeout(() => setPicker("time"), 150);
    } else {
      const base = when || new Date();
      const d = new Date(base); d.setHours(sel.getHours(), sel.getMinutes(), 0, 0);
      setWhen(d);
    }
  };

  const save = async () => {
    if (!title.trim()) { Alert.alert("Add a title"); return; }
    setSaving(true);
    try {
      const body: any = { title: title.trim(), [dateField]: when ? when.toISOString() : null };
      if (type === "task") { body.priority = priority; body.category = category; }
      else { body.event_type = eventType; body.location = location || null; }
      await api.patch(`/${type}s/${initial.id}`, body);
      router.back();
    } catch (e: any) { Alert.alert("Couldn't save", e?.message || "Try again."); }
    finally { setSaving(false); }
  };

  const toggleDone = async () => {
    const next = status === "done" ? "open" : "done";
    setSaving(true);
    try { await api.patch(`/tasks/${initial.id}`, { status: next }); setStatus(next); router.back(); }
    catch (e: any) { Alert.alert("Couldn't update", e?.message || "Try again."); }
    finally { setSaving(false); }
  };

  const del = () => {
    Alert.alert(`Delete this ${type}?`, "This can't be undone.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api.del(`/${type}s/${initial.id}`); router.back(); }
        catch (e: any) { Alert.alert("Couldn't delete", e?.message || "Try again."); }
      } },
    ]);
  };

  const whenLabel = when
    ? when.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : "No date / time set";

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Edit {type}</Text>
        <Pressable onPress={() => router.back()} testID="detail-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: insets.bottom + 40 }} keyboardShouldPersistTaps="handled">
        {status === "done" ? (
          <View style={styles.doneBanner}><Feather name="check-circle" size={16} color={C.success} /><Text style={styles.doneTxt}>Completed — reopen below to work on it again.</Text></View>
        ) : null}

        <Text style={styles.label}>Title</Text>
        <TextInput style={styles.input} value={title} onChangeText={setTitle} placeholder="Title" placeholderTextColor={C.onSurface3} testID="detail-title" />

        <Text style={styles.label}>Date & time</Text>
        <Pressable style={styles.dateBtn} onPress={() => setPicker("date")} testID="detail-datetime">
          <Feather name="calendar" size={16} color={C.brand} />
          <Text style={styles.dateTxt}>{whenLabel}</Text>
          {when ? <Pressable onPress={() => setWhen(null)} hitSlop={10} testID="detail-clear-date"><Feather name="x-circle" size={16} color={C.onSurface3} /></Pressable> : null}
        </Pressable>

        {type === "task" ? (
          <>
            <Text style={styles.label}>Priority</Text>
            <View style={styles.chips}>
              {["normal", "high"].map((p) => (
                <Pressable key={p} style={[styles.chip, priority === p && styles.chipOn]} onPress={() => setPriority(p)} testID={`prio-${p}`}>
                  <Text style={[styles.chipTxt, priority === p && styles.chipTxtOn]}>{p}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.label}>Type</Text>
            <View style={styles.chips}>
              {CATEGORIES.map((c) => (
                <Pressable key={c} style={[styles.chip, category === c && styles.chipOn]} onPress={() => setCategory(c)}>
                  <Text style={[styles.chipTxt, category === c && styles.chipTxtOn]}>{c}</Text>
                </Pressable>
              ))}
            </View>
          </>
        ) : (
          <>
            <Text style={styles.label}>Type</Text>
            <View style={styles.chips}>
              {EVENT_TYPES.map((c) => (
                <Pressable key={c} style={[styles.chip, eventType === c && styles.chipOn]} onPress={() => setEventType(c)}>
                  <Text style={[styles.chipTxt, eventType === c && styles.chipTxtOn]}>{c}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.label}>Location</Text>
            <TextInput style={styles.input} value={location} onChangeText={setLocation} placeholder="e.g. Room B12" placeholderTextColor={C.onSurface3} />
          </>
        )}

        <Btn label="Save changes" icon="save" onPress={save} testID="detail-save" style={{ marginTop: S.xl }} />
        {type === "task" ? (
          <Btn label={status === "done" ? "Reopen task" : "Mark as done"} variant="soft"
            icon={status === "done" ? "rotate-ccw" : "check"} onPress={toggleDone} style={{ marginTop: S.sm }} testID="detail-toggle" />
        ) : null}
        <Btn label={`Delete ${type}`} variant="ghost" icon="trash-2" onPress={del} style={{ marginTop: S.sm }} testID="detail-delete" />
      </ScrollView>

      {picker ? (
        <DateTimePicker
          value={when || new Date()}
          mode={picker}
          is24Hour={false}
          display={Platform.OS === "ios" ? "spinner" : "default"}
          onChange={onPick}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface, textTransform: "capitalize" },
  label: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface, marginTop: S.lg, marginBottom: S.xs },
  input: { backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.border, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  dateBtn: { flexDirection: "row", alignItems: "center", gap: S.sm, backgroundColor: C.surface2, borderRadius: R.md, borderWidth: 1, borderColor: C.borderStrong, padding: S.md },
  dateTxt: { flex: 1, fontFamily: F.bodyMed, fontSize: 15, color: C.onSurface },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: S.sm },
  chip: { paddingHorizontal: S.md, paddingVertical: 8, borderRadius: R.pill, borderWidth: 1, borderColor: C.border, backgroundColor: C.surface2 },
  chipOn: { backgroundColor: C.brand, borderColor: C.brand },
  chipTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.onSurface2, textTransform: "capitalize" },
  chipTxtOn: { color: C.onBrand },
  doneBanner: { flexDirection: "row", alignItems: "center", gap: S.sm, backgroundColor: C.brand3, borderRadius: R.md, padding: S.md },
  doneTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.onBrand3, flex: 1 },
});
