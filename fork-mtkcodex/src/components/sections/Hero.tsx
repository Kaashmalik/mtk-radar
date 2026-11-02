import Link from 'next/link';
import { CheckCircle2, PlayCircle } from 'lucide-react';
import { site } from '@/data/site';
import { Button } from '@/components/ui/primitives';
import { Aurora, RotatingWord } from '@/components/motion/Effects';
import HeroDemo from './HeroDemo';

export default function Hero() {
  return (
    <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
      <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <Aurora />

      <div className="container-x grid items-center gap-14 pb-20 pt-14 lg:grid-cols-[1.05fr_1fr] lg:pb-24 lg:pt-20">
        <div>
          <Link
            href="/products"
            className="inline-flex items-center gap-2 rounded-full border border-line bg-elevated/70 py-1 pl-1 pr-3 text-xs font-medium text-fg-muted backdrop-blur transition hover:border-accent"
          >
            <span className="rounded-full bg-cta px-2 py-0.5 font-semibold text-on-cta">New</span>
            7 SaaS platforms, ready to launch under your brand →
          </Link>
          <h1 className="mt-6 text-[2.6rem] font-extrabold leading-[1.04] sm:text-6xl lg:text-[4.2rem]">
            Code that scales
            <br />
            your <RotatingWord words={['business.', 'workflows.', 'operations.', 'growth.']} />
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-fg-muted">{site.tagline}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button href="/contact?intent=demo" size="lg" arrow>
              Book a free demo
            </Button>
            <Button href="#demos" size="lg" variant="secondary">
              <PlayCircle className="size-5" /> See products in action
            </Button>
          </div>
          <ul className="mt-8 grid gap-2 text-sm text-fg-muted sm:grid-cols-2">
            {['Free consultation & fixed quotes', 'You own 100% of the source code', 'Weekly demos & live preview links', '12-hour response, worldwide'].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <CheckCircle2 className="size-4 shrink-0 text-accent" /> {t}
              </li>
            ))}
          </ul>
        </div>

        <HeroDemo />
      </div>
    </section>
  );
}
