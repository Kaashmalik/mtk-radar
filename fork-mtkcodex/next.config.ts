import type { NextConfig } from 'next';

const isDev = process.env.NODE_ENV === 'development';

// Google hosts used by GA4, AdSense (incl. its ad-quality checks) and the map embed.
const google = [
  'https://*.google.com',
  'https://*.googletagmanager.com',
  'https://*.google-analytics.com',
  'https://*.analytics.google.com',
  'https://*.googlesyndication.com',
  'https://*.doubleclick.net',
  'https://*.adtrafficquality.google',
  'https://*.gstatic.com',
].join(' ');

// Static pages cannot carry per-request nonces, so inline scripts (theme
// bootstrap, consent defaults, JSON-LD) are allowed; everything else is locked
// to this origin and the Google hosts above.
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''} https://www.googletagmanager.com https://pagead2.googlesyndication.com https://*.adtrafficquality.google https://*.doubleclick.net`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self' ${google}`,
  `frame-src ${google}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'self'",
  'upgrade-insecure-requests',
].join('; ');

const nextConfig: NextConfig = {
  poweredByHeader: false,
  compress: true,
  images: { formats: ['image/avif', 'image/webp'] },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()' },
          { key: 'Content-Security-Policy', value: contentSecurityPolicy },
        ],
      },
      {
        // Lead data and chats: never cache, never leak a referrer.
        source: '/admin/:path*',
        headers: [
          { key: 'Cache-Control', value: 'no-store' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
        ],
      },
    ];
  },
  // Friendly aliases for URLs visitors commonly try on company sites.
  async redirects() {
    return [
      { source: '/signin', destination: '/login', permanent: true },
      { source: '/sign-in', destination: '/login', permanent: true },
      { source: '/signup', destination: '/contact?intent=demo', permanent: false },
      { source: '/register', destination: '/contact?intent=demo', permanent: false },
      { source: '/resources', destination: '/blog', permanent: false },
      { source: '/insights', destination: '/blog', permanent: false },
      { source: '/solutions', destination: '/industries', permanent: false },
      { source: '/company', destination: '/about', permanent: false },
      { source: '/partners', destination: '/contact', permanent: false },
      { source: '/demo', destination: '/contact?intent=demo', permanent: false },
      { source: '/saas-projects', destination: '/products', permanent: true },
      { source: '/saas', destination: '/products', permanent: true },
      { source: '/lahore', destination: '/locations/lahore', permanent: true },
      { source: '/location', destination: '/locations', permanent: true },
    ];
  },
};

export default nextConfig;
