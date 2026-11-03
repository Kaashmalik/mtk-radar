import type { Metadata } from "next";
import { Container, CtaBand, MeasurementOptions, PageHero, ServicesGrid } from "@/components/site/sections";
import { Reveal } from "@/components/motion/reveal";
import { addons } from "@/lib/config";
import { getSiteMedia } from "@/lib/data/public";
import { rs } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Ladies Suit Stitching Services in Lahore",
  description: "Simple, designer, party, maxi and bridal stitching with doorstep pickup across Lahore.",
};

export default async function ServicesPage() {
  return (
    <>
      <PageHero
        eyebrow="Services"
        title={
          <>
            Every cut, <em className="text-wine">every occasion.</em>
          </>
        }
        body="From everyday lawn to bridal lehengas — stitched by master tailors at our Garhi Shahu workshop."
      />
      <section className="py-20">
        <Container>
          <ServicesGrid media={await getSiteMedia()} />
        </Container>
      </section>
      <section className="pb-24">
        <Container>
          <Reveal className="rounded-[var(--radius-lg)] border border-line p-8 md:p-12">
            <p className="eyebrow">Add-ons</p>
            <h2 className="mt-3 text-3xl text-plum">Finishing touches</h2>
            <ul className="mt-8 grid gap-x-12 gap-y-4 sm:grid-cols-2">
              {addons.map((a) => (
                <li key={a.value} className="flex items-baseline justify-between gap-4 border-b border-dashed border-line pb-3">
                  <span>{a.label}</span>
                  <span className="font-semibold">+{rs(a.price)}</span>
                </li>
              ))}
              <li className="flex items-baseline justify-between gap-4 border-b border-dashed border-line pb-3">
                <span>Alterations</span>
                <span className="font-semibold">from {rs(400)}</span>
              </li>
            </ul>
          </Reveal>
        </Container>
      </section>
      <MeasurementOptions />
      <div className="pt-24">
        <CtaBand />
      </div>
    </>
  );
}
