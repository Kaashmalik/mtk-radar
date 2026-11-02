import { products } from '@/data/products';
import { services } from '@/data/services';
import { industries } from '@/data/content';

/** Public marketing pages, shared by the sitemap and the analytics beacon. */
export const STATIC_PAGES = [
  '',
  '/platform',
  '/products',
  '/services',
  '/industries',
  '/customers',
  '/pricing',
  '/about',
  '/blog',
  '/careers',
  '/contact',
  '/privacy',
  '/terms',
  '/cookies',
  '/disclaimer',
  '/locations',
  '/locations/lahore',
];

const KNOWN_PATHS = new Set<string>([
  '/',
  ...STATIC_PAGES.filter(Boolean),
  '/login',
  ...products.map((p) => `/products/${p.slug}`),
  ...services.map((s) => `/services/${s.id}`),
  ...industries.map((i) => `/industries/${i.id}`),
]);

/** Blog posts are files read at build time, so match their slug shape instead. */
const BLOG_POST = /^\/blog\/[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * Normalises a reported page path and returns it only if it is a real public
 * page, so nobody can fill the analytics dashboard with invented URLs.
 */
export function trackablePath(value: unknown): string {
  if (typeof value !== 'string' || value.length > 300) return '';
  let path = value.split(/[?#]/)[0];
  if (path.length > 1) path = path.replace(/\/+$/, '');
  if (KNOWN_PATHS.has(path) || BLOG_POST.test(path)) return path;
  return '';
}
