import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { industries } from '@/data/content';
import { getProduct } from '@/data/products';
import PageHeader from '@/components/ui/PageHeader';
import Reveal from '@/components/ui/Reveal';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Industries',
  description: 'Industry software for sports & media, agriculture, e-commerce, finance & retail, education and security — built and run by MTK Codex.',
  path: '/industries',
  keywords: ['industry software solutions', 'agritech software', 'edtech software', 'sports tech software', 'fintech software'],
});

export default function IndustriesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Industries"
        title={
          <>
            Industry know-how, <span className="text-gradient">built into the software.</span>
          </>
        }
        text="We've shipped production platforms across six industries. Pick yours to see the challenges we solve and the products ready for you."
      />
      <section className="container-x grid gap-5 py-20 sm:grid-cols-2 lg:grid-cols-3">
        {industries.map((ind, i) => {
          const p = getProduct(ind.product)!;
          return (
            <Reveal key={ind.id} delay={(i % 3) * 80}>
              <Link href={`/industries/${ind.id}`} className="card spotlight group relative flex h-full flex-col overflow-hidden p-7 transition hover:-translate-y-1 hover:shadow-float">
                <div className="absolute -right-14 -top-14 size-40 rounded-full opacity-20 blur-2xl transition group-hover:opacity-40" style={{ background: p.accent }} />
                <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: p.accent }}>
                  {ind.name}
                </span>
                <h2 className="mt-3 text-xl font-bold">{ind.headline}</h2>
                <p className="mt-3 flex-1 text-sm leading-relaxed text-fg-muted">{ind.text}</p>
                <p className="mt-5 text-xs text-fg-subtle">
                  Featured: <strong className="text-fg">{p.name}</strong>
                </p>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand">
                  Explore <ArrowUpRight className="size-4 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </span>
              </Link>
            </Reveal>
          );
        })}
      </section>
      <CtaBand title="Don't see your industry?" text="Our platform adapts to any domain. Tell us how your business works and we'll show you what's possible." />
    </>
  );
}
