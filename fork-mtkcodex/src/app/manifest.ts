import type { MetadataRoute } from 'next';
import { site } from '@/data/site';

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: `${site.name} — ${site.slogan}`,
    short_name: site.name,
    description: site.tagline,
    start_url: '/?source=pwa',
    scope: '/',
    lang: 'en',
    dir: 'ltr',
    display: 'standalone',
    orientation: 'portrait-primary',
    background_color: '#031f2b',
    theme_color: '#031f2b',
    categories: ['business', 'productivity', 'developer'],
    icons: [
      { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
    // Long-press the home-screen icon on Android to jump straight to these.
    shortcuts: [
      { name: 'Book a demo', short_name: 'Demo', url: '/contact?intent=demo', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
      { name: 'Products', url: '/products', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
      { name: 'Services', url: '/services', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
      { name: 'Client login', short_name: 'Login', url: '/login', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
    ],
  };
}
