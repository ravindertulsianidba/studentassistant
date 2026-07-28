import LegalPage from "@/src/components/LegalPage";

export default function PrivacyPolicy() {
  return (
    <LegalPage
      title="Privacy Policy"
      effectiveDate="July 28, 2026"
      introduction="GotU: AI Student Assistant is operated by Decisiv Labs. This policy explains what information GotU collects, why it is used, how it is protected, and how you can access or delete it."
      sections={[
        {
          heading: "Information we collect",
          bullets: [
            "Account information, including your name, email address, authentication provider, verification status and security records.",
            "Student content you choose to provide, including courses, schedules, assignments, deadlines, tasks, notes, reminders, uploaded documents, screenshots and imported pages.",
            "Audio recordings, transcripts and information extracted from lectures or active-listening sessions when you use recording features.",
            "Calendar information when you connect or permit GotU to read or create calendar events.",
            "AI requests and generated results needed to provide memory search, study notes, briefings, reviews and task extraction.",
            "Usage, allowance, diagnostics and device information needed to operate, secure and improve the service.",
            "Subscription information from Google Play, including product, plan, subscription state, renewal status and protected purchase-token records. GotU does not receive your full payment-card details.",
          ]
        },
        {
          heading: "How we use information",
          bullets: [
            "Provide, personalize and maintain GotU features.",
            "Create notes, tasks, reminders, summaries, briefings and study assistance.",
            "Authenticate accounts, prevent abuse and protect account security.",
            "Verify Google Play purchases and manage Premium access.",
            "Measure feature allowances, reliability and operating costs.",
            "Respond to support, privacy and account-deletion requests.",
            "Comply with legal obligations and enforce our terms.",
          ]
        },
        {
          heading: "AI processing",
          paragraphs: [
            "GotU uses OpenAI services to process content required for AI-assisted features. Relevant prompts, documents, images, transcripts or other content may be sent to OpenAI when you request those features. Do not submit information you are not authorized to process.",
            "AI-generated information can be incomplete or inaccurate. Review important academic information, dates and recommendations before relying on them."
          ]
        },
        {
          heading: "Service providers",
          paragraphs: [
            "We use service providers only as needed to operate GotU. These may include OpenAI for AI processing, Google for authentication, Google Play subscriptions and related services, Expo for app delivery and notifications, and infrastructure providers used to host and secure the application."
          ]
        },
        {
          heading: "Sharing",
          paragraphs: [
            "We do not sell your personal information. We disclose information to service providers only as needed to provide GotU, protect the service, comply with law, or complete a transaction you request."
          ]
        },
        {
          heading: "Storage and security",
          paragraphs: [
            "GotU uses access controls, encrypted network connections, protected authentication tokens and encryption for Google Play purchase tokens. No system can guarantee absolute security, but we use reasonable safeguards appropriate to the information processed."
          ]
        },
        {
          heading: "Retention and deletion",
          paragraphs: [
            "Student content and account information are retained while your account is active or as needed to provide GotU. You can delete your account inside GotU under Settings, or request deletion using the instructions on our Account Deletion page.",
            "Account deletion removes your account, student content, recordings, transcripts, notes, tasks, calendar links, usage history and active entitlements. A limited non-reversible Google Play token hash and deleted internal account identifier may be retained to prevent purchase-token reuse, fraud and entitlement errors. The usable encrypted purchase token is removed. Limited records may also be retained when required by law, dispute resolution or security obligations."
          ]
        },
        {
          heading: "Your choices",
          bullets: [
            "Review or export available account data from GotU.",
            "Disconnect calendar access or change device permissions.",
            "Manage or cancel your Google Play subscription through Google Play.",
            "Delete your GotU account in the app or request deletion by email.",
          ]
        },
        {
          heading: "Children",
          paragraphs: [
            "GotU is not directed to children under 13. If you believe a child under 13 has provided personal information, contact us so we can investigate and delete it where appropriate."
          ]
        },
        {
          heading: "International processing",
          paragraphs: [
            "Service providers may process information in countries other than your own. Privacy protections and lawful-access rules may differ between jurisdictions."
          ]
        },
        {
          heading: "Changes to this policy",
          paragraphs: [
            "We may update this policy when GotU, our providers or legal requirements change. The effective date above identifies the current version."
          ]
        },
        {
          heading: "Contact",
          paragraphs: [
            "For privacy, support or account-deletion questions, email ravindertulsianidba@gmail.com."
          ]
        },
      ]}
    />
  );
}
