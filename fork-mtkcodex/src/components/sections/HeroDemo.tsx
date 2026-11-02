'use client';

import { useEffect, useState } from 'react';
import { Pause, Play } from 'lucide-react';
import { products } from '@/data/products';
import ProductDemo, { HeroWidgets } from '@/components/demo/ProductDemo';
import { prefersReducedMotion } from '@/components/motion/useInView';

const DURATION = 5000;
// Desktop-style demos read best in the hero; the phone mockup is shown elsewhere.
const heroProducts = products.filter((p) => p.demo !== 'alertpro');

/** Auto-cycling product preview with progress pills (pauses on hover). */
export default function HeroDemo() {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false); // temporary, while hovered
  const [stopped, setStopped] = useState(false); // sticky, after a click or the pause button
  const halted = paused || stopped;

  useEffect(() => {
    if (halted || prefersReducedMotion()) return;
    const t = setTimeout(() => setI((x) => (x + 1) % heroProducts.length), DURATION);
    return () => clearTimeout(t);
  }, [i, halted]);

  const p = heroProducts[i];

  return (
    <div className="relative" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="relative">
        <div key={p.slug} className="word-in block">
          <ProductDemo product={p} />
        </div>
        <HeroWidgets />
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
        {heroProducts.map((prod, k) => (
          <button
            key={prod.slug}
            type="button"
            onClick={() => {
              setI(k);
              setStopped(true);
            }}
            aria-label={`Show ${prod.name}`}
            className={`relative h-7 overflow-hidden rounded-full border px-3 text-[11px] font-semibold transition ${
              k === i ? 'border-transparent bg-elevated text-fg shadow-card' : 'border-line text-fg-subtle hover:text-fg'
            }`}
          >
            {k === i && (
              <span
                key={`${i}-${halted}`}
                className="absolute inset-x-0 bottom-0 h-[2px] origin-left"
                style={{
                  background: prod.accent,
                  animation: halted ? 'none' : `tab-progress ${DURATION}ms linear forwards`,
                  transform: halted ? 'scaleX(1)' : undefined,
                }}
              />
            )}
            <span className="relative">{prod.name}</span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => setStopped((s) => !s)}
          aria-label={stopped ? 'Resume product slideshow' : 'Pause product slideshow'}
          className="grid size-7 place-items-center rounded-full border border-line text-fg-subtle transition hover:border-brand hover:text-brand"
        >
          {stopped ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
        </button>
      </div>
    </div>
  );
}
