export type DemoKind = 'instalease' | 'dairy' | 'edu' | 'ssl' | 'laraib' | 'alertpro' | 'downloader' | 'radar';

export interface Product {
  slug: string;
  name: string;
  cloud: string; // short product-family label, e.g. "FinTech Cloud"
  category: string;
  tagline: string;
  description: string;
  overview: string;
  accent: string; // CSS color used for this product's highlights
  demo: DemoKind;
  liveUrl?: string;
  githubUrl?: string;
  /** Source is private: show the founder's GitHub profile and a "walkthrough on request" note instead. */
  privateSource?: boolean;
  status: 'Live' | 'Beta' | 'Available';
  platforms: string[];
  audience: string[];
  metrics: { value: string; label: string }[];
  features: { title: string; text: string }[];
  stack: string[];
}

export const products: Product[] = [
  {
    slug: 'shakir-super-league',
    name: 'Shakir Super League',
    cloud: 'Sports Cloud',
    category: 'White-label League Management',
    tagline: 'Launch your own branded cricket league — live, in minutes.',
    description:
      'White-label SaaS for cricket leagues — real-time scoring, AI commentary in five languages, live streaming, fantasy and analytics.',
    overview:
      'Tournament organisers launch a branded league with custom domain, logo and teams. Ball-by-ball scoring syncs instantly over WebSockets, GPT commentary runs in English, Urdu, Punjabi, Pashto and Sindhi, matches stream over WebRTC, and fans play fantasy cricket with automated points.',
    accent: '#ef4444',
    demo: 'ssl',
    githubUrl: 'https://github.com/Kaashmalik/mtk-ssl2026',
    status: 'Beta',
    platforms: ['Web', 'Streaming', 'White-label'],
    audience: ['Tournament organisers', 'Cricket clubs', 'Sports media'],
    metrics: [
      { value: '5', label: 'AI commentary languages' },
      { value: '<1s', label: 'Score sync latency' },
      { value: '∞', label: 'Branded leagues per platform' },
    ],
    features: [
      { title: 'Ball-by-ball live scoring', text: 'WebSocket sync with offline resilience for ground scorers.' },
      { title: 'AI commentary', text: 'Multi-language GPT commentary with caching and circuit breakers.' },
      { title: 'Live streaming', text: 'Low-latency WebRTC broadcast powered by Mediasoup.' },
      { title: 'Fantasy & analytics', text: 'Automated fantasy points and ClickHouse-powered stats.' },
    ],
    stack: ['Next.js 15', 'NestJS 11', 'PostgreSQL', 'Redis', 'Kafka', 'ClickHouse', 'Stripe', 'OpenAI', 'Mediasoup', 'Docker'],
  },
  {
    slug: 'mtk-dairy',
    name: 'MTK Dairy',
    cloud: 'AgriTech Cloud',
    category: 'Dairy Farm Management',
    tagline: 'Smart herd, milk and finance management for modern farms.',
    description:
      'Multi-tenant platform for dairy farms and cooperatives — milk production, cattle health, breeding cycles and financial analytics.',
    overview:
      'MTK Dairy helps farmers, cooperatives and agri-enterprises move off paper. Track milk yield per animal, health and vaccination records, breeding cycles and expenses, with IoT integration for milking machines, bilingual English/Urdu UI and offline PWA support for the field.',
    accent: '#22c55e',
    demo: 'dairy',
    liveUrl: 'https://dairy.mtkcodex.site',
    githubUrl: 'https://github.com/Kaashmalik/malik-tech-dairy',
    status: 'Live',
    platforms: ['Web', 'PWA', 'IoT API'],
    audience: ['Dairy farms', 'Cooperatives', 'Agri-enterprises'],
    metrics: [
      { value: '500+', label: 'Farms onboarded' },
      { value: '50K+', label: 'Animals tracked' },
      { value: '99.9%', label: 'Uptime SLA' },
    ],
    features: [
      { title: 'Milk production tracking', text: 'Per-animal yield with IoT feeds from automated milking machines.' },
      { title: 'Health & breeding', text: 'Vaccinations, treatments, heat detection and calving schedules.' },
      { title: '7-role access control', text: 'From farm owner to accountant, with full audit logging.' },
      { title: 'Local payments', text: 'JazzCash, EasyPaisa and XPay subscriptions with feature gating.' },
    ],
    stack: ['Next.js 15', 'TypeScript', 'Clerk', 'Supabase', 'Drizzle ORM', 'Firebase', 'Upstash Redis', 'BullMQ', 'next-intl'],
  },
  {
    slug: 'laraibcreative',
    name: 'LaraibCreative',
    cloud: 'Commerce Cloud',
    category: 'Luxury Fashion E-commerce',
    tagline: 'Premium storefronts with custom-order workflows built in.',
    description:
      'Luxury fashion e-commerce for custom-stitched suits and bridal wear — measurements, order tracking and local payments.',
    overview:
      'LaraibCreative is a production storefront for a Pakistani luxury fashion brand. Customers submit body measurements for custom stitching, follow a 9-stage order pipeline in real time and pay via COD, JazzCash or EasyPaisa, while the brand manages everything from a full admin dashboard.',
    accent: '#ec4899',
    demo: 'laraib',
    liveUrl: 'https://www.laraibcreative.studio',
    status: 'Live',
    platforms: ['Web', 'Mobile-first'],
    audience: ['Fashion brands', 'Boutiques', 'D2C retailers'],
    metrics: [
      { value: '9-stage', label: 'Order pipeline' },
      { value: '3', label: 'Local payment methods' },
      { value: '60%', label: 'Faster page loads' },
    ],
    features: [
      { title: 'Custom stitching flow', text: 'Measurement capture tied to every order line.' },
      { title: 'Real-time order tracking', text: 'Customers follow production from cutting to delivery.' },
      { title: 'Rich collections', text: 'Filter by fabric, occasion and price with wishlist sync.' },
      { title: 'Payment verification', text: 'Admin workflow for COD, JazzCash and EasyPaisa.' },
    ],
    stack: ['Next.js 14', 'React 18', 'TypeScript', 'Node.js', 'Express', 'MongoDB', 'JWT', 'Zustand', 'Cloudinary'],
  },
  {
    slug: 'instalease',
    name: 'InstalEase',
    cloud: 'FinTech Cloud',
    category: 'Installment & Retail Finance',
    tagline: 'Run every installment, contract and payment from one dashboard.',
    description:
      'Multi-tenant SaaS for retail installment businesses — contracts, customers, guarantors, payments and late fees with real-time analytics.',
    overview:
      'InstalEase digitises the full installment lifecycle for appliance, mobile, electronics and furniture retailers: CNIC-verified onboarding, contract creation, automatic scheduling, receipts, guarantor management and overdue tracking. Every shop is fully isolated with PostgreSQL Row Level Security, and owners see revenue and recovery in real time.',
    accent: '#4f6bff',
    demo: 'instalease',
    // liveUrl: 'https://instalease.mtkcodex.site', // re-enable once the site is back online
    githubUrl: 'https://github.com/Kaashmalik/MTK-instalease',
    status: 'Live',
    platforms: ['Web', 'PWA'],
    audience: ['Retail installment shops', 'Electronics & appliance dealers', 'Micro-finance teams'],
    metrics: [
      { value: '6', label: 'Role levels (RBAC)' },
      { value: 'RLS', label: 'Tenant data isolation' },
      { value: 'Real-time', label: 'Revenue dashboards' },
    ],
    features: [
      { title: 'Contract automation', text: 'Create contracts, auto-generate schedules and PDF receipts in seconds.' },
      { title: 'CNIC OCR verification', text: 'Tesseract-powered ID capture speeds up customer onboarding.' },
      { title: 'Overdue & late-fee engine', text: 'Automatic reminders and late-fee calculation keep recovery on track.' },
      { title: 'Super Admin portal', text: 'Tiered plans, shop registration and platform-wide oversight.' },
    ],
    stack: ['Next.js 16', 'React 19', 'TypeScript', 'Supabase', 'PostgreSQL RLS', 'TanStack Query', 'Recharts', 'Twilio', 'Sentry'],
  },
  {
    slug: 'mtk-edu',
    name: 'MTK Edu',
    cloud: 'Education Cloud',
    category: 'School Management',
    tagline: 'From admission to graduation — one intelligent campus platform.',
    description:
      'Enterprise school management SaaS with AI insights, biometric attendance, offline-first mobile apps and 90+ APIs.',
    overview:
      'MTK Edu gives K-12 schools, colleges and training centres a dedicated subdomain and a complete academic system: admissions, attendance, exams, fees, library and reporting. AI predicts student performance and drafts reports, while teachers mark attendance from an offline-first mobile app.',
    accent: '#f59e0b',
    demo: 'edu',
    status: 'Available',
    platforms: ['Web', 'iOS', 'Android'],
    audience: ['Schools', 'Colleges', 'Training centres'],
    metrics: [
      { value: '90+', label: 'REST API endpoints' },
      { value: '7', label: 'Role levels' },
      { value: '20h+', label: 'Admin hours saved weekly' },
    ],
    features: [
      { title: 'AI performance insights', text: 'Predict at-risk students and auto-generate report cards.' },
      { title: 'Biometric attendance', text: 'Face recognition with Azure Face API, synced from mobile.' },
      { title: 'Offline-first mobile', text: 'React Native + WatermelonDB keeps working without internet.' },
      { title: 'Subdomain per school', text: 'Complete tenant isolation with branded portals.' },
    ],
    stack: ['Next.js 15', 'Laravel 11', 'PostgreSQL', 'Redis', 'React Native', 'Expo', 'WatermelonDB', 'OpenAI', 'Sentry'],
  },
  {
    slug: 'mtk-alertpro',
    name: 'MTK AlertPro',
    cloud: 'Security Cloud',
    category: 'AI Video Surveillance',
    tagline: 'Turn any IP camera into an AI security guard.',
    description:
      'Privacy-first mobile app with on-device person and vehicle detection, instant alerts and alarm integration.',
    overview:
      'MTK AlertPro runs TensorFlow.js with SSD MobileNet V2 directly on the phone — no cloud video processing, no privacy trade-offs. It connects to most RTSP/HTTP IP cameras, detects people and vehicles in real time and triggers push notifications, alarms and red-alert mode in under two seconds.',
    accent: '#06b6d4',
    demo: 'alertpro',
    status: 'Beta',
    platforms: ['iOS', 'Android'],
    audience: ['Homes', 'Shops & warehouses', 'Security teams'],
    metrics: [
      { value: '<2s', label: 'Alert latency' },
      { value: '80%+', label: 'IP cameras supported' },
      { value: '0', label: 'Frames sent to cloud' },
    ],
    features: [
      { title: 'On-device AI', text: 'Real-time person/vehicle detection with zero cloud dependency.' },
      { title: 'Smart alerts', text: 'Cooldowns, alarm sounds, vibration patterns and red-alert mode.' },
      { title: 'Universal cameras', text: 'RTSP/HTTP streams with auto-reconnect and offline caching.' },
      { title: 'Subscriptions', text: 'RevenueCat-powered plans, ready to monetise.' },
    ],
    stack: ['React Native', 'Expo 52', 'TypeScript', 'TensorFlow.js', 'MobileNet V2', 'Supabase', 'FCM', 'RevenueCat'],
  },
  {
    slug: 'mtk-download-manager',
    name: 'MTK Download Manager',
    cloud: 'Desktop Suite',
    category: 'Cross-platform Desktop App',
    tagline: 'Download from 1000+ sites with a smart, beautiful queue.',
    description:
      'Electron desktop app for videos, music and files from 1000+ sites — queue management, live progress and auto-updates.',
    overview:
      'A professional desktop download manager for Windows, macOS and Linux. Powered by yt-dlp, it supports 1000+ websites with format selection, subtitles and chapters, a drag-and-drop priority queue, parallel downloads, system tray mode and automatic updates through GitHub Releases.',
    accent: '#a855f7',
    demo: 'downloader',
    status: 'Available',
    platforms: ['Windows', 'macOS', 'Linux'],
    audience: ['Creators', 'Media teams', 'Power users'],
    metrics: [
      { value: '1000+', label: 'Supported websites' },
      { value: '3', label: 'Desktop platforms' },
      { value: 'Auto', label: 'Updates via releases' },
    ],
    features: [
      { title: 'Smart queue', text: 'Pause, resume, reorder and run parallel downloads.' },
      { title: 'Live progress', text: 'Speed, ETA and size per item in real time.' },
      { title: 'Format control', text: 'Pick quality, embed subtitles and chapter markers.' },
      { title: 'Native feel', text: 'System tray, toasts and a polished dark UI.' },
    ],
    stack: ['Electron 28', 'React 18', 'TypeScript', 'Vite 5', 'Tailwind CSS', 'Zustand', 'Better-SQLite3', 'yt-dlp'],
  },
  {
    slug: 'mtk-radar',
    name: 'MTK Radar AI',
    cloud: 'Media Automation Cloud',
    category: 'AI Content Automation Platform',
    tagline: 'From a verified offer to a published video on four platforms — automated, with a human in control.',
    description:
      'Finds AI and developer offers, verifies them against official sources, turns them into real claim-walkthrough videos and schedules them to YouTube, Facebook, Instagram and TikTok.',
    overview:
      'MTK Radar AI watches a registry of trusted sources, keeps immutable evidence snapshots of official pages, and only lets verified offers become videos. It writes the script, records the real claim flow, renders 16:9 and 9:16 cuts with captions, measures every render for quality, then schedules platform-specific posts. One automation policy decides which stages run on their own: Manual, Assisted (the default) or Autopilot inside server-side guardrails, with a kill switch and dry-run.',
    accent: '#f97316',
    demo: 'radar',
    privateSource: true,
    status: 'Beta',
    platforms: ['Web dashboard', 'Chrome extension', 'Background workers'],
    audience: ['Tech content creators', 'Developer-relations teams', 'Media agencies', 'Education channels'],
    metrics: [
      { value: '9', label: 'Automated pipeline stages' },
      { value: '4', label: 'Platforms published to' },
      { value: '3', label: 'Automation modes + kill switch' },
    ],
    features: [
      {
        title: 'Trusted source radar',
        text: 'RSS, GitHub releases, official-page watch and trend signals (Hacker News, Reddit, Hugging Face papers, Google Trends) ranked by trust tier.',
      },
      {
        title: 'Evidence-first verification',
        text: 'Immutable snapshots with URL, timestamp, publisher and content hash. Only provider-owned evidence can mark an offer verified.',
      },
      {
        title: 'Script & storyboard studio',
        text: 'Versioned claim scripts, command cards, shot lists and platform copy — English by default, Urdu voiceover opt-in.',
      },
      {
        title: 'Real capture, measured renders',
        text: 'Human-operated browser capture with redaction review, FFmpeg renders and automatic QC for black frames, freezes, silence, loudness and caption safe areas.',
      },
      {
        title: 'Scheduled multi-platform publishing',
        text: 'Official YouTube, Meta, Instagram and TikTok APIs, per-platform packages, publish windows, retries with backoff and a circuit breaker.',
      },
      {
        title: 'Automation control & audit',
        text: 'Manual, Assisted or Autopilot per stage, guardrails enforced by the API, daily caps, dry-run, a global pause switch and a full audit trail.',
      },
    ],
    stack: ['Next.js', 'TypeScript', 'FastAPI', 'Python', 'PostgreSQL 16', 'Redis', 'S3 / MinIO', 'Playwright', 'FFmpeg', 'Docker', 'Chrome MV3', 'YouTube Data API', 'Meta Graph API', 'TikTok API'],
  },
];

export const getProduct = (slug: string) => products.find((p) => p.slug === slug);
