import { useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Redirect, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { useAuth } from "@/src/auth";

// Internal engineering route only. Never linked from the normal login screen and never
// shipped to preview/pilot/production: requires BOTH __DEV__ and the explicit flag
// EXPO_PUBLIC_ENABLE_DEV_LOGIN=true (default false). The backend additionally requires
// ALLOW_INSECURE_DEV=true and returns 404 for /auth/dev-login otherwise.
const DEV_LOGIN_ENABLED = __DEV__ && process.env.EXPO_PUBLIC_ENABLE_DEV_LOGIN === "true";

export default function DevLogin() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { devSignIn } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!DEV_LOGIN_ENABLED) return <Redirect href="/login" />;

  const go = async () => {
    if (!email.trim()) return;
    setBusy(true); setErr("");
    try { await devSignIn(email.trim()); } catch (e: any) { setErr(e?.message || "Sign-in failed"); } finally { setBusy(false); }
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top + S.xxl }]}>
      <Feather name="terminal" size={28} color={C.brand} />
      <Text style={styles.title}>Internal dev login</Text>
      <Text style={styles.sub}>Engineering only. Not available in preview/pilot/production builds.</Text>
      {err ? <Text style={styles.err}>{err}</Text> : null}
      <TextInput style={styles.input} placeholder="engineer@university.edu" placeholderTextColor={C.onSurface3}
        autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} testID="devroute-email" />
      <Pressable style={styles.btn} onPress={go} disabled={busy} testID="devroute-signin">
        {busy ? <ActivityIndicator color={C.onBrand} /> : <Text style={styles.btnTxt}>Dev sign-in</Text>}
      </Pressable>
      <Pressable onPress={() => router.replace("/login")} style={{ paddingVertical: S.md }}>
        <Text style={styles.link}>Back to sign in</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface, padding: S.xl, alignItems: "center", gap: S.md },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface, marginTop: S.sm },
  sub: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center" },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error },
  input: { alignSelf: "stretch", backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: R.md, padding: S.md, fontFamily: F.body, fontSize: 15, color: C.onSurface, marginTop: S.md },
  btn: { alignSelf: "stretch", backgroundColor: C.brand, borderRadius: R.md, height: 50, alignItems: "center", justifyContent: "center" },
  btnTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onBrand },
  link: { fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2 },
});
