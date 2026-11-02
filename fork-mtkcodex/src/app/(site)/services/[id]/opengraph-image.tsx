import { renderOg, ogSize } from '@/lib/og';
import { services } from '@/data/services';

export const size = ogSize;
export const contentType = 'image/png';
export const alt = 'MTK Codex service';

export function generateStaticParams() {
  return services.map((s) => ({ id: s.id }));
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = services.find((x) => x.id === id)!;
  return renderOg({ eyebrow: 'Services', title: s.title, subtitle: s.summary });
}
