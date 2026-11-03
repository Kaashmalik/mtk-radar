import type { Metadata } from "next";
import { Container, CraftSection, CtaBand, PageHero, Promises } from "@/components/site/sections";
import { Reveal } from "@/components/motion/reveal";
import { breadcrumbLd, JsonLd } from "@/lib/seo";
import { getSiteMedia } from "@/lib/data/public";
import { brand } from "@/lib/config";

export const metadata: Metadata = {
  title: "About Laraib Creative",
  description: "A Lahore tailoring house that brings master-tailor craftsmanship online — with our own riders, saved measurements and delivery dates we keep.",
  alternates: { canonical: "/about" },
};

export default async function AboutPage() {
  const media = await getSiteMedia();
  return (
    <>
      <JsonLd data={breadcrumbLd([{ name: "About", path: "/about" }])} />
      <PageHero
        eyebrow="About us"
        title={
          <>
            A tailoring house, <em className="text-wine">rebuilt around you.</em>
          </>
        }
        body="Laraib Creative pairs a master tailor's workshop in Garhi Shahu with a modern way to order — so getting a suit stitched no longer means repeated trips, missed Eid deadlines and guesswork."
      />
      <section className="py-20">
        <Container className="grid gap-12 md:grid-cols-2">
          <Reveal>
            <h2 className="text-3xl text-plum">Two partners, one promise</h2>
            <p className="mt-4 leading-relaxed text-ink/85">
              Our stitching partner runs the workshop: cutting, stitching, finishing and quality checks by experienced karigars. Our technology partner built the platform you are using — online ordering,
              saved measurements, live tracking and our rider system. Together we answer to one standard: the suit you ordered, fitting as promised, on the date we gave you.
            </p>
          </Reveal>
          <Reveal delay={0.1}>
            <h2 className="text-3xl text-plum">Visit the studio</h2>
            <p className="mt-4 leading-relaxed text-ink/85">
              You are always welcome at {brand.address}. Drop off fabric, get measured in our fitting room or talk through a bridal design. Open {brand.hours}.
            </p>
          </Reveal>
        </Container>
      </section>
      <CraftSection media={media} />
      <Promises />
      <CtaBand />
    </>
  );
}
