import { useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F, HERO } from "@/src/theme";
import { api } from "@/src/api";
import { Card, SectionTitle, Loading, Empty, Badge } from "@/src/components/ui";

const RISK_TONE: any = { error: "error", warning: "warning", info: "info" };
const ICON: any = { class: "book-open", lab: "activity", exam: "edit-3", meeting: "users", study: "book", personal: "star", assignment: "file-text" };

export default function Today() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [tasks, setTasks] = useState<any[]>([]);
  const [recent, setRecent] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState<any[]>([]);
  const [showDone, setShowDone] = useState(false);

  const load = useCallback(async () => {
    try {
      const tz = -new Date().getTimezoneOffset();
      const [b, t, m] = await Promise.all([api.get(`/briefing?tz_offset_min=${tz}`), api.get("/tasks?status=open"), api.get("/timeline?kind=all")]);
      setData(b); setTasks(t); setRecent(m.slice(0, 5));
      if (showDone) setDone(await api.get("/tasks?status=done"));
    } catch (e) {} finally { setLoading(false); setRefreshing(false); }
  }, [showDone]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openItem = (type: "task" | "event", item: any) =>
    router.push({ pathname: "/item-detail", params: { type, data: JSON.stringify(item) } });

  const toggleDone = async () => {
    if (showDone) { setShowDone(false); return; }
    try { setDone(await api.get("/tasks?status=done")); setShowDone(true); } catch (e) {}
  };

  const toggle = async (id: string) => {
    setTasks((p) => p.filter((x) => x.id !== id));
    await api.patch(`/tasks/${id}`, { status: "done" });
    load();
  };

  const fmtDue = (s?: string) => {
    if (!s) return "No date";
    const d = new Date(s);
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  };

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={C.brand} />}
      >
        <View style={styles.hero}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(24,28,26,0.25)", "rgba(24,28,26,0.9)"]} style={StyleSheet.absoluteFill} />
          <View style={[styles.heroContent, { paddingTop: insets.top + S.lg }]}>
            <View style={styles.heroTopRow}>
              <View style={styles.heroActions}>
                <IconBtn icon="search" onPress={() => router.push("/search")} testID="open-search" />
                <IconBtn icon="inbox" onPress={() => router.push("/inbox")} testID="open-inbox" />
                <IconBtn icon="file-text" onPress={() => router.push("/notes")} testID="open-notes" />
              </View>
            </View>
            <Text style={styles.greeting} testID="briefing-greeting">{data?.greeting || "Welcome"}</Text>
            <Text style={styles.date}>{data?.date || ""}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <Pressable style={styles.prompt} onPress={() => router.push("/quick-capture")} testID="ai-prompt">
            <View style={styles.promptIcon}><Feather name="zap" size={18} color={C.onBrand} /></View>
            <Text style={styles.promptTxt}>What can I help you remember today?</Text>
            <Feather name="mic" size={18} color={C.brand} />
          </Pressable>
          {loading ? <Loading label="Preparing your briefing..." /> : (
            <>
              <View style={styles.stats}>
                <Stat label="Classes" value={data?.stats?.classes ?? 0} />
                <Stat label="Deadlines" value={data?.stats?.deadlines ?? 0} />
                <Stat label="Tasks" value={data?.stats?.open_tasks ?? 0} />
                <Stat label="Review" value={data?.stats?.review ?? 0} />
              </View>

              {data?.stats?.review ? (
                <Pressable onPress={() => router.push("/inbox")} testID="inbox-summary" style={{ marginTop: S.lg }}>
                  <Card style={styles.rowCard}>
                    <View style={styles.iconChip}><Feather name="inbox" size={16} color={C.onBrand3} /></View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>AI Inbox</Text>
                      <Text style={styles.itemSub}>{data.stats.review} suggestion{data.stats.review > 1 ? "s" : ""} waiting for review</Text>
                    </View>
                    <Feather name="chevron-right" size={18} color={C.onSurface3} />
                  </Card>
                </Pressable>
              ) : null}

              {data?.risks?.length ? (
                <View style={{ marginTop: S.xl }}>
                  <SectionTitle>What needs attention</SectionTitle>
                  <Card testID="risk-card" style={{ gap: S.md }}>
                    {data.risks.map((r: any, i: number) => (
                      <View key={i} style={styles.riskRow}>
                        <Feather name="alert-triangle" size={16} color={r.level === "error" ? C.error : r.level === "warning" ? C.warning : C.brand} />
                        <Text style={styles.riskTxt}>{r.text}</Text>
                      </View>
                    ))}
                  </Card>
                </View>
              ) : null}

              {data?.due_today?.length ? (
                <View style={{ marginTop: S.xl }}>
                  <SectionTitle>Due today</SectionTitle>
                  {data.due_today.map((t: any) => (
                    <Card key={t.id} style={styles.rowCard} testID={`duetoday-${t.id}`}>
                      <Pressable onPress={() => toggle(t.id)} testID={`duetoday-toggle-${t.id}`} style={styles.checkbox} hitSlop={10} />
                      <Pressable style={{ flex: 1 }} onPress={() => openItem("task", t)} testID={`duetoday-open-${t.id}`}>
                        <Text style={styles.itemTitle}>{t.title}</Text>
                        <Text style={styles.itemSub}>{[t.category, t.course].filter(Boolean).join(" · ") || "Due by end of day"}</Text>
                      </Pressable>
                      {t.priority === "high" ? <Badge label="High" tone="error" /> : null}
                      <Feather name="chevron-right" size={18} color={C.onSurface3} />
                    </Card>
                  ))}
                </View>
              ) : null}

              <View style={{ marginTop: S.xl }}>
                <SectionTitle>Today’s schedule</SectionTitle>
                {data?.today_classes?.length ? data.today_classes.map((e: any) => (
                  e.external ? (
                    <Card key={e.id} style={styles.rowCard} testID={`ext-${e.id}`}>
                      <View style={styles.iconChip}><Feather name="calendar" size={16} color={C.onBrand3} /></View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{e.title}</Text>
                        <Text style={styles.itemSub}>{[e.location, "from your calendar"].filter(Boolean).join(" · ")}</Text>
                      </View>
                      <Badge label="External" tone="info" />
                    </Card>
                  ) : (
                  <Pressable key={e.id} onPress={() => openItem("event", e)} testID={`class-${e.id}`}>
                    <Card style={styles.rowCard}>
                      <View style={styles.iconChip}><Feather name={ICON[e.event_type] || "calendar"} size={16} color={C.onBrand3} /></View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{e.title}</Text>
                        <Text style={styles.itemSub}>{[e.event_type, e.location, e.course].filter(Boolean).join(" · ") || "—"}</Text>
                      </View>
                      <Feather name="chevron-right" size={18} color={C.onSurface3} />
                    </Card>
                  </Pressable>
                  )
                )) : data?.due_today?.length ? (
                  <Empty icon="clock" title="No timed events today." sub="Your due-today tasks are listed above." />
                ) : <Empty icon="sun" title="Your schedule is clear today." sub="Import your class schedule to see it here." />}
              </View>

              <View style={{ marginTop: S.xl }}>
                <SectionTitle>Upcoming deadlines</SectionTitle>
                {data?.deadlines?.length ? data.deadlines.map((t: any) => (
                  <Pressable key={t.id} onPress={() => openItem("task", t)} testID={`deadline-${t.id}`}>
                    <Card style={styles.rowCard}>
                      <Feather name="flag" size={16} color={C.warning} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>{t.title}</Text>
                        <Text style={styles.itemSub}>{fmtDue(t.due)}{t.course ? ` · ${t.course}` : ""}</Text>
                      </View>
                      <Feather name="chevron-right" size={18} color={C.onSurface3} />
                    </Card>
                  </Pressable>
                )) : <Empty icon="check-circle" title="No deadlines this week." />}
              </View>

              <View style={{ marginTop: S.xl }}>
                <View style={styles.memHead}>
                  <SectionTitle>Open tasks</SectionTitle>
                  <Pressable onPress={toggleDone} testID="toggle-completed"><Text style={styles.seeAll}>{showDone ? "Hide completed" : "Show completed"}</Text></Pressable>
                </View>
                {(() => {
                  const shownIds = new Set<string>([
                    ...(data?.due_today || []).map((t: any) => t.id),
                    ...(data?.deadlines || []).map((t: any) => t.id),
                    ...(data?.overdue || []).map((t: any) => t.id),
                  ]);
                  const openTasks = tasks.filter((t: any) => !shownIds.has(t.id));
                  return openTasks.length ? openTasks.map((t: any) => (
                  <Card key={t.id} style={styles.rowCard} testID={`task-${t.id}`}>
                    <Pressable onPress={() => toggle(t.id)} testID={`task-toggle-${t.id}`} style={styles.checkbox} hitSlop={10} />
                    <Pressable style={{ flex: 1 }} onPress={() => openItem("task", t)} testID={`task-open-${t.id}`}>
                      <Text style={styles.itemTitle}>{t.title}</Text>
                      <Text style={styles.itemSub}>{[t.category, t.due ? fmtDue(t.due) : null, t.course].filter(Boolean).join(" · ")}</Text>
                    </Pressable>
                    {t.priority === "high" ? <Badge label="High" tone="error" /> : null}
                    <Feather name="chevron-right" size={18} color={C.onSurface3} />
                  </Card>
                )) : <Empty icon="coffee" title="No other open tasks." sub="Tap + to capture something." />;
                })()}

                {showDone ? (done.length ? done.map((t: any) => (
                  <Card key={t.id} style={styles.rowCard} testID={`done-${t.id}`}>
                    <View style={styles.checkboxDone}><Feather name="check" size={13} color={C.onBrand} /></View>
                    <Pressable style={{ flex: 1 }} onPress={() => openItem("task", t)} testID={`done-open-${t.id}`}>
                      <Text style={[styles.itemTitle, styles.strike]}>{t.title}</Text>
                      <Text style={styles.itemSub}>Completed · tap to reopen or edit</Text>
                    </Pressable>
                    <Feather name="chevron-right" size={18} color={C.onSurface3} />
                  </Card>
                )) : <Text style={styles.emptyDone}>No completed tasks yet.</Text>) : null}
              </View>

              <View style={{ marginTop: S.xl }}>
                <View style={styles.memHead}>
                  <SectionTitle>Recent memory</SectionTitle>
                  <Pressable onPress={() => router.push("/(tabs)/timeline")} testID="see-memory"><Text style={styles.seeAll}>See all</Text></Pressable>
                </View>
                {recent.length ? recent.map((m: any) => (
                  <Card key={m.id} style={styles.rowCard}>
                    <Feather name="database" size={16} color={C.brand} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle} numberOfLines={1}>{m.title}</Text>
                      {m.subtitle ? <Text style={styles.itemSub}>{m.subtitle}</Text> : null}
                    </View>
                  </Card>
                )) : <Empty icon="database" title="Nothing captured yet." />}
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat} testID={`stat-${label.toLowerCase()}`}>
      <Text style={styles.statVal}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}
function IconBtn({ icon, onPress, testID }: any) {
  return (
    <Pressable onPress={onPress} testID={testID} style={styles.iconBtn} hitSlop={8}>
      <Feather name={icon} size={18} color={C.onInverse} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  hero: { height: 220, justifyContent: "flex-end" },
  heroContent: { padding: S.xl, paddingBottom: S.xl },
  heroTopRow: { flexDirection: "row", justifyContent: "flex-end", marginBottom: S.lg },
  heroActions: { flexDirection: "row", gap: S.sm },
  iconBtn: { width: 40, height: 40, borderRadius: R.pill, backgroundColor: "rgba(255,255,255,0.18)", alignItems: "center", justifyContent: "center" },
  greeting: { fontFamily: F.display, fontSize: 30, color: "#fff" },
  date: { fontFamily: F.bodyMed, fontSize: 14, color: "rgba(255,255,255,0.85)", marginTop: 2 },
  body: { padding: S.lg },
  stats: { flexDirection: "row", gap: S.sm },
  stat: { flex: 1, backgroundColor: C.surface2, borderRadius: R.md, padding: S.md, alignItems: "center", borderWidth: 1, borderColor: C.border },
  statVal: { fontFamily: F.display, fontSize: 24, color: C.brand },
  statLabel: { fontFamily: F.body, fontSize: 11, color: C.onSurface3, marginTop: 2 },
  rowCard: { flexDirection: "row", alignItems: "center", gap: S.md, marginBottom: S.sm, padding: S.md },
  iconChip: { width: 34, height: 34, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  itemTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  itemSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  riskRow: { flexDirection: "row", alignItems: "center", gap: S.sm },
  riskTxt: { fontFamily: F.body, fontSize: 13, color: C.onSurface, flex: 1 },
  checkbox: { width: 22, height: 22, borderRadius: 6, borderWidth: 2, borderColor: C.borderStrong },
  checkboxDone: { width: 22, height: 22, borderRadius: 6, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  strike: { textDecorationLine: "line-through", color: C.onSurface3 },
  emptyDone: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, paddingVertical: S.sm, paddingLeft: S.xs },
  prompt: { flexDirection: "row", alignItems: "center", gap: S.md, backgroundColor: C.surface2, borderRadius: R.lg, borderWidth: 1, borderColor: C.borderStrong, padding: S.lg },
  promptIcon: { width: 34, height: 34, borderRadius: R.pill, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  promptTxt: { flex: 1, fontFamily: F.bodyMed, fontSize: 15, color: C.onSurface2 },
  memHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  seeAll: { fontFamily: F.bodyMed, fontSize: 13, color: C.brand },
});
