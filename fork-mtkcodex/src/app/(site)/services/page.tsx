import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { Check } from 'lucide-react';
import { services } from '@/data/services';
import PageHeader from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/primitives';
import ServiceIcon from '@/components/ui/ServiceIcon';
import Reveal from '@/components/ui/Reveal';
import Automation from '@/components/sections/Automation';
import InfinityLoop from '@/components/sections/InfinityLoop';
import ScrapingShowcase from '@/components/sections/ScrapingShowcase';
import CrmShowcase from '@/components/sections/CrmShowcase';
import Process from '@/components/sections/Process';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Software Development Services',
  description: 'Custom software development, SaaS white-labelling, maintenance, modernisation, code & security audits, business automation, AI integration and mobile apps by MTK Codex.',
  path: '/services',
  keywords: ['software development company', 'software maintenance', 'code audit', 'business process automation', 'AI integration services', 'Next.js development'],
});

export default function ServicesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Services"
        title={
          <>
            Engineering for every stage of <span className="text-gradient">your software.</span>
          </>
        }
        text="New product, legacy system or somewhere in between — we design, build, audit, maintain and automate with one accountable team."
      >
        <Button href="/contact?intent=quote" size="lg" arrow>
          Get a free estimate
        </Button>
        <Button href="/contact?service=audit" size="lg" variant="secondary">
          Request a code audit
        </Button>
      </PageHeader>

      <InfinityLoop compact />

      <section className="container-x space-y-6 py-20">
        {services.map((s, i) => (
          <Reveal key={s.id}>
            <article id={s.id} className="card spotlight grid scroll-mt-24 gap-8 p-8 sm:p-10 lg:grid-cols-[1fr_1fr] lg:items-center">
              <div>
                <span className="font-display text-sm font-bold text-fg-subtle">{String(i + 1).padStart(2, '0')}</span>
                <div className="mt-3 flex items-center gap-4">
                  <span className="grid size-12 place-items-center rounded-xl bg-brand-soft text-brand">
                    <ServiceIcon name={s.icon} className="size-6" />
                  </span>
                  <h2 className="text-2xl font-bold sm:text-3xl">{s.title}</h2>
                </div>
                <p className="mt-4 text-lg leading-relaxed text-fg-muted">{s.summary}</p>
                <Button href={`/services/${s.id}`} variant="ghost" arrow className="mt-4 -ml-4">
                  Explore this service
                </Button>
              </div>
              <ul className="grid gap-3 sm:grid-cols-2">
                {s.deliverables.map((d) => (
                  <li key={d} className="flex items-start gap-3 rounded-xl bg-muted p-4 text-sm font-medium">
                    <Check className="mt-0.5 size-4 shrink-0 text-accent" /> {d}
                  </li>
                ))}
              </ul>
            </article>
          </Reveal>
        ))}
      </section>

      <ScrapingShowcase />
      <CrmShowcase />
      <Automation />
      <Process />
      <CtaBand />
    </>
  );
}
