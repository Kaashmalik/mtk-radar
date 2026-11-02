import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { Star } from 'lucide-react';
import { testimonials } from '@/data/content';
import { getProduct } from '@/data/products';
import PageHeader from '@/components/ui/PageHeader';
import Stats from '@/components/sections/Stats';
import CtaBand from '@/components/sections/CtaBand';
import Reveal from '@/components/ui/Reveal';

export const metadata: Metadata = pageMeta({
  title: 'Customer Stories',
  description: 'How sports leagues, retailers and schools run on software built by MTK Codex — real client reviews and results.',
  path: '/customers',
  keywords: ['client reviews', 'case studies', 'software company reviews'],
});

export default function CustomersPage() {
  return (
    <>
      <PageHeader
        eyebrow="Customer stories"
        title={
          <>
            Real businesses. <span className="text-gradient">Real results.</span>
          </>
        }
        text="From retail finance to schools and sports leagues — here is what our clients say about working with MTK Codex."
      />
      <Stats />
      <section className="container-x grid gap-6 pb-20 md:grid-cols-2 lg:grid-cols-3">
        {testimonials.map((t, i) => {
          const p = getProduct(t.product);
          return (
            <Reveal key={t.name} delay={i * 90}>
              <figure className="card flex h-full flex-col p-8">
                <span className="h-1 w-12 rounded-full" style={{ background: p?.accent }} />
                <div className="mt-6 flex gap-1 text-amber-500">
                  {Array.from({ length: t.rating }).map((_, k) => (
                    <Star key={k} className="size-4 fill-current" />
                  ))}
                </div>
                <blockquote className="mt-4 flex-1 leading-relaxed">&ldquo;{t.quote}&rdquo;</blockquote>
                <figcaption className="mt-6 border-t border-line pt-6">
                  <p className="font-semibold">{t.name}</p>
                  <p className="text-sm text-fg-muted">
                    {t.role} · {t.company}
                  </p>
                  {p && (
                    <Link href={`/products/${p.slug}`} className="mt-3 inline-block text-sm font-semibold text-brand">
                      About {p.name} →
                    </Link>
                  )}
                </figcaption>
              </figure>
            </Reveal>
          );
        })}
      </section>
      <CtaBand title="Become our next success story." />
    </>
  );
}
