import { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Linking, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { useAuth } from "@/src/auth";
import { ensurePermission as notifPerm, syncAndSchedule } from "@/src/services/notifications";
import { ensurePermission as calPerm } from "@/src/services/calendar";

type PermState = "idle" | "granted" | "denied" | "blocked" | "unavailable";

const SLIDES = [
  { icon: "zap", title: "Capture anything, instantly", body: "Type, speak, or snap a photo of a syllabus, email, or whiteboard. Student Assistant turns it into tasks, classes, and deadlines — automatically." },
  { icon: "layers", title: "It remembers so you don't", body: "Everything you capture is organized by course and searchable forever. No more digging through screenshots and group chats." },
  { icon: "bell", title: "Never miss what matters", body: "Get a gentle nudge before every class, deadline, and commitment — and a daily brief of what needs your attention." },
];

function PermCard({ icon, title, body, state, onEnable, onSettings, cta }: any) {
  return (
    <View style={styles.card}>
      <View style={styles.cardIcon}><Feather name={icon} size={20} color={C.brand} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardBody}>{body}</Text>
      </View>
      {state === "granted" ? (
        <View style={styles.doneBadge}><Feather name="check" size={16} color={C.onBrand} /></View>
      ) : state === "blocked" ? (
        <Pressable onPress={onSettings} style={styles.enableBtn}><Text style={styles.enableTxt}>Settings</Text></Pressable>
      ) : state === "unavailable" ? (
        <Text style={styles.naTxt}>In app</Text>
      ) : (
        <Pressable onPress={onEnable} style={styles.enableBtn}><Text style={styles.enableTxt}>{cta}</Text></Pressable>
      )}
    </View>
  );
}

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { completeOnboarding } = useAuth();
  const [step, setStep] = useState(0);
  const [notif, setNotif] = useState<PermState>("idle");
  const [cal, setCal] = useState<PermState>("idle");

  const isSetup = step === SLIDES.length;
  const total = SLIDES.length + 1;

  const finish = async () => {
    await completeOnboarding();
    router.replace("/(tabs)");
  };

  const enableNotif = async () => {
    try {
      const r = await notifPerm();
      if (r.granted) { setNotif("granted"); syncAndSchedule().catch(() => {}); }
      else if (!r.canAskAgain) setNotif(Platform.OS === "web" ? "unavailable" : "blocked");
      else setNotif("denied");
    } catch { setNotif("unavailable"); }
  };
  const enableCal = async () => {
    try {
      const r = await calPerm();
      if (r.granted) setCal("granted");
      else if (!r.canAskAgain) setCal(Platform.OS === "web" ? "unavailable" : "blocked");
      else setCal("denied");
    } catch { setCal("unavailable"); }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + S.md, paddingBottom: insets.bottom + S.lg }]}>
      <View style={styles.top}>
        <View style={styles.dots}>
          {Array.from({ length: total }).map((_, i) => (
            <View key={i} style={[styles.dot, i === step && styles.dotActive]} />
          ))}
        </View>
        {!isSetup && (
          <Pressable testID="onboarding-skip" onPress={finish} hitSlop={10}><Text style={styles.skip}>Skip</Text></Pressable>
        )}
      </View>

      {!isSetup ? (
        <View style={styles.slide}>
          <View style={styles.heroIcon}><Feather name={SLIDES[step].icon as any} size={40} color={C.brand} /></View>
          <Text style={styles.title}>{SLIDES[step].title}</Text>
          <Text style={styles.body}>{SLIDES[step].body}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: S.lg }} showsVerticalScrollIndicator={false}>
          <Text style={styles.setupTitle}>Recommended setup</Text>
          <Text style={styles.setupSub}>Turn on what's useful for you. You're always in control — enable each only if you want it.</Text>

          <PermCard icon="bell" title="Reminders & alerts"
            body="Get notified before classes, deadlines, and things you promised to do."
            state={notif} cta="Enable" onEnable={enableNotif} onSettings={() => Linking.openSettings()} />
          {notif === "denied" && <Text style={styles.retryHint}>No problem — you can enable notifications later in Settings.</Text>}

          <PermCard icon="calendar" title="Calendar (optional)"
            body="Add your classes and deadlines to your device calendar automatically."
            state={cal} cta="Connect" onEnable={enableCal} onSettings={() => Linking.openSettings()} />
          {cal === "denied" && <Text style={styles.retryHint}>You can connect your calendar anytime from Settings.</Text>}

          <View style={styles.infoBox}>
            <Text style={styles.infoHead}>Asked only when you need them</Text>
            <View style={styles.infoRow}><Feather name="mic" size={16} color={C.onSurface2} /><Text style={styles.infoTxt}>Microphone — the first time you record a lecture.</Text></View>
            <View style={styles.infoRow}><Feather name="camera" size={16} color={C.onSurface2} /><Text style={styles.infoTxt}>Camera — the first time you scan a document.</Text></View>
            <View style={styles.infoRow}><Feather name="image" size={16} color={C.onSurface2} /><Text style={styles.infoTxt}>Photos & files use your system picker — no library access needed.</Text></View>
          </View>
        </ScrollView>
      )}

      <View style={styles.footer}>
        {isSetup ? (
          <Pressable testID="onboarding-done" onPress={finish} style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}>
            <Text style={styles.primaryTxt}>Get started</Text>
          </Pressable>
        ) : (
          <Pressable testID="onboarding-next" onPress={() => setStep((s) => s + 1)} style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}>
            <Text style={styles.primaryTxt}>{step === SLIDES.length - 1 ? "Set up my assistant" : "Next"}</Text>
          </Pressable>
        )}
        {isSetup && (
          <Pressable testID="onboarding-maybe" onPress={finish} style={{ alignItems: "center", paddingVertical: S.sm }}>
            <Text style={styles.maybe}>Maybe later</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface, paddingHorizontal: S.xl },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", height: 32 },
  dots: { flexDirection: "row", gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: C.border },
  dotActive: { backgroundColor: C.brand, width: 20 },
  skip: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface3 },
  slide: { flex: 1, alignItems: "center", justifyContent: "center", gap: S.lg, paddingHorizontal: S.md },
  heroIcon: { width: 96, height: 96, borderRadius: 48, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: F.display, fontSize: 26, color: C.onSurface, textAlign: "center" },
  body: { fontFamily: F.body, fontSize: 16, color: C.onSurface2, textAlign: "center", lineHeight: 24 },
  setupTitle: { fontFamily: F.display, fontSize: 24, color: C.onSurface, marginTop: S.lg },
  setupSub: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, lineHeight: 21, marginTop: S.xs, marginBottom: S.lg },
  card: { flexDirection: "row", alignItems: "center", gap: S.md, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: R.md, padding: S.md, marginBottom: S.sm },
  cardIcon: { width: 40, height: 40, borderRadius: R.sm, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  cardBody: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, lineHeight: 18, marginTop: 2 },
  enableBtn: { backgroundColor: C.brand, borderRadius: R.pill, paddingHorizontal: S.md, height: 36, alignItems: "center", justifyContent: "center" },
  enableTxt: { fontFamily: F.bodyBold, fontSize: 13, color: C.onBrand },
  doneBadge: { width: 32, height: 32, borderRadius: 16, backgroundColor: C.brand, alignItems: "center", justifyContent: "center" },
  naTxt: { fontFamily: F.bodyMed, fontSize: 12, color: C.onSurface3 },
  retryHint: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginBottom: S.sm, marginLeft: S.xs },
  infoBox: { backgroundColor: C.surface3, borderRadius: R.md, padding: S.md, marginTop: S.md, gap: S.sm },
  infoHead: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface },
  infoRow: { flexDirection: "row", alignItems: "center", gap: S.sm },
  infoTxt: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, flex: 1, lineHeight: 18 },
  footer: { gap: S.xs },
  primary: { backgroundColor: C.brand, borderRadius: R.md, height: 54, alignItems: "center", justifyContent: "center" },
  primaryTxt: { fontFamily: F.bodyBold, fontSize: 16, color: C.onBrand },
  maybe: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface3 },
});
