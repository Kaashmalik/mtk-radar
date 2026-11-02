import { process } from '@/data/services';
import { SectionHeading } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

export default function Process() {
  return (
    <section id="how-we-work" className="scroll-mt-20 bg-muted py-20">
      <div className="container-x">
        <SectionHeading eyebrow="How we work" title="From first call to continuous growth." text="A transparent, five-step delivery model — no surprises, no black boxes." />
        <ol className="relative mt-14 grid gap-5 md:grid-cols-5">
          <div className="absolute left-0 right-0 top-7 hidden h-px bg-[linear-gradient(90deg,transparent,var(--brand),var(--accent),transparent)] md:block" />
          {process.map((p, i) => (
            <Reveal as="li" key={p.step} delay={i * 90} className="relative">
              <span className="relative z-10 grid size-14 place-items-center rounded-2xl border border-line bg-elevated font-display text-lg font-bold text-brand shadow-card">
                {p.step}
              </span>
              <h3 className="mt-5 text-lg font-bold">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-fg-muted">{p.text}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
