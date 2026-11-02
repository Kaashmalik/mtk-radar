import { brandIcon, packIco } from '@/lib/brandIcon';

export const dynamic = 'force-static';

// Classic /favicon.ico (16, 32, 48 px) for older browsers, search results and bookmarks.
export async function GET() {
  const pngs = await Promise.all(
    [16, 32, 48].map(async (size) => ({ size, data: new Uint8Array(await brandIcon(size).arrayBuffer()) })),
  );
  return new Response(packIco(pngs), {
    headers: { 'Content-Type': 'image/x-icon', 'Cache-Control': 'public, max-age=31536000, immutable' },
  });
}
