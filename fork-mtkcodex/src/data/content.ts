export interface Testimonial {
  name: string;
  role: string;
  company: string;
  product: string; // product slug
  quote: string;
  rating: number;
}

// Real client feedback. Add new reviews here as they come in.
export const testimonials: Testimonial[] = [
  {
    name: 'Shakir Hussain',
    role: 'Tournament Director',
    company: 'Shakir Super League',
    product: 'shakir-super-league',
    quote:
      'We needed a white-label platform that could run an entire cricket league — live scoring, AI commentary in 5 languages, fantasy cricket, and streaming. They delivered all of it as a reusable SaaS product. Other leagues now use the same platform under their own brand.',
    rating: 5,
  },
  {
    name: 'Ahmed Raza',
    role: 'Business Owner',
    company: 'InstalEase client',
    product: 'instalease',
    quote:
      'MTK Codex built our complete installment management platform from the ground up — multi-tenant architecture, real-time dashboards, payment tracking, the works. The system handles 6 different user roles flawlessly and our shops onboard within minutes. Production-grade from day one.',
    rating: 5,
  },
  {
    name: 'Fatima Noor',
    role: 'School Administrator',
    company: 'MTK Edu client',
    product: 'mtk-edu',
    quote:
      'Managing 2000+ students across attendance, exams, fees, and reports was chaos before MTK Edu. The biometric attendance and AI-powered report generation alone saved us 20+ hours per week. Teachers now mark attendance from their phones — even offline.',
    rating: 5,
  },
];

export const industries = [
  {
    id: 'sports',
    name: 'Sports & Media',
    headline: 'Engage fans with live, branded experiences.',
    text: 'Live scoring, streaming, AI commentary and fantasy leagues — white-labelled for your brand.',
    product: 'shakir-super-league',
    wins: ['Real-time scoring', 'Multi-language AI commentary', 'Live WebRTC streaming'],
  },
  {
    id: 'agriculture',
    name: 'Agriculture',
    headline: 'Bring data-driven decisions to the farm.',
    text: 'Herd, crop and production tracking with IoT integrations and offline field apps.',
    product: 'mtk-dairy',
    wins: ['IoT device integration', 'Bilingual Urdu/English UI', 'Offline PWA for field teams'],
  },
  {
    id: 'commerce',
    name: 'E-commerce',
    headline: 'Sell more with storefronts built to convert.',
    text: 'Fast, mobile-first stores with custom order flows, local payments and admin control.',
    product: 'laraibcreative',
    wins: ['Custom order workflows', 'JazzCash / EasyPaisa / COD', 'Admin order pipeline'],
  },
  {
    id: 'finance',
    name: 'Finance & Retail',
    headline: 'Digitise lending, installments and point-of-sale.',
    text: 'Contract automation, payment reconciliation, recovery workflows and real-time revenue analytics.',
    product: 'instalease',
    wins: ['Automated payment schedules', 'Overdue recovery workflows', 'Branch-level analytics'],
  },
  {
    id: 'education',
    name: 'Education',
    headline: 'Run your entire campus from one platform.',
    text: 'Admissions, attendance, exams, fees and AI-powered academic insights for every role.',
    product: 'mtk-edu',
    wins: ['Biometric attendance', 'AI report generation', 'Parent & teacher mobile apps'],
  },
  {
    id: 'security',
    name: 'Security & IoT',
    headline: 'Smarter monitoring with AI at the edge.',
    text: 'Computer vision, device integrations and instant alerts — privacy-first by design.',
    product: 'mtk-alertpro',
    wins: ['On-device detection', 'Sub-2s alerts', 'Works with existing cameras'],
  },
];

export const engagementModels = [
  {
    name: 'SaaS Subscription',
    price: 'From $29',
    period: '/month',
    description: 'Use one of our ready platforms with your branding, hosting and support included.',
    features: ['Choose any MTK Codex product', 'Your logo & sub-domain', 'Hosting, backups & updates', 'Email & WhatsApp support'],
    cta: 'Start with a demo',
    href: '/contact?intent=demo',
    featured: false,
  },
  {
    name: 'Custom Project',
    price: 'Fixed quote',
    period: '',
    description: 'A product built for you — scoped, designed, delivered and handed over with full source code.',
    features: ['Discovery & fixed estimate', 'UI/UX design & prototypes', 'Weekly demos & preview links', 'Source code & documentation', '30 days post-launch support'],
    cta: 'Get a free estimate',
    href: '/contact?intent=quote',
    featured: true,
  },
  {
    name: 'Care & Growth Plan',
    price: 'From $199',
    period: '/month',
    description: 'Maintenance, improvements and automation for software you already run.',
    features: ['Monitoring & bug-fix SLA', 'Security patches & upgrades', 'Monthly improvement hours', 'Automation roadmap', 'Quarterly audit report'],
    cta: 'Talk to us',
    href: '/contact?service=maintenance',
    featured: false,
  },
];

export const faqs = [
  {
    q: 'What is MTK Codex?',
    a: 'MTK Codex is a SaaS development company and software house based in Lahore, Pakistan, founded by Muhammad Kashif. We build ready-to-launch SaaS projects — including Shakir Super League, MTK Dairy and LaraibCreative — and provide custom software development, maintenance, code audits, web scraping, CRM systems and business automation for clients worldwide.',
  },
  {
    q: 'Can you work on software that another team built?',
    a: 'Yes. Most maintenance and improvement engagements start with a short code and security audit, so we understand the system before we change it. You get a written report and a prioritised roadmap.',
  },
  {
    q: 'Do I own the source code of a custom project?',
    a: 'Yes. For custom projects, the full source code, documentation and deployment access are handed over to you at launch.',
  },
  {
    q: 'Can I use one of your SaaS products under my own brand?',
    a: 'Our platforms are multi-tenant and white-label ready. We configure your logo, domain, roles and data, then train your team.',
  },
  {
    q: 'Which payment gateways do you integrate?',
    a: 'Stripe, RevenueCat and local Pakistani gateways including JazzCash, EasyPaisa and XPay, as well as COD and bank-slip verification workflows.',
  },
  {
    q: 'How do you communicate during a project?',
    a: 'Weekly demos with live preview links, a shared progress board, and direct WhatsApp/email access to the engineer building your product. We respond within 12 hours.',
  },
  {
    q: 'Do you work with international clients?',
    a: 'Yes. We are based in Lahore and work remotely with clients worldwide, with overlap across European, Middle Eastern and US time zones.',
  },
];

export const industryChallenges: Record<string, { challenges: string[]; services: string[] }> = {
  finance: {
    challenges: ['Paper ledgers and spreadsheets for installments', 'Missed payments and slow recovery', 'No real-time view across branches'],
    services: ['crm', 'automation', 'custom-development'],
  },
  agriculture: {
    challenges: ['Production data recorded on paper', 'Health and breeding events missed', 'Field teams without reliable internet'],
    services: ['saas-white-label', 'automation', 'mobile-desktop'],
  },
  education: {
    challenges: ['Manual attendance and report cards', 'Disconnected fee, exam and student records', 'Little insight into at-risk students'],
    services: ['saas-white-label', 'ai', 'mobile-desktop'],
  },
  sports: {
    challenges: ['Scoring on paper, results posted late', 'Fans with no live experience', 'Every league rebuilding the same tools'],
    services: ['saas-white-label', 'ai', 'custom-development'],
  },
  commerce: {
    challenges: ['Slow, generic storefronts that do not convert', 'Custom orders managed over chat', 'Local payment methods not supported'],
    services: ['web-scraping', 'custom-development', 'improvement'],
  },
  security: {
    challenges: ['Cameras record but nobody is watching', 'Cloud video services raise privacy concerns', 'Alerts arrive too late to act'],
    services: ['ai', 'mobile-desktop', 'custom-development'],
  },
};
