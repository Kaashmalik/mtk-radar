import type { Metadata, Viewport } from 'next';
import { Inter, Sora } from 'next/font/google';
import './globals.css';
import { fullAddress, maps, site } from '@/data/site';
import { services } from '@/data/services';
import { FOUNDER_ID, ORG_ID } from '@/lib/seo';
import { ADSENSE_CLIENT, ConsentDefaults } from '@/components/layout/ThirdPartyScripts';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const sora = Sora({ subsets: ['latin'], variable: '--font-sora', display: 'swap' });

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: {
    default: `${site.name} — SaaS Projects, Software Development & Automation | Lahore`,
    template: `%s · ${site.name}`,
  },
  description: `MTK Codex is a SaaS development company and software house in Lahore. ${site.tagline} SaaS projects, custom software, web scraping, CRM, automation and AI for businesses worldwide.`,
  applicationName: site.name,
  category: 'technology',
  keywords: [
    'MTK Codex',
    'MTKCodex',
    'SaaS projects',
    'SaaS Codex',
    'MTK Codex SaaS',
    'software development company',
    'software house in Lahore',
    'Pakistan software company',
    'SaaS development company',
    'custom software development',
    'white-label SaaS',
    'software maintenance and support',
    'code and security audit',
    'business process automation',
    'AI integration services',
    'Next.js development agency',
    'mobile app development',
  ],
  authors: [{ name: site.founder.name, url: site.social.portfolio }],
  creator: site.founder.name,
  publisher: site.name,
  alternates: { canonical: '/' },
  formatDetection: { telephone: false, email: false, address: false },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true, 'max-image-preview': 'large', 'max-snippet': -1, 'max-video-preview': -1 } },
  openGraph: {
    type: 'website',
    siteName: site.name,
    title: `${site.name} — ${site.slogan}`,
    description: site.tagline,
    url: '/',
    locale: 'en_US',
  },
  twitter: { card: 'summary_large_image', title: `${site.name} — ${site.slogan}`, description: site.tagline },
  // Set these env vars after verifying the domain in Google Search Console / Bing Webmaster Tools.
  verification: {
    google: process.env.GOOGLE_SITE_VERIFICATION,
    other: process.env.BING_SITE_VERIFICATION ? { 'msvalidate.01': process.env.BING_SITE_VERIFICATION } : undefined,
  },
  // Full icon set: SVG for modern browsers, ICO/PNG fallbacks, Apple touch and Safari pinned tab.
  icons: {
    icon: [
      { url: '/favicon.ico', sizes: '16x16 32x32 48x48' },
      { url: '/icon.svg', type: 'image/svg+xml' },
      { url: '/icons/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/icons/favicon-16.png', sizes: '16x16', type: 'image/png' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
    shortcut: '/favicon.ico',
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
    other: [{ rel: 'mask-icon', url: '/safari-pinned-tab.svg', color: '#62d84e' }],
  },
  appleWebApp: { capable: true, title: site.name, statusBarStyle: 'black-translucent' },
  other: {
    'msapplication-TileColor': '#031f2b',
    'msapplication-config': '/browserconfig.xml',
    // AdSense site-ownership meta tag (set NEXT_PUBLIC_ADSENSE_CLIENT=ca-pub-…).
    ...(ADSENSE_CLIENT ? { 'google-adsense-account': ADSENSE_CLIENT } : {}),
  },
};

export const viewport: Viewport = {
  // Kept in sync with the chosen theme by `ThemeToggle` and the boot script.
  themeColor: '#031f2b',
};

// Applies the saved theme (dark by default) before paint to avoid a flash.
const themeScript = `(function(){document.documentElement.classList.add('js');try{var t=localStorage.getItem('theme');var d=t?t==='dark':true;document.documentElement.classList.toggle('dark',d);var m=document.querySelector('meta[name="theme-color"]');if(m)m.content=d?'#031f2b':'#f5f8f7';}catch(e){document.documentElement.classList.add('dark');}})();`;

// Site-wide entity graph: the company, its founder and the website (referenced by @id from other pages).
const orgJsonLd = {
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': ['Organization', 'ProfessionalService'],
      '@id': ORG_ID,
      name: site.name,
      alternateName: site.alternateNames,
      legalName: site.name,
      slogan: site.slogan,
      description: site.tagline,
      url: site.url,
      logo: `${site.url}/icon.svg`,
      image: `${site.url}/opengraph-image`,
      email: site.email,
      telephone: site.phone,
      priceRange: '$$',
      foundingDate: '2024',
      founder: { '@id': FOUNDER_ID },
      address: {
        '@type': 'PostalAddress',
        ...(site.address.street ? { streetAddress: site.address.street } : {}),
        addressLocality: site.address.city,
        addressRegion: site.address.region,
        postalCode: site.address.postalCode,
        addressCountry: site.address.countryCode,
      },
      geo: { '@type': 'GeoCoordinates', latitude: site.geo.lat, longitude: site.geo.lng },
      hasMap: maps.open,
      location: fullAddress,
      openingHoursSpecification: [{ '@type': 'OpeningHoursSpecification', dayOfWeek: site.openingHours.days, opens: site.openingHours.opens, closes: site.openingHours.closes }],
      areaServed: site.serviceAreas.map((a) => ({ '@type': a.code === 'EU' ? 'Place' : 'Country', name: a.name })),
      contactPoint: [{ '@type': 'ContactPoint', contactType: 'sales', email: site.email, telephone: site.phone, availableLanguage: ['English', 'Urdu'] }],
      knowsAbout: ['SaaS development', 'Multi-tenant architecture', 'Next.js', 'React Native', 'Business process automation', 'AI integration', 'Software maintenance', 'Code audits'],
      makesOffer: services.map((s) => ({ '@type': 'Offer', itemOffered: { '@type': 'Service', name: s.title, url: `${site.url}/services/${s.id}` } })),
      sameAs: [site.social.github, site.social.linkedin, site.social.portfolio, ...(site.googleBusinessUrl ? [site.googleBusinessUrl] : [])],
    },
    {
      '@type': 'Person',
      '@id': FOUNDER_ID,
      name: site.founder.name,
      jobTitle: 'CEO & Founder',
      image: `${site.url}${site.founder.image}`,
      worksFor: { '@id': ORG_ID },
      url: site.social.portfolio,
      sameAs: [site.social.github, site.social.linkedin, site.social.portfolio],
    },
    {
      '@type': 'WebSite',
      '@id': `${site.url}/#website`,
      name: site.name,
      alternateName: site.alternateNames,
      url: site.url,
      inLanguage: 'en',
      publisher: { '@id': ORG_ID },
    },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${sora.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <ConsentDefaults />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd).replace(/</g, '\\u003c') }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
