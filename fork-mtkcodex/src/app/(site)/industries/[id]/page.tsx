import type { Metadata } from 'next';

import { breadcrumbs, JsonLd, pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2 } from 'lucide-react';
import { industries, industryChallenges } from '@/data/content';
import { getProduct } from '@/data/products';
import { services } from '@/data/services';
import { Button } from '@/components/ui/primitives';
import ServiceIcon from '@/components/ui/ServiceIcon';
import ProductDemo from '@/components/demo/ProductDemo';
import Reveal from '@/components/ui/Reveal';
import CtaBand from '@/components/sections/CtaBand';

export function generateStaticParams() {
  return industries.map((i) => ({ id: i.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const ind = industries.find((i) => i.id === id);
  return ind ? pageMeta({ title: `${ind.name} Software Solutions`, description: `${ind.headline} ${ind.text}`, path: `/industries/${ind.id}`, keywords: [`${ind.name} software`, ...ind.wins] }) : {};
}

export default async function IndustryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ind = industries.find((i) => i.id === id);
  if (!ind) notFound();
  const product = getProduct(ind.product)!;
  const extra = industryChallenges[ind.id];
  const related = services.filter((s) => extra.services.includes(s.id));

  return (
    <>
      <JsonLd
        data={breadcrumbs([
          { name: 'Industries', path: '/industries' },
          { name: ind.name, path: `/industries/${ind.id}` },
        ])}
      />
      <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
        <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
        <div className="aurora-1 glow -z-10 right-[-5%] top-[-20%] size-[480px] opacity-35" style={{ background: product.accent }} />
        <div className="container-x grid items-center gap-12 pb-20 pt-10 lg:grid-cols-2">
          <div>
            <Link href="/industries" className="inline-flex items-center gap-1 text-sm font-medium text-fg-muted hover:text-brand">
              <ArrowLeft className="size-4" /> All industries
            </Link>
            <p className="eyebrow mt-6">{ind.name}</p>
            <h1 className="mt-3 text-4xl font-extrabold leading-[1.05] sm:text-5xl">{ind.headline}</h1>
            <p className="mt-5 text-lg leading-relaxed text-fg-muted">{ind.text}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button href={`/contact?intent=demo&product=${product.slug}`} size="lg" arrow>
                Book a demo
              </Button>
              <Button href={`/products/${product.slug}`} size="lg" variant="secondary">
                Explore {product.name}
              </Button>
            </div>
          </div>
          <ProductDemo product={product} />
        </div>
      </section>

      <section className="container-x grid gap-6 py-20 lg:grid-cols-2">
        <Reveal>
          <div className="card h-full p-8">
            <h2 className="text-2xl font-bold">The challenge</h2>
            <ul className="mt-6 space-y-4">
              {extra.challenges.map((c) => (
                <li key={c} className="flex gap-3">
                  <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-500" />
                  <span className="text-fg-muted">{c}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
        <Reveal delay={100}>
          <div className="card h-full p-8">
            <h2 className="text-2xl font-bold">How we solve it</h2>
            <ul className="mt-6 space-y-4">
              {[...ind.wins, ...product.features.slice(0, 2).map((f) => f.title)].map((w) => (
                <li key={w} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-accent" />
                  <span className="font-medium">{w}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </section>

      <section className="container-x pb-20">
        <h2 className="text-2xl font-bold sm:text-3xl">Recommended services</h2>
        <div className="mt-8 grid gap-5 md:grid-cols-3">
          {related.map((s) => (
            <Link key={s.id} href={`/services/${s.id}`} className="card spotlight group p-6 transition hover:-translate-y-1 hover:border-brand">
              <ServiceIcon name={s.icon} className="size-6 text-brand" />
              <h3 className="mt-4 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-sm text-fg-muted">{s.summary}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand">
                Learn more <ArrowRight className="size-4" />
              </span>
            </Link>
          ))}
        </div>
      </section>

      <CtaBand title={`Let's modernise ${ind.name.toLowerCase()} together.`} />
    </>
  );
}
