import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import * as billing from "@/src/services/billing";
import { useAuth } from "@/src/auth";

const HEADLINE = "Stay ahead of deadlines without doing all the organizing yourself.";
const VALUE = "Record lectures, capture commitments, organize academic information and receive personalized guidance with higher monthly AI allowances.";

const PRIVACY_URL = "https://studentassistant.decisivlabs.com/privacy";
const TERMS_URL = "https://studentassistant.decisivlabs.com/terms";

const PREMIUM_POINTS = [
  { icon: "mic", t: "240 audio minutes / 30-day cycle for lectures + active listening" },
  { icon: "file-text", t: "25 AI imports (syllabi, screenshots, schedules) per month" },
  { icon: "search", t: "100 AI Memory questions across your courses" },
  { icon: "sunrise", t: "Personalized Daily Briefings & Weekly Reviews" },
  { icon: "check-circle", t: "Automated commitment & task extraction, smart prioritization" },
];

function planLabel(period?: string) {
  if (!period) return "";
  if (/P1M/i.test(period)) return "per month";
  if (/P1Y/i.test(period)) return "per year";
  return period;
}

export default function Paywall() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const params = useLocalSearchParams<{ feature?: string; reason?: string }>();
  const [loading, setLoading] = useState(true);
  const [cfg, setCfg] = useState<any>(null);
  const [products, setProducts] = useState<billing.PlayProduct[]>([]);
  const [selected, setSelected] = useState<"annual" | "monthly">("annual");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<billing.BillingStatus | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      billing.logEvent("paywall_impression", undefined, String(params.feature || params.reason || "open"));
      try {
        const [c, s] = await Promise.all([billing.fetchPlanConfig(), billing.fetchStatus()]);
        setCfg(c); setStatus(s);
        if (billing.canPurchase()) setProducts(await billing.loadProducts(c.product_id));
      } catch { /* keep UI usable */ }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const priceFor = (basePlanId: string) => products.find((p) => p.basePlanId === basePlanId);

  const onSubscribe = async () => {
    setMsg("");
    if (!billing.BILLING_ENABLED || !billing.canPurchase()) {
      setMsg("Subscriptions aren't available in this build yet.");
      return;
    }
    const basePlan = selected === "annual" ? cfg.annual_base_plan_id : cfg.monthly_base_plan_id;
    setBusy(true);
    billing.logEvent("purchase_start", selected);
    try {
      const r: any = await billing.purchase(cfg.product_id, basePlan, billing.obfuscatedAccountId(user?.id));
      if (r?.pending) { setMsg("Your purchase is pending. We'll unlock Premium once it clears."); return; }
      billing.logEvent("purchase_complete", selected);
      router.back();
    } catch (e: any) {
      if (e?.code === "cancelled") { setMsg(""); return; } // cancellation is not an error
      billing.logEvent("purchase_fail", selected, String(e?.code || "error"));
      setMsg("We couldn't complete that just now. Please try again in a moment.");
    } finally { setBusy(false); }
  };

  const onRestore = async () => {
    setMsg(""); setBusy(true);
    billing.logEvent("restore_attempt");
    try { await billing.restore(); router.back(); }
    catch (e: any) { setMsg(String(e?.message || "Nothing to restore.")); }
    finally { setBusy(false); }
  };

  const onManage = () => {
    const pkg = cfg?.package_name || "com.decisivlabs.studentassistant";
    const sku = cfg?.product_id || "student_assistant_premium";
    Linking.openURL(`https://play.google.com/store/account/subscriptions?sku=${sku}&package=${pkg}`);
  };

  if (loading) {
    return <View style={[styles.root, { justifyContent: "center" }]}><ActivityIndicator size="large" color={C.brand} /></View>;
  }

  const annual = priceFor(cfg?.annual_base_plan_id);
  const monthly = priceFor(cfg?.monthly_base_plan_id);

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingTop: insets.top + S.md, paddingBottom: insets.bottom + S.xxl }}>
        <Pressable testID="paywall-close" onPress={() => router.back()} style={styles.close} hitSlop={12}>
          <Feather name="x" size={24} color={C.onSurface2} />
        </Pressable>

        <View style={styles.badge}><Feather name="zap" size={14} color={C.brand} /><Text style={styles.badgeTxt}>GotU Premium</Text></View>
        <Text style={styles.headline}>{HEADLINE}</Text>
        <Text style={styles.value}>{VALUE}</Text>

        <View style={styles.points}>
          {PREMIUM_POINTS.map((p) => (
            <View key={p.t} style={styles.point}>
              <Feather name={p.icon as any} size={18} color={C.brand} />
              <Text style={styles.pointTxt}>{p.t}</Text>
            </View>
          ))}
        </View>

        {/* Plan options — annual first but monthly always visible. */}
        <PlanCard label="Annual" selected={selected === "annual"} onPress={() => setSelected("annual")}
          price={annual?.localizedPrice} period={planLabel(annual?.billingPeriod) || "per year"}
          note="Best value" testID="plan-annual" />
        <PlanCard label="Monthly" selected={selected === "monthly"} onPress={() => setSelected("monthly")}
          price={monthly?.localizedPrice} period={planLabel(monthly?.billingPeriod) || "per month"}
          testID="plan-monthly" />

        {!billing.BILLING_ENABLED && (
          <Text style={styles.soon} testID="paywall-testbuild-notice">
            Premium purchasing is not available in this test build. Your Free plan and one-time
            Starter Pack keep working now.
          </Text>
        )}
        {!!msg && <Text style={styles.err}>{msg}</Text>}

        <Pressable testID="paywall-subscribe" disabled={busy} onPress={onSubscribe}
          style={({ pressed }) => [styles.cta, (busy || !billing.BILLING_ENABLED) && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
          {busy ? <ActivityIndicator color={C.onBrand} /> : <Text style={styles.ctaTxt}>Continue</Text>}
        </Pressable>

        <Text style={styles.fine}>
          Subscriptions renew automatically unless cancelled at least 24 hours before the end of the
          current period. Manage or cancel anytime in Google Play. Prices are shown by Google Play in
          your local currency.
        </Text>

        <View style={styles.linksRow}>
          <Pressable testID="paywall-restore" onPress={onRestore}><Text style={styles.link}>Restore Purchases</Text></Pressable>
          <Text style={styles.dot}>·</Text>
          <Pressable testID="paywall-manage" onPress={onManage}><Text style={styles.link}>Manage Subscription</Text></Pressable>
        </View>
        <View style={styles.linksRow}>
          <Pressable onPress={() => Linking.openURL(PRIVACY_URL)}><Text style={styles.linkMuted}>Privacy Policy</Text></Pressable>
          <Text style={styles.dot}>·</Text>
          <Pressable onPress={() => Linking.openURL(TERMS_URL)}><Text style={styles.linkMuted}>Terms of Service</Text></Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

function PlanCard({ label, price, period, note, selected, onPress, testID }: any) {
  return (
    <Pressable testID={testID} onPress={onPress}
      style={[styles.plan, selected && styles.planSel]}>
      <View style={styles.radio}>{selected ? <View style={styles.radioDot} /> : null}</View>
      <View style={{ flex: 1 }}>
        <Text style={styles.planLabel}>{label}{note ? <Text style={styles.planNote}>  {note}</Text> : null}</Text>
        <Text style={styles.planPrice}>{price ? `${price} ${period}` : "Price shown at checkout"}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  close: { alignSelf: "flex-end", padding: S.xs },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start",
    backgroundColor: C.brand3, paddingHorizontal: S.sm, paddingVertical: 5, borderRadius: R.pill, marginTop: S.xs },
  badgeTxt: { fontFamily: F.bodyBold, fontSize: 12, color: C.brand },
  headline: { fontFamily: F.display, fontSize: 26, lineHeight: 32, color: C.onSurface, marginTop: S.md },
  value: { fontFamily: F.body, fontSize: 15, lineHeight: 22, color: C.onSurface2, marginTop: S.sm },
  points: { marginTop: S.lg, gap: S.sm },
  point: { flexDirection: "row", alignItems: "center", gap: S.sm },
  pointTxt: { flex: 1, fontFamily: F.body, fontSize: 14, color: C.onSurface },
  plan: { flexDirection: "row", alignItems: "center", gap: S.sm, padding: S.md, borderRadius: R.lg,
    borderWidth: 1.5, borderColor: C.border, marginTop: S.md },
  planSel: { borderColor: C.brand, backgroundColor: C.brand3 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: C.brand, alignItems: "center", justifyContent: "center" },
  radioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: C.brand },
  planLabel: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface },
  planNote: { fontFamily: F.bodyBold, fontSize: 12, color: C.brand },
  planPrice: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: 2 },
  soon: { fontFamily: F.body, fontSize: 13, color: C.onSurface2, marginTop: S.md, textAlign: "center" },
  err: { fontFamily: F.body, fontSize: 13, color: C.error, marginTop: S.sm, textAlign: "center" },
  cta: { backgroundColor: C.brand, borderRadius: R.pill, paddingVertical: 16, alignItems: "center", marginTop: S.lg },
  ctaTxt: { fontFamily: F.bodyBold, fontSize: 16, color: C.onBrand },
  fine: { fontFamily: F.body, fontSize: 11, lineHeight: 16, color: C.onSurface2, marginTop: S.md, textAlign: "center" },
  linksRow: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: S.sm, marginTop: S.md },
  link: { fontFamily: F.bodyBold, fontSize: 13, color: C.brand },
  linkMuted: { fontFamily: F.body, fontSize: 12, color: C.onSurface2 },
  dot: { color: C.onSurface2 },
});
