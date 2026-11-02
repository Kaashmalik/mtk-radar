/** Makes the admin installable on a phone ("Add to Home Screen"), opening straight to the inbox. */
export function GET() {
  return Response.json(
    {
      name: 'MTK Codex CRM',
      short_name: 'MTK CRM',
      description: 'Leads, live chat, WhatsApp and email in one inbox.',
      id: '/admin',
      start_url: '/admin/inbox',
      scope: '/admin/',
      display: 'standalone',
      background_color: '#031f2b',
      theme_color: '#031f2b',
      icons: [
        { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      ],
    },
    { headers: { 'Content-Type': 'application/manifest+json', 'Cache-Control': 'public, max-age=3600' } },
  );
}
