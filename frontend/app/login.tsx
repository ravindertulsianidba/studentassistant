import { useEffect, useMemo, useRef, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator,
  ScrollView, KeyboardAvoidingView, Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Feather } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";
import * as Google from "expo-auth-session/providers/google";
import { C, S, R, F, HERO } from "@/src/theme";
import { useAuth } from "@/src/auth";

WebBrowser.maybeCompleteAuthSession();

const WEB_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
const ANDROID_ID = process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID;
const IOS_ID = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
const GOOGLE_ENABLED = !!(WEB_ID || ANDROID_ID || IOS_ID);

function scorePassword(pw: string): { score: number; label: string; color: string } {
  if (!pw) return { score: 0, label: "", color: C.border };
  let s = 0;
  if (pw.length >= 10) s++;
  if (pw.length >= 14) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw) || /[^A-Za-z0-9]/.test(pw)) s++;
  if (/\s/.test(pw) && pw.length >= 16) s++;
  s = Math.min(s, 4);
  const map = [
    { label: "Too short", color: C.error },
    { label: "Weak", color: C.error },
    { label: "Fair", color: C.warning },
    { label: "Good", color: C.brand },
    { label: "Strong", color: C.success },
  ];
  return { score: s, ...map[s] };
}

function GoogleButton({ onError, onBusy }: { onError: (m: string) => void; onBusy: (b: boolean) => void }) {
  const { signInWithGoogleToken } = useAuth();
  const [request, response, promptAsync] = Google.useIdTokenAuthRequest({
    webClientId: WEB_ID, androidClientId: ANDROID_ID, iosClientId: IOS_ID,
  });
  useEffect(() => {
    if (response?.type === "success" && response.params?.id_token) {
      onBusy(true);
      signInWithGoogleToken(response.params.id_token)
        .catch((e) => onError(String(e.message || e)))
        .finally(() => onBusy(false));
    }
  }, [response]);
  return (
    <Pressable testID="google-signin" disabled={!request} onPress={() => { onError(""); promptAsync(); }}
      style={({ pressed }) => [styles.google, !request && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
      <Feather name="log-in" size={18} color={C.onSurface} />
      <Text style={styles.googleTxt}>Continue with Google</Text>
    </Pressable>
  );
}

type Mode = "signin" | "signup" | "forgot" | "check-verify" | "check-reset";

function Field({ icon, ...props }: any) {
  return (
    <View style={styles.fieldWrap}>
      <Feather name={icon} size={18} color={C.onSurface3} style={styles.fieldIcon} />
      <TextInput style={styles.input} placeholderTextColor={C.onSurface3} {...props} />
    </View>
  );
}

function PasswordField({ value, onChangeText, placeholder, testID, show, onToggle }: any) {
  return (
    <View style={styles.fieldWrap}>
      <Feather name="lock" size={18} color={C.onSurface3} style={styles.fieldIcon} />
      <TextInput testID={testID} style={[styles.input, { paddingRight: 44 }]} placeholder={placeholder}
        placeholderTextColor={C.onSurface3} secureTextEntry={!show} autoCapitalize="none"
        autoComplete="off" value={value} onChangeText={onChangeText} />
      <Pressable onPress={onToggle} hitSlop={10} style={styles.eye}>
        <Feather name={show ? "eye-off" : "eye"} size={18} color={C.onSurface3} />
      </Pressable>
    </View>
  );
}

export default function Login() {
  const insets = useSafeAreaInsets();
  const { signUp, signInWithPassword, resendVerification, forgotPassword, devSignIn } = useAuth();

  const [mode, setMode] = useState<Mode>("signin");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [info, setInfo] = useState("");

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [devEmail, setDevEmail] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef<any>(null);

  const strength = useMemo(() => scorePassword(pw), [pw]);

  useEffect(() => () => clearInterval(timerRef.current), []);
  const startCooldown = () => {
    setCooldown(60);
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => setCooldown((c) => { if (c <= 1) clearInterval(timerRef.current); return c - 1; }), 1000);
  };

  const reset = (m: Mode) => { setErr(""); setInfo(""); setPw(""); setPw2(""); setMode(m); };

  const doSignIn = async () => {
    setErr(""); setInfo("");
    if (!email.trim() || !pw) { setErr("Enter your email and password."); return; }
    setBusy(true);
    try { await signInWithPassword(email.trim(), pw); }
    catch (e: any) {
      const msg = e.message || "Sign-in failed";
      setErr(msg);
      if (/verify your email/i.test(msg)) reset("check-verify");
    } finally { setBusy(false); }
  };

  const doSignUp = async () => {
    setErr(""); setInfo("");
    if (!email.trim()) { setErr("Enter your email."); return; }
    if (pw.length < 10) { setErr("Password must be at least 10 characters."); return; }
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    setBusy(true);
    try {
      await signUp(email.trim(), pw, name.trim() || undefined);
      startCooldown();
      reset("check-verify");
    } catch (e: any) { setErr(e.message || "Could not create account"); }
    finally { setBusy(false); }
  };

  const doForgot = async () => {
    setErr(""); setInfo("");
    if (!email.trim()) { setErr("Enter your email."); return; }
    setBusy(true);
    try { await forgotPassword(email.trim()); startCooldown(); setMode("check-reset"); }
    catch (e: any) { setErr(e.message || "Request failed"); }
    finally { setBusy(false); }
  };

  const doResend = async () => {
    if (cooldown > 0) return;
    setErr(""); setBusy(true);
    try {
      if (mode === "check-reset") await forgotPassword(email.trim());
      else await resendVerification(email.trim());
      setInfo("Email sent. Check your inbox and spam folder.");
      startCooldown();
    } catch (e: any) { setErr(e.message || "Could not resend"); }
    finally { setBusy(false); }
  };

  const dev = async () => {
    if (!devEmail.trim()) return;
    setBusy(true); setErr("");
    try { await devSignIn(devEmail.trim()); } catch (e: any) { setErr(e.message || "Sign-in failed"); } finally { setBusy(false); }
  };

  const isCheck = mode === "check-verify" || mode === "check-reset";

  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1 }}>
        <View style={styles.hero}>
          <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(24,28,26,0.3)", "rgba(24,28,26,0.95)"]} style={StyleSheet.absoluteFill} />
          <View style={[styles.heroContent, { paddingTop: insets.top + S.lg }]}>
            <View style={styles.logo}><Feather name="feather" size={20} color={C.onBrand} /></View>
            <Text style={styles.title}>Student Assistant</Text>
            <Text style={styles.tagline}>Capture it once — never forget it again.</Text>
          </View>
        </View>

        <View style={[styles.body, { paddingBottom: insets.bottom + S.xl }]}>
          {isCheck ? (
            <CheckEmail mode={mode} email={email} cooldown={cooldown} busy={busy}
              info={info} err={err} onResend={doResend}
              onChangeEmail={() => reset(mode === "check-reset" ? "forgot" : "signup")}
              onBackToSignIn={() => reset("signin")} />
          ) : (
            <>
              {mode !== "forgot" ? (
                <View style={styles.tabs}>
                  <Pressable testID="tab-signin" onPress={() => reset("signin")} style={[styles.tab, mode === "signin" && styles.tabActive]}>
                    <Text style={[styles.tabTxt, mode === "signin" && styles.tabTxtActive]}>Sign In</Text>
                  </Pressable>
                  <Pressable testID="tab-signup" onPress={() => reset("signup")} style={[styles.tab, mode === "signup" && styles.tabActive]}>
                    <Text style={[styles.tabTxt, mode === "signup" && styles.tabTxtActive]}>Create Account</Text>
                  </Pressable>
                </View>
              ) : (
                <Pressable testID="forgot-back" onPress={() => reset("signin")} style={styles.backRow}>
                  <Feather name="arrow-left" size={18} color={C.onSurface2} />
                  <Text style={styles.backTxt}>Back to sign in</Text>
                </Pressable>
              )}

              {err ? <Text style={styles.err} testID="login-error">{err}</Text> : null}
              {info ? <Text style={styles.info}>{info}</Text> : null}

              {mode === "forgot" && (
                <Text style={styles.lead}>Enter your email and we'll send you a link to reset your password.</Text>
              )}

              {mode === "signup" && (
                <Field testID="name" icon="user" placeholder="Full name (optional)" autoCapitalize="words"
                  value={name} onChangeText={setName} />
              )}

              <Field testID="email" icon="mail" placeholder="you@university.edu" autoCapitalize="none"
                keyboardType="email-address" autoComplete="email" value={email} onChangeText={setEmail} />

              {mode !== "forgot" && (
                <PasswordField testID="password" placeholder="Password" value={pw} onChangeText={setPw}
                  show={showPw} onToggle={() => setShowPw((s) => !s)} />
              )}

              {mode === "signup" && (
                <>
                  {pw.length > 0 && (
                    <View style={styles.strengthRow}>
                      <View style={styles.strengthBar}>
                        {[0, 1, 2, 3].map((i) => (
                          <View key={i} style={[styles.strengthSeg,
                            { backgroundColor: i < strength.score ? strength.color : C.border }]} />
                        ))}
                      </View>
                      <Text style={[styles.strengthLabel, { color: strength.color }]}>{strength.label}</Text>
                    </View>
                  )}
                  <PasswordField testID="password2" placeholder="Confirm password" value={pw2} onChangeText={setPw2}
                    show={showPw} onToggle={() => setShowPw((s) => !s)} />
                  <Text style={styles.hint}>Use at least 10 characters. Passphrases are welcome.</Text>
                </>
              )}

              {mode === "signin" && (
                <Pressable testID="forgot-link" onPress={() => reset("forgot")} style={styles.forgotLink}>
                  <Text style={styles.forgotTxt}>Forgot password?</Text>
                </Pressable>
              )}

              <Pressable testID="submit"
                disabled={busy}
                onPress={mode === "signin" ? doSignIn : mode === "signup" ? doSignUp : doForgot}
                style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }, busy && { opacity: 0.7 }]}>
                {busy ? <ActivityIndicator color={C.onBrand} /> :
                  <Text style={styles.primaryTxt}>
                    {mode === "signin" ? "Sign In" : mode === "signup" ? "Create Account" : "Send reset link"}
                  </Text>}
              </Pressable>

              {mode !== "forgot" && (
                <>
                  <View style={styles.divider}><View style={styles.hr} /><Text style={styles.or}>or</Text><View style={styles.hr} /></View>
                  {GOOGLE_ENABLED ? (
                    <GoogleButton onError={setErr} onBusy={setBusy} />
                  ) : (
                    <View style={[styles.google, { opacity: 0.6 }]} testID="google-disabled">
                      <Feather name="log-in" size={18} color={C.onSurface} />
                      <Text style={styles.googleTxt}>Continue with Google</Text>
                    </View>
                  )}
                  {!GOOGLE_ENABLED && (
                    <Text style={styles.note}>Google Sign-In activates in the installed app build.</Text>
                  )}
                </>
              )}

              {__DEV__ && (
                <>
                  <View style={styles.divider}><View style={styles.hr} /><Text style={styles.or}>dev-only</Text><View style={styles.hr} /></View>
                  <Field testID="dev-email" icon="terminal" placeholder="dev@university.edu" autoCapitalize="none"
                    keyboardType="email-address" value={devEmail} onChangeText={setDevEmail} />
                  <Pressable testID="dev-signin" disabled={busy} onPress={dev}
                    style={({ pressed }) => [styles.secondary, pressed && { opacity: 0.85 }]}>
                    <Text style={styles.secondaryTxt}>Quick sign-in (dev)</Text>
                  </Pressable>
                </>
              )}
            </>
          )}

          <Text style={styles.legal}>By continuing you agree to record only where permitted and to our Terms & Privacy Policy.</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function CheckEmail({ mode, email, cooldown, busy, info, err, onResend, onChangeEmail, onBackToSignIn }: any) {
  const isReset = mode === "check-reset";
  return (
    <View style={{ gap: S.md }}>
      <View style={styles.checkIcon}><Feather name="mail" size={26} color={C.brand} /></View>
      <Text style={styles.checkTitle}>{isReset ? "Check your email" : "Verify your email"}</Text>
      <Text style={styles.lead}>
        {isReset ? "If an account exists, we've sent a password reset link to " : "We've sent a verification link to "}
        <Text style={styles.emailBold}>{email}</Text>.
        {isReset ? " The link expires in 1 hour." : " Open it to activate your account. The link expires in 24 hours."}
      </Text>
      {err ? <Text style={styles.err}>{err}</Text> : null}
      {info ? <Text style={styles.info}>{info}</Text> : null}

      <Pressable testID="resend" disabled={busy || cooldown > 0} onPress={onResend}
        style={({ pressed }) => [styles.primary, (busy || cooldown > 0) && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
        {busy ? <ActivityIndicator color={C.onBrand} /> :
          <Text style={styles.primaryTxt}>{cooldown > 0 ? `Resend in ${cooldown}s` : "Resend email"}</Text>}
      </Pressable>

      <Pressable testID="change-email" onPress={onChangeEmail} style={styles.secondary}>
        <Text style={styles.secondaryTxt}>Use a different email</Text>
      </Pressable>
      <Pressable testID="back-to-signin" onPress={onBackToSignIn} style={styles.backRow}>
        <Feather name="arrow-left" size={18} color={C.onSurface2} />
        <Text style={styles.backTxt}>Back to sign in</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  hero: { height: 230, justifyContent: "flex-end" },
  heroContent: { padding: S.xl },
  logo: { width: 40, height: 40, borderRadius: R.md, backgroundColor: C.brand, alignItems: "center", justifyContent: "center", marginBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 26, color: "#fff" },
  tagline: { fontFamily: F.body, fontSize: 14, color: "rgba(255,255,255,0.85)", marginTop: S.xs, lineHeight: 20 },
  body: { flex: 1, padding: S.xl, gap: S.md },
  tabs: { flexDirection: "row", backgroundColor: C.surface3, borderRadius: R.md, padding: 4 },
  tab: { flex: 1, height: 40, alignItems: "center", justifyContent: "center", borderRadius: R.sm },
  tabActive: { backgroundColor: C.surface2, ...({ elevation: 1 }) },
  tabTxt: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface3 },
  tabTxtActive: { fontFamily: F.bodyBold, color: C.onSurface },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, textAlign: "center" },
  info: { fontFamily: F.bodyMed, fontSize: 13, color: C.success, textAlign: "center" },
  lead: { fontFamily: F.body, fontSize: 14, color: C.onSurface2, lineHeight: 21 },
  emailBold: { fontFamily: F.bodyBold, color: C.onSurface },
  fieldWrap: { justifyContent: "center" },
  fieldIcon: { position: "absolute", left: S.md, zIndex: 1 },
  input: { backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: R.md, paddingVertical: S.md, paddingLeft: 42, paddingRight: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface, minHeight: 50 },
  eye: { position: "absolute", right: S.md, padding: 4 },
  strengthRow: { flexDirection: "row", alignItems: "center", gap: S.sm, marginTop: -S.xs },
  strengthBar: { flexDirection: "row", gap: 4, flex: 1 },
  strengthSeg: { flex: 1, height: 4, borderRadius: 2 },
  strengthLabel: { fontFamily: F.bodyMed, fontSize: 11, width: 56, textAlign: "right" },
  hint: { fontFamily: F.body, fontSize: 12, color: C.onSurface3 },
  forgotLink: { alignSelf: "flex-end" },
  forgotTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.brand },
  primary: { backgroundColor: C.brand, borderRadius: R.md, height: 52, alignItems: "center", justifyContent: "center", marginTop: S.xs },
  primaryTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onBrand },
  secondary: { borderRadius: R.md, height: 48, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: C.border, backgroundColor: C.surface2 },
  secondaryTxt: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  google: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: S.sm, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.borderStrong, borderRadius: R.md, height: 52 },
  googleTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  note: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, textAlign: "center" },
  divider: { flexDirection: "row", alignItems: "center", gap: S.md, marginVertical: S.xs },
  hr: { flex: 1, height: 1, backgroundColor: C.border },
  or: { fontFamily: F.bodyMed, fontSize: 11, color: C.onSurface3 },
  backRow: { flexDirection: "row", alignItems: "center", gap: S.sm, alignSelf: "flex-start", paddingVertical: S.xs },
  backTxt: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2 },
  checkIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  checkTitle: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  legal: { fontFamily: F.body, fontSize: 11, color: C.onSurface3, textAlign: "center", marginTop: S.md },
});
