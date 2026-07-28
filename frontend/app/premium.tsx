import { useCallback, useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking, AppState, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { Card, Btn, Badge } from "@/src/components/ui";
import { useAuth } from "@/src/auth";
import * as billing from "@/src/services/billing";

const PRIVACY_URL = "https://studentassistant.decisivlabs.com/privacy";
const TERMS_URL = "https://studentassistant.decisivlabs.com/terms";

const HEADLINE = "Stay ahead of deadlines without doing all the organizing yourself.";
const VALUE = "Higher monthly AI allowances for recording lectures, capturing commitments, organizing academic information and personalized guidance.";

// Labels for the authoritative allowance keys returned by /api/plan/config. Values ALWAYS come
// from the backend so the UI can never drift from what is actually enforced.
const PREMIUM_LABELS: Record<string, (n: number) => string> = {
  audio_minutes: (n) => `${n} audio minutes per 30-day period`,
  ai_import: (n) => `${n} AI imports (syllabi, screenshots, schedules) / month`,
  import_pages: (n) => `${n} imported pages / month`,
  memory_question: (n) => `${n} AI Memory questions / month`,
  briefing: (n) => `${n} personalized Daily Briefings / month`,
  weekly_review: (n) => `${n} AI Weekly Reviews / month`,
};

function planPeriod(period?: string) {
  if (!period) return "";
  if (/P1M/i.test(period)) return "per month";
  if (/P1Y/i.test(period)) return "per year";
  return period;
}

function fmtDate(iso?: string | null) {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }); }
  catch { return null; }
}

export default function Premium() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [cfg, setCfg] = useState<any>(null);
  const [status, setStatus] = useState<billing.BillingStatus | null>(null);
  const [products, setProducts] = useState<billing.PlayProduct[]>([]);
  const [selected, setSelected] = useState<"annual" | "monthly">("annual");
  const [msg, setMsg] = useState("");

  const refresh = useCallback(async (withProducts = false) => {
    try {
      const [c, s] = await Promise.all([billing.fetchPlanConfig(), billing.refreshEntitlement()]);
      setCfg(c); setStatus(s);
      if (withProducts && billing.canPurchase()) {
        try { setProducts(await billing.loadProducts(c.product_id)); } catch { /* keep UI usable */ }
      }
    } catch { /* keep UI usable */ }
  }, []);

  useEffect(() => {
    (async () => {
      billing.logEvent("upgrade_opened", undefined, "premium_screen");
      await refresh(true);
      setLoading(false);
    })();
  }, [refresh]);

  // Refresh account state when the screen regains focus...
  useFocusEffect(useCallback(() => { refresh(false); }, [refresh]));
  // ...and when the app returns to the foreground.
  const appState = useRef(AppState.currentState);
  useEffect(() => {
    const sub = AppState.addEventListener("change", (next) => {
      if (appState.current.match(/inactive|background/) && next === "active") refresh(false);
      appState.current = next;
    });
    return () => sub.remove();
  }, [refresh]);

  const isPremium = status?.plan === "premium";
  const priceFor = (id?: string) => products.find((p) => p.basePlanId === id);
  const annual = priceFor(cfg?.annual_base_plan_id);
  const monthly = priceFor(cfg?.monthly_base_plan_id);

  // Savings only when both localized prices exist AND share the same currency (reliable).
  let savings: string | null = null;
  if (annual?.localizedPrice && monthly?.localizedPrice && annual.currency && annual.currency === monthly.currency) {
    const num = (s?: string) => { const m = String(s || "").replace(/[^0-9.,]/g, "").replace(",", "."); const v = parseFloat(m); return isNaN(v) ? null : v; };
    const a = num(annual.localizedPrice); const m = num(monthly.localizedPrice);
    if (a && m && m > 0) { const pct = Math.round((1 - a / (m * 12)) * 100); if (pct > 0 && pct < 100) savings = `Save ~${pct}%`; }
  }

  const onSubscribe = async () => {
    setMsg("");
    if (!billing.BILLING_ENABLED || !billing.canPurchase()) {
      setMsg(unsupportedMessage()); return;
    }
    const basePlan = selected === "annual" ? cfg.annual_base_plan_id : cfg.monthly_base_plan_id;
    setBusy(true);
    billing.logEvent("purchase_start", selected);
    try {
      const r: any = await billing.purchase(cfg.product_id, basePlan, billing.obfuscatedAccountId(user?.id));
      if (r?.pending) { setMsg("Your purchase is pending. We'll unlock Premium once it clears."); await refresh(false); return; }
      billing.logEvent("purchase_complete", selected);
      await refresh(false);
      setMsg("");
    } catch (e: any) {
      // User cancellation is not an error.
      if (e?.code === "cancelled") { setMsg(""); }
      else { billing.logEvent("purchase_fail", selected, String(e?.code || "error")); setMsg(consumerError(String(e?.message || ""))); }
    } finally { setBusy(false); }
  };

  const onRestore = async () => {
    setMsg(""); setBusy(true);
    billing.logEvent("restore_attempt");
    try { await billing.restore(); await refresh(false); setMsg("Purchases restored."); }
    catch (e: any) { setMsg(consumerError(String(e?.message || ""))); }
    finally { setBusy(false); }
  };

  const onManage = () => {
    const pkg = cfg?.package_name || status?.product?.package_name || "com.decisivlabs.studentassistant";
    const sku = cfg?.product_id || status?.product?.product_id || "student_assistant_premium";
    Linking.openURL(`https://play.google.com/store/account/subscriptions?sku=${sku}&package=${pkg}`);
  };

  if (loading) {
    return <View style={[styles.root, { justifyContent: "center" }]}><ActivityIndicator size="large" color={C.brand} /></View>;
  }

  const canBuy = billing.BILLING_ENABLED && billing.canPurchase();
  const periodEnd = fmtDate(status?.current_period_end);

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ padding: S.lg, paddingTop: insets.top + S.md, paddingBottom: insets.bottom + S.xxl }} showsVerticalScrollIndicator={false}>
        <Pressable testID="premium-close" onPress={() => router.back()} style={styles.close} hitSlop={12}>
          <Feather name="x" size={24} color={C.onSurface2} />
        </Pressable>

        <View style={styles.badge}><Feather name="zap" size={14} color={C.brand} /><Text style={styles.badgeTxt}>GotU Premium</Text></View>

        {/* Current subscription state */}
        <Card testID="premium-state" style={{ gap: S.xs, marginTop: S.sm }}>
          <View style={styles.stateRow}>
            <Text style={styles.stateLabel}>Your plan</Text>
            <Badge label={isPremium ? "Premium" : "Free"} tone={isPremium ? "success" : "info"} />
          </View>
          {isPremium && periodEnd ? (
            <Text style={styles.meta} testID="premium-renewal">
              {status?.renews ? `Renews on ${periodEnd}` : `Access until ${periodEnd}`}
              {status?.state === "grace_period" ? " · payment issue — update your payment method in Google Play" : ""}
              {status?.state === "account_hold" ? " · on hold — fix your payment method in Google Play" : ""}
            </Text>
          ) : null}
          {!isPremium ? <Text style={styles.meta}>You are on the Free plan with a one-time Starter Pack.</Text> : null}
        </Card>

        <Text style={styles.headline}>{HEADLINE}</Text>
        <Text style={styles.value}>{VALUE}</Text>

        {/* Benefits + Free vs Premium comparison — values sourced from the backend config. */}
        <Text style={styles.section}>What Premium includes</Text>
        <Card style={{ gap: S.sm }}>
          {cfg?.premium ? Object.keys(PREMIUM_LABELS).filter((k) => cfg.premium[k] != null).map((k) => (
            <View key={k} style={styles.point}>
              <Feather name="check" size={16} color={C.brand} />
              <Text style={styles.pointTxt}>{PREMIUM_LABELS[k](cfg.premium[k])}</Text>
            </View>
          )) : null}
        </Card>

        <Text style={styles.section}>Free vs Premium</Text>
        <Card style={{ gap: 0 }}>
          <View style={[styles.cmpRow, styles.cmpHead]}>
            <Text style={[styles.cmpCell, styles.cmpFeature, styles.cmpHeadTxt]}>Monthly AI allowance</Text>
            <Text style={[styles.cmpCell, styles.cmpHeadTxt]}>Free</Text>
            <Text style={[styles.cmpCell, styles.cmpHeadTxt]}>Premium</Text>
          </View>
          {comparisonRows(cfg).map((r) => (
            <View key={r.key} style={styles.cmpRow}>
              <Text style={[styles.cmpCell, styles.cmpFeature]}>{r.label}</Text>
              <Text style={styles.cmpCell}>{r.free}</Text>
              <Text style={[styles.cmpCell, styles.cmpPrem]}>{r.premium}</Text>
            </View>
          ))}
        </Card>
        <Text style={styles.fineNote}>Free allowances are a one-time Starter Pack. Premium allowances reset every 30-day period. Your saved data always stays available.</Text>

        {/* Purchase controls — Android only, never a broken button elsewhere. */}
        {!isPremium && canBuy ? (
          <>
            <Text style={styles.section}>Choose your plan</Text>
            <PlanCard label="Annual" selected={selected === "annual"} onPress={() => setSelected("annual")}
              price={annual?.localizedPrice} period={planPeriod(annual?.billingPeriod) || "per year"}
              note={savings || "Best value"} testID="plan-annual" />
            <PlanCard label="Monthly" selected={selected === "monthly"} onPress={() => setSelected("monthly")}
              price={monthly?.localizedPrice} period={planPeriod(monthly?.billingPeriod) || "per month"}
              testID="plan-monthly" />

            {!!msg && <Text style={styles.err}>{msg}</Text>}
            <Pressable testID="premium-subscribe" disabled={busy} onPress={onSubscribe}
              style={({ pressed }) => [styles.cta, busy && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
              {busy ? <ActivityIndicator color={C.onBrand} /> : <Text style={styles.ctaTxt}>Continue</Text>}
            </Pressable>
            <Text style={styles.fine}>
              This is an auto-renewing subscription. Your Google Play account is charged at
              confirmation and again each billing period ({planPeriod(annual?.billingPeriod) || "yearly"} /
              {" "}{planPeriod(monthly?.billingPeriod) || "monthly"}) until you cancel. Cancel or manage
              anytime in Google Play at least 24 hours before renewal. Prices are shown by Google Play
              in your local currency.
            </Text>
          </>
        ) : null}

        {!isPremium && !canBuy ? (
          <Card testID="premium-unsupported" style={{ marginTop: S.lg }}>
            <Text style={styles.body}>{unsupportedMessage()}</Text>
          </Card>
        ) : null}

        {isPremium ? (
          <Btn label="Manage Premium in Google Play" variant="soft" icon="external-link" onPress={onManage} testID="premium-manage-main" style={{ marginTop: S.lg }} />
        ) : null}
        {!!msg && (isPremium || !canBuy) ? <Text style={styles.err}>{msg}</Text> : null}

        {/* Account actions + legal */}
        <View style={styles.linksRow}>
          <Pressable testID="premium-restore" onPress={onRestore}><Text style={styles.link}>Restore purchases</Text></Pressable>
          <Text style={styles.dot}>·</Text>
          <Pressable testID="premium-manage" onPress={onManage}><Text style={styles.link}>Manage subscription</Text></Pressable>
        </View>
        <View style={styles.linksRow}>
          <Pressable onPress={() => Linking.openURL(PRIVACY_URL)}><Text style={styles.linkMuted}>Privacy Policy</Text></Pressable>
          <Text style={styles.dot}>·</Text>
          <Pressable onPress={() => Linking.openURL(TERMS_URL)}><Text style={styles.linkMuted}>Terms of Use</Text></Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

function unsupportedMessage() {
  if (Platform.OS === "web") return "Subscriptions are purchased and managed in the GotU Android app. Your Free plan works everywhere.";
  return "Subscriptions are available in the installed Android app from Google Play. Your Free plan works here.";
}

function consumerError(_raw: string) {
  // Never surface raw store/provider errors, tokens, payloads or stack traces.
  return "We couldn't complete that just now. Please try again in a moment.";
}

function comparisonRows(cfg: any) {
  const f = cfg?.free_starter || {};
  const p = cfg?.premium || {};
  const rows = [
    { key: "audio_minutes", label: "Audio minutes", free: f.audio_minutes != null ? `${f.audio_minutes}` : "—", premium: p.audio_minutes != null ? `${p.audio_minutes}` : "—" },
    { key: "ai_import", label: "AI imports", free: f.ai_import != null ? `${f.ai_import}` : "—", premium: p.ai_import != null ? `${p.ai_import}` : "—" },
    { key: "import_pages", label: "Imported pages", free: f.import_pages != null ? `${f.import_pages}` : "—", premium: p.import_pages != null ? `${p.import_pages}` : "—" },
    { key: "memory_question", label: "AI Memory questions", free: f.memory_question != null ? `${f.memory_question}` : "—", premium: p.memory_question != null ? `${p.memory_question}` : "—" },
    { key: "briefing", label: "Daily Briefings", free: f.ai_briefing != null ? `${f.ai_briefing} shared` : "—", premium: p.briefing != null ? `${p.briefing}` : "—" },
    { key: "weekly_review", label: "Weekly Reviews", free: f.ai_briefing != null ? "shared" : "—", premium: p.weekly_review != null ? `${p.weekly_review}` : "—" },
  ];
  return rows;
}

function PlanCard({ label, price, period, note, selected, onPress, testID }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.plan, selected && styles.planSel]}>
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
  badge: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: C.brand3, paddingHorizontal: S.sm, paddingVertical: 5, borderRadius: R.pill },
  badgeTxt: { fontFamily: F.bodyBold, fontSize: 12, color: C.brand },
  stateRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stateLabel: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  headline: { fontFamily: F.display, fontSize: 24, lineHeight: 30, color: C.onSurface, marginTop: S.lg },
  value: { fontFamily: F.body, fontSize: 15, lineHeight: 22, color: C.onSurface2, marginTop: S.sm },
  section: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface, marginTop: S.xl, marginBottom: S.sm },
  point: { flexDirection: "row", alignItems: "center", gap: S.sm },
  pointTxt: { flex: 1, fontFamily: F.body, fontSize: 14, color: C.onSurface },
  body: { fontFamily: F.body, fontSize: 14, color: C.onSurface, lineHeight: 20 },
  meta: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  cmpRow: { flexDirection: "row", alignItems: "center", paddingVertical: S.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border },
  cmpHead: { borderBottomWidth: 1, borderBottomColor: C.borderStrong },
  cmpHeadTxt: { fontFamily: F.bodyBold, color: C.onSurface2 },
  cmpCell: { flex: 1, fontFamily: F.body, fontSize: 13, color: C.onSurface, textAlign: "center" },
  cmpFeature: { flex: 1.6, textAlign: "left" },
  cmpPrem: { fontFamily: F.bodyBold, color: C.brand },
  fineNote: { fontFamily: F.body, fontSize: 11, lineHeight: 16, color: C.onSurface3, marginTop: S.sm },
  plan: { flexDirection: "row", alignItems: "center", gap: S.sm, padding: S.md, borderRadius: R.lg, borderWidth: 1.5, borderColor: C.border, marginTop: S.md },
  planSel: { borderColor: C.brand, backgroundColor: C.brand3 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: C.brand, alignItems: "center", justifyContent: "center" },
  radioDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: C.brand },
  planLabel: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface },
  planNote: { fontFamily: F.bodyBold, fontSize: 12, color: C.brand },
  planPrice: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, marginTop: 2 },
  err: { fontFamily: F.body, fontSize: 13, color: C.error, marginTop: S.sm, textAlign: "center" },
  cta: { backgroundColor: C.brand, borderRadius: R.pill, paddingVertical: 16, alignItems: "center", marginTop: S.lg },
  ctaTxt: { fontFamily: F.bodyBold, fontSize: 16, color: C.onBrand },
  fine: { fontFamily: F.body, fontSize: 11, lineHeight: 16, color: C.onSurface2, marginTop: S.md, textAlign: "center" },
  linksRow: { flexDirection: "row", justifyContent: "center", alignItems: "center", gap: S.sm, marginTop: S.lg },
  link: { fontFamily: F.bodyBold, fontSize: 13, color: C.brand },
  linkMuted: { fontFamily: F.body, fontSize: 12, color: C.onSurface2 },
  dot: { color: C.onSurface2 },
});
