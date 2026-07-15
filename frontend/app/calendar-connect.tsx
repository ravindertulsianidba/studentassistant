import { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Btn, Badge } from "@/src/components/ui";
import { listCalendars, getConnection, connect, disconnect, fullSync, DeviceCalendar } from "@/src/services/calendar";

const STATUS_TONE: any = { connected: "success", read_only: "info", syncing: "info", sync_failed: "error", permission_revoked: "error", disconnected: "info" };
const STATUS_LABEL: any = { connected: "Connected", read_only: "Read only", syncing: "Syncing…", sync_failed: "Sync failed", permission_revoked: "Permission revoked", disconnected: "Not connected" };

export default function CalendarConnect() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const isDevice = Platform.OS === "ios" || Platform.OS === "android";
  const [conn, setConn] = useState<any>(null);
  const [cals, setCals] = useState<DeviceCalendar[]>([]);
  const [reviews, setReviews] = useState<any[]>([]);
  const [access, setAccess] = useState<"read_write" | "read_only">("read_write");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([getConnection(), api.get("/calendar/review").catch(() => [])]);
      setConn(c); setReviews(r || []);
      if (isDevice) setCals(await listCalendars());
    } finally { setLoading(false); }
  }, [isDevice]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const doConnect = async (cal: DeviceCalendar) => {
    setBusy(true);
    try { await connect(cal, access); await load(); } finally { setBusy(false); }
  };
  const doSync = async () => { setBusy(true); try { await fullSync(); await load(); } finally { setBusy(false); } };
  const doDisconnect = async () => { setBusy(true); try { await disconnect(); await load(); } finally { setBusy(false); } };
  const resolve = async (id: string, approve: boolean) => {
    setReviews((p) => p.filter((x) => x.id !== id));
    try { await api.post(`/calendar/review/${id}`, { approve }); } catch {}
    load();
  };

  const status = conn?.connected ? conn.status : "disconnected";

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={10} testID="cal-back"><Feather name="x" size={22} color={C.onSurface} /></Pressable>
        <Text style={styles.hTitle}>Calendar</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: insets.bottom + S.xl }} showsVerticalScrollIndicator={false}>
        {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xl }} /> : (
          <>
            <Card style={styles.statusCard}>
              <View style={styles.statusRow}>
                <View style={styles.calIcon}><Feather name="calendar" size={18} color={C.brand} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemTitle}>{conn?.connected ? (conn.calendar_title || "Calendar") : "No calendar connected"}</Text>
                  <Text style={styles.itemSub}>{conn?.connected ? [conn.account_name, conn.provider].filter(Boolean).join(" · ") : "Connect the calendar you already use"}</Text>
                </View>
                <Badge label={STATUS_LABEL[status] || status} tone={STATUS_TONE[status] || "default"} />
              </View>
              {conn?.failure_reason && status === "sync_failed" ? (
                <Text style={styles.failTxt}>{conn.failure_reason}</Text>
              ) : null}
              {status === "permission_revoked" ? (
                <Pressable onPress={() => Linking.openSettings()} style={styles.settingsLink}>
                  <Text style={styles.settingsTxt}>Open Settings to re-grant calendar access</Text>
                </Pressable>
              ) : null}
              {conn?.connected ? (
                <View style={styles.actionRow}>
                  <Btn label="Sync now" variant="soft" icon="refresh-cw" onPress={doSync} testID="cal-sync-now" />
                  <Btn label="Disconnect" variant="ghost" icon="log-out" onPress={doDisconnect} testID="cal-disconnect" />
                </View>
              ) : null}
              {conn?.last_sync ? <Text style={styles.metaTxt}>Last synced {new Date(conn.last_sync).toLocaleString()}</Text> : null}
            </Card>

            {reviews.length ? (
              <View style={{ marginTop: S.xl }}>
                <SectionTitle>Confirm calendar changes</SectionTitle>
                {reviews.map((r) => (
                  <Card key={r.id} style={{ gap: S.sm }} testID={`calrev-${r.id}`}>
                    <Text style={styles.itemTitle}>{r.kind === "external_delete" ? "Event deleted externally" : "Event changed externally"}</Text>
                    <Text style={styles.itemSub}>{r.detail}</Text>
                    <View style={styles.actionRow}>
                      <Btn label={r.kind === "external_delete" ? "Remove it" : "Apply change"} variant="soft" icon="check" onPress={() => resolve(r.id, true)} testID={`calrev-approve-${r.id}`} />
                      <Btn label="Keep mine" variant="ghost" icon="x" onPress={() => resolve(r.id, false)} testID={`calrev-dismiss-${r.id}`} />
                    </View>
                  </Card>
                ))}
              </View>
            ) : null}

            <View style={{ marginTop: S.xl }}>
              <SectionTitle>Access</SectionTitle>
              <View style={styles.segment}>
                {(["read_write", "read_only"] as const).map((m) => (
                  <Pressable key={m} onPress={() => setAccess(m)} testID={`access-${m}`}
                    style={[styles.seg, access === m && styles.segActive]}>
                    <Text style={[styles.segTxt, access === m && styles.segTxtActive]}>{m === "read_write" ? "Read & write" : "Read only"}</Text>
                  </Pressable>
                ))}
              </View>
              <Text style={styles.hint}>{access === "read_write" ? "Approved events are added to your calendar; external events are read for awareness." : "External events are read for schedule awareness. Student Assistant won't write to your calendar."}</Text>
            </View>

            <View style={{ marginTop: S.xl }}>
              <SectionTitle>Choose a calendar</SectionTitle>
              {!isDevice ? (
                <Card><Text style={styles.itemSub}>Connecting to your device calendar (Google, Microsoft 365, Outlook, Exchange, and others synced to Android/iOS) is available in the installed app build — not in the web preview.</Text></Card>
              ) : busy ? <ActivityIndicator color={C.brand} /> : cals.length ? cals.map((cal) => (
                <Pressable key={cal.id} onPress={() => doConnect(cal)} testID={`cal-${cal.id}`} disabled={busy}>
                  <Card style={styles.rowCard}>
                    <View style={styles.calIcon}><Feather name="calendar" size={16} color={C.brand} /></View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>{cal.title}</Text>
                      <Text style={styles.itemSub}>{[cal.account, cal.provider].filter(Boolean).join(" · ")}{cal.allowsModifications ? "" : " · read-only"}</Text>
                    </View>
                    {conn?.calendar_id === cal.id ? <Feather name="check-circle" size={18} color={C.success} /> : <Feather name="chevron-right" size={18} color={C.onSurface3} />}
                  </Card>
                </Pressable>
              )) : <Card><Text style={styles.itemSub}>No device calendars found. Add an account (Google / Microsoft 365 / Outlook / Exchange) in your device Settings, then reopen this screen.</Text></Card>}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  hTitle: { fontFamily: F.display, fontSize: 18, color: C.onSurface },
  statusCard: { gap: S.md },
  statusRow: { flexDirection: "row", alignItems: "center", gap: S.md },
  calIcon: { width: 36, height: 36, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  itemTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  itemSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2, lineHeight: 17 },
  failTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.error },
  settingsLink: { paddingVertical: S.xs },
  settingsTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.brand },
  actionRow: { flexDirection: "row", gap: S.sm },
  metaTxt: { fontFamily: F.body, fontSize: 11, color: C.onSurface3 },
  rowCard: { flexDirection: "row", alignItems: "center", gap: S.md, marginBottom: S.sm, padding: S.md },
  segment: { flexDirection: "row", backgroundColor: C.surface3, borderRadius: R.md, padding: 4 },
  seg: { flex: 1, height: 40, alignItems: "center", justifyContent: "center", borderRadius: R.sm },
  segActive: { backgroundColor: C.surface2 },
  segTxt: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface3 },
  segTxtActive: { fontFamily: F.bodyBold, color: C.onSurface },
  hint: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: S.sm, lineHeight: 17 },
});
