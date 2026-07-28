import { Linking } from "react-native";
import LegalPage from "@/src/components/LegalPage";

const EMAIL =
  "mailto:ravindertulsianidba@gmail.com" +
  "?subject=GotU%20account%20deletion%20request";

export default function AccountDeletion() {
  return (
    <LegalPage
      title="Delete Your GotU Account"
      effectiveDate="July 28, 2026"
      introduction="You can permanently delete your GotU account and associated student data directly in the app or request deletion by email."
      actionLabel="Email an account-deletion request"
      onAction={() => Linking.openURL(EMAIL)}
      sections={[
        {
          heading: "Delete inside GotU",
          bullets: [
            "Open GotU and sign in.",
            "Select Settings.",
            "Select Delete my account.",
            "Review the warning and confirm deletion.",
            "Password accounts must confirm their password.",
          ]
        },
        {
          heading: "Request deletion by email",
          paragraphs: [
            "Email ravindertulsianidba@gmail.com from the email address associated with your GotU account. Use the subject “GotU account deletion request.” We may ask you to verify account ownership before processing the request."
          ]
        },
        {
          heading: "What is deleted",
          paragraphs: [
            "Deletion removes your GotU account, authentication sessions, courses, schedules, tasks, deadlines, reminders, notes, imports, uploaded content, recordings, transcripts, calendar connections, AI usage records and active GotU entitlements."
          ]
        },
        {
          heading: "Limited records retained",
          paragraphs: [
            "GotU may retain a non-reversible Google Play purchase-token hash and deleted internal account identifier to prevent purchase reuse, fraud and entitlement errors. The usable encrypted purchase token is removed. Records required by law, billing disputes or security obligations may be retained only as necessary."
          ]
        },
        {
          heading: "Google Play subscription",
          paragraphs: [
            "Deleting GotU does not cancel a Google Play subscription. Cancel it separately under Subscriptions in Google Play to stop future renewals."
          ]
        },
        {
          heading: "Processing time",
          paragraphs: [
            "In-app deletion is processed immediately. Verified email requests are normally processed within 30 days, subject to legal or security requirements."
          ]
        },
      ]}
    />
  );
}
