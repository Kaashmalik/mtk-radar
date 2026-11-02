'use client';

import { useEffect, useState } from 'react';
import { site } from '@/data/site';

// Approximate marker positions on the stylised globe (viewBox 300×300, HQ near centre).
const HQ = { x: 182, y: 128 };
const markers = [
  { code: 'AE', x: 150, y: 150 },
  { code: 'SA', x: 128, y: 168 },
  { code: 'EU', x: 112, y: 96 },
  { code: 'GB', x: 92, y: 82 },
  { code: 'US', x: 46, y: 112 },
  { code: 'PK', x: 196, y: 140 },
];

const DAY_INDEX: Record<string, number> = { Sunday: 0, Monday: 1, Tuesday: 2, Wednesday: 3, Thursday: 4, Friday: 5, Saturday: 6 };

/** Live office clock + open/closed status in the office timezone. */
export function useOfficeStatus() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!now) return { time: '--:--', open: null as boolean | null };
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', { timeZone: site.timezone, weekday: 'long', hour: '2-digit', minute: '2-digit', hour12: false })
      .formatToParts(now)
      .map((p) => [p.type, p.value]),
  );
  const minutes = Number(parts.hour) * 60 + Number(parts.minute);
  const [oh, om] = site.openingHours.opens.split(':').map(Number);
  const [ch, cm] = site.openingHours.closes.split(':').map(Number);
  const openDay = site.openingHours.days.some((d) => DAY_INDEX[d] === DAY_INDEX[parts.weekday]);
  const open = openDay && minutes >= oh * 60 + om && minutes < ch * 60 + cm;
  const time = new Intl.DateTimeFormat('en-US', { timeZone: site.timezone, hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(now);
  return { time, open };
}

/** Animated globe: HQ in Lahore with data arcs to the regions we serve. */
export default function GlobalReach() {
  return (
    <svg viewBox="0 0 300 300" className="mx-auto w-full max-w-[320px]" role="img" aria-label={`MTK Codex headquarters in Lahore serving ${site.serviceAreas.map((a) => a.name).join(', ')}`}>
      <defs>
        <radialGradient id="globe-fill" cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#0b5a5f" />
          <stop offset="0.6" stopColor="#063646" />
          <stop offset="1" stopColor="#021a26" />
        </radialGradient>
        <radialGradient id="globe-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0.7" stopColor="#62d84e" stopOpacity="0.25" />
          <stop offset="1" stopColor="#62d84e" stopOpacity="0" />
        </radialGradient>
        <clipPath id="globe-clip">
          <circle cx="150" cy="150" r="120" />
        </clipPath>
      </defs>

      <circle cx="150" cy="150" r="148" fill="url(#globe-glow)" />
      <circle cx="150" cy="150" r="120" fill="url(#globe-fill)" stroke="#62d84e" strokeOpacity="0.35" />

      <g clipPath="url(#globe-clip)" fill="none" stroke="#9be8c6" strokeOpacity="0.16">
        {/* latitudes */}
        {[-80, -40, 0, 40, 80].map((dy) => (
          <ellipse key={dy} cx="150" cy={150 + dy} rx={Math.sqrt(120 ** 2 - dy ** 2)} ry={Math.max(4, 22 - Math.abs(dy) / 5)} />
        ))}
        {/* rotating meridians */}
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <ellipse key={i} cx="150" cy="150" ry="120" rx="0">
            <animate attributeName="rx" values="0;120;0" dur="12s" begin={`${-i * 2}s`} repeatCount="indefinite" />
            <animate attributeName="stroke-opacity" values="0.05;0.3;0.05" dur="12s" begin={`${-i * 2}s`} repeatCount="indefinite" />
          </ellipse>
        ))}
        {/* drifting dotted "land" texture */}
        <g stroke="none" fill="#9be8c6" fillOpacity="0.22">
          {Array.from({ length: 70 }).map((_, k) => {
            const x = 40 + ((k * 37) % 230);
            const y = 50 + ((k * 53) % 200);
            return <circle key={k} cx={x} cy={y} r="1.3" />;
          })}
          <animateTransform attributeName="transform" type="translate" values="0 0;-30 0;0 0" dur="24s" repeatCount="indefinite" />
        </g>
      </g>

      {/* arcs from HQ */}
      {markers.map((m, i) => {
        const mx = (HQ.x + m.x) / 2;
        const my = Math.min(HQ.y, m.y) - 40;
        const d = `M${HQ.x},${HQ.y} Q${mx},${my} ${m.x},${m.y}`;
        return (
          <g key={m.code}>
            <path id={`arc-${m.code}`} d={d} fill="none" stroke="#62d84e" strokeOpacity="0.55" strokeWidth="1.2" className="flow-line" />
            <circle r="2.4" fill="#eaffd9">
              <animateMotion dur={`${2.4 + i * 0.3}s`} repeatCount="indefinite" begin={`${i * 0.4}s`}>
                <mpath href={`#arc-${m.code}`} />
              </animateMotion>
            </circle>
            <circle cx={m.x} cy={m.y} r="3.5" fill="#2dd4bf" />
            <text x={m.x} y={m.y - 7} textAnchor="middle" fontSize="9" fontWeight="700" fill="#cdeee3">
              {m.code}
            </text>
          </g>
        );
      })}

      {/* HQ */}
      <circle cx={HQ.x} cy={HQ.y} r="6" fill="#62d84e">
        <animate attributeName="r" values="6;7.5;6" dur="1.6s" repeatCount="indefinite" />
      </circle>
      <circle cx={HQ.x} cy={HQ.y} r="6" fill="none" stroke="#62d84e" strokeWidth="2">
        <animate attributeName="r" values="6;22" dur="1.6s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.9;0" dur="1.6s" repeatCount="indefinite" />
      </circle>
      <rect x={HQ.x + 10} y={HQ.y - 24} width="58" height="18" rx="9" fill="#62d84e" />
      <text x={HQ.x + 39} y={HQ.y - 12} textAnchor="middle" fontSize="9" fontWeight="800" fill="#032d1a">
        LAHORE HQ
      </text>
    </svg>
  );
}
