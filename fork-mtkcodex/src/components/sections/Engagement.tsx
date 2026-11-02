import { Check } from 'lucide-react';
import { engagementModels } from '@/data/content';
import { Button, SectionHeading } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

export default function Engagement({ heading = true }: { heading?: boolean }) {
  return (
    <section className="container-x py-20">
      {heading && (
        <SectionHeading eyebrow="Ways to work with us" title="Flexible engagement, transparent pricing." text="Subscribe to a platform, commission a custom build, or keep your existing software in expert hands." />
      )}
      <div className="mt-14 grid gap-6 lg:grid-cols-3">
        {engagementModels.map((m, i) => (
          <Reveal key={m.name} delay={i * 90}>
            <div
              className={`relative flex h-full flex-col rounded-[20px] p-8 ${
                m.featured ? 'night shadow-float ring-1 ring-lime/40' : 'card'
              }`}
            >
              {m.featured && (
                <span className="absolute -top-3 left-8 rounded-full bg-cta px-3 py-1 text-xs font-bold text-on-cta">Most popular</span>
              )}
              <h3 className="text-xl font-bold">{m.name}</h3>
              <p className={`mt-2 text-sm ${m.featured ? 'text-white/80' : 'text-fg-muted'}`}>{m.description}</p>
              <p className="mt-6 font-display text-4xl font-extrabold">
                {m.price}
                <span className={`text-base font-medium ${m.featured ? 'text-white/70' : 'text-fg-subtle'}`}>{m.period}</span>
              </p>
              <ul className="mt-6 flex-1 space-y-3 text-sm">
                {m.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check className={`mt-0.5 size-4 shrink-0 ${m.featured ? 'text-lime' : 'text-accent'}`} /> {f}
                  </li>
                ))}
              </ul>
              <Button
                href={m.href}
                variant={m.featured ? 'secondary' : 'primary'}
                className={`mt-8 w-full ${m.featured ? '!border-transparent !bg-cta !text-on-cta' : ''}`}
                arrow
              >
                {m.cta}
              </Button>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
