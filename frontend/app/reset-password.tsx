import { useMemo, useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { useAuth } from "@/src/auth";

function scorePassword(pw: string) {
  if (!pw) return { score: 0, label: "", color: C.border };
  let s = 0;
  if (pw.length >= 10) s++;
  if (pw.length >= 14) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw) || /[^A-Za-z0-9]/.test(pw)) s++;
  s = Math.min(s, 4);
  const map = [
    { label: "Too short", color: C.error }, { label: "Weak", color: C.error },
    { label: "Fair", color: C.warning }, { label: "Good", color: C.brand }, { label: "Strong", color: C.success },
  ];
  return { score: s, ...map[s] };
}

export default function ResetPassword() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { resetPassword } = useAuth();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const strength = useMemo(() => scorePassword(pw), [pw]);

  const submit = async () => {
    setErr("");
    if (!token) { setErr("This reset link is invalid."); return; }
    if (pw.length < 10) { setErr("Password must be at least 10 characters."); return; }
    if (pw !== pw2) { setErr("Passwords don't match."); return; }
    setBusy(true);
    try { await resetPassword(String(token), pw); setDone(true); }
    catch (e: any) { setErr(e.message || "Could not reset password."); }
    finally { setBusy(false); }
  };

  if (done) {
    return (
      <View style={[styles.root, { paddingTop: insets.top + S.xxl, justifyContent: "center" }]}>
        <View style={{ alignItems: "center", gap: S.md }}>
          <View style={styles.icon}><Feather name="check-circle" size={30} color={C.brand} /></View>
          <Text style={styles.title}>Password updated</Text>
          <Text style={styles.sub}>Your password has been changed and all sessions were signed out.</Text>
          <Pressable testID="go-signin" onPress={() => router.replace("/login")}
            style={({ pressed }) => [styles.btn, pressed && { opacity: 0.85 }]}>
            <Text style={styles.btnTxt}>Sign in</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: S.xl, paddingTop: insets.top + S.xxl, gap: S.md }}>
        <Text style={styles.title}>Reset password</Text>
        <Text style={styles.sub}>Choose a new password for your account.</Text>
        {err ? <Text style={styles.err}>{err}</Text> : null}

        <View style={styles.fieldWrap}>
          <Feather name="lock" size={18} color={C.onSurface3} style={styles.fieldIcon} />
          <TextInput testID="new-password" style={styles.input} placeholder="New password" placeholderTextColor={C.onSurface3}
            secureTextEntry={!show} autoCapitalize="none" value={pw} onChangeText={setPw} />
          <Pressable onPress={() => setShow((s) => !s)} hitSlop={10} style={styles.eye}>
            <Feather name={show ? "eye-off" : "eye"} size={18} color={C.onSurface3} />
          </Pressable>
        </View>
        {pw.length > 0 && (
          <View style={styles.strengthRow}>
            <View style={styles.strengthBar}>
              {[0, 1, 2, 3].map((i) => (
                <View key={i} style={[styles.strengthSeg, { backgroundColor: i < strength.score ? strength.color : C.border }]} />
              ))}
            </View>
            <Text style={[styles.strengthLabel, { color: strength.color }]}>{strength.label}</Text>
          </View>
        )}
        <View style={styles.fieldWrap}>
          <Feather name="lock" size={18} color={C.onSurface3} style={styles.fieldIcon} />
          <TextInput testID="confirm-password" style={styles.input} placeholder="Confirm new password" placeholderTextColor={C.onSurface3}
            secureTextEntry={!show} autoCapitalize="none" value={pw2} onChangeText={setPw2} />
        </View>

        <Pressable testID="submit-reset" disabled={busy} onPress={submit}
          style={({ pressed }) => [styles.btn, pressed && { opacity: 0.85 }, busy && { opacity: 0.7 }]}>
          {busy ? <ActivityIndicator color={C.onBrand} /> : <Text style={styles.btnTxt}>Update password</Text>}
        </Pressable>
        <Pressable onPress={() => router.replace("/login")} style={{ alignSelf: "center", paddingVertical: S.sm }}>
          <Text style={{ fontFamily: F.bodyMed, fontSize: 14, color: C.onSurface2 }}>Back to sign in</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  icon: { width: 64, height: 64, borderRadius: 32, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: F.display, fontSize: 24, color: C.onSurface },
  sub: { fontFamily: F.body, fontSize: 15, color: C.onSurface2, textAlign: "center", lineHeight: 22, paddingHorizontal: S.lg },
  err: { fontFamily: F.bodyMed, fontSize: 13, color: C.error, textAlign: "center" },
  fieldWrap: { justifyContent: "center" },
  fieldIcon: { position: "absolute", left: S.md, zIndex: 1 },
  input: { backgroundColor: C.surface2, borderWidth: 1, borderColor: C.border, borderRadius: R.md, paddingVertical: S.md, paddingLeft: 42, paddingRight: 44, fontFamily: F.body, fontSize: 15, color: C.onSurface, minHeight: 50 },
  eye: { position: "absolute", right: S.md, padding: 4 },
  strengthRow: { flexDirection: "row", alignItems: "center", gap: S.sm, marginTop: -S.xs },
  strengthBar: { flexDirection: "row", gap: 4, flex: 1 },
  strengthSeg: { flex: 1, height: 4, borderRadius: 2 },
  strengthLabel: { fontFamily: F.bodyMed, fontSize: 11, width: 56, textAlign: "right" },
  btn: { backgroundColor: C.brand, borderRadius: R.md, height: 52, alignItems: "center", justifyContent: "center", marginTop: S.sm },
  btnTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onBrand },
});
