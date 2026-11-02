'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/primitives';
import { prefersReducedMotion } from '@/components/motion/useInView';
import { SpiderWeb } from '@/components/motion/MtkSpider';

const sources = ['E-commerce stores', 'Marketplaces', 'Business directories', 'Real-estate portals', 'PDFs & documents'];
const outputs = ['Your CRM', 'Google Sheets', 'Live dashboard', 'Database / API', 'Alerts & email'];
const colors = ['#62d84e', '#2dd4bf', '#60a5fa', '#fbbf24', '#f472b6'];
const ys = [50, 115, 180, 245, 310];

const logLines = [
  '» MTK Spider crawling 42 pages · competitor-a.com',
  '✓ 1,284 product prices refreshed · competitor-a.com',
  '✓ 312 new B2B leads extracted · business directory',
  '⟳ Layout change detected → selector auto-healed',
  '✓ 96 listings de-duplicated & geocoded',
  '✓ Price drop alert sent to #sales (−12%)',
  '✓ 2,040 rows synced to Google Sheets',
  '✓ 58 leads pushed to CRM pipeline',
  '⟳ Respecting robots.txt · throttled to 1 req/s',
  '» Search: "dental clinics Lahore" → 186 businesses found',
  '» Following pagination · page 7 of 12',
];

// Portrait layout for phones: two rows of sources above the web, two rows of outputs below.
const mobileSources = [
  { x: 62, y: 28, label: 'Stores' },
  { x: 180, y: 28, label: 'Marketplaces' },
  { x: 298, y: 28, label: 'Directories' },
  { x: 110, y: 78, label: 'Real estate' },
  { x: 250, y: 78, label: 'PDFs & docs' },
];
const mobileOutputs = [
  { x: 110, y: 522, label: 'Your CRM' },
  { x: 250, y: 522, label: 'Google Sheets' },
  { x: 62, y: 572, label: 'Dashboard' },
  { x: 180, y: 572, label: 'DB / API' },
  { x: 298, y: 572, label: 'Alerts' },
];
// Curves into the top of the web (180,198) and out of its bottom (180,326).
const mobileInPath = (x: number, y: number) => `M${x},${y + 16} C${x},${y + 90} 180,130 180,198`;
const mobileOutPath = (x: number, y: number) => `M180,400 C180,450 ${x},${y - 70} ${x},${y - 16}`;

// Bezier from a source/output row to the engine at (450,180).
const inPath = (y: number) => `M200,${y} C320,${y} 330,180 400,180`;
const outPath = (y: number) => `M500,180 C570,180 580,${y} 700,${y}`;

/** Animated data pipeline: sources → MTK Spider (crawling its web) → destinations, with a live job log. */
export default function ScrapingShowcase() {
  const [log, setLog] = useState(logLines.slice(0, 4));
  const [records, setRecords] = useState(48210);
  const [still, setStill] = useState(false);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setStill(true);
      return;
    }
    let k = 4;
    const t = setInterval(() => {
      setLog((l) => [logLines[k++ % logLines.length], ...l].slice(0, 4));
      setRecords((r) => r + Math.floor(40 + Math.random() * 160));
    }, 1800);
    return () => clearInterval(t);
  }, []);

  return (
    <section id="scraping" className="night relative isolate scroll-mt-20 overflow-hidden py-24">
      <div className="aurora-1 glow -z-10 left-[-10%] top-[20%] size-[480px] bg-[#14a89a] opacity-25" />
      <div className="container-x">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr] lg:items-center">
          <div>
            <p className="eyebrow !text-lime">Web scraping & data extraction</p>
            <h2 className="mt-4 text-3xl font-bold leading-[1.1] sm:text-5xl">
              The web is your database. <span className="text-lime-grad">We make it usable.</span>
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-white/70">
              Prices, leads, listings, reviews and documents — collected on schedule, cleaned, de-duplicated and delivered straight into your CRM, sheets or
              dashboards. For any business, in any industry.
            </p>
            <ul className="mt-6 space-y-2 text-sm text-white/80">
              {['Self-healing scrapers that survive layout changes', 'Scheduled runs with alerts and change detection', 'Proxy rotation, rate-limiting and CAPTCHA-aware flows', 'Clean exports: CSV, Excel, JSON, API, webhook'].map((t) => (
                <li key={t} className="flex gap-2">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-lime" /> {t}
                </li>
              ))}
            </ul>
            <p className="mt-6 flex items-start gap-2 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/60">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-lime" />
              Ethical by design: we collect publicly available data only, respect robots.txt and site terms, and follow data-protection law.
            </p>
            <Button href="/services/web-scraping" size="lg" arrow className="mt-8">
              Start a data project
            </Button>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur sm:p-6">
            {/* Desktop: animated SVG pipeline */}
            <svg viewBox="0 0 900 360" className="hidden w-full md:block" role="img" aria-label="MTK Spider crawling the web: data flows from websites through its web into business tools">
              {ys.map((y, i) => (
                <g key={`in${i}`}>
                  <path id={`in-${i}`} d={inPath(y)} fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="2" />
                  <path d={inPath(y)} fill="none" stroke={colors[i]} strokeOpacity="0.6" strokeWidth="1.5" className="flow-line" />
                  {!still &&
                    [0, 1].map((n) => (
                      <circle key={n} r="4.5" fill={colors[i]}>
                        <animateMotion dur={`${2.2 + i * 0.25}s`} begin={`${n * 1.1 + i * 0.3}s`} repeatCount="indefinite">
                          <mpath href={`#in-${i}`} />
                        </animateMotion>
                      </circle>
                    ))}
                  <rect x="20" y={y - 20} width="180" height="40" rx="20" fill="#06293a" stroke={colors[i]} strokeOpacity="0.5" />
                  <circle cx="42" cy={y} r="5" fill={colors[i]} />
                  <text x="56" y={y + 5} fill="#e6f2ef" fontSize="14" fontWeight="600">
                    {sources[i]}
                  </text>
                </g>
              ))}
              {ys.map((y, i) => (
                <g key={`out${i}`}>
                  <path id={`out-${i}`} d={outPath(y)} fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="2" />
                  <path d={outPath(y)} fill="none" stroke="#62d84e" strokeOpacity="0.55" strokeWidth="1.5" className="flow-line" />
                  {!still && (
                    <rect x="6" y="-6" width="12" height="12" rx="3" fill="#62d84e">
                      <animateMotion dur={`${2 + i * 0.2}s`} begin={`${0.6 + i * 0.35}s`} repeatCount="indefinite">
                        <mpath href={`#out-${i}`} />
                      </animateMotion>
                    </rect>
                  )}
                  <rect x="700" y={y - 20} width="180" height="40" rx="12" fill="#0b3a2a" stroke="#62d84e" strokeOpacity="0.5" />
                  <text x="790" y={y + 5} fill="#e6f2ef" fontSize="14" fontWeight="600" textAnchor="middle">
                    {outputs[i]}
                  </text>
                </g>
              ))}
              {/* MTK Spider: crawls its web, searching each junction */}
              <SpiderWeb cx={450} cy={180} r={72} still={still} />
            </svg>

            {/* Mobile: the same animated pipeline, stacked vertically */}
            <svg viewBox="0 0 360 600" className="w-full md:hidden" role="img" aria-label="MTK Spider crawling the web: data flows from websites through its web into business tools">
              {mobileSources.map((src, i) => (
                <g key={`min${i}`}>
                  <path id={`m-in-${i}`} d={mobileInPath(src.x, src.y)} fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="2" />
                  <path d={mobileInPath(src.x, src.y)} fill="none" stroke={colors[i]} strokeOpacity="0.6" strokeWidth="1.5" className="flow-line" />
                  {!still &&
                    [0, 1].map((n) => (
                      <circle key={n} r="4" fill={colors[i]}>
                        <animateMotion dur={`${2 + i * 0.25}s`} begin={`${n * 1 + i * 0.3}s`} repeatCount="indefinite">
                          <mpath href={`#m-in-${i}`} />
                        </animateMotion>
                      </circle>
                    ))}
                  <rect x={src.x - 54} y={src.y - 16} width="108" height="32" rx="16" fill="#06293a" stroke={colors[i]} strokeOpacity="0.6" />
                  <text x={src.x} y={src.y + 4.5} fill="#e6f2ef" fontSize="12.5" fontWeight="600" textAnchor="middle">
                    {src.label}
                  </text>
                </g>
              ))}

              <SpiderWeb cx={180} cy={262} r={64} still={still} label={false} />
              <text x="180" y="366" textAnchor="middle" fill="#ffffff" fontSize="16" fontWeight="800">
                MTK Spider
              </text>
              <text x="180" y="384" textAnchor="middle" fill="#62d84e" fontSize="10" fontWeight="700" letterSpacing="2">
                CRAWL · CLEAN · DEDUPE · ENRICH
              </text>

              {mobileOutputs.map((out, i) => (
                <g key={`mout${i}`}>
                  <path id={`m-out-${i}`} d={mobileOutPath(out.x, out.y)} fill="none" stroke="#ffffff" strokeOpacity="0.12" strokeWidth="2" />
                  <path d={mobileOutPath(out.x, out.y)} fill="none" stroke="#62d84e" strokeOpacity="0.55" strokeWidth="1.5" className="flow-line" />
                  {!still && (
                    <rect x="-5" y="-5" width="10" height="10" rx="2.5" fill="#62d84e">
                      <animateMotion dur={`${1.8 + i * 0.2}s`} begin={`${0.5 + i * 0.35}s`} repeatCount="indefinite">
                        <mpath href={`#m-out-${i}`} />
                      </animateMotion>
                    </rect>
                  )}
                  <rect x={out.x - 54} y={out.y - 16} width="108" height="32" rx="10" fill="#0b3a2a" stroke="#62d84e" strokeOpacity="0.6" />
                  <text x={out.x} y={out.y + 4.5} fill="#e6f2ef" fontSize="12.5" fontWeight="600" textAnchor="middle">
                    {out.label}
                  </text>
                </g>
              ))}
            </svg>

            {/* live job log */}
            <div className="mt-4 grid gap-3 sm:grid-cols-[auto_1fr]">
              <div className="rounded-2xl bg-black/30 px-4 py-3">
                <p className="text-[11px] uppercase tracking-wider text-white/50">Records today</p>
                <p className="font-display text-2xl font-bold tabular-nums text-lime">{records.toLocaleString('en-US')}</p>
                <p className="text-[10px] text-white/40">sample job</p>
              </div>
              <ul className="space-y-1 overflow-hidden rounded-2xl bg-black/30 p-3 font-mono text-[11px] text-white/75" aria-live="off">
                {log.map((l, i) => (
                  <li key={`${l}-${i}`} className={`truncate ${i === 0 ? 'word-in text-white' : 'opacity-60'}`}>
                    {l}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
