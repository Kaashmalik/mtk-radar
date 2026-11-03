import type { Metadata } from "next";
import Link from "next/link";
import { articles } from "@/lib/content/journal";
import { breadcrumbLd, JsonLd } from "@/lib/seo";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { Stagger, StaggerItem } from "@/components/motion/reveal";
import { formatDay } from "@/lib/pricing";

export const metadata: Metadata = {
  title: "Style Journal — Fit, Fabric & Design Guides",
  description: "Practical guides from our master tailors: measuring yourself, choosing necklines, Eid stitching timelines and caring for lawn, chiffon and khaddar.",
  alternates: { canonical: "/journal" },
};

export default function JournalPage() {
  const [lead, ...rest] = [...articles].sort((a, b) => b.published.localeCompare(a.published));
  return (
    <>
      <JsonLd data={breadcrumbLd([{ name: "Style Journal", path: "/journal" }])} />
      <PageHero
        eyebrow="Style Journal"
        title={
          <>
            Notes from <em className="text-wine">the cutting table.</em>
          </>
        }
        body="Fit, fabric and design guides written by the people who stitch your suits."
      />
      <section className="py-20">
        <Container>
          <Link href={`/journal/${lead.slug}`} className="group grid gap-8 border-b border-line pb-14 lg:grid-cols-[1.2fr_1fr] lg:items-end">
            <div>
              <p className="eyebrow">
                {lead.category} · {lead.readMinutes} min read
              </p>
              <h2 className="mt-4 text-[clamp(2rem,4vw,3.2rem)] leading-[1.05] text-plum group-hover:text-wine">{lead.title}</h2>
            </div>
            <div>
              <p className="text-lg text-muted">{lead.excerpt}</p>
              <p className="mt-4 text-sm text-plum">Read the guide →</p>
            </div>
          </Link>
          <Stagger className="mt-14 grid gap-10 md:grid-cols-3">
            {rest.map((a) => (
              <StaggerItem key={a.slug}>
                <Link href={`/journal/${a.slug}`} className="group block">
                  <p className="text-xs font-semibold tracking-[0.18em] text-gold uppercase">{a.category}</p>
                  <h3 className="mt-3 text-2xl text-plum group-hover:text-wine">{a.title}</h3>
                  <p className="mt-3 text-sm text-muted">{a.excerpt}</p>
                  <p className="mt-4 text-xs text-muted">
                    {formatDay(a.published)} · {a.readMinutes} min read
                  </p>
                </Link>
              </StaggerItem>
            ))}
          </Stagger>
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
