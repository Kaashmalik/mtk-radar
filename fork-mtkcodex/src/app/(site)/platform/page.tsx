import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { Activity, Bot, CreditCard, Globe2, Lock, Plug, Server, Workflow } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import { Button, SectionHeading } from '@/components/ui/primitives';
import { Aurora } from '@/components/motion/Effects';
import PlatformDiagram from '@/components/sections/PlatformDiagram';
import ImpactDashboard from '@/components/sections/ImpactDashboard';
import Stats from '@/components/sections/Stats';
import CtaBand from '@/components/sections/CtaBand';
import Reveal from '@/components/ui/Reveal';

export const metadata: Metadata = pageMeta({
  title: 'Platform',
  description: 'The MTK Codex platform: multi-tenant architecture, built-in security, automation engine, AI layer and integrations behind every product we build.',
  path: '/platform',
  keywords: ['multi-tenant SaaS platform', 'SaaS architecture', 'AI platform', 'workflow automation platform'],
});

const capabilities = [
  { icon: Server, title: 'Multi-tenancy', text: 'PostgreSQL Row Level Security, Clerk Organizations and subdomain isolation keep every customer’s data separate.' },
  { icon: Lock, title: 'Security & access', text: 'Role-based access with up to 7 levels, audit logs, encrypted secrets and secure auth (Clerk, Sanctum, JWT).' },
  { icon: Workflow, title: 'Automation engine', text: 'BullMQ, Laravel Horizon and Kafka power background jobs, schedules, reminders and event-driven workflows.' },
  { icon: Bot, title: 'AI layer', text: 'OpenAI GPT, Vercel AI SDK streaming, Tesseract OCR and TensorFlow.js on-device vision.' },
  { icon: CreditCard, title: 'Payments & billing', text: 'Stripe, RevenueCat, JazzCash, EasyPaisa, XPay and COD with subscriptions and feature gating.' },
  { icon: Plug, title: 'Integrations', text: 'REST & WebSocket APIs, IoT devices, Twilio, WhatsApp, Resend, Cloudinary and your existing tools.' },
  { icon: Globe2, title: 'Global-ready', text: 'Internationalisation with RTL Urdu support, PWA offline mode and edge delivery via Vercel & Cloudflare.' },
  { icon: Activity, title: 'Observability', text: 'Sentry error tracking, PostHog analytics, uptime monitoring and real-time dashboards.' },
];

const stack = ['Next.js', 'React', 'TypeScript', 'NestJS', 'Laravel', 'Node.js', 'PostgreSQL', 'Supabase', 'Redis', 'Kafka', 'ClickHouse', 'Firebase', 'React Native', 'Expo', 'Electron', 'Docker', 'Vercel', 'Cloudflare', 'Stripe', 'OpenAI', 'TensorFlow.js', 'Sentry'];

export default function PlatformPage() {
  return (
    <>
      <div className="relative isolate overflow-hidden">
        <Aurora />
        <PageHeader
          eyebrow="Platform"
          title={
            <>
              The engine behind <span className="text-gradient">every MTK Codex product.</span>
            </>
          }
          text="Enterprise-grade architecture — multi-tenant, secure, automated and AI-ready — packaged so growing businesses can launch faster and scale without rewrites."
        >
          <Button href="/contact?intent=demo" size="lg" arrow>
            Book a platform demo
          </Button>
          <Button href="/products" size="lg" variant="secondary">
            See products built on it
          </Button>
        </PageHeader>
      </div>

      <PlatformDiagram cta={false} />

      <section className="container-x py-20">
        <SectionHeading eyebrow="Capabilities" title="Everything a modern business platform needs." />
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {capabilities.map((c, i) => (
            <Reveal key={c.title} delay={(i % 4) * 70}>
              <div className="card spotlight h-full p-6 transition hover:-translate-y-1 hover:shadow-float">
                <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent">
                  <c.icon className="size-5" />
                </span>
                <h3 className="mt-5 text-lg font-bold">{c.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-fg-muted">{c.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <ImpactDashboard />
      <Stats />

      <section className="pb-20">
        <p className="container-x mb-6 text-center text-xs font-semibold uppercase tracking-[0.18em] text-fg-subtle">Technology we run in production</p>
        <div className="marquee relative overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_10%,black_90%,transparent)]">
          <div className="marquee-track gap-3 pr-3">
            {[...stack, ...stack].map((t, i) => (
              <span key={i} aria-hidden={i >= stack.length} className="shrink-0 rounded-full border border-line bg-elevated px-5 py-2.5 text-sm font-semibold text-fg-muted">
                {t}
              </span>
            ))}
          </div>
        </div>
      </section>

      <CtaBand title="Build on a platform that's already proven." />
    </>
  );
}
