'use client';

import { useEffect, useState } from 'react';
import { prefersReducedMotion } from './useInView';

/** Thin gradient bar at the top of the page showing scroll progress. */
export function ScrollProgress() {
  const [p, setP] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const h = document.documentElement.scrollHeight - window.innerHeight;
      setP(h > 0 ? window.scrollY / h : 0);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);
  return (
    <div
      aria-hidden
      className="fixed inset-x-0 top-0 z-[60] h-[3px] origin-left bg-[linear-gradient(90deg,#62d84e,#2dd4bf,#60a5fa)]"
      style={{ transform: `scaleX(${p})` }}
    />
  );
}

/** Feeds cursor position into `.spotlight` cards via CSS variables (one global listener). */
export function SpotlightProvider() {
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.('.spotlight') as HTMLElement | null;
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty('--mx', `${e.clientX - r.left}px`);
      el.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, []);
  return null;
}

/** Cycles through words with a blur-in animation. */
export function RotatingWord({ words, interval = 2600, className = '' }: { words: string[]; interval?: number; className?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const t = setInterval(() => setI((x) => (x + 1) % words.length), interval);
    return () => clearInterval(t);
  }, [words.length, interval]);
  return (
    <span className={`relative inline-block ${className}`}>
      {/* Gradient lives on a child: Chrome won't paint background-clip text under an animated filter. */}
      <span key={i} className="word-in inline-block">
        <span className="text-gradient">{words[i]}</span>
      </span>
    </span>
  );
}

/** Animated aurora blobs for hero backgrounds. */
export function Aurora({ className = '' }: { className?: string }) {
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 -z-10 overflow-hidden ${className}`}>
      <div className="aurora-1 absolute left-[-10%] top-[-25%] size-[560px] rounded-full bg-[#14a89a] opacity-40 blur-[110px]" />
      <div className="aurora-2 absolute right-[-12%] top-[0%] size-[480px] rounded-full bg-[#62d84e] opacity-30 blur-[110px]" />
      <div className="aurora-3 absolute bottom-[-35%] left-[30%] size-[520px] rounded-full bg-[#0ea5a4] opacity-30 blur-[120px]" />
      <div className="aurora-2 absolute left-[45%] top-[10%] size-[300px] rounded-full bg-[#3b82f6] opacity-20 blur-[100px]" />
    </div>
  );
}
