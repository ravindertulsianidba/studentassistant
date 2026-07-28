import { router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

export type LegalSection = {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
};

type Props = {
  title: string;
  effectiveDate: string;
  introduction: string;
  sections: LegalSection[];
  actionLabel?: string;
  onAction?: () => void;
};

export default function LegalPage({
  title,
  effectiveDate,
  introduction,
  sections,
  actionLabel,
  onAction,
}: Props) {
  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Go back"
          onPress={() => router.back()}
          style={styles.back}
        >
          <Text style={styles.backText}>‹</Text>
        </Pressable>
        <Text style={styles.brand}>GotU</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.date}>Effective: {effectiveDate}</Text>
        <Text style={styles.intro}>{introduction}</Text>

        {sections.map((section) => (
          <View key={section.heading} style={styles.section}>
            <Text style={styles.heading}>{section.heading}</Text>

            {section.paragraphs?.map((paragraph, index) => (
              <Text key={`${section.heading}-p-${index}`} style={styles.body}>
                {paragraph}
              </Text>
            ))}

            {section.bullets?.map((bullet, index) => (
              <View key={`${section.heading}-b-${index}`} style={styles.bulletRow}>
                <Text style={styles.bullet}>•</Text>
                <Text style={styles.bulletText}>{bullet}</Text>
              </View>
            ))}
          </View>
        ))}

        {actionLabel && onAction ? (
          <Pressable
            accessibilityRole="link"
            onPress={onAction}
            style={styles.actionButton}
          >
            <Text style={styles.actionText}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FAFBF9" },
  header: {
    minHeight: 72,
    paddingTop: 16,
    paddingHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: 1,
    borderBottomColor: "#DDE5DF",
    backgroundColor: "#14432C",
  },
  back: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  backText: { color: "#FFF9EA", fontSize: 40, lineHeight: 42 },
  brand: {
    color: "#FFF9EA",
    fontSize: 22,
    fontWeight: "700",
    marginLeft: 8,
  },
  content: {
    width: "100%",
    maxWidth: 860,
    alignSelf: "center",
    paddingHorizontal: 24,
    paddingTop: 36,
    paddingBottom: 72,
  },
  title: { color: "#172019", fontSize: 38, lineHeight: 44, fontWeight: "800" },
  date: { color: "#5D6A61", fontSize: 15, marginTop: 10, marginBottom: 24 },
  intro: { color: "#303A33", fontSize: 18, lineHeight: 28, marginBottom: 18 },
  section: { marginTop: 26 },
  heading: {
    color: "#14432C",
    fontSize: 23,
    lineHeight: 30,
    fontWeight: "700",
    marginBottom: 10,
  },
  body: { color: "#303A33", fontSize: 16, lineHeight: 25, marginBottom: 10 },
  actionButton: {
    backgroundColor: "#14432C",
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 20,
    alignItems: "center",
    marginTop: 34,
  },
  actionText: { color: "#FFF9EA", fontSize: 16, fontWeight: "700" },
  bulletRow: { flexDirection: "row", paddingRight: 12, marginBottom: 8 },
  bullet: { color: "#14432C", fontSize: 19, lineHeight: 25, marginRight: 10 },
  bulletText: { flex: 1, color: "#303A33", fontSize: 16, lineHeight: 25 },
});
