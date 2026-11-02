import type { Metadata } from 'next';

import { breadcrumbs, JsonLd, FOUNDER_ID, ORG_ID, absoluteUrl, pageMeta } from '@/lib/seo';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { formatDate, getPost, getPosts, renderMarkdown } from '@/lib/blog';
import { site } from '@/data/site';
import CtaBand from '@/components/sections/CtaBand';
import AdSlot from '@/components/ads/AdSlot';

export function generateStaticParams() {
  return getPosts().map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const p = getPost(slug);
  return p ? pageMeta({ title: p.title, description: p.summary, path: `/blog/${p.slug}`, keywords: p.tags, type: 'article', publishedTime: p.date }) : {};
}

export default async function PostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) notFound();

  return (
    <>
      <JsonLd
        data={[
          breadcrumbs([
            { name: 'Insights', path: '/blog' },
            { name: post.title, path: `/blog/${post.slug}` },
          ]),
          {
            '@context': 'https://schema.org',
            '@type': 'BlogPosting',
            headline: post.title,
            description: post.summary,
            datePublished: post.date,
            dateModified: post.date,
            keywords: post.tags.join(', '),
            mainEntityOfPage: absoluteUrl(`/blog/${post.slug}`),
            image: absoluteUrl(`/blog/${post.slug}/opengraph-image`),
            author: { '@id': FOUNDER_ID },
            publisher: { '@id': ORG_ID },
          },
        ]}
      />
      <article className="container-x max-w-3xl py-16">
        <Link href="/blog" className="inline-flex items-center gap-1 text-sm font-medium text-fg-muted hover:text-brand">
          <ArrowLeft className="size-4" /> All insights
        </Link>
        <div className="mt-8 flex flex-wrap gap-2">
          {post.tags.map((t) => (
            <span key={t} className="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-medium text-brand">
              {t}
            </span>
          ))}
        </div>
        <h1 className="mt-4 text-3xl font-extrabold leading-tight sm:text-5xl">{post.title}</h1>
        <p className="mt-4 text-lg text-fg-muted">{post.summary}</p>
        <div className="mt-6 flex items-center gap-3 border-b border-line pb-8 text-sm">
          <span className="grid size-10 place-items-center rounded-full bg-[linear-gradient(135deg,#62d84e,#14a89a)] font-display font-bold text-on-cta">MK</span>
          <div>
            <p className="font-semibold">{site.founder.name}</p>
            <p className="text-fg-subtle">
              {formatDate(post.date)} · {post.readingMinutes} min read
            </p>
          </div>
        </div>
        <div className="prose-mtk mt-8" dangerouslySetInnerHTML={{ __html: renderMarkdown(post.body) }} />
        <AdSlot />
      </article>
      <CtaBand />
    </>
  );
}
