import { site } from '@/data/site';
import Reveal from '@/components/ui/Reveal';
import CountUp from '@/components/motion/CountUp';

export default function Stats() {
  return (
    <section className="container-x py-20">
      <Reveal className="grid grid-cols-2 gap-px overflow-hidden rounded-3xl border border-line bg-line md:grid-cols-3 lg:grid-cols-6">
        {site.stats.map((s) => (
          <div key={s.label} className="spotlight bg-elevated p-6 text-center">
            <CountUp value={s.value} className="text-gradient font-display text-3xl font-extrabold sm:text-4xl" />
            <p className="mt-2 text-xs leading-snug text-fg-muted sm:text-sm">{s.label}</p>
          </div>
        ))}
      </Reveal>
    </section>
  );
}
