'use client';

import { useEffect, useState } from 'react';
import { prefersReducedMotion, useInView } from './useInView';

/** Animates the numeric part of a label like "500+", "99.9%", "<2s" or "50K+". */
export default function CountUp({ value, duration = 1600, className }: { value: string; duration?: number; className?: string }) {
  const match = value.match(/^(\D*)(\d+(?:\.\d+)?)(.*)$/);
  const [ref, inView] = useInView<HTMLSpanElement>(0.4);
  const target = match ? parseFloat(match[2]) : 0;
  const decimals = match?.[2].includes('.') ? match[2].split('.')[1].length : 0;
  const [n, setN] = useState(0);

  useEffect(() => {
    if (!inView || !match) return;
    if (prefersReducedMotion()) {
      setN(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      setN(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, target, duration]);

  if (!match) return <span className={className}>{value}</span>;
  return (
    <span ref={ref} className={className} aria-label={value}>
      {match[1]}
      {inView ? n.toFixed(decimals) : (0).toFixed(decimals)}
      {match[3]}
    </span>
  );
}
