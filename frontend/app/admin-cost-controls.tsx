/**
 * Administrative cost-control panel (AI request cap).
 *
 * This route is deliberately NOT linked from any consumer navigation. It is reachable only by
 * an operator who knows the deep link (/admin-cost-controls). Authorization is enforced entirely
 * by the backend: reading or changing the cap requires a verified administrator (server-side
 * ADMIN_EMAILS check). A normal authenticated user receives HTTP 403 here and sees a
 * "not authorized" message — the control is never rendered for them.
 */
import { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TextInput, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Btn } from "@/src/components/ui";

export default function AdminCostControls() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const [cap, setCap] = useState<any>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const c = await api.get("/admin/ai-cap");
      setCap(c); setInput(String(c.daily_ai_limit)); setAuthorized(true);
    } catch (e: any) {
      setAuthorized(false);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    const n = parseInt(input, 10);
    if (isNaN(n) || n < 0) { Alert.alert("Enter a number", "0 means unlimited."); return; }
    setBusy(true);
    try {
      const r = await api.patch("/admin/ai-cap", { daily_ai_limit: n });
      setCap(r);
      Alert.alert("Saved", n === 0 ? "Cap set to unlimited." : `Administrative daily AI cap set to ${n}.`);
    } catch (e: any) {
      Alert.alert("Not saved", "You are not authorized, or the request failed.");
    } finally { setBusy(false); }
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingTop: insets.top + S.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: S.sm }}>
          <Feather name="shield" size={20} color={C.brand} />
          <Text style={styles.title}>Cost controls (admin)</Text>
        </View>
        <Text style={styles.sub}>Internal operations only</Text>

        {loading ? (
          <Text style={styles.body}>Checking authorization…</Text>
        ) : !authorized ? (
          <Card style={{ gap: S.md, marginTop: S.xl }}>
            <Text style={styles.body}>You are not authorized to view or change cost controls.</Text>
            <Btn label="Go back" variant="soft" icon="arrow-left" onPress={() => router.back()} />
          </Card>
        ) : (
          <Card style={{ gap: S.md, marginTop: S.xl }}>
            <Text style={styles.body}>Administrative daily AI request cap (0 = unlimited). This protects operational costs and is enforced server-side for every account.</Text>
            <Text style={styles.meta}>Current effective cap: {cap?.unlimited ? "unlimited" : cap?.daily_ai_limit} · source: {cap?.source}</Text>
            <View style={styles.row}>
              <TextInput style={styles.input} value={input} onChangeText={setInput} keyboardType="number-pad" testID="admin-cap-input" />
              <Btn label={busy ? "Saving…" : "Save cap"} variant="soft" icon="save" onPress={save} testID="admin-cap-save" style={{ flex: 1 }} />
            </View>
            <Btn label="Close" variant="ghost" icon="x" onPress={() => router.back()} />
          </Card>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  body: { fontFamily: F.body, fontSize: 14, color: C.onSurface, lineHeight: 20 },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  row: { flexDirection: "row", gap: S.sm, alignItems: "center" },
  input: { width: 90, backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.borderStrong, padding: S.md, fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface, textAlign: "center" },
});
