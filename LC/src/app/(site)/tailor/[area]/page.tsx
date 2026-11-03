import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CalendarClock, MapPin, Truck } from "lucide-react";
import { areas } from "@/lib/content/areas";
import { zones } from "@/lib/config";
import { breadcrumbLd, faqLd, JsonLd, localBusinessLd } from "@/lib/seo";
import { Container, CtaBand, PageHero, ServicesGrid } from "@/components/site/sections";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { ButtonLink } from "@/components/ui/button";
import { getSiteMedia } from "@/lib/data/public";
import { rs } from "@/lib/utils";

export function generateStaticParams() {
  return areas.map((a) => ({ area: a.slug }));
}

export async function generateMetadata({ params }: PageProps<"/tailor/[area]">): Promise<Metadata> {
  const { area: slug } = await params;
  const area = areas.find((a) => a.slug === slug);
  if (!area) return {};
  const title = `Ladies Tailor in ${area.name} — Doorstep Pickup & Delivery`;
  const description = `Online ladies suit stitching in ${area.name}, Lahore. Our riders collect your fabric (${area.pickupDays.toLowerCase()}), we stitch to your measurements and deliver back. ${area.popular.join(", ")}.`;
  return { title, description, alternates: { canonical: `/tailor/${area.slug}` }, openGraph: { title, description } };
}

export default async function AreaPage({ params }: PageProps<"/tailor/[area]">) {
  const { area: slug } = await params;
  const area = areas.find((a) => a.slug === slug);
  if (!area) notFound();
  const zone = zones.find((z) => z.code === area.zone)!;
  const media = await getSiteMedia();
  const others = areas.filter((a) => a.slug !== area.slug);

  const faqs = [
    { q: `Do you pick up fabric in ${area.name}?`, a: `Yes. Laraib riders collect fabric in ${area.name} — ${area.pickupDays.toLowerCase()}. You choose the slot at checkout and give the rider a 4-digit handover code.` },
    { q: `What does pickup and delivery cost in ${area.name}?`, a: `${area.name} is in our Zone ${zone.code}: ${rs(zone.fee)} per trip, and free on orders above ${rs(zone.freeAbove)}.` },
    { q: "How long does stitching take?", a: "Standard 7–10 days, Priority 4–5 days and Express in 48 hours. The estimated delivery date is shown before you pay." },
    { q: "Can someone measure me at home?", a: `Yes — book a home measurement visit when you order and a trained Laraib measurer (female staff by default) will visit ${area.name} with the rider.` },
  ];

  return (
    <>
      <JsonLd data={[localBusinessLd([area.name, "Lahore"]), breadcrumbLd([{ name: "Areas we serve", path: "/tailor" }, { name: area.name, path: `/tailor/${area.slug}` }]), faqLd(faqs)]} />
      <PageHero
        eyebrow={`Ladies tailor · ${area.name}`}
        title={
          <>
            Suit stitching in {area.name}, <em className="text-wine">collected from your door.</em>
          </>
        }
        body={area.intro}
      />

      <section className="py-20">
        <Container className="grid gap-12 lg:grid-cols-[1fr_1.2fr]">
          <Stagger className="space-y-4">
            {[
              { icon: Truck, label: "Pickup & delivery", value: `${rs(zone.fee)} per trip · free above ${rs(zone.freeAbove)}` },
              { icon: CalendarClock, label: "Pickup days", value: area.pickupDays },
              { icon: MapPin, label: "From our workshop", value: `About ${area.distanceKm} km from Garhi Shahu` },
            ].map(({ icon: Icon, label, value }) => (
              <StaggerItem key={label} className="flex gap-4 rounded-[var(--radius-lg)] border border-line p-5">
                <Icon className="mt-0.5 size-5 shrink-0 text-gold" strokeWidth={1.5} />
                <div>
                  <p className="text-xs font-semibold tracking-[0.18em] text-muted uppercase">{label}</p>
                  <p className="mt-1">{value}</p>
                </div>
              </StaggerItem>
            ))}
            <ButtonLink href="/order" size="lg" className="mt-4">
              Book a pickup in {area.name}
            </ButtonLink>
          </Stagger>
          <Reveal>
            <h2 className="text-3xl text-plum">Where we collect in {area.name}</h2>
            <ul className="mt-6 flex flex-wrap gap-2">
              {area.sectors.map((s) => (
                <li key={s} className="rounded-full border border-line px-4 py-1.5 text-sm">
                  {s}
                </li>
              ))}
            </ul>
            <h3 className="mt-10 text-xl text-plum">Most ordered here</h3>
            <ul className="mt-4 space-y-2 text-muted">
              {area.popular.map((p) => (
                <li key={p}>— {p}</li>
              ))}
            </ul>
          </Reveal>
        </Container>
      </section>

      <section className="bg-cream/60 py-20">
        <Container>
          <h2 className="mb-10 text-3xl text-plum">What we stitch for {area.name}</h2>
          <ServicesGrid media={media} />
        </Container>
      </section>

      <section className="py-20">
        <Container className="grid gap-14 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <h2 className="text-3xl text-plum">Questions from {area.name}</h2>
            <div className="mt-8 divide-y divide-line border-y border-line">
              {faqs.map((f) => (
                <details key={f.q} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-6">
                    {f.q}
                    <span className="font-display text-2xl text-gold transition-transform group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-muted">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
          <div>
            <h2 className="text-xl text-plum">Other areas we serve</h2>
            <ul className="mt-5 grid grid-cols-2 gap-2 text-sm">
              {others.map((a) => (
                <li key={a.slug}>
                  <Link href={`/tailor/${a.slug}`} className="link-thread text-ink/80 hover:text-plum">
                    Ladies tailor in {a.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
