import type { Metadata } from "next";
import { Check } from "lucide-react";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { garments, tiers, zones } from "@/lib/config";
import { rs } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Stitching Prices",
  description: "Transparent ladies suit stitching prices in Lahore — no surprises at delivery.",
};

export default function PricingPage() {
  return (
    <>
      <PageHero
        eyebrow="Pricing"
        title={
          <>
            Clear prices. <em className="text-wine">No surprises at delivery.</em>
          </>
        }
        body="Base price + the design details you choose + delivery speed. You see the exact total before you pay."
      />
      <section className="py-20">
        <Container className="grid gap-14 lg:grid-cols-[1.3fr_1fr]">
          <Reveal>
            <h2 className="text-3xl text-plum">Base stitching</h2>
            <table className="mt-8 w-full text-left">
              <thead className="text-xs tracking-wider text-muted uppercase">
                <tr className="border-b border-line">
                  <th className="py-3 font-semibold">Garment</th>
                  <th className="py-3 font-semibold">Standard time</th>
                  <th className="py-3 text-right font-semibold">From</th>
                </tr>
              </thead>
              <tbody>
                {garments.map((g) => (
                  <tr key={g.slug} className="border-b border-dashed border-line">
                    <td className="py-4">
                      <p className="font-medium">{g.name}</p>
                      <p className="text-sm text-muted">{g.blurb}</p>
                    </td>
                    <td className="py-4 text-sm text-muted">{g.days} days</td>
                    <td className="py-4 text-right font-semibold">{rs(g.basePrice)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-xs text-muted">Bridal prices are confirmed after consultation.</p>
          </Reveal>

          <div className="space-y-10">
            <div>
              <h2 className="text-3xl text-plum">Delivery speed</h2>
              <Stagger className="mt-8 space-y-3">
                {tiers.map((t) => (
                  <StaggerItem key={t.value} className="flex items-center justify-between rounded-[var(--radius-md)] border border-line p-5">
                    <div>
                      <p className="font-semibold">{t.label}</p>
                      <p className="text-sm text-muted">{t.days}</p>
                    </div>
                    <p className="font-semibold">{t.fee ? `+${rs(t.fee)}` : "Included"}</p>
                  </StaggerItem>
                ))}
              </Stagger>
            </div>
            <div>
              <h2 className="text-3xl text-plum">Pickup & delivery</h2>
              <ul className="mt-6 space-y-3 text-sm">
                {zones.map((z) => (
                  <li key={z.code} className="flex gap-3">
                    <Check className="mt-0.5 size-4 shrink-0 text-gold" />
                    <span>
                      <strong>Zone {z.code}:</strong> {rs(z.fee)} per trip, free on orders above {rs(z.freeAbove)}
                    </span>
                  </li>
                ))}
                <li className="flex gap-3">
                  <Check className="mt-0.5 size-4 shrink-0 text-gold" />
                  <span>Drop-off at our Garhi Shahu studio is always free.</span>
                </li>
              </ul>
            </div>
          </div>
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
