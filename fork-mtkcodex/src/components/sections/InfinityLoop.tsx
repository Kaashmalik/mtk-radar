'use client';

import { useEffect, useState } from 'react';
import { Code2, Compass, PenTool, Rocket, TrendingUp, Workflow } from 'lucide-react';
import { prefersReducedMotion } from '@/components/motion/useInView';

// Stage positions are in SVG viewBox units (800 × 340) so labels stay pinned to the curve.
const stages = [
  { name: 'Discover', icon: Compass, x: 230, y: 78, side: 'build' },
  { name: 'Design', icon: PenTool, x: 92, y: 170, side: 'build' },
  { name: 'Build', icon: Code2, x: 230, y: 262, side: 'build' },
  { name: 'Launch', icon: Rocket, x: 570, y: 78, side: 'run' },
  { name: 'Automate', icon: Workflow, x: 708, y: 170, side: 'run' },
  { name: 'Scale', icon: TrendingUp, x: 570, y: 262, side: 'run' },
] as const;

const PATH =
  'M400,170 C470,70 690,60 700,170 C690,280 470,270 400,170 C330,70 110,60 100,170 C110,280 330,270 400,170 Z';

// The viewBox grows above and below the loop for the lead streams.
const VB_TOP = -120;
const VB_HEIGHT = 580;

/** Where leads come from: they stream down into the MTK centre. */
const leadSources = [
  { label: 'MTK Spider', x: 150, color: '#62d84e' },
  { label: 'Website', x: 275, color: '#2dd4bf' },
  { label: 'Live chat', x: 400, color: '#fbbf24' },
  { label: 'WhatsApp', x: 525, color: '#25d366' },
  { label: 'Email', x: 650, color: '#60a5fa' },
];
/** What leaves the loop: results delivered back to the business. */
const results = [
  { label: 'Won deals', x: 150 },
  { label: 'Follow-ups', x: 275 },
  { label: 'Dashboards', x: 400 },
  { label: 'Automations', x: 525 },
  { label: 'Reports', x: 650 },
];
const IN_Y = -88;
const OUT_Y = 428;
const inPath = (x: number) => `M${x},${IN_Y + 16} C${x},${IN_Y + 120} 400,40 400,140`;
const outPath = (x: number) => `M400,200 C400,300 ${x},${OUT_Y - 120} ${x},${OUT_Y - 16}`;

/** Animated ∞ loop: continuous Build ↔ Run lifecycle with packets travelling the curve. */
export default function InfinityLoop({ compact = false }: { compact?: boolean }) {
  const [active, setActive] = useState(0);
  const [still, setStill] = useState(false);
  // Order the highlight follows as packets travel: right loop then left loop.
  const order = [3, 4, 5, 0, 1, 2];

  useEffect(() => {
    if (prefersReducedMotion()) {
      setStill(true);
      return;
    }
    const t = setInterval(() => setActive((a) => (a + 1) % order.length), 1400);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = order[active];

  return (
    <section className={`night relative isolate overflow-hidden ${compact ? 'py-16' : 'py-24'}`}>
      <div className="absolute inset-0 -z-10 opacity-40 [background-image:radial-gradient(rgba(98,216,78,0.18)_1px,transparent_1px)] [background-size:28px_28px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
      <div className="container-x">
        <div className="mx-auto max-w-3xl text-center">
          <p className="eyebrow !text-lime">The MTK Codex loop</p>
          <h2 className="mt-4 text-3xl font-bold leading-[1.1] sm:text-5xl">
            Build, run, improve — <span className="text-lime-grad">forever.</span>
          </h2>
          <p className="mt-5 text-lg text-white/70">
            Software is never finished. Our continuous delivery loop connects engineering with operations, so every release feeds automation, data and the
            next improvement.
          </p>
        </div>

        {/* Phones: the in-SVG labels are too small, so name the streams here */}
        <div className="mt-10 sm:hidden">
          <p className="text-center text-[10px] font-bold tracking-[0.2em] text-lime">LEADS IN</p>
          <div className="mt-2 flex flex-wrap justify-center gap-1.5">
            {leadSources.map((src) => (
              <span key={src.label} className="rounded-full border px-2.5 py-1 text-[11px] font-semibold text-white/85" style={{ borderColor: `${src.color}99` }}>
                {src.label}
              </span>
            ))}
          </div>
        </div>

        <div className="relative mx-auto mt-4 max-w-4xl sm:mt-12">
          <svg viewBox={`0 ${VB_TOP} 800 ${VB_HEIGHT}`} className="w-full overflow-visible" role="img" aria-label="Infinity loop of the delivery lifecycle, with leads flowing in to MTK and results flowing out">
            <defs>
              <linearGradient id="inf-grad" x1="0" x2="1">
                <stop offset="0" stopColor="#2dd4bf" />
                <stop offset="0.5" stopColor="#62d84e" />
                <stop offset="1" stopColor="#60a5fa" />
              </linearGradient>
              <filter id="inf-glow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="6" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <path id="inf-path" d={PATH} />
            </defs>

            {/* leads in: every channel streams into the MTK centre */}
            {leadSources.map((src, i) => (
              <g key={src.label}>
                <path id={`lead-in-${i}`} d={inPath(src.x)} fill="none" stroke={src.color} strokeOpacity="0.22" strokeWidth="2" />
                <path d={inPath(src.x)} fill="none" stroke={src.color} strokeOpacity="0.55" strokeWidth="1.5" className="flow-line" />
                {!still &&
                  [0, 1].map((n) => (
                    <circle key={n} r="5" fill={src.color} filter="url(#inf-glow)">
                      <animateMotion dur={`${2.6 + i * 0.3}s`} begin={`${n * 1.3 + i * 0.4}s`} repeatCount="indefinite">
                        <mpath href={`#lead-in-${i}`} />
                      </animateMotion>
                    </circle>
                  ))}
                <rect x={src.x - 58} y={IN_Y - 18} width="116" height="36" rx="18" fill="#06293a" stroke={src.color} strokeOpacity="0.7" className="hidden sm:block" />
                <text x={src.x} y={IN_Y + 5} textAnchor="middle" fill="#e6f2ef" fontSize="15" fontWeight="700" className="hidden sm:block">
                  {src.label}
                </text>
              </g>
            ))}
            <text x="400" y={IN_Y - 30} textAnchor="middle" fill="#62d84e" fontSize="12" fontWeight="700" letterSpacing="3" className="hidden sm:block">
              LEADS IN
            </text>

            {/* results out: the loop delivers back to the business */}
            {results.map((out, i) => (
              <g key={out.label}>
                <path id={`result-out-${i}`} d={outPath(out.x)} fill="none" stroke="#62d84e" strokeOpacity="0.22" strokeWidth="2" />
                <path d={outPath(out.x)} fill="none" stroke="#62d84e" strokeOpacity="0.5" strokeWidth="1.5" className="flow-line" />
                {!still && (
                  <rect x="-5.5" y="-5.5" width="11" height="11" rx="3" fill="#62d84e" filter="url(#inf-glow)">
                    <animateMotion dur={`${2.4 + i * 0.25}s`} begin={`${0.8 + i * 0.45}s`} repeatCount="indefinite">
                      <mpath href={`#result-out-${i}`} />
                    </animateMotion>
                  </rect>
                )}
                <rect x={out.x - 58} y={OUT_Y - 18} width="116" height="36" rx="10" fill="#0b3a2a" stroke="#62d84e" strokeOpacity="0.6" className="hidden sm:block" />
                <text x={out.x} y={OUT_Y + 5} textAnchor="middle" fill="#e6f2ef" fontSize="15" fontWeight="700" className="hidden sm:block">
                  {out.label}
                </text>
              </g>
            ))}
            <text x="400" y={OUT_Y + 44} textAnchor="middle" fill="#62d84e" fontSize="12" fontWeight="700" letterSpacing="3" className="hidden sm:block">
              RESULTS OUT
            </text>

            <use href="#inf-path" fill="none" stroke="url(#inf-grad)" strokeOpacity="0.18" strokeWidth="34" strokeLinecap="round" />
            <use href="#inf-path" fill="none" stroke="url(#inf-grad)" strokeWidth="3" />
            <use href="#inf-path" className="flow-line" fill="none" stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.5" />

            {/* travelling packets */}
            {!still && [0, 1.6, 3.2, 4.8, 6.4].map((delay, i) => (
              <circle key={i} r={i % 2 ? 5 : 7} fill={i % 2 ? '#60a5fa' : '#62d84e'} filter="url(#inf-glow)">
                <animateMotion dur="8s" repeatCount="indefinite" begin={`-${delay}s`} rotate="auto">
                  <mpath href="#inf-path" />
                </animateMotion>
              </circle>
            ))}

            {/* centre knot */}
            <circle cx="400" cy="170" r="30" fill="#032d42" stroke="#62d84e" strokeOpacity="0.6" strokeWidth="2" />
            <circle cx="400" cy="170" r="30" fill="none" stroke="#62d84e" strokeWidth="2" className="flow-line" />
            <text x="400" y="176" textAnchor="middle" fill="#fff" fontSize="18" fontWeight="800">
              MTK
            </text>
            <text x="250" y="174" textAnchor="middle" fill="#a6bfc6" fontSize="13" fontWeight="600" letterSpacing="3">
              BUILD
            </text>
            <text x="550" y="174" textAnchor="middle" fill="#a6bfc6" fontSize="13" fontWeight="600" letterSpacing="3">
              RUN
            </text>

            {/* stage nodes */}
            {stages.map((s, i) => {
              const on = i === current;
              const color = s.side === 'build' ? '#2dd4bf' : '#62d84e';
              return (
                <g key={s.name} style={{ transition: 'opacity .4s' }} opacity={on ? 1 : 0.75}>
                  <circle cx={s.x} cy={s.y} r={on ? 26 : 20} fill="#06293a" stroke={color} strokeWidth={on ? 3 : 1.5} style={{ transition: 'r .4s' }} />
                  {on && (
                    <circle cx={s.x} cy={s.y} r="26" fill="none" stroke={color} strokeWidth="2">
                      <animate attributeName="r" from="26" to="44" dur="1.4s" repeatCount="indefinite" />
                      <animate attributeName="opacity" from="0.8" to="0" dur="1.4s" repeatCount="indefinite" />
                    </circle>
                  )}
                  <text
                    // Top/bottom stages label above/below; side stages label outward.
                    x={s.y === 170 ? s.x + (s.x < 400 ? -34 : 34) : s.x}
                    y={s.y < 170 ? s.y - 36 : s.y > 170 ? s.y + 50 : s.y + 5}
                    textAnchor={s.y === 170 ? (s.x < 400 ? 'end' : 'start') : 'middle'}
                    fill={on ? '#fff' : '#a6bfc6'}
                    fontSize="15"
                    fontWeight="700"
                    className="hidden sm:block"
                  >
                    {s.name}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Icons overlaid on the nodes (percent of the viewBox) */}
          {stages.map((s, i) => (
            <span
              key={s.name}
              className="pointer-events-none absolute grid -translate-x-1/2 -translate-y-1/2 place-items-center"
              style={{ left: `${(s.x / 800) * 100}%`, top: `${((s.y - VB_TOP) / VB_HEIGHT) * 100}%`, color: i === current ? '#fff' : s.side === 'build' ? '#2dd4bf' : '#62d84e' }}
            >
              <s.icon className="size-3.5 sm:size-5" />
            </span>
          ))}
        </div>

        <div className="mt-2 sm:hidden">
          <div className="flex flex-wrap justify-center gap-1.5">
            {results.map((out) => (
              <span key={out.label} className="rounded-lg border border-lime/40 bg-lime/10 px-2.5 py-1 text-[11px] font-semibold text-white/85">
                {out.label}
              </span>
            ))}
          </div>
          <p className="mt-2 text-center text-[10px] font-bold tracking-[0.2em] text-lime">RESULTS OUT</p>
        </div>

        <ol className="mx-auto mt-10 grid max-w-4xl grid-cols-3 gap-2 text-center text-xs sm:grid-cols-6 sm:text-sm">
          {order.map((idx, k) => {
            const s = stages[idx];
            return (
              <li
                key={s.name}
                className={`rounded-full border px-3 py-2 font-semibold transition ${k === active ? 'border-lime bg-lime/15 text-white' : 'border-white/10 text-white/55'}`}
              >
                {s.name}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
