import type { Metadata } from 'next';

import { breadcrumbs, JsonLd, ORG_ID, absoluteUrl, pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, ArrowUpRight, Check, Target } from 'lucide-react';
import { process, serviceDetails, services } from '@/data/services';
import { getProduct } from '@/data/products';
import { Button } from '@/components/ui/primitives';
import ServiceIcon from '@/components/ui/ServiceIcon';
import { Aurora } from '@/components/motion/Effects';
import Reveal from '@/components/ui/Reveal';
import CtaBand from '@/components/sections/CtaBand';
import Automation from '@/components/sections/Automation';
import InfinityLoop from '@/components/sections/InfinityLoop';
import ScrapingShowcase from '@/components/sections/ScrapingShowcase';
import CrmShowcase from '@/components/sections/CrmShowcase';

export function generateStaticParams() {
  return services.map((s) => ({ id: s.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const s = services.find((x) => x.id === id);
  return s ? pageMeta({ title: s.title, description: `${s.summary} ${serviceDetails[s.id].intro}`.slice(0, 300), path: `/services/${s.id}`, keywords: [s.title, ...s.deliverables] }) : {};
}

export default async function ServicePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = services.find((x) => x.id === id);
  if (!s) notFound();
  const d = serviceDetails[s.id];
  const related = d.related.map(getProduct).filter((p) => !!p);
  const others = services.filter((x) => x.id !== s.id).slice(0, 4);

  return (
    <>
      <JsonLd
        data={[
          breadcrumbs([
            { name: 'Services', path: '/services' },
            { name: s.title, path: `/services/${s.id}` },
          ]),
          {
            '@context': 'https://schema.org',
            '@type': 'Service',
            name: s.title,
            serviceType: s.title,
            description: d.intro,
            url: absoluteUrl(`/services/${s.id}`),
            provider: { '@id': ORG_ID },
            areaServed: 'Worldwide',
            hasOfferCatalog: {
              '@type': 'OfferCatalog',
              name: `${s.title} deliverables`,
              itemListElement: s.deliverables.map((x) => ({ '@type': 'Offer', itemOffered: { '@type': 'Service', name: x } })),
            },
          },
        ]}
      />
      <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
        <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
        <Aurora />
        <div className="container-x py-16 sm:py-20">
          <Link href="/services" className="inline-flex items-center gap-1 text-sm font-medium text-fg-muted hover:text-brand">
            <ArrowLeft className="size-4" /> All services
          </Link>
          <span className="mt-8 grid size-14 place-items-center rounded-2xl bg-cta text-on-cta shadow-[0_12px_30px_-8px_var(--cta)]">
            <ServiceIcon name={s.icon} className="size-7" />
          </span>
          <h1 className="mt-6 max-w-3xl text-4xl font-extrabold leading-[1.05] sm:text-6xl">{s.title}</h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-fg-muted">{d.intro}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href={`/contact?service=${s.id}`} size="lg" arrow>
              Discuss your project
            </Button>
            <Button href="/pricing" size="lg" variant="secondary">
              See pricing
            </Button>
          </div>
        </div>
      </section>

      {s.id === 'web-scraping' ? <ScrapingShowcase /> : s.id === 'crm' ? <CrmShowcase /> : s.id === 'automation' ? <Automation /> : <InfinityLoop compact />}

      <section className="container-x grid gap-6 py-20 lg:grid-cols-[1.3fr_1fr]">
        <Reveal>
          <div className="card h-full p-8">
            <h2 className="text-2xl font-bold">What you get</h2>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2">
              {s.deliverables.map((x) => (
                <li key={x} className="flex items-start gap-3 rounded-xl bg-muted p-4 text-sm font-medium">
                  <Check className="mt-0.5 size-4 shrink-0 text-accent" /> {x}
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
        <Reveal delay={100}>
          <div className="night h-full rounded-[20px] p-8">
            <h2 className="text-2xl font-bold">Outcomes</h2>
            <ul className="mt-6 space-y-4">
              {d.outcomes.map((o) => (
                <li key={o} className="flex gap-3">
                  <Target className="mt-0.5 size-5 shrink-0 text-lime" />
                  <span className="text-white/85">{o}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </section>

      <section className="container-x pb-20">
        <h2 className="text-2xl font-bold sm:text-3xl">How we deliver</h2>
        <ol className="mt-8 grid gap-4 md:grid-cols-5">
          {process.map((p, i) => (
            <Reveal as="li" key={p.step} delay={i * 70}>
              <div className="card h-full p-5">
                <span className="font-display text-sm font-bold text-brand">{p.step}</span>
                <h3 className="mt-2 font-bold">{p.title}</h3>
                <p className="mt-1 text-sm text-fg-muted">{p.text}</p>
              </div>
            </Reveal>
          ))}
        </ol>
      </section>

      {related.length > 0 && (
        <section className="container-x pb-20">
          <h2 className="text-2xl font-bold sm:text-3xl">Proof in production</h2>
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {related.map((p) => (
              <Link key={p!.slug} href={`/products/${p!.slug}`} className="card spotlight group p-6 transition hover:-translate-y-1">
                <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: p!.accent }}>
                  {p!.cloud}
                </span>
                <h3 className="mt-2 text-lg font-bold group-hover:text-brand">{p!.name}</h3>
                <p className="mt-1 text-sm text-fg-muted">{p!.tagline}</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section className="container-x pb-12">
        <h2 className="text-lg font-bold">Other services</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {others.map((o) => (
            <Link key={o.id} href={`/services/${o.id}`} className="inline-flex items-center gap-1 rounded-full border border-line px-4 py-2 text-sm font-medium text-fg-muted transition hover:border-brand hover:text-brand">
              {o.title} <ArrowUpRight className="size-3.5" />
            </Link>
          ))}
        </div>
      </section>

      <CtaBand />
    </>
  );
}
