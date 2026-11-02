'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Quote, Star } from 'lucide-react';
import { testimonials } from '@/data/content';
import { getProduct } from '@/data/products';
import { SectionHeading } from '@/components/ui/primitives';

export default function Testimonials({ heading = true }: { heading?: boolean }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = testimonials.length;

  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => setI((x) => (x + 1) % n), 7000);
    return () => clearInterval(id);
  }, [paused, n]);

  const t = testimonials[i];
  const product = getProduct(t.product);

  return (
    <section className="container-x py-20" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      {heading && (
        <SectionHeading eyebrow="Customer stories" title="Trusted by teams who run on our software." />
      )}
      <div className="mt-12 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <figure className="card relative overflow-hidden p-8 sm:p-12" aria-live="polite">
          <Quote className="absolute right-8 top-8 size-16 text-brand opacity-10" />
          <div className="flex gap-1 text-amber-500">
            {Array.from({ length: t.rating }).map((_, k) => (
              <Star key={k} className="size-5 fill-current" />
            ))}
          </div>
          <blockquote key={i} className="word-in mt-6 font-display text-xl font-medium leading-relaxed sm:text-2xl">
            &ldquo;{t.quote}&rdquo;
          </blockquote>
          <figcaption className="mt-8 flex items-center gap-4">
            <span
              className="grid size-12 place-items-center rounded-full font-display font-bold text-white"
              style={{ background: product?.accent ?? 'var(--brand)' }}
            >
              {t.name.split(' ').map((w) => w[0]).join('')}
            </span>
            <div>
              <p className="font-semibold">{t.name}</p>
              <p className="text-sm text-fg-muted">
                {t.role} · {t.company}
              </p>
            </div>
          </figcaption>
          <div className="mt-8 flex items-center gap-3">
            <button type="button" aria-label="Previous review" onClick={() => setI((i - 1 + n) % n)} className="grid size-10 place-items-center rounded-full border border-line hover:border-brand hover:text-brand">
              <ChevronLeft className="size-5" />
            </button>
            <button type="button" aria-label="Next review" onClick={() => setI((i + 1) % n)} className="grid size-10 place-items-center rounded-full border border-line hover:border-brand hover:text-brand">
              <ChevronRight className="size-5" />
            </button>
            <div className="ml-2 flex gap-1.5">
              {testimonials.map((_, k) => (
                <button
                  key={k}
                  type="button"
                  aria-label={`Show review ${k + 1}`}
                  onClick={() => setI(k)}
                  className={`h-1.5 rounded-full transition-all ${k === i ? 'w-8 bg-cta' : 'w-3 bg-line-strong'}`}
                />
              ))}
            </div>
          </div>
        </figure>

        <div className="grid gap-6">
          <div className="night rounded-[20px] p-8">
            <p className="font-display text-5xl font-extrabold text-lime">5.0</p>
            <div className="mt-2 flex gap-1">
              {Array.from({ length: 5 }).map((_, k) => (
                <Star key={k} className="size-4 fill-current" />
              ))}
            </div>
            <p className="mt-3 text-white/80">Average client rating, with 100% client satisfaction across 10+ delivered projects.</p>
          </div>
          {product && (
            <Link href={`/products/${product.slug}`} className="card group p-6 transition hover:border-brand">
              <p className="text-xs text-fg-subtle">Story featured on</p>
              <p className="mt-1 text-lg font-bold group-hover:text-brand">{product.name}</p>
              <p className="mt-1 text-sm text-fg-muted">{product.tagline}</p>
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
