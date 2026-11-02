import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { products } from '@/data/products';
import { SectionHeading, StatusBadge } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

export default function ProductSuite() {
  return (
    <section id="products" className="container-x py-20">
      <SectionHeading
        eyebrow="Products"
        title={
          <>
            One partner. <span className="text-gradient">Seven ready-to-launch</span> SaaS clouds.
          </>
        }
        text="Proven, multi-tenant products you can subscribe to, white-label as your own, or use as the foundation for a custom build."
      />
      <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {products.map((p, i) => (
          <Reveal key={p.slug} delay={(i % 3) * 80} className={i === 0 ? 'lg:col-span-2' : ''}>
            <Link
              href={`/products/${p.slug}`}
              className="card spotlight group relative flex h-full flex-col overflow-hidden p-7 transition duration-300 hover:-translate-y-1 hover:shadow-float"
            >
              <div
                className="absolute -right-16 -top-16 size-48 rounded-full opacity-20 blur-2xl transition group-hover:opacity-40"
                style={{ background: p.accent }}
              />
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: p.accent }}>
                  {p.cloud}
                </span>
                <StatusBadge status={p.status} />
              </div>
              <h3 className="mt-4 text-2xl font-bold">{p.name}</h3>
              <p className="mt-1 text-sm font-medium text-fg-muted">{p.tagline}</p>
              <p className="mt-4 flex-1 text-sm leading-relaxed text-fg-muted">{p.description}</p>
              <div className="mt-6 flex flex-wrap gap-2">
                {p.metrics.map((m) => (
                  <span key={m.label} className="rounded-full bg-muted px-3 py-1 text-xs">
                    <strong className="font-semibold text-fg">{m.value}</strong> <span className="text-fg-subtle">{m.label}</span>
                  </span>
                ))}
              </div>
              <span className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-brand">
                Explore {p.name} <ArrowUpRight className="size-4 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </span>
            </Link>
          </Reveal>
        ))}
        <Reveal delay={160}>
          <Link
            href="/contact?intent=quote"
            className="group flex h-full flex-col justify-between rounded-[20px] border border-dashed border-line-strong p-7 transition hover:border-brand"
          >
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-brand">Custom Cloud</span>
              <h3 className="mt-4 text-2xl font-bold">Your next platform</h3>
              <p className="mt-3 text-sm leading-relaxed text-fg-muted">
                Have an idea or an existing system? We design and build it with the same production-grade foundation.
              </p>
            </div>
            <span className="mt-6 inline-flex items-center gap-1 text-sm font-semibold text-brand">
              Start a project <ArrowUpRight className="size-4" />
            </span>
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
