import { renderOg, ogSize } from '@/lib/og';
import { getProduct, products } from '@/data/products';

export const size = ogSize;
export const contentType = 'image/png';
export const alt = 'MTK Codex product';

export function generateStaticParams() {
  return products.map((p) => ({ slug: p.slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const p = getProduct((await params).slug)!;
  return renderOg({ eyebrow: `${p.cloud} · ${p.category}`, title: p.name, subtitle: p.tagline, accent: p.accent });
}
