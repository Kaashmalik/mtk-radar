import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { services } from '@/data/services';
import { SectionHeading } from '@/components/ui/primitives';
import ServiceIcon from '@/components/ui/ServiceIcon';
import Reveal from '@/components/ui/Reveal';

export default function ServicesGrid() {
  return (
    <section id="services" className="container-x py-20">
      <SectionHeading
        eyebrow="Services"
        title={
          <>
            Build it. Fix it. Scrape it. <span className="text-gradient">Automate it.</span>
          </>
        }
        text="Whether you need a new product or need your current software to work harder, one accountable team covers the full lifecycle."
      />
      <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {services.map((s, i) => (
          <Reveal key={s.id} delay={(i % 5) * 70}>
            <Link href={`/services/${s.id}`} className="card spotlight group flex h-full flex-col p-6 transition hover:-translate-y-1 hover:border-brand hover:shadow-float">
              <span className="grid size-11 place-items-center rounded-xl bg-brand-soft text-brand transition group-hover:bg-cta group-hover:text-on-cta">
                <ServiceIcon name={s.icon} className="size-5" />
              </span>
              <h3 className="mt-5 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-fg-muted">{s.summary}</p>
              <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-brand">
                Learn more <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
              </span>
            </Link>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
