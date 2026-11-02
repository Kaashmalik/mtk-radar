export const site = {
  name: 'MTK Codex',
  slogan: 'Code That Scales Your Business.',
  tagline:
    'We build, audit, automate and scale the software your business runs on — from ready-to-launch SaaS platforms to custom enterprise systems.',
  url: 'https://mtkcodex.tech',
  email: 'kaash0542@gmail.com',
  phone: '+92 303 8111297',
  whatsapp: '923020718182',
  location: 'Lahore, Pakistan · Serving clients worldwide',
  hours: 'Mon–Sat · Response within 12 hours',
  // Names people search for; used in structured data so Google ties them to this site.
  alternateNames: ['MTKCodex', 'MTK Codex SaaS', 'MTK Codex Software House'],
  // Local SEO. Add your street address once your Google Business Profile is verified,
  // and keep it identical everywhere (website, Google, LinkedIn, directories).
  address: {
    street: '',
    city: 'Lahore',
    region: 'Punjab',
    postalCode: '54000',
    country: 'Pakistan',
    countryCode: 'PK',
  },
  geo: { lat: 31.5204, lng: 74.3587 },
  openingHours: { days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'], opens: '10:00', closes: '19:00', label: 'Mon–Sat · 10:00–19:00 PKT' },
  timezone: 'Asia/Karachi',
  // Paste your Google Business Profile links here once created (shown as buttons when set).
  googleBusinessUrl: '',
  googleReviewUrl: '',
  serviceAreas: [
    { name: 'Pakistan', code: 'PK', note: 'On-site & remote' },
    { name: 'United Arab Emirates', code: 'AE', note: '−1 hr from Lahore' },
    { name: 'Saudi Arabia', code: 'SA', note: '−2 hrs from Lahore' },
    { name: 'United Kingdom', code: 'GB', note: 'Morning overlap' },
    { name: 'Europe', code: 'EU', note: 'Morning overlap' },
    { name: 'United States & Canada', code: 'US', note: 'Evening overlap' },
  ],
  founder: {
    image: '/images/founder.jpg',
    name: 'Muhammad Kashif',
    role: 'CEO & Founder · Full-Stack SaaS Architect',
    bio: 'Muhammad Kashif founded MTK Codex to give growing businesses the kind of engineering usually reserved for enterprises. He has designed and shipped seven production platforms across FinTech, AgriTech, EdTech, SportsTech, e-commerce, AI security and desktop software — owning every layer from database schema and APIs to UI, payments, automation and deployment.',
    highlights: [
      '7 production platforms shipped across 7 industries',
      'Multi-tenant architecture with PostgreSQL RLS & Clerk Organizations',
      'AI in production: GPT, TensorFlow.js on-device ML, streaming AI UIs',
      'Web, mobile and desktop delivery from a single team',
    ],
    certifications: [
      'AWS Certified Cloud Practitioner',
      'Vercel Next.js Certification',
      'Google TensorFlow Developer Certificate',
      'Meta React Native Specialization',
    ],
  },
  social: {
    github: 'https://github.com/Kaashmalik',
    linkedin: 'https://www.linkedin.com/in/muhammadkashif-mtkcodex',
    portfolio: 'https://pf.mtkcodex.site',
  },
  stats: [
    { value: '7', label: 'Production platforms shipped' },
    { value: '500+', label: 'Tenants served on our SaaS' },
    { value: '50K+', label: 'Records tracked every day' },
    { value: '99.9%', label: 'Uptime across live products' },
    { value: '200+', label: 'API endpoints in production' },
    { value: '95+', label: 'Lighthouse performance score' },
  ],
} as const;

const mapQuery = encodeURIComponent(
  [site.name, site.address.street, site.address.city, site.address.country].filter(Boolean).join(', '),
);

export const maps = {
  // Keyless Google Maps embed + deep links.
  embed: `https://www.google.com/maps?q=${site.geo.lat},${site.geo.lng}&z=12&output=embed`,
  open: site.googleBusinessUrl || `https://www.google.com/maps/search/?api=1&query=${mapQuery}`,
  directions: `https://www.google.com/maps/dir/?api=1&destination=${site.geo.lat},${site.geo.lng}`,
};

export const fullAddress = [site.address.street, site.address.city, site.address.region, site.address.postalCode, site.address.country].filter(Boolean).join(', ');

export const whatsappLink =(text = "Hello MTK Codex, I'd like to discuss a project. Please let me know the best time for a quick call.") =>
  `https://wa.me/${site.whatsapp}?text=${encodeURIComponent(text)}`;
