import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { areas } from "@/lib/content/areas";
import { zones } from "@/lib/config";
import { breadcrumbLd, JsonLd } from "@/lib/seo";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { Stagger, StaggerItem } from "@/components/motion/reveal";

export const metadata: Metadata = {
  title: "Areas We Serve — Ladies Tailor with Pickup Across Lahore",
  description: "Laraib riders collect fabric across Lahore: Gulberg, DHA, Cantt, Askari, Model Town, Shadman, Johar Town and Bahria Town.",
  alternates: { canonical: "/tailor" },
};

export default function AreasPage() {
  return (
    <>
      <JsonLd data={breadcrumbLd([{ name: "Areas we serve", path: "/tailor" }])} />
      <PageHero
        eyebrow="Areas we serve"
        title={
          <>
            Our riders, <em className="text-wine">across Lahore.</em>
          </>
        }
        body="Pickup and delivery from our Garhi Shahu workshop. Closer areas get same-day slots; farther areas run on fixed days so every trip is on time."
      />
      <section className="py-20">
        <Container>
          <Stagger className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {areas.map((a) => {
              const z = zones.find((x) => x.code === a.zone)!;
              return (
                <StaggerItem key={a.slug}>
                  <Link href={`/tailor/${a.slug}`} className="group flex h-full flex-col rounded-[var(--radius-lg)] border border-line p-6 transition-colors hover:border-plum">
                    <span className="text-xs font-semibold tracking-[0.18em] text-gold uppercase">Zone {a.zone} · {z.name}</span>
                    <span className="font-display mt-3 text-2xl text-plum">{a.name}</span>
                    <span className="mt-2 flex-1 text-sm text-muted">{a.pickupDays}</span>
                    <span className="mt-6 inline-flex items-center gap-1 text-sm text-plum">
                      Details <ArrowUpRight className="size-4 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                    </span>
                  </Link>
                </StaggerItem>
              );
            })}
          </Stagger>
          <p className="mt-10 text-sm text-muted">Outside these areas or outside Lahore? Courier your fabric to our studio — we&rsquo;ll courier it back stitched.</p>
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
