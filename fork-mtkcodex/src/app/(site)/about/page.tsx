import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { Eye, Gauge, HeartHandshake, Lock } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import { SectionHeading } from '@/components/ui/primitives';
import Founder from '@/components/sections/Founder';
import Stats from '@/components/sections/Stats';
import CtaBand from '@/components/sections/CtaBand';
import LocationMap from '@/components/location/LocationMap';
import Reveal from '@/components/ui/Reveal';

export const metadata: Metadata = pageMeta({
  title: 'About Us',
  description: 'MTK Codex is a Lahore-based software company founded by Muhammad Kashif, building SaaS platforms, custom systems and automations for businesses worldwide.',
  path: '/about',
  keywords: ['about MTK Codex', 'Muhammad Kashif', 'software house Lahore', 'Pakistan software company'],
});

const values = [
  { icon: Gauge, title: 'Built to scale', text: 'Multi-tenant, cached and monitored from day one — so growth never means a rewrite.' },
  { icon: Lock, title: 'Secure by default', text: 'Row-level security, role-based access and audit logs are standard, not add-ons.' },
  { icon: Eye, title: 'Radical transparency', text: 'Weekly demos, live preview links and fixed quotes. You always know where things stand.' },
  { icon: HeartHandshake, title: 'Long-term partners', text: 'We stay after launch — maintaining, improving and automating as your business evolves.' },
];

const timeline = [
  { year: '2022', title: 'Freelance beginnings', text: '10+ client projects delivered — storefronts, dashboards and landing pages.' },
  { year: '2023', title: 'Full-stack & commerce', text: 'LaraibCreative launched; stack standardised on Next.js, TypeScript and Tailwind.' },
  { year: '2024', title: 'MTK Codex founded', text: 'Shift to multi-tenant SaaS: InstalEase, MTK Dairy and MTK Edu take shape.' },
  { year: '2025', title: 'AI & multi-platform', text: 'Shakir Super League, MTK AlertPro and MTK Download Manager expand into AI, mobile and desktop.' },
  { year: '2026', title: 'Services company', text: 'MTK Codex opens its platforms and engineering team to businesses worldwide.' },
];

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="About MTK Codex"
        title={
          <>
            We engineer the software <span className="text-gradient">businesses run on.</span>
          </>
        }
        text="MTK Codex is a Lahore-based software company building SaaS platforms, custom systems and automations for growing businesses around the world."
      />
      <Stats />

      <section className="container-x py-12">
        <SectionHeading eyebrow="Our values" title="What every MTK Codex project stands on." />
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {values.map((v, i) => (
            <Reveal key={v.title} delay={i * 80}>
              <div className="card h-full p-6">
                <v.icon className="size-6 text-brand" />
                <h3 className="mt-4 text-lg font-bold">{v.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-fg-muted">{v.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <Founder />

      <section className="container-x py-12">
        <SectionHeading eyebrow="Our journey" title="From freelance to a full software company." />
        <ol className="mx-auto mt-12 max-w-3xl border-l border-line pl-8">
          {timeline.map((t) => (
            <Reveal as="li" key={t.year} className="relative pb-10 last:pb-0">
              <span className="absolute -left-[41px] top-1 grid size-5 place-items-center rounded-full border-4 border-bg bg-cta" />
              <p className="font-display text-sm font-bold text-brand">{t.year}</p>
              <h3 className="mt-1 text-xl font-bold">{t.title}</h3>
              <p className="mt-1 text-fg-muted">{t.text}</p>
            </Reveal>
          ))}
        </ol>
      </section>

      <LocationMap />
      <CtaBand />
    </>
  );
}
