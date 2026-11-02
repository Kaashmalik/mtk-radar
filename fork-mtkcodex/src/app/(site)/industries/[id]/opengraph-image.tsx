import { renderOg, ogSize } from '@/lib/og';
import { industries } from '@/data/content';

export const size = ogSize;
export const contentType = 'image/png';
export const alt = 'MTK Codex industry solutions';

export function generateStaticParams() {
  return industries.map((i) => ({ id: i.id }));
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const ind = industries.find((x) => x.id === id)!;
  return renderOg({ eyebrow: `${ind.name} software`, title: ind.headline, subtitle: ind.text });
}
