import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { ArrowUpRight, Clock } from 'lucide-react';
import { formatDate, getPosts } from '@/lib/blog';
import PageHeader from '@/components/ui/PageHeader';
import Reveal from '@/components/ui/Reveal';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Insights',
  description: 'Engineering insights from MTK Codex on SaaS architecture, AI integration, Next.js and modern UI design.',
  path: '/blog',
  keywords: ['SaaS engineering blog', 'Next.js guides', 'AI SaaS'],
});

const accents = ['#14a89a', '#62d84e', '#3b82f6', '#f59e0b'];

export default function BlogPage() {
  const posts = getPosts();
  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title={
          <>
            Notes from the <span className="text-gradient">engineering floor.</span>
          </>
        }
        text="How we design, build and scale production software — architecture, AI, UI and lessons learned."
      />
      <section className="container-x grid gap-6 py-20 md:grid-cols-2">
        {posts.map((p, i) => (
          <Reveal key={p.slug} delay={i * 90}>
            <Link href={`/blog/${p.slug}`} className="card spotlight group flex h-full flex-col overflow-hidden transition hover:-translate-y-1 hover:shadow-float">
              <div className="relative h-44 overflow-hidden" style={{ background: `linear-gradient(135deg, ${accents[i % 4]}, #032d42)` }}>
                <div className="bg-grid absolute inset-0 opacity-40" />
                <span className="absolute bottom-4 left-6 font-display text-6xl font-extrabold text-white/20">0{i + 1}</span>
              </div>
              <div className="flex flex-1 flex-col p-7">
                <div className="flex flex-wrap gap-2">
                  {p.tags.slice(0, 3).map((t) => (
                    <span key={t} className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-fg-muted">
                      {t}
                    </span>
                  ))}
                </div>
                <h2 className="mt-4 text-xl font-bold group-hover:text-brand">{p.title}</h2>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-fg-muted">{p.summary}</p>
                <div className="mt-6 flex items-center justify-between text-xs text-fg-subtle">
                  <span>
                    {formatDate(p.date)} · <Clock className="inline size-3" /> {p.readingMinutes} min read
                  </span>
                  <ArrowUpRight className="size-4 text-brand transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                </div>
              </div>
            </Link>
          </Reveal>
        ))}
      </section>
      <CtaBand />
    </>
  );
}
