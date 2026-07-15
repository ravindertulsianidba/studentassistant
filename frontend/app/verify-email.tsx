import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { useAuth } from "@/src/auth";

export default function VerifyEmail() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { verifyEmail } = useAuth();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      if (!token) { setStatus("error"); setMsg("This link is missing its verification token."); return; }
      try { await verifyEmail(String(token)); setStatus("ok"); setMsg("Your email is verified. You can now sign in."); }
      catch (e: any) { setStatus("error"); setMsg(e.message || "We couldn't verify this link."); }
    })();
  }, [token]);

  const ok = status === "ok";
  return (
    <View style={[styles.root, { paddingTop: insets.top + S.xxl, paddingBottom: insets.bottom + S.xl }]}>
      <View style={styles.card}>
        {status === "loading" ? (
          <><ActivityIndicator size="large" color={C.brand} /><Text style={styles.title}>Verifying…</Text></>
        ) : (
          <>
            <View style={[styles.icon, { backgroundColor: ok ? C.brand3 : "#F6E7E7" }]}>
              <Feather name={ok ? "check-circle" : "alert-circle"} size={30} color={ok ? C.brand : C.error} />
            </View>
            <Text style={styles.title}>{ok ? "Email verified" : "Verification failed"}</Text>
            <Text style={styles.sub}>{msg}</Text>
            <Pressable testID="go-signin" onPress={() => router.replace("/login")}
              style={({ pressed }) => [styles.btn, pressed && { opacity: 0.85 }]}>
              <Text style={styles.btnTxt}>{ok ? "Continue to sign in" : "Back to sign in"}</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface, padding: S.xl, justifyContent: "center" },
  card: { alignItems: "center", gap: S.md },
  icon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: F.display, fontSize: 24, color: C.onSurface, marginTop: S.sm },
  sub: { fontFamily: F.body, fontSize: 15, color: C.onSurface2, textAlign: "center", lineHeight: 22 },
  btn: { backgroundColor: C.brand, borderRadius: R.md, height: 52, alignItems: "center", justifyContent: "center", paddingHorizontal: S.xxl, marginTop: S.md },
  btnTxt: { fontFamily: F.bodyBold, fontSize: 15, color: C.onBrand },
});
