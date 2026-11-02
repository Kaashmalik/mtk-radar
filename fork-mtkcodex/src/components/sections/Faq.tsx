import { Plus } from 'lucide-react';
import { faqs } from '@/data/content';
import { SectionHeading } from '@/components/ui/primitives';

export default function Faq() {
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })),
  };
  return (
    <section className="container-x grid gap-12 py-20 lg:grid-cols-[1fr_1.4fr]">
      <SectionHeading align="left" eyebrow="FAQ" title="Questions, answered." text="Can't find what you're looking for? Message us on WhatsApp — we reply within 12 hours." />
      <div className="divide-y divide-line rounded-[20px] border border-line bg-elevated">
        {faqs.map((f) => (
          <details key={f.q} className="group p-6">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold">
              {f.q}
              <Plus className="size-5 shrink-0 text-brand transition-transform group-open:rotate-45" />
            </summary>
            <p className="mt-3 leading-relaxed text-fg-muted">{f.a}</p>
          </details>
        ))}
      </div>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </section>
  );
}
