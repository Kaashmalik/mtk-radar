/**
 * Service worker for the installed admin app, served from /admin/sw.js so its
 * scope is /admin/. It only handles push alerts and notification clicks; it
 * does not cache pages, so lead data is never stored offline.
 */
const script = `
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: 'MTK Codex', body: event.data && event.data.text() }; }
  const title = data.title || 'MTK Codex';
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    data: { url: data.url || '/admin/inbox' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data && event.notification.data.url || '/admin/inbox', self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin + '/admin')) {
        await client.focus();
        return client.navigate(url.href);
      }
    }
    return self.clients.openWindow(url.href);
  })());
});
`;

export function GET() {
  return new Response(script, {
    headers: {
      'Content-Type': 'text/javascript; charset=utf-8',
      'Cache-Control': 'no-cache',
      'Service-Worker-Allowed': '/admin/',
    },
  });
}
