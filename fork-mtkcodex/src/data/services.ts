export interface Service {
  id: string;
  icon: 'Code2' | 'Wrench' | 'ShieldCheck' | 'Workflow' | 'Rocket' | 'Bot' | 'Smartphone' | 'Cloud' | 'ScanSearch' | 'Contact';
  title: string;
  summary: string;
  deliverables: string[];
}

export const services: Service[] = [
  {
    id: 'custom-development',
    icon: 'Code2',
    title: 'Custom Software Development',
    summary: 'Web apps, SaaS platforms, portals and internal tools engineered around how your business actually works.',
    deliverables: ['Multi-tenant SaaS architecture', 'Admin dashboards & portals', 'APIs & integrations', 'Payments: Stripe, JazzCash, EasyPaisa'],
  },
  {
    id: 'saas-white-label',
    icon: 'Rocket',
    title: 'Ready-made SaaS & White-label',
    summary: 'Launch faster on our proven platforms — branded, configured and deployed for your organisation.',
    deliverables: ['Your brand, domain & logo', 'Configuration & data migration', 'Training & onboarding', 'Subscription billing setup'],
  },
  {
    id: 'maintenance',
    icon: 'Wrench',
    title: 'Maintenance & Support',
    summary: 'Keep existing systems healthy with monitoring, bug fixes, upgrades and an SLA you can rely on.',
    deliverables: ['Uptime & error monitoring', 'Security patches & upgrades', 'Bug-fix SLA', 'Monthly health reports'],
  },
  {
    id: 'improvement',
    icon: 'Cloud',
    title: 'Modernisation & Improvement',
    summary: 'Turn slow, legacy or fragile software into fast, maintainable, modern systems — without stopping the business.',
    deliverables: ['Framework & stack migration', 'Performance tuning (95+ Lighthouse)', 'UI/UX redesign', 'Database optimisation'],
  },
  {
    id: 'audit',
    icon: 'ShieldCheck',
    title: 'Code & Security Audit',
    summary: 'An independent, prioritised review of your codebase, architecture, security and infrastructure.',
    deliverables: ['Architecture & code quality review', 'Security & OWASP checks', 'Performance & cost review', 'Actionable remediation roadmap'],
  },
  {
    id: 'automation',
    icon: 'Workflow',
    title: 'Business Process Automation',
    summary: 'Eliminate repetitive work — connect your tools and let workflows run themselves.',
    deliverables: ['Workflow & approval automation', 'Reports & notifications', 'CRM / ERP / WhatsApp integrations', 'Scheduled jobs & queues'],
  },
  {
    id: 'web-scraping',
    icon: 'ScanSearch',
    title: 'Web Scraping & Data Extraction',
    summary: 'Turn the public web into clean, structured data — prices, leads, listings and market intelligence, delivered on schedule.',
    deliverables: ['Custom scrapers & crawlers', 'Price & competitor monitoring', 'Lead & directory extraction', 'Clean data to Sheets, CRM, API or DB'],
  },
  {
    id: 'crm',
    icon: 'Contact',
    title: 'CRM Systems & Integration',
    summary: 'Custom CRMs and expert setup of the one you use — pipelines, automations and reporting your sales team will actually love.',
    deliverables: ['Custom CRM development', 'HubSpot / Zoho / Salesforce setup', 'Lead capture & sales pipelines', 'WhatsApp, email & calling integration'],
  },
  {
    id: 'ai',
    icon: 'Bot',
    title: 'AI Integration & Agents',
    summary: 'Put AI to work inside your product: assistants, document processing, predictions and on-device ML.',
    deliverables: ['AI chat & copilots', 'Document & OCR pipelines', 'Predictive analytics', 'On-device computer vision'],
  },
  {
    id: 'mobile-desktop',
    icon: 'Smartphone',
    title: 'Mobile & Desktop Apps',
    summary: 'Cross-platform iOS, Android and desktop apps that share one codebase and one team.',
    deliverables: ['React Native / Expo apps', 'Offline-first sync', 'Electron desktop apps', 'App store & auto-update delivery'],
  },
];

export const process = [
  { step: '01', title: 'Discover', text: 'Free consultation and a written scope: goals, users, risks and a fixed estimate.' },
  { step: '02', title: 'Design', text: 'Architecture, data model and clickable UI prototypes approved before code.' },
  { step: '03', title: 'Build', text: 'Weekly sprints with live preview links, demos and transparent progress.' },
  { step: '04', title: 'Launch', text: 'Hardened deployment, monitoring, documentation and team training.' },
  { step: '05', title: 'Scale', text: 'Ongoing support, automation and improvements as your business grows.' },
];

export const automations = [
  { trigger: 'New order placed', action: 'Invoice generated → WhatsApp receipt sent → stock updated' },
  { trigger: 'Payment overdue', action: 'Reminder SMS → late fee applied → manager notified' },
  { trigger: 'Lead form submitted', action: 'CRM record created → sales assigned → follow-up scheduled' },
  { trigger: 'Month end', action: 'Reports compiled → PDF emailed to owners → backups verified' },
];

export const serviceDetails: Record<string, { intro: string; outcomes: string[]; related: string[] }> = {
  'custom-development': {
    intro:
      'We turn your process into a product. Starting from a written scope and clickable prototype, we build secure, multi-tenant web platforms with clean APIs, role-based access and payments — then hand over full source code and documentation.',
    outcomes: ['A product that matches how your team really works', 'Architecture ready for thousands of users', 'Full ownership of code and data'],
    related: ['instalease', 'mtk-edu', 'shakir-super-league'],
  },
  'saas-white-label': {
    intro:
      'Skip months of development. Pick a proven MTK Codex platform, and we brand it, configure it, migrate your data and train your team — so you go live in days with a product that already runs in production.',
    outcomes: ['Launch in days instead of months', 'Lower upfront cost with a subscription', 'Continuous updates from our product roadmap'],
    related: ['mtk-dairy', 'instalease', 'shakir-super-league'],
  },
  maintenance: {
    intro:
      'Software is never "done". We monitor uptime and errors, patch security issues, upgrade dependencies and fix bugs under a clear SLA — with a monthly health report so you always know the state of your system.',
    outcomes: ['Fewer outages and faster fixes', 'Up-to-date, secure dependencies', 'Predictable monthly cost'],
    related: ['mtk-dairy', 'laraibcreative'],
  },
  improvement: {
    intro:
      'Slow pages, fragile code or an outdated stack holding you back? We modernise incrementally — migrating frameworks, redesigning UI and tuning databases — without stopping your business.',
    outcomes: ['95+ Lighthouse performance', 'Lower hosting costs', 'A codebase new developers can work in'],
    related: ['laraibcreative', 'instalease'],
  },
  audit: {
    intro:
      'An independent review of your codebase, architecture, security and infrastructure. You receive a prioritised, plain-language report with severity ratings and a remediation roadmap — whether we do the fixes or your team does.',
    outcomes: ['Clear list of security risks', 'Prioritised technical-debt roadmap', 'Confidence before investment or scale-up'],
    related: ['instalease', 'mtk-dairy'],
  },
  automation: {
    intro:
      'If your team does it twice, it can be automated. We map your workflows, then connect your apps, WhatsApp, email, CRMs and payment gateways with queues and scheduled jobs that run reliably in the background.',
    outcomes: ['Hours of manual work removed every week', 'Fewer data-entry errors', 'Instant notifications and reports'],
    related: ['instalease', 'mtk-dairy', 'mtk-edu'],
  },
  'web-scraping': {
    intro:
      'We design robust, ethical data pipelines that collect publicly available information from websites, marketplaces, directories and documents — then clean, de-duplicate and deliver it exactly where your team works. Scrapers run on a schedule, survive layout changes and alert you when something breaks. We respect robots.txt, site terms and data-protection law, and recommend official APIs wherever they exist.',
    outcomes: ['Fresh competitor prices and stock levels every day', 'Targeted lead lists without manual copy-paste', 'Market data your analysts can trust'],
    related: ['instalease', 'laraibcreative', 'mtk-dairy'],
  },
  crm: {
    intro:
      'Whether you need a CRM built around your exact sales process or expert setup of HubSpot, Zoho or Salesforce, we design pipelines, lead scoring, automated follow-ups and dashboards — and connect them to your website, WhatsApp, email, calling and billing so no lead slips through.',
    outcomes: ['Every lead captured and followed up automatically', 'Clear pipeline visibility for managers', 'Higher conversion with less admin work'],
    related: ['instalease', 'mtk-edu', 'laraibcreative'],
  },
  ai: {
    intro:
      'Practical AI that earns its place: assistants inside your product, document and OCR pipelines, predictive analytics and on-device computer vision — built with safeguards, caching and cost control.',
    outcomes: ['AI features customers actually use', 'Controlled, predictable AI costs', 'Privacy-first options with on-device ML'],
    related: ['mtk-alertpro', 'shakir-super-league', 'mtk-edu'],
  },
  'mobile-desktop': {
    intro:
      'One team for every screen. We build React Native apps for iOS and Android with offline-first sync, and Electron desktop apps for Windows, macOS and Linux with auto-updates.',
    outcomes: ['iOS, Android and desktop from one codebase', 'Apps that keep working offline', 'Store-ready builds and auto-updates'],
    related: ['mtk-alertpro', 'mtk-download-manager', 'mtk-edu'],
  },
};
