import LegalPage from "@/src/components/LegalPage";

export default function TermsOfService() {
  return (
    <LegalPage
      title="Terms of Service"
      effectiveDate="July 28, 2026"
      introduction="These Terms govern your use of GotU: AI Student Assistant. By creating an account or using GotU, you agree to these Terms."
      sections={[
        {
          heading: "Eligibility and accounts",
          paragraphs: [
            "You must be at least 13 years old and legally able to agree to these Terms. You are responsible for accurate account information, protecting your credentials and activity conducted through your account."
          ]
        },
        {
          heading: "Permitted use",
          paragraphs: [
            "GotU is provided for lawful personal educational use. You may not misuse the service, interfere with its operation, bypass limits, access another person’s account, upload unlawful material, or use GotU to violate academic-integrity rules or another person’s rights."
          ]
        },
        {
          heading: "Your content",
          paragraphs: [
            "You retain ownership of content you submit. You give GotU permission to host, process and transmit that content only as needed to provide, secure and improve the requested service.",
            "You are responsible for having permission to upload documents and record people or lectures. Recording laws and institutional rules vary. Obtain consent when required."
          ]
        },
        {
          heading: "AI-generated information",
          paragraphs: [
            "GotU uses artificial intelligence and may produce incomplete, incorrect or outdated results. GotU does not replace your instructors, institution, professional advice or official academic records. Verify deadlines, requirements and important decisions using authoritative sources."
          ]
        },
        {
          heading: "Free and Premium plans",
          paragraphs: [
            "Features and allowances vary by plan and may be shown in the app. Premium subscriptions are purchased and billed through Google Play. Prices, taxes, renewal terms, trials and payment methods are displayed by Google Play before purchase."
          ]
        },
        {
          heading: "Renewal and cancellation",
          paragraphs: [
            "Subscriptions renew automatically unless cancelled through Google Play before the end of the current billing period. Deleting your GotU account does not automatically cancel your Google Play subscription. Cancel the subscription separately in Google Play to prevent future charges."
          ]
        },
        {
          heading: "Availability and changes",
          paragraphs: [
            "We may modify, suspend or discontinue features, limits or integrations to maintain security, reliability, legal compliance or service viability. We will avoid materially reducing paid service during an active billing period where reasonably possible."
          ]
        },
        {
          heading: "Termination",
          paragraphs: [
            "You may stop using GotU or delete your account at any time. We may restrict or terminate access for material violations, security threats, fraud, unlawful use or conduct that harms GotU or other users."
          ]
        },
        {
          heading: "Disclaimers",
          paragraphs: [
            "GotU is provided on an as-available basis. To the extent permitted by law, we do not guarantee uninterrupted operation, error-free AI output, academic outcomes, data recovery or compatibility with every device or third-party service."
          ]
        },
        {
          heading: "Limitation of liability",
          paragraphs: [
            "To the extent permitted by law, Decisiv Labs will not be liable for indirect, incidental, special or consequential losses arising from your use of GotU. Nothing in these Terms excludes rights or liability that cannot legally be excluded."
          ]
        },
        {
          heading: "Governing law",
          paragraphs: [
            "These Terms are governed by the laws of Ontario and the applicable federal laws of Canada, without limiting mandatory consumer protections that apply where you live."
          ]
        },
        {
          heading: "Contact",
          paragraphs: [
            "Questions about these Terms can be sent to ravindertulsianidba@gmail.com."
          ]
        },
      ]}
    />
  );
}
