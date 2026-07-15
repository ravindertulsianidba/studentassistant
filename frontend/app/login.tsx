import { useEffect, useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator } from "react-native";
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

// Only mounts when a Google client ID is configured (avoids the hook throwing).
function GoogleButton({ onError, onBusy }: { onError: (m: string) => void; onBusy: (b: boolean) => void }) {
  const { signInWithGoogleToken } = useAuth();
  const [request, response, promptAsync] = Google.useIdTokenAuthRequest({
    webClientId: WEB_ID,
    androidClientId: ANDROID_ID,
    iosClientId: IOS_ID,
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

export default function Login() {
  const insets = useSafeAreaInsets();
  const { devSignIn } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [email, setEmail] = useState("");

  const dev = async () => {
    if (!email.trim()) return;
    setBusy(true); setErr("");
    try { await devSignIn(email.trim()); } catch (e: any) { setErr(e.message || "Sign-in failed"); } finally { setBusy(false); }
  };

  return (
    <View style={styles.root}>
      <View style={styles.hero}>
        <Image source={{ uri: HERO }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <LinearGradient colors={["rgba(24,28,26,0.3)", "rgba(24,28,26,0.95)"]} style={StyleSheet.absoluteFill} />
        <View style={[styles.heroContent, { paddingTop: insets.top + S.xxl }]}>
          <View style={styles.logo}><Feather name="feather" size={22} color={C.onBrand} /></View>
          <Text style={styles.title}>Student Assistant</Text>
          <Text style={styles.tagline}>Your AI academic executive assistant. Capture it once — never forget it again.</Text>
        </View>
      </View>

      <View style={[styles.body, { paddingBottom: insets.bottom + S.xl }]}>
        {err ? <Text style={styles.err} testID="login-error">{err}</Text> : null}

        {WEB_ID || ANDROID_ID || IOS_ID ? (
          <GoogleButton onError={setErr} onBusy={setBusy} />
        ) : (
          <View style={[styles.google, { opacity: 0.6 }]} testID="google-disabled">
            <Feather name="log-in" size={18} color={C.onSurface} />
            <Text style={styles.googleTxt}>Continue with Google</Text>
          </View>
        )}
        <Text style={styles.note}>{__DEV__ ? "Google Sign-In activates in the installed app build. In this dev preview, use quick sign-in below." : "Sign in with your Google account to continue."}</Text>

        {__DEV__ ? (
          <>
            <View style={styles.divider}><View style={styles.hr} /><Text style={styles.or}>dev-only sign-in</Text><View style={styles.hr} /></View>
            <TextInput testID="dev-email" style={styles.input} placeholder="you@university.edu" placeholderTextColor={C.onSurface3}
              autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
            <Pressable testID="dev-signin" disabled={busy} onPress={dev} style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}>
              {busy ? <ActivityIndicator color={C.onBrand} /> : <Text style={styles.primaryTxt}>Continue (dev)</Text>}
            </Pressable>
          </>
        ) : null}

        <Text style={styles.legal}>By continuing you agree to record only where permitted and to our Terms & Privacy Policy.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  hero: { height: 360, justifyContent: "flex-end" },
  heroContent: { padding: S.xl },
  logo: { width: 44, height: 44, borderRadius: R.md, backgroundColor: C.brand, alignItems: "center", justifyContent: "center", marginBottom: S.md },
  title: { fontFamily: F.display, fontSize: 30, color: "#fff" },
  tagline: { fontFamily: F.body, fontSize: 15, color: "rgba(255,255,255,0.85)", marginTop: S.sm, lineHeight: 21 },
  body: { flex: 1, padding: S.xl, gap: S.md },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, textAlign: "center" },
  google: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: S.sm, backgroundColor: C.surface2, borderWidth: 1, borderColor: C.borderStrong, borderRadius: R.md, height: 52 },
  googleTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onSurface },
  note: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, textAlign: "center" },
  divider: { flexDirection: "row", alignItems: "center", gap: S.md, marginTop: S.sm },
  hr: { flex: 1, height: 1, backgroundColor: C.border },
  or: { fontFamily: F.bodyMed, fontSize: 11, color: C.onSurface3 },
  input: { backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: R.md, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  primary: { backgroundColor: C.brand, borderRadius: R.md, height: 52, alignItems: "center", justifyContent: "center" },
  primaryTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onBrand },
  legal: { fontFamily: F.body, fontSize: 11, color: C.onSurface3, textAlign: "center", marginTop: S.sm },
});
