import type { Metadata } from 'next';
import { site } from '@/data/site';

export const absoluteUrl = (path = '') => `${site.url}${path}`;

/** Per-page metadata with canonical URL, Open Graph and Twitter cards. */
export function pageMeta({
  title,
  description,
  path,
  keywords = [],
  type = 'website',
  publishedTime,
}: {
  title: string;
  description: string;
  path: string;
  keywords?: string[];
  type?: 'website' | 'article';
  publishedTime?: string;
}): Metadata {
  return {
    title,
    description,
    keywords: [...keywords, 'MTK Codex'],
    alternates: { canonical: path },
    openGraph: {
      type,
      url: path,
      siteName: site.name,
      title: `${title} · ${site.name}`,
      description,
      locale: 'en_US',
      ...(publishedTime ? { publishedTime, authors: [site.founder.name] } : {}),
    },
    twitter: { card: 'summary_large_image', title: `${title} · ${site.name}`, description },
  };
}

export const ORG_ID = `${site.url}/#organization`;
export const FOUNDER_ID = `${site.url}/#founder`;

export function breadcrumbs(items: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [{ name: 'Home', path: '' }, ...items].map((it, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: it.name,
      item: absoluteUrl(it.path),
    })),
  };
}

export function JsonLd({ data }: { data: object | object[] }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, '\\u003c') }} />;
}
