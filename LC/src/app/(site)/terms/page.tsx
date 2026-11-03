import type { Metadata } from "next";
import { LegalPage } from "@/components/site/legal-page";
import { brand } from "@/lib/config";

export const metadata: Metadata = { title: "Terms of Service", description: "The terms for ordering stitching services from Laraib Creative.", alternates: { canonical: "/terms" } };

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Terms of Service"
      path="/terms"
      updated="4 November 2026"
      sections={[
        {
          heading: "Orders",
          body: [
            `By placing an order on ${brand.domain} you ask ${brand.name} to stitch the garments you selected using the fabric you provide and the measurements you choose. An order is confirmed once we have verified your advance payment. Prices shown at checkout include stitching, chosen design options, urgency and pickup/delivery fees.`,
          ],
        },
        {
          heading: "Payments",
          body: [
            "We accept bank transfer, JazzCash, Easypaisa and Raast to the business accounts shown at checkout, and cash to our rider or at our studio. An advance (usually 50%) confirms your order; the balance is due on delivery. Only pay into accounts titled \"Laraib Creative\" shown on our website — we will never ask you to pay into a personal account over the phone.",
          ],
        },
        {
          heading: "Delivery dates",
          body: [
            "The estimated delivery date is calculated from the day we receive your fabric. If we miss a promised date for reasons within our control, we will tell you as early as possible and offer a remedy such as a refund of the urgency fee or a discount. Delays caused by late fabric, incorrect measurements provided by the customer, or events beyond our control are excluded.",
          ],
        },
        {
          heading: "Measurements and fit",
          body: [
            "We stitch to the measurements you give us, a garment you send for copying, our standard size you select, or measurements taken by our staff. Alterations needed because of measurements you supplied are offered at a reduced charge; alterations needed because of our error are free within 7 days of delivery.",
          ],
        },
        {
          heading: "Fabric",
          body: [
            "Please check that your fabric is sufficient for the design you choose. Handovers are photographed so the condition of your fabric is recorded. See our Refund, Alteration & Fabric Policy for what happens if fabric is short, damaged or lost.",
          ],
        },
        {
          heading: "Handover codes",
          body: ["Share your 4-digit handover code only with a Laraib rider at the moment of pickup or delivery. A completed handover with the correct code confirms you gave or received the items."],
        },
        {
          heading: "Reviews and content",
          body: ["Reviews must be your own honest experience of an order you received. We may decline to publish reviews that contain personal information, offensive content or are unrelated to our service, and we may reply publicly."],
        },
        {
          heading: "Contact",
          body: [`${brand.name}, ${brand.address}. ${brand.phone} · ${brand.email}.`],
        },
      ]}
    />
  );
}
