import type { Metadata } from "next";
import { LegalPage } from "@/components/site/legal-page";

export const metadata: Metadata = {
  title: "Refund, Alteration & Fabric Policy",
  description: "Free alterations within 7 days, cancellations, refunds and what happens if fabric is short or damaged.",
  alternates: { canonical: "/refund-policy" },
};

export default function RefundPolicyPage() {
  return (
    <LegalPage
      eyebrow="Policies"
      title="Refund, Alteration & Fabric Policy"
      path="/refund-policy"
      updated="4 November 2026"
      sections={[
        {
          heading: "Free alterations within 7 days",
          body: [
            "If your suit does not fit as ordered, tell us within 7 days of delivery through WhatsApp or your account. Our rider collects it (free within our pickup zones) and we alter it free of charge when the issue comes from our stitching or from measurements taken by our staff.",
          ],
        },
        {
          heading: "Cancellations",
          body: [
            [
              "Before your fabric is cut: full refund of your advance, minus any pickup trip already made.",
              "After cutting has started: the stitching charge cannot be refunded because the fabric has been cut to your design; we will complete and deliver the order.",
              "Express and Priority urgency fees are refunded if we miss the promised date for reasons within our control.",
            ],
          ],
        },
        {
          heading: "Refunds",
          body: ["Approved refunds are paid back to the same bank or wallet account the payment came from within 7 working days, and we send you proof of transfer."],
        },
        {
          heading: "If fabric is short",
          body: ["If your fabric is not enough for the chosen design, we contact you before cutting with options — a simpler design, a matching fabric we can source, or returning the fabric uncut."],
        },
        {
          heading: "If fabric is damaged or lost",
          body: [
            "Every handover is photographed and scanned, so we always know where your fabric is. In the rare case that fabric is damaged or lost while in our care, we will compensate you for its value based on your purchase receipt or a fair market estimate, in addition to refunding the stitching charge.",
          ],
        },
        {
          heading: "Not covered",
          body: [
            [
              "Shrinkage or colour bleeding caused by the fabric itself, or by washing that does not follow care instructions.",
              "Changes of mind about a design that was stitched as ordered.",
              "Alterations requested more than 7 days after delivery (available at our standard alteration rates).",
            ],
          ],
        },
      ]}
    />
  );
}
