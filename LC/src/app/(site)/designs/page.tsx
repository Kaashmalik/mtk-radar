import type { Metadata } from "next";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { Lookbook } from "@/components/site/lookbook";
import { getDesigns } from "@/lib/data/public";

export const metadata: Metadata = {
  title: "Lookbook — Suit Designs to Order",
  description: "Browse neckline, sleeve and daman designs for everyday, Eid, party and formal wear — then order the look stitched to your measurements.",
};

export default async function DesignsPage() {
  const designs = await getDesigns();
  return (
    <>
      <PageHero
        eyebrow="Lookbook"
        title={
          <>
            Pick a look. <em className="text-wine">We&rsquo;ll cut it to you.</em>
          </>
        }
        body="Every design opens the order form with its neckline, sleeves and daman already chosen — change anything you like."
      />
      <section className="py-20">
        <Container>
          <Lookbook designs={designs} />
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
