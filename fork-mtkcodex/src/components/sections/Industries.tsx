'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { industries } from '@/data/content';
import { getProduct } from '@/data/products';
import { SectionHeading } from '@/components/ui/primitives';

export default function Industries() {
  const [active, setActive] = useState(industries[0].id);
  const ind = industries.find((i) => i.id === active)!;
  const product = getProduct(ind.product)!;

  return (
    <section id="industries" className="container-x scroll-mt-24 py-20">
      <SectionHeading
        eyebrow="Industries"
        title="Built for the way your industry works."
        text="Domain-ready software for the sectors we know best — and the engineering depth to take on any other."
      />
      <div className="mt-12 grid gap-6 lg:grid-cols-[280px_1fr]">
        <div role="tablist" aria-orientation="vertical" className="flex gap-2 overflow-x-auto [scrollbar-width:none] lg:flex-col">
          {industries.map((i) => (
            <button
              key={i.id}
              type="button"
              role="tab"
              aria-selected={i.id === active}
              onClick={() => setActive(i.id)}
              className={`shrink-0 rounded-xl px-4 py-3 text-left text-sm font-semibold transition ${
                i.id === active ? 'bg-cta text-on-cta shadow-card' : 'text-fg-muted hover:bg-muted hover:text-fg'
              }`}
            >
              {i.name}
            </button>
          ))}
        </div>
        <div role="tabpanel" className="card relative overflow-hidden p-8 sm:p-10">
          <div className="absolute -right-20 -top-20 size-72 rounded-full opacity-20 blur-3xl" style={{ background: product.accent }} />
          <p className="eyebrow">{ind.name}</p>
          <h3 className="mt-3 max-w-xl text-2xl font-bold sm:text-3xl">{ind.headline}</h3>
          <p className="mt-3 max-w-xl text-fg-muted">{ind.text}</p>
          <ul className="mt-6 grid gap-3 sm:grid-cols-3">
            {ind.wins.map((w) => (
              <li key={w} className="flex items-start gap-2 rounded-xl bg-muted p-4 text-sm font-medium">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" /> {w}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-col gap-4 rounded-2xl border border-line p-5 sm:flex-row sm:items-center">
            <span className="size-3 shrink-0 rounded" style={{ background: product.accent }} />
            <div className="flex-1">
              <p className="text-xs text-fg-subtle">Featured solution</p>
              <p className="font-semibold">
                {product.name} — {product.tagline}
              </p>
            </div>
            <div className="flex gap-4">
              <Link href={`/industries/${ind.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-brand">
                Industry details <ArrowRight className="size-4" />
              </Link>
              <Link href={`/products/${product.slug}`} className="inline-flex items-center gap-1 text-sm font-semibold text-fg-muted hover:text-brand">
                View product
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
