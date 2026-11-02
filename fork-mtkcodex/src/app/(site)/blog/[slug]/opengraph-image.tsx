import { renderOg, ogSize } from '@/lib/og';
import { getPost, getPosts } from '@/lib/blog';

export const size = ogSize;
export const contentType = 'image/png';
export const alt = 'MTK Codex insight';

export function generateStaticParams() {
  return getPosts().map((p) => ({ slug: p.slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = getPost(slug)!;
  return renderOg({ eyebrow: 'Insights', title: p.title, subtitle: p.summary });
}
