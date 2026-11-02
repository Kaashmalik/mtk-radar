import { renderOg, ogSize } from '@/lib/og';
import { site } from '@/data/site';

export const alt = `${site.name} — ${site.slogan}`;
export const size = ogSize;
export const contentType = 'image/png';

export default function Image() {
  return renderOg({ eyebrow: 'Software · SaaS · Automation', title: site.slogan, subtitle: site.tagline });
}
