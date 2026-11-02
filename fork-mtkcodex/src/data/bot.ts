import { products, type Product } from './products';
import { services, type Service } from './services';
import { industries, engagementModels, faqs } from './content';
import { fullAddress, maps, site, whatsappLink } from './site';

export type BotLink = { label: string; href: string };
export type BotReply = { text: string; links?: BotLink[]; suggestions?: string[] };

type Intent = { keywords: string[]; reply: BotReply };

export const MENU = ['Products', 'Services', 'Industries', 'Pricing', 'Book a demo', 'Talk to a human'];

/* ------------------------------------------------------------------ */
/* Replies generated from site data, so the bot always matches the site */
/* ------------------------------------------------------------------ */

// Extra words people use for each item (English + Roman-Urdu), on top of its name.
const productWords: Record<string, string[]> = {
  'shakir-super-league': ['ssl', 'shakir', 'cricket', 'league', 'tournament', 'scoring', 'fantasy', 'commentary', 'sports', 'match', 'streaming'],
  'mtk-dairy': ['dairy', 'farm', 'milk', 'cattle', 'cow', 'buffalo', 'livestock', 'herd', 'doodh', 'janwar'],
  laraibcreative: ['laraib', 'fashion', 'clothes', 'dress', 'stitching', 'boutique', 'bridal', 'lehenga', 'kapray'],
  instalease: ['instalease', 'installment', 'instalment', 'qist', 'aqsaat', 'lease', 'emi', 'electronics shop'],
  'mtk-edu': ['school', 'edu', 'college', 'student', 'attendance', 'exam', 'fees', 'academy', 'teacher'],
  'mtk-alertpro': ['alertpro', 'camera', 'cctv', 'surveillance', 'detection', 'alarm', 'intruder'],
  'mtk-download-manager': ['download manager', 'downloader', 'youtube download', 'video download', 'yt-dlp'],
  'mtk-radar': ['radar', 'mtk radar', 'content automation', 'video automation', 'auto publish', 'youtube automation', 'tiktok', 'instagram reels', 'social media automation', 'faceless channel'],
};

const serviceWords: Record<string, string[]> = {
  'custom-development': ['website', 'web app', 'web development', 'custom software', 'develop', 'portal', 'dashboard', 'saas development', 'build software', 'banwana'],
  'saas-white-label': ['white label', 'white-label', 'my brand', 'own brand', 'resell', 'rebrand', 'ready made', 'ready-made', 'subscription'],
  maintenance: ['maintain', 'maintenance', 'support', 'bug', 'fix', 'existing', 'sla', 'monitoring', 'down', 'crash', 'error'],
  improvement: ['seo', 'need seo', 'seo services', 'rank on google', 'already have a website', 'google ranking', 'search engine', 'lighthouse', 'improve', 'slow', 'upgrade', 'modernise', 'modernize', 'redesign', 'migration', 'performance', 'speed', 'legacy'],
  audit: ['audit', 'code review', 'security check', 'code quality', 'vulnerability', 'pentest', 'review my code'],
  automation: ['automation', 'automate', 'workflow', 'zapier', 'make.com', 'n8n', 'reminder', 'whatsapp automation', 'manual work', 'repetitive'],
  'web-scraping': ['scrap', 'scrape', 'scraping', 'scraper', 'crawl', 'extract', 'extraction', 'data mining', 'leads list', 'price monitoring', 'competitor', 'collect data', 'data from website'],
  crm: ['crm', 'hubspot', 'zoho', 'salesforce', 'pipeline', 'sales team', 'lead management', 'customer management', 'follow up', 'follow-up'],
  ai: ['ai', 'chatgpt', 'openai', 'gpt', 'machine learning', 'ocr', 'artificial intelligence', 'llm', 'chatbot', 'computer vision'],
  'mobile-desktop': ['mobile', 'android', 'ios', 'app', 'react native', 'iphone', 'desktop', 'electron', 'play store', 'app store'],
};

const industryWords: Record<string, string[]> = {
  sports: ['sports industry', 'sports club', 'sports media'],
  agriculture: ['agriculture', 'agritech', 'farming', 'crops', 'kisan'],
  commerce: ['ecommerce', 'e-commerce', 'online store', 'retail store', 'online shop', 'sell online'],
  finance: ['finance', 'fintech', 'lending', 'retail finance', 'loan'],
  education: ['education', 'edtech', 'university', 'training centre', 'coaching'],
  security: ['security industry', 'iot', 'smart devices'],
};

const productReply = (x: Product): BotReply => ({
  text: `**${x.name}** · ${x.cloud} (${x.status})\n${x.description}\n\nHighlights: ${x.features.map((f) => f.title).join(' · ')}.`,
  links: [
    { label: `Open ${x.name} page`, href: `/products/${x.slug}` },
    ...(x.liveUrl ? [{ label: 'Open live app', href: x.liveUrl }] : []),
    { label: 'Book a demo', href: `/contact?intent=demo&product=${x.slug}` },
  ],
  suggestions: ['Pricing', 'White-label for my brand', ...products.filter((o) => o.slug !== x.slug).slice(0, 2).map((o) => o.name), 'Menu'],
});

const serviceReply = (s: Service): BotReply => ({
  text: `**${s.title}**\n${s.summary}\n\nWhat's included: ${s.deliverables.join(' · ')}.`,
  links: [
    { label: `Open ${s.title} page`, href: `/services/${s.id}` },
    { label: 'Discuss this service', href: `/contact?service=${s.id}` },
  ],
  suggestions: ['Pricing', 'How long does it take?', ...services.filter((o) => o.id !== s.id).slice(0, 2).map((o) => o.title), 'Menu'],
});

const industryReply = (id: string): BotReply => {
  const ind = industries.find((i) => i.id === id)!;
  const prod = products.find((x) => x.slug === ind.product)!;
  return {
    text: `**${ind.name}** — ${ind.headline}\n${ind.text}\n\nRecommended platform: **${prod.name}**.`,
    links: [
      { label: `Open ${ind.name} page`, href: `/industries/${ind.id}` },
      { label: `See ${prod.name}`, href: `/products/${prod.slug}` },
    ],
    suggestions: [prod.name, 'Book a demo', 'Industries', 'Menu'],
  };
};

/* ------------------------------ menus ------------------------------ */

const productsMenu: BotReply = {
  text: 'Here are our **7 ready-to-launch platforms**. Tap one to open its page, or ask me about any of them:',
  links: products.map((x) => ({ label: x.name, href: `/products/${x.slug}` })),
  suggestions: [...products.map((x) => x.name), 'Menu'],
};

const servicesMenu: BotReply = {
  text: 'We cover the full software lifecycle — **10 services**. Tap one to open its page, or pick it below to learn more:',
  links: services.map((s) => ({ label: s.title, href: `/services/${s.id}` })),
  suggestions: [...services.map((s) => s.title), 'Menu'],
};

const industriesMenu: BotReply = {
  text: 'We build domain-ready software for these industries:',
  links: industries.map((i) => ({ label: i.name, href: `/industries/${i.id}` })),
  suggestions: [...industries.map((i) => i.name), 'Menu'],
};

export const welcome: BotReply = {
  text: `Hi! I'm **MTK Bot** 🤖\nI can show you our products and services, open the right page for you, explain pricing, or connect you with the team. Where shall we start?`,
  suggestions: MENU,
};

const pricingReply: BotReply = {
  text: `Pricing depends on scope — consultation and estimates are free.\n\n${engagementModels.map((m) => `• **${m.name}:** ${m.price}${m.period}`).join('\n')}`,
  links: [
    { label: 'Open pricing page', href: '/pricing' },
    { label: 'Get a free estimate', href: '/contact?intent=quote' },
  ],
  suggestions: ['How long does it take?', 'Do I own the code?', 'Book a demo', 'Menu'],
};

const humanReply: BotReply = {
  text: `Happy to connect you! 🙌 Message the team on WhatsApp, email **${site.email}** or call **${site.phone}**. We reply within 12 hours.`,
  links: [
    { label: 'Chat on WhatsApp', href: whatsappLink() },
    { label: 'Contact form', href: '/contact' },
  ],
  suggestions: ['Book a demo', 'Menu'],
};

const faq = (q: string) => faqs.find((f) => f.q.toLowerCase().includes(q))!.a;

/* ------------------------------ intents ----------------------------- */
// Earlier intents win ties, so menus and pricing sit near the top.
const intents: Intent[] = [
  { keywords: ['menu', 'main menu', 'start over', 'options', 'help me', 'what can you do'], reply: welcome },
  { keywords: ['hi', 'hello', 'hey', 'salam', 'assalam', 'aoa', 'hola', 'good morning', 'good evening'], reply: welcome },
  { keywords: ['products', 'product list', 'all products', 'your products', 'platforms', 'saas products', 'which apps'], reply: productsMenu },
  { keywords: ['services', 'all services', 'what services', 'what do you do', 'what do you offer', 'kya karte'], reply: servicesMenu },
  { keywords: ['industries', 'industry', 'sectors', 'which business'], reply: industriesMenu },
  { keywords: ['price', 'pricing', 'cost', 'kitna', 'kitne', 'qeemat', 'rate', 'budget', 'charges', 'fee', 'how much', 'quote', 'estimate', 'paise'], reply: pricingReply },
  {
    keywords: ['demo', 'meeting', 'appointment', 'schedule', 'consultation', 'book a demo'],
    reply: { text: 'Great! A free demo or consultation is 30 minutes with the engineer who builds your product. Pick a time that suits you:', links: [{ label: 'Book a demo', href: '/contact?intent=demo' }, { label: 'WhatsApp us', href: whatsappLink('Hello MTK Codex, I would like to book a demo. Could you share your available time slots?') }], suggestions: ['Products', 'Services', 'Menu'] },
  },
  ...products.map((x) => ({ keywords: [x.name.toLowerCase(), ...(productWords[x.slug] ?? [])], reply: productReply(x) })),
  ...services.map((s) => ({ keywords: [s.title.toLowerCase(), ...(serviceWords[s.id] ?? [])], reply: serviceReply(s) })),
  ...industries.map((i) => ({ keywords: [i.name.toLowerCase(), ...(industryWords[i.id] ?? [])], reply: industryReply(i.id) })),
  // After services/products, so 'WhatsApp' alone means 'contact us' but never outranks e.g. 'HubSpot with WhatsApp'.
  { keywords: ['talk to a human', 'human', 'agent', 'real person', 'contact', 'email', 'phone number', 'whatsapp number', 'on whatsapp', 'whatsapp', 'reach you', 'rabta', 'call me'], reply: humanReply },
  {
    keywords: ['how long', 'timeline', 'deadline', 'kitna time', 'duration', 'how many weeks', 'how fast', 'jaldi'],
    reply: { text: 'A white-label SaaS launch can take **days**. Custom projects run in weekly sprints — most MVPs take a few weeks — and you get a live preview link every week.', links: [{ label: 'How we work', href: '/services#how-we-work' }], suggestions: ['Pricing', 'Book a demo', 'Menu'] },
  },
  { keywords: ['own the code', 'ownership', 'source code', 'code handover', 'intellectual property'], reply: { text: faq('source code'), suggestions: ['Pricing', 'Menu'] } },
  { keywords: ['another team', 'someone else built', 'existing software', 'old system', 'take over'], reply: { text: faq('another team'), links: [{ label: 'Code audit', href: '/services/audit' }, { label: 'Maintenance', href: '/services/maintenance' }], suggestions: ['Maintenance & Support', 'Menu'] } },
  { keywords: ['communicate', 'updates', 'progress', 'report', 'weekly'], reply: { text: faq('communicate'), suggestions: ['Book a demo', 'Menu'] } },
  { keywords: ['payment gateway', 'jazzcash', 'easypaisa', 'stripe', 'gateway', 'cod', 'xpay', 'revenuecat'], reply: { text: faq('payment gateways'), suggestions: ['E-commerce', 'Menu'] } },
  {
    keywords: ['tech', 'stack', 'technology', 'next.js', 'nextjs', 'react', 'laravel', 'nestjs', 'node', 'database', 'postgres'],
    reply: { text: 'Our core stack: **Next.js, React, TypeScript, NestJS, Laravel, Node.js, PostgreSQL/Supabase, Redis, React Native and Electron** — deployed on Vercel, Docker and Cloudflare.', links: [{ label: 'Open platform page', href: '/platform' }], suggestions: ['Services', 'Menu'] },
  },
  { keywords: ['platform', 'architecture', 'multi tenant', 'multi-tenant', 'scalable', 'secure'], reply: { text: 'Every MTK Codex product runs on one proven foundation: multi-tenant data, built-in security (RLS, RBAC, audit logs), an automation engine and an AI layer.', links: [{ label: 'Open platform page', href: '/platform' }], suggestions: ['Products', 'Menu'] } },
  { keywords: ['international', 'abroad', 'outside pakistan', 'where are you', 'where is your', 'location', 'office', 'based in', 'which country', 'time zone', 'timezone', 'address', 'map', 'directions', 'visit you', 'kahan'], reply: { text: `Our headquarters is in **${fullAddress}** (${site.openingHours.label}). We also work remotely with clients worldwide, overlapping Gulf, European and US time zones.`, links: [{ label: 'Open in Google Maps', href: maps.open }, { label: 'Get directions', href: maps.directions }, { label: 'Locations page', href: '/locations' }], suggestions: ['Book a demo', 'Talk to a human', 'Menu'] } },
  { keywords: ['founder', 'ceo', 'owner', 'kashif', 'who are you', 'about you', 'about company', 'team', 'experience'], reply: { text: `MTK Codex was founded by **${site.founder.name}**, CEO & Full-Stack SaaS Architect, who has shipped 7 production platforms across 7 industries.`, links: [{ label: 'Open about page', href: '/about' }], suggestions: ['Products', 'Menu'] } },
  { keywords: ['review', 'testimonial', 'clients', 'customers', 'case study', 'portfolio', 'previous work'], reply: { text: 'Our clients include sports leagues, retailers, schools and farms. Read their stories and see live platforms:', links: [{ label: 'Customer stories', href: '/customers' }, { label: 'Founder portfolio', href: site.social.portfolio }], suggestions: ['Products', 'Menu'] } },
  { keywords: ['blog', 'article', 'insight', 'guide'], reply: { text: 'Our latest guides:', links: [{ label: 'Web scraping guide', href: '/blog/web-scraping-for-business-2026' }, { label: 'Choosing a CRM', href: '/blog/choosing-a-crm-2026' }, { label: 'Automation playbook', href: '/blog/business-automation-playbook' }, { label: 'All insights', href: '/blog' }], suggestions: ['Menu'] } },
  { keywords: ['job', 'jobs', 'career', 'hiring', 'internship', 'vacancy', 'cv', 'resume', 'naukri', 'work with you'], reply: { text: 'We are building a talent network for full-stack, mobile, backend, UI/UX and QA roles, plus internships.', links: [{ label: 'Open careers page', href: '/careers' }], suggestions: ['Menu'] } },
  { keywords: ['login', 'log in', 'sign in', 'my account', 'dashboard access'], reply: { text: 'Each MTK Codex product has its own secure sign-in. Choose yours here:', links: [{ label: 'Client login', href: '/login' }], suggestions: ['Talk to a human', 'Menu'] } },
  { keywords: ['free audit', 'offer', 'discount', 'promotion'], reply: { text: 'New clients can claim a **free code & security audit** this quarter.', links: [{ label: 'Claim free audit', href: '/contact?service=audit' }], suggestions: ['Code & Security Audit', 'Menu'] } },
  { keywords: ['privacy', 'cookie', 'gdpr', 'data protection', 'terms'], reply: { text: 'Your privacy matters. Review our policies or change cookie choices any time from the footer.', links: [{ label: 'Privacy policy', href: '/privacy' }, { label: 'Cookie policy', href: '/cookies' }, { label: 'Terms', href: '/terms' }], suggestions: ['Menu'] } },
  { keywords: ['thanks', 'thank you', 'shukriya', 'great', 'awesome', 'bye', 'perfect'], reply: { text: "You're welcome! 😊 Anything else? I'm right here — or message the team on WhatsApp.", suggestions: ['Menu', 'Talk to a human'] } },
];

/* ---------------------------- matching ----------------------------- */

// Hyphens become spaces so 'web-scraping' and 'web scraping' match the same keywords.
const normalise = (s: string) => ` ${s.toLowerCase().replace(/[^a-z0-9\s.]/g, ' ').replace(/\s+/g, ' ').trim()} `;

// Allows one typo in longer single words ("scrapping", "maintanance").
function closeEnough(a: string, b: string) {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  let j = 0;
  let edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      i++;
      j++;
      continue;
    }
    if (++edits > 1) return false;
    if (a.length > b.length) i++;
    else if (b.length > a.length) j++;
    else {
      i++;
      j++;
    }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}

const exact = new Map<string, BotReply>();
for (const it of intents) exact.set(normalise(it.keywords[0]).trim(), it.reply);
exact.set('menu', welcome);

export function answer(question: string): BotReply {
  const q = normalise(question);
  const direct = exact.get(q.trim());
  if (direct) return direct;

  const words = q.trim().split(' ');
  let best: Intent | null = null;
  let bestScore = 0;
  for (const intent of intents) {
    let score = 0;
    for (const k of intent.keywords) {
      const key = normalise(k).trim();
      // Short keywords must be whole words; longer ones must start a word (so 'scrap' matches 'scraping' but 'rate' never matches 'integrate').
      if (key.length <= 3 ? q.includes(` ${key} `) : q.includes(` ${key}`)) score += key.length > 6 ? 2 : 1;
      else if (!key.includes(' ') && key.length >= 6 && words.some((w) => closeEnough(w, key))) score += 1;
    }
    if (score > bestScore) {
      best = intent;
      bestScore = score;
    }
  }
  if (best) return best.reply;
  return {
    text: "I'm not sure I can answer that one properly. 🙈 Our team can help you directly on WhatsApp — usually within a few hours.",
    links: [
      { label: 'Ask on WhatsApp', href: whatsappLink(`Hi MTK Codex, I have a question: ${question}`) },
      { label: 'Email us', href: `mailto:${site.email}` },
    ],
    suggestions: ['Menu', 'Products', 'Services'],
  };
}

/* ------------------------- page awareness -------------------------- */

/** A context-specific opener for the page the visitor is on (or null for generic pages). */
export function contextReply(pathname: string): BotReply | null {
  const [, section, slug] = pathname.split('/');
  if (section === 'services' && slug) {
    const s = services.find((x) => x.id === slug);
    if (s)
      return {
        text: `You're viewing **${s.title}**. I can explain what's included, pricing and timelines — or get you started right away.`,
        links: [{ label: 'Discuss this service', href: `/contact?service=${s.id}` }],
        suggestions: [s.title, 'Pricing', 'How long does it take?', 'Services', 'Talk to a human'],
      };
  }
  if (section === 'products' && slug) {
    const x = products.find((p) => p.slug === slug);
    if (x)
      return {
        text: `You're viewing **${x.name}**. Want a quick summary, a live demo, or pricing for your business?`,
        links: [...(x.liveUrl ? [{ label: 'Open live app', href: x.liveUrl }] : []), { label: 'Book a demo', href: `/contact?intent=demo&product=${x.slug}` }],
        suggestions: [x.name, 'Pricing', 'White-label for my brand', 'Products', 'Talk to a human'],
      };
  }
  if (section === 'industries' && slug) {
    const ind = industries.find((i) => i.id === slug);
    if (ind) return { text: `Interested in **${ind.name}** software? I can show the matching platform and services.`, suggestions: [ind.name, 'Services', 'Book a demo', 'Menu'] };
  }
  if (section === 'services') return { text: 'Browsing our services? Pick one and I will open its page or explain what is included.', suggestions: [...services.map((s) => s.title), 'Menu'] };
  if (section === 'products') return { text: 'Browsing our products? Pick one for a quick summary and its live link.', suggestions: [...products.map((p) => p.name), 'Menu'] };
  if (section === 'pricing') return { text: 'Questions about pricing? I can explain each plan or get you a free estimate.', suggestions: ['Pricing', 'Do I own the code?', 'Book a demo', 'Menu'] };
  if (section === 'contact') return { text: 'Ready to talk? Fill in the form, or message the team instantly on WhatsApp.', links: [{ label: 'Chat on WhatsApp', href: whatsappLink() }], suggestions: ['Pricing', 'Menu'] };
  return null;
}
