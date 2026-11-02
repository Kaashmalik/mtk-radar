import type { Metadata } from 'next';

import { breadcrumbs, JsonLd, ORG_ID, absoluteUrl, pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, ArrowRight, Check, ExternalLink } from 'lucide-react';
import { getProduct, products } from '@/data/products';
import { testimonials } from '@/data/content';
import { site } from '@/data/site';
import { Button, StatusBadge } from '@/components/ui/primitives';
import { GithubIcon } from '@/components/ui/BrandIcons';
import ProductDemo from '@/components/demo/ProductDemo';
import Reveal from '@/components/ui/Reveal';
import CtaBand from '@/components/sections/CtaBand';
import AutomationFlow from '@/components/sections/AutomationFlow';

export function generateStaticParams() {
  return products.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const p = getProduct(slug);
  if (!p) return {};
  return pageMeta({ title: `${p.name} — ${p.category} Software`, description: p.description, path: `/products/${p.slug}`, keywords: [p.name, p.category, p.cloud, ...p.audience] });
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = getProduct(slug);
  if (!p) notFound();

  const review = testimonials.find((t) => t.product === p.slug);
  const idx = products.findIndex((x) => x.slug === p.slug);
  const next = products[(idx + 1) % products.length];

  return (
    <>
      <JsonLd
        data={[
          breadcrumbs([
            { name: 'Products', path: '/products' },
            { name: p.name, path: `/products/${p.slug}` },
          ]),
          {
            '@context': 'https://schema.org',
            '@type': 'SoftwareApplication',
            name: p.name,
            description: p.overview,
            url: absoluteUrl(`/products/${p.slug}`),
            applicationCategory: p.platforms.some((x) => ['iOS', 'Android'].includes(x)) ? 'MobileApplication' : p.platforms.some((x) => ['Windows', 'macOS', 'Linux'].includes(x)) ? 'DesktopEnhancementApplication' : 'BusinessApplication',
            applicationSubCategory: p.category,
            operatingSystem: p.platforms.join(', '),
            featureList: p.features.map((f) => f.title).join(', '),
            publisher: { '@id': ORG_ID },
            offers: { '@type': 'Offer', url: absoluteUrl(`/contact?intent=demo&product=${p.slug}`), availability: 'https://schema.org/InStock' },
            ...(review
              ? { review: { '@type': 'Review', reviewBody: review.quote, author: { '@type': 'Person', name: review.name }, reviewRating: { '@type': 'Rating', ratingValue: review.rating, bestRating: 5 } } }
              : {}),
          },
        ]}
      />
      <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
        <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
        <div className="glow -z-10 right-[-5%] top-[-20%] size-[480px] opacity-40" style={{ background: p.accent }} />
        <div className="container-x grid items-center gap-12 pb-20 pt-10 lg:grid-cols-2">
          <div>
            <Link href="/products" className="inline-flex items-center gap-1 text-sm font-medium text-fg-muted hover:text-brand">
              <ArrowLeft className="size-4" /> All products
            </Link>
            <div className="mt-6 flex items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: p.accent }}>
                {p.cloud}
              </span>
              <StatusBadge status={p.status} />
            </div>
            <h1 className="mt-3 text-4xl font-extrabold leading-[1.05] sm:text-6xl">{p.name}</h1>
            <p className="mt-4 text-xl font-medium">{p.tagline}</p>
            <p className="mt-4 leading-relaxed text-fg-muted">{p.overview}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button href={`/contact?intent=demo&product=${p.slug}`} size="lg" arrow>
                Book a demo
              </Button>
              {p.liveUrl && (
                <Button href={p.liveUrl} external size="lg" variant="secondary">
                  Open live app <ExternalLink className="size-4" />
                </Button>
              )}
              {p.githubUrl && (
                <Button href={p.githubUrl} external size="lg" variant="ghost">
                  <GithubIcon className="size-4" /> Source
                </Button>
              )}
              {p.privateSource && (
                <Button href={site.social.github} external size="lg" variant="ghost">
                  <GithubIcon className="size-4" /> {site.founder.name.split(' ').at(-1)} on GitHub
                </Button>
              )}
            </div>
            {p.privateSource && (
              <p className="mt-3 text-sm text-fg-subtle">
                Private codebase — a live walkthrough of the code and pipeline is available on request.
              </p>
            )}
          </div>
          <ProductDemo product={p} />
        </div>
      </section>

      <section className="container-x py-16">
        <div className="grid gap-px overflow-hidden rounded-3xl border border-line bg-line sm:grid-cols-3">
          {p.metrics.map((m) => (
            <div key={m.label} className="bg-elevated p-8 text-center">
              <p className="font-display text-4xl font-extrabold" style={{ color: p.accent }}>
                {m.value}
              </p>
              <p className="mt-2 text-sm text-fg-muted">{m.label}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="container-x pb-16">
        <h2 className="text-3xl font-bold sm:text-4xl">Key capabilities</h2>
        <div className="mt-8 grid gap-5 sm:grid-cols-2">
          {p.features.map((f, i) => (
            <Reveal key={f.title} delay={i * 70}>
              <div className="card h-full p-7">
                <span className="grid size-10 place-items-center rounded-xl text-white" style={{ background: p.accent }}>
                  <Check className="size-5" />
                </span>
                <h3 className="mt-5 text-xl font-bold">{f.title}</h3>
                <p className="mt-2 text-fg-muted">{f.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {p.demo === 'radar' && <AutomationFlow accent={p.accent} />}

      <section className="container-x grid gap-6 pb-16 lg:grid-cols-3">
        <div className="card p-7">
          <h3 className="text-lg font-bold">Built for</h3>
          <ul className="mt-4 space-y-2 text-fg-muted">
            {p.audience.map((a) => (
              <li key={a} className="flex items-center gap-2">
                <span className="size-1.5 rounded-full" style={{ background: p.accent }} /> {a}
              </li>
            ))}
          </ul>
        </div>
        <div className="card p-7">
          <h3 className="text-lg font-bold">Platforms</h3>
          <div className="mt-4 flex flex-wrap gap-2">
            {p.platforms.map((x) => (
              <span key={x} className="rounded-full bg-muted px-3 py-1 text-sm font-medium">
                {x}
              </span>
            ))}
          </div>
        </div>
        <div className="card p-7">
          <h3 className="text-lg font-bold">Technology</h3>
          <div className="mt-4 flex flex-wrap gap-2">
            {p.stack.map((x) => (
              <span key={x} className="rounded-full border border-line px-3 py-1 text-xs text-fg-muted">
                {x}
              </span>
            ))}
          </div>
        </div>
      </section>

      {review && (
        <section className="container-x pb-16">
          <figure className="card p-8 sm:p-12">
            <blockquote className="font-display text-xl font-medium leading-relaxed sm:text-2xl">&ldquo;{review.quote}&rdquo;</blockquote>
            <figcaption className="mt-6 text-sm text-fg-muted">
              <strong className="text-fg">{review.name}</strong> · {review.role}, {review.company}
            </figcaption>
          </figure>
        </section>
      )}

      <section className="container-x pb-8">
        <Link href={`/products/${next.slug}`} className="card group flex items-center justify-between gap-4 p-6 transition hover:border-brand">
          <div>
            <p className="text-xs text-fg-subtle">Next product</p>
            <p className="text-lg font-bold group-hover:text-brand">
              {next.name} <span className="font-normal text-fg-muted">— {next.tagline}</span>
            </p>
          </div>
          <ArrowRight className="size-5 shrink-0 text-brand transition group-hover:translate-x-1" />
        </Link>
      </section>

      <CtaBand title={`Launch ${p.name} for your business.`} text="Get a guided walkthrough, pricing for your size, and a launch plan — free and with no obligation." />
    </>
  );
}
