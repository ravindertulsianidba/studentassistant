import React from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, ViewStyle, TextStyle } from "react-native";
import { Feather } from "@expo/vector-icons";
import { C, S, R, F, shadow } from "../theme";

export function Card({ children, style, testID }: { children: React.ReactNode; style?: ViewStyle; testID?: string }) {
  return <View testID={testID} style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ children, style }: { children: React.ReactNode; style?: TextStyle }) {
  return <Text style={[styles.section, style]}>{children}</Text>;
}

export function Btn({ label, onPress, icon, variant = "primary", testID, style }:
  { label: string; onPress: () => void; icon?: any; variant?: "primary" | "ghost" | "soft"; testID?: string; style?: ViewStyle }) {
  const bg = variant === "primary" ? C.brand : variant === "soft" ? C.brand3 : "transparent";
  const fg = variant === "primary" ? C.onBrand : variant === "soft" ? C.onBrand3 : C.brand;
  return (
    <Pressable testID={testID} onPress={onPress}
      style={({ pressed }) => [styles.btn, { backgroundColor: bg, opacity: pressed ? 0.85 : 1 },
        variant === "ghost" && { borderWidth: 1, borderColor: C.border }, style]}>
      {icon ? <Feather name={icon} size={16} color={fg} /> : null}
      <Text style={[styles.btnTxt, { color: fg }]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({ label, active, onPress, testID }: { label: string; active?: boolean; onPress: () => void; testID?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress}
      style={[styles.chip, active ? { backgroundColor: C.inverse, borderColor: C.inverse } : null]}>
      <Text style={[styles.chipTxt, active ? { color: C.onInverse } : null]}>{label}</Text>
    </Pressable>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={styles.center} testID="loading-state">
      <ActivityIndicator color={C.brand} />
      {label ? <Text style={styles.muted}>{label}</Text> : null}
    </View>
  );
}

export function Empty({ icon = "inbox", title, sub, testID }: { icon?: any; title: string; sub?: string; testID?: string }) {
  return (
    <View style={styles.center} testID={testID || "empty-state"}>
      <View style={styles.emptyIcon}><Feather name={icon} size={26} color={C.brand} /></View>
      <Text style={styles.emptyTitle}>{title}</Text>
      {sub ? <Text style={styles.muted}>{sub}</Text> : null}
    </View>
  );
}

export function Badge({ label, tone = "info" }: { label: string; tone?: "info" | "warning" | "error" | "success" }) {
  const map: any = { info: C.brand, warning: C.warning, error: C.error, success: C.success };
  return (
    <View style={[styles.badge, { backgroundColor: map[tone] + "1A" }]}>
      <View style={[styles.dot, { backgroundColor: map[tone] }]} />
      <Text style={[styles.badgeTxt, { color: map[tone] }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: C.surface2, borderRadius: R.lg, padding: S.lg, borderWidth: 1, borderColor: C.border, ...shadow },
  section: { fontFamily: F.display, fontSize: 16, color: C.onSurface, marginBottom: S.md },
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: S.sm, paddingVertical: 14, paddingHorizontal: S.lg, borderRadius: R.md, minHeight: 48 },
  btnTxt: { fontFamily: F.bodyBold, fontSize: 15 },
  chip: { height: 36, paddingHorizontal: S.lg, borderRadius: R.pill, backgroundColor: C.surface3, borderWidth: 1, borderColor: C.border, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  chipTxt: { fontFamily: F.bodyMed, fontSize: 13, color: C.onSurface3 },
  center: { alignItems: "center", justifyContent: "center", padding: S.xxl, gap: S.sm },
  muted: { fontFamily: F.body, fontSize: 13, color: C.onSurface3, textAlign: "center" },
  emptyIcon: { width: 56, height: 56, borderRadius: R.pill, backgroundColor: C.brand3, alignItems: "center", justifyContent: "center", marginBottom: S.sm },
  emptyTitle: { fontFamily: F.bodyBold, fontSize: 16, color: C.onSurface },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 5, borderRadius: R.pill, alignSelf: "flex-start" },
  dot: { width: 6, height: 6, borderRadius: 3 },
  badgeTxt: { fontFamily: F.bodyMed, fontSize: 12 },
});
