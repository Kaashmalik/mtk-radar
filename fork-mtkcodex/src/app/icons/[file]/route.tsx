import { brandIcon } from '@/lib/brandIcon';

export const dynamic = 'force-static';
export const dynamicParams = false;

// Every PNG icon the site, manifest and OS integrations reference.
const files: Record<string, { size: number; variant: 'standard' | 'maskable' | 'tile' }> = {
  'favicon-16.png': { size: 16, variant: 'standard' },
  'favicon-32.png': { size: 32, variant: 'standard' },
  'favicon-48.png': { size: 48, variant: 'standard' },
  'icon-192.png': { size: 192, variant: 'standard' },
  'icon-512.png': { size: 512, variant: 'standard' },
  'maskable-192.png': { size: 192, variant: 'maskable' },
  'maskable-512.png': { size: 512, variant: 'maskable' },
  'apple-touch-icon.png': { size: 180, variant: 'maskable' }, // iOS rounds corners itself, so no transparency
  'mstile-150.png': { size: 150, variant: 'tile' },
  'mstile-310.png': { size: 310, variant: 'tile' },
};

export function generateStaticParams() {
  return Object.keys(files).map((file) => ({ file }));
}

export async function GET(_req: Request, { params }: { params: Promise<{ file: string }> }) {
  const f = files[(await params).file];
  if (!f) return new Response('Not found', { status: 404 });
  const res = brandIcon(f.size, f.variant);
  res.headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  return res;
}
