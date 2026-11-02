'use client';

import { useEffect, useId, useState } from 'react';
import { prefersReducedMotion, useInView } from './useInView';

/* Lightweight animated SVG charts. They animate when scrolled into view. */

const W = 320;
const H = 120;

function toPath(values: number[], max: number, min = 0) {
  const span = max - min || 1;
  return values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${((i / (values.length - 1)) * W).toFixed(1)} ${(H - ((v - min) / span) * (H - 8) - 4).toFixed(1)}`).join(' ');
}

export function AreaChart({ values, color, labels, height = 140 }: { values: number[]; color: string; labels?: string[]; height?: number }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  const id = useId().replace(/:/g, '');
  const max = Math.max(...values) * 1.1;
  const line = toPath(values, max);
  return (
    <div ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }} className="w-full overflow-visible" role="img" aria-label="Area chart">
        <defs>
          <linearGradient id={`a${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.35" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
          <clipPath id={`c${id}`}>
            <rect x="0" y="0" height={H} width={inView ? W : 0} style={{ transition: 'width 1.6s cubic-bezier(.2,.7,.2,1)' }} />
          </clipPath>
        </defs>
        {[0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} stroke="currentColor" strokeOpacity="0.08" vectorEffect="non-scaling-stroke" />
        ))}
        <g clipPath={`url(#c${id})`}>
          <path d={`${line} L ${W} ${H} L 0 ${H} Z`} fill={`url(#a${id})`} />
          <path d={line} fill="none" stroke={color} strokeWidth="2.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </g>
      </svg>
      {labels && (
        <div className="mt-2 flex justify-between text-[10px] text-fg-subtle">
          {labels.map((l) => (
            <span key={l}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export function BarChart({ values, color, labels, height = 140 }: { values: number[]; color: string; labels?: string[]; height?: number }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  const max = Math.max(...values);
  return (
    <div ref={ref}>
      <div className="flex items-end gap-2" style={{ height }}>
        {values.map((v, i) => (
          <div key={i} className="group relative flex h-full flex-1 items-end">
            <div
              className="w-full rounded-t-md"
              style={{
                height: inView ? `${(v / max) * 100}%` : '0%',
                background: i === values.length - 1 ? color : `color-mix(in srgb, ${color} 45%, transparent)`,
                transition: `height 1s cubic-bezier(.2,.7,.2,1) ${i * 70}ms`,
              }}
            />
            <span className="pointer-events-none absolute -top-6 left-1/2 -translate-x-1/2 rounded bg-fg px-1.5 py-0.5 text-[10px] font-semibold text-bg opacity-0 transition group-hover:opacity-100">
              {v}
            </span>
          </div>
        ))}
      </div>
      {labels && (
        <div className="mt-2 flex gap-2 text-[10px] text-fg-subtle">
          {labels.map((l) => (
            <span key={l} className="flex-1 text-center">
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function Donut({ segments, size = 150, label, sub }: { segments: { value: number; color: string; name: string }[]; size?: number; label?: string; sub?: string }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = 15.915; // circumference = 100
  return (
    <div ref={ref} className="flex flex-wrap items-center gap-6">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 36 36" className="size-full -rotate-0" role="img" aria-label="Donut chart">
          <circle cx="18" cy="18" r={r} fill="none" stroke="currentColor" strokeOpacity="0.08" strokeWidth="4" />
          {segments.map((s, i) => {
            const pct = (s.value / total) * 100;
            const offset = 25 - segments.slice(0, i).reduce((sum, prev) => sum + (prev.value / total) * 100, 0);
            return (
              <circle
                key={s.name}
                cx="18"
                cy="18"
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth="4"
                strokeDasharray={`${inView ? Math.max(pct - 1, 0) : 0} ${100}`}
                strokeDashoffset={offset}
                style={{ transition: `stroke-dasharray 1.2s cubic-bezier(.2,.7,.2,1) ${i * 120}ms` }}
              />
            );
          })}
        </svg>
        {label && (
          <div className="absolute inset-0 grid place-items-center text-center">
            <div>
              <p className="font-display text-2xl font-bold">{label}</p>
              {sub && <p className="text-[10px] text-fg-subtle">{sub}</p>}
            </div>
          </div>
        )}
      </div>
      <ul className="space-y-1.5 text-xs">
        {segments.map((s) => (
          <li key={s.name} className="flex items-center gap-2">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
            <span className="text-fg-muted">{s.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A streaming line chart that appends a new point every tick — "live telemetry" feel. */
export function LiveChart({ color, base = 60, spread = 18, points = 28, interval = 1100, height = 120, unit = '' }: { color: string; base?: number; spread?: number; points?: number; interval?: number; height?: number; unit?: string }) {
  const id = useId().replace(/:/g, '');
  const [data, setData] = useState<number[]>(() => Array.from({ length: points }, (_, i) => base + Math.sin(i / 2.5) * spread * 0.6));
  const [ref, inView] = useInView<HTMLDivElement>(0.1);

  useEffect(() => {
    if (!inView || prefersReducedMotion()) return;
    const t = setInterval(() => {
      setData((d) => {
        const last = d[d.length - 1];
        const next = Math.max(base - spread, Math.min(base + spread, last + (Math.random() - 0.5) * spread * 0.7));
        return [...d.slice(1), next];
      });
    }, interval);
    return () => clearInterval(t);
  }, [inView, base, spread, interval]);

  const max = base + spread * 1.3;
  const min = base - spread * 1.3;
  const line = toPath(data, max, min);
  const last = data[data.length - 1];
  const lastY = H - ((last - min) / (max - min)) * (H - 8) - 4;

  return (
    <div ref={ref} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ height }} className="w-full overflow-visible" role="img" aria-label="Live chart">
        <defs>
          <linearGradient id={`l${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.3" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={`${line} L ${W} ${H} L 0 ${H} Z`} fill={`url(#l${id})`} style={{ transition: 'd 1s linear' }} />
        <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" style={{ transition: 'd 1s linear' }} />
      </svg>
      <span
        className="pulse-dot absolute right-0 size-2.5 -translate-y-1/2 translate-x-1/2 rounded-full"
        style={{ top: `${(lastY / H) * 100}%`, background: color, color, transition: 'top 1s linear' }}
      />
      <span className="absolute right-3 top-0 rounded-md bg-elevated/80 px-2 py-0.5 text-xs font-semibold tabular-nums backdrop-blur" style={{ color }}>
        {last.toFixed(0)}
        {unit}
      </span>
    </div>
  );
}

export function Sparkline({ values, color, className = 'h-8 w-24' }: { values: number[]; color: string; className?: string }) {
  const [ref, inView] = useInView<SVGSVGElement>();
  const max = Math.max(...values);
  const min = Math.min(...values);
  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={className} aria-hidden>
      <path
        d={toPath(values, max, min)}
        fill="none"
        stroke={color}
        strokeWidth="3"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        strokeDasharray="1"
        strokeDashoffset={inView ? 0 : 1}
        style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)' }}
      />
    </svg>
  );
}

export function ProgressRing({ value, color, size = 64, label }: { value: number; color: string; size?: number; label?: string }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  return (
    <div ref={ref} className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 36 36" className="size-full -rotate-90" aria-hidden>
        <circle cx="18" cy="18" r="15.915" fill="none" stroke="currentColor" strokeOpacity="0.1" strokeWidth="3" />
        <circle
          cx="18"
          cy="18"
          r="15.915"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${inView ? value : 0} 100`}
          style={{ transition: 'stroke-dasharray 1.4s cubic-bezier(.2,.7,.2,1)' }}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-xs font-bold">{label ?? `${value}%`}</span>
    </div>
  );
}
