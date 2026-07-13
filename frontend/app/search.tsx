import { useState } from "react";
import { View, Text, StyleSheet, TextInput, Pressable, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F } from "@/src/theme";
import { api } from "@/src/api";
import { Card, Loading } from "@/src/components/ui";

const EXAMPLES = [
  "When is Assignment 2 due?",
  "What commitments did I make this week?",
  "Show everything related to Sociology",
  "What did my professor emphasize?",
];

export default function Search() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<any>(null);

  const go = async (query?: string) => {
    const term = query ?? q;
    if (!term.trim()) return;
    setQ(term);
    setLoading(true);
    try { setRes(await api.post("/search", { query: term })); } catch (e) {} finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + S.sm }]}>
        <Text style={styles.title}>Search</Text>
        <Pressable onPress={() => router.back()} testID="search-close" hitSlop={10}><Feather name="x" size={24} color={C.onSurface2} /></Pressable>
      </View>

      <View style={styles.searchBar}>
        <Feather name="search" size={18} color={C.onSurface3} />
        <TextInput
          testID="search-input"
          style={styles.input}
          placeholder="Ask anything about your semester…"
          placeholderTextColor={C.onSurface3}
          value={q}
          onChangeText={setQ}
          autoFocus
          returnKeyType="search"
          onSubmitEditing={() => go()}
        />
        {q ? <Pressable onPress={() => go()} testID="search-go"><Feather name="arrow-right-circle" size={22} color={C.brand} /></Pressable> : null}
      </View>

      <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
        {loading ? <Loading label="Searching your memory…" /> : res ? (
          <>
            <Card testID="search-answer" style={{ gap: S.sm }}>
              <View style={styles.aiRow}><Feather name="cpu" size={14} color={C.brand} /><Text style={styles.aiLabel}>Assistant</Text></View>
              <Text style={styles.answer}>{res.answer}</Text>
            </Card>
            {res.matches?.length ? (
              <>
                <Text style={styles.matchHead}>Related</Text>
                {res.matches.map((m: any) => (
                  <Card key={m.id} style={styles.matchCard}>
                    <Text style={styles.matchTitle}>{m.title}</Text>
                    {m.subtitle ? <Text style={styles.matchSub}>{m.subtitle}</Text> : null}
                  </Card>
                ))}
              </>
            ) : null}
          </>
        ) : (
          <>
            <Text style={styles.exLabel}>Try asking</Text>
            {EXAMPLES.map((e) => (
              <Pressable key={e} style={styles.ex} onPress={() => go(e)} testID={`search-ex-${e.slice(0, 6)}`}>
                <Feather name="corner-down-right" size={14} color={C.brand} />
                <Text style={styles.exTxt}>{e}</Text>
              </Pressable>
            ))}
          </>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: S.lg, paddingBottom: S.sm },
  title: { fontFamily: F.display, fontSize: 22, color: C.onSurface },
  searchBar: { flexDirection: "row", alignItems: "center", gap: S.sm, backgroundColor: C.surface2, marginHorizontal: S.lg, paddingHorizontal: S.md, borderRadius: R.pill, borderWidth: 1, borderColor: C.border, height: 50 },
  input: { flex: 1, fontFamily: F.body, fontSize: 15, color: C.onSurface },
  aiRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  aiLabel: { fontFamily: F.bodyBold, fontSize: 12, color: C.brand },
  answer: { fontFamily: F.body, fontSize: 15, color: C.onSurface, lineHeight: 22 },
  matchHead: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface3, marginTop: S.lg, marginBottom: S.sm },
  matchCard: { marginBottom: S.sm, padding: S.md },
  matchTitle: { fontFamily: F.bodyBold, fontSize: 14, color: C.onSurface },
  matchSub: { fontFamily: F.body, fontSize: 12, color: C.onSurface3, marginTop: 2 },
  exLabel: { fontFamily: F.bodyBold, fontSize: 13, color: C.onSurface3, marginBottom: S.sm },
  ex: { flexDirection: "row", alignItems: "center", gap: S.sm, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  exTxt: { fontFamily: F.body, fontSize: 15, color: C.onSurface2, flex: 1 },
});
