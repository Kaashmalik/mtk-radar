import type { Metadata } from "next";
import { LegalPage } from "@/components/site/legal-page";
import { brand } from "@/lib/config";

export const metadata: Metadata = { title: "Privacy Policy", description: "How Laraib Creative collects, uses and protects your personal information.", alternates: { canonical: "/privacy" } };

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Privacy Policy"
      path="/privacy"
      updated="4 November 2026"
      sections={[
        {
          heading: "Who we are",
          body: [`${brand.name} is a ladies tailoring business with its studio and warehouse at ${brand.address}. This policy explains what personal information we collect through ${brand.domain}, why, and the choices you have. Contact us at ${brand.email} or ${brand.phone} with any privacy question.`],
        },
        {
          heading: "Information we collect",
          body: [
            [
              "Contact details: name, mobile/WhatsApp number, email address, delivery address and landmark.",
              "Order details: garment and design choices, reference pictures you upload, delivery and pickup preferences.",
              "Measurements and fit notes, saved in measurement profiles you control.",
              "Payment information: the payment slip or transaction ID you send us. We never ask for or store card numbers or wallet PINs.",
              "Photos taken at handover (fabric collected, suit delivered) and, only with your consent, photos of your finished suit for our gallery — never showing your face.",
              "Technical data such as device type and pages visited, used to keep the site secure and working.",
            ],
          ],
        },
        {
          heading: "How we use it",
          body: [
            [
              "To stitch, deliver and support your order, including WhatsApp, SMS and email updates about it.",
              "To verify payments and keep accounting records.",
              "To prevent fraud and abuse of our forms.",
              "To improve our service. We do not sell your personal information.",
            ],
          ],
        },
        {
          heading: "Cookies and advertising",
          body: [
            "We use essential cookies to keep you signed in and to remember your order draft. With your permission (\"Accept all\" in the cookie banner) we also allow Google AdSense to show advertising on our Style Journal pages. Google and its partners may use cookies to show ads based on your visits to this and other websites.",
            "You can opt out of personalised advertising at any time in Google's Ads Settings (adssettings.google.com), and you can change your choice on this site by clearing your browser's site data. Learn how Google uses information from sites that use its services at policies.google.com/technologies/partner-sites.",
          ],
        },
        {
          heading: "Who we share it with",
          body: [
            "We share information only with service providers that help us run the business, under their own security and privacy commitments: our hosting and database providers, our image storage provider, WhatsApp (Meta) for order messages, couriers for deliveries outside Lahore, and Google for advertising as described above. Our own riders see only the name, phone, address and cash amount needed for their job.",
          ],
        },
        {
          heading: "Keeping your information safe",
          body: [
            "Payment slips, receipts and handover photos are stored privately and are visible only to authorised staff. Staff access is role-based and changes to orders and payments are logged. We keep order records for as long as needed for accounting and warranty purposes, then delete or anonymise them.",
          ],
        },
        {
          heading: "Your choices",
          body: [
            "You can view and edit your measurement profiles in your account, ask us for a copy of the information we hold about you, ask us to correct it, or ask us to delete your account. Gallery photos of your order are removed on request. Contact us using the details above.",
          ],
        },
        {
          heading: "Children",
          body: ["Our services are intended for adults. Orders for children are placed by a parent or guardian."],
        },
        {
          heading: "Changes",
          body: ["We will update this page if our practices change. The date at the top shows the latest version."],
        },
      ]}
    />
  );
}
