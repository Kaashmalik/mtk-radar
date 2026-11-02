'use client';

import { useEffect, useState } from 'react';
import { Check, ExternalLink, Pause, Play } from 'lucide-react';
import { products } from '@/data/products';
import { Button, SectionHeading } from '@/components/ui/primitives';
import ProductDemo from '@/components/demo/ProductDemo';
import { prefersReducedMotion } from '@/components/motion/useInView';

const DURATION = 9000;

export default function DemoShowcase() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [stopped, setStopped] = useState(false);
  const p = products[active];
  const running = !paused && !stopped;

  // Auto-advance like an enterprise product tour; a click on any tab stops it so the visitor can read.
  useEffect(() => {
    if (!running || prefersReducedMotion()) return;
    const t = setTimeout(() => setActive((x) => (x + 1) % products.length), DURATION);
    return () => clearTimeout(t);
  }, [active, running]);

  return (
    <section id="demos" className="relative scroll-mt-16 overflow-hidden bg-muted py-20" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="container-x">
        <SectionHeading
          eyebrow="Product demos"
          title="See every platform in action."
          text="Click through live previews of our products. Want the full walkthrough? Book a guided demo with the engineer who built it."
        />

        <div role="tablist" aria-label="Products" className="mt-10 flex gap-2 overflow-x-auto pb-2 [scrollbar-width:none] sm:flex-wrap sm:justify-center">
          {products.map((prod, i) => (
            <button
              key={prod.slug}
              role="tab"
              type="button"
              aria-selected={i === active}
              aria-controls="demo-panel"
              onClick={() => {
                setActive(i);
                setStopped(true);
              }}
              className={`relative shrink-0 overflow-hidden rounded-full border px-4 py-2 text-sm font-semibold transition ${
                i === active ? 'border-transparent text-white shadow-card' : 'border-line bg-elevated text-fg-muted hover:text-fg'
              }`}
              style={i === active ? { background: prod.accent } : undefined}
            >
              {i === active && running && (
                <span
                  key={active}
                  className="absolute inset-x-0 bottom-0 h-[3px] origin-left bg-white/70"
                  style={{ animation: `tab-progress ${DURATION}ms linear forwards` }}
                />
              )}
              <span className="relative">{prod.name}</span>
            </button>
          ))}
          <button
            type="button"
            onClick={() => setStopped((s) => !s)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-elevated px-4 py-2 text-sm font-semibold text-fg-muted transition hover:border-brand hover:text-brand"
          >
            {stopped ? <Play className="size-4" /> : <Pause className="size-4" />}
            {stopped ? 'Auto-play' : 'Pause'}
          </button>
        </div>

        <div id="demo-panel" role="tabpanel" className="mt-10 grid items-center gap-10 lg:grid-cols-[1fr_1.25fr]">
          <div key={p.slug} className="word-in block">
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: p.accent }}>
              {p.cloud} · {p.category}
            </span>
            <h3 className="mt-3 text-3xl font-bold">{p.tagline}</h3>
            <p className="mt-4 leading-relaxed text-fg-muted">{p.overview}</p>
            <ul className="mt-6 space-y-3">
              {p.features.map((f) => (
                <li key={f.title} className="flex gap-3 text-sm">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-white" style={{ background: p.accent }}>
                    <Check className="size-3" />
                  </span>
                  <span>
                    <strong className="font-semibold">{f.title}.</strong> <span className="text-fg-muted">{f.text}</span>
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button href={`/products/${p.slug}`} arrow>
                Product details
              </Button>
              {p.liveUrl ? (
                <Button href={p.liveUrl} external variant="secondary">
                  Open live app <ExternalLink className="size-4" />
                </Button>
              ) : (
                <Button href={`/contact?intent=demo&product=${p.slug}`} variant="secondary">
                  Request guided demo
                </Button>
              )}
            </div>
          </div>
          <div key={`${p.slug}-demo`} className="word-in block">
            <ProductDemo product={p} />
          </div>
        </div>
      </div>
    </section>
  );
}
