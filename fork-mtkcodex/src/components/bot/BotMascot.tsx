'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * MTK Bot: a cartoon robot drawn in SVG. Floats, blinks, glows its antenna,
 * waves on hover and follows the cursor with its eyes.
 */
export default function BotMascot({ size = 64, waving = false, follow = true }: { size?: number; waving?: boolean; follow?: boolean }) {
  const ref = useRef<SVGSVGElement>(null);
  const [look, setLook] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (!follow) return;
    const onMove = (e: PointerEvent) => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const dx = e.clientX - (r.left + r.width / 2);
      const dy = e.clientY - (r.top + r.height / 2);
      const d = Math.hypot(dx, dy) || 1;
      const m = Math.min(1, d / 300) * 2.6; // max pupil travel in viewBox units
      setLook({ x: (dx / d) * m, y: (dy / d) * m });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => window.removeEventListener('pointermove', onMove);
  }, [follow]);

  return (
    <svg ref={ref} viewBox="0 0 100 100" width={size} height={size} className="bot-float overflow-visible" aria-hidden>
      <defs>
        <linearGradient id="bot-head" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#d6f5e4" />
        </linearGradient>
        <linearGradient id="bot-face" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0b4f6c" />
          <stop offset="1" stopColor="#032d42" />
        </linearGradient>
        <linearGradient id="bot-body" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#62d84e" />
          <stop offset="1" stopColor="#14a89a" />
        </linearGradient>
        <radialGradient id="bot-bulb">
          <stop offset="0" stopColor="#eaffd9" />
          <stop offset="1" stopColor="#62d84e" />
        </radialGradient>
      </defs>

      {/* ground shadow */}
      <ellipse className="bot-shadow" cx="50" cy="97" rx="20" ry="3" fill="#000" opacity="0.18" />

      {/* antenna */}
      <line x1="50" y1="14" x2="50" y2="24" stroke="#94a3b8" strokeWidth="2.5" strokeLinecap="round" />
      <circle className="bot-bulb" cx="50" cy="11" r="5" fill="url(#bot-bulb)" />

      {/* arms */}
      <g className={waving ? 'bot-wave' : ''} style={{ transformOrigin: '78px 66px' }}>
        <path d="M78 66 Q90 58 90 46" stroke="url(#bot-body)" strokeWidth="6" strokeLinecap="round" fill="none" />
        <circle cx="90" cy="44" r="4.5" fill="#ffffff" stroke="#14a89a" strokeWidth="1.5" />
      </g>
      <path d="M22 66 Q12 72 13 82" stroke="url(#bot-body)" strokeWidth="6" strokeLinecap="round" fill="none" />
      <circle cx="13" cy="84" r="4.5" fill="#ffffff" stroke="#14a89a" strokeWidth="1.5" />

      {/* body */}
      <rect x="27" y="60" width="46" height="32" rx="14" fill="url(#bot-body)" />
      <rect x="40" y="70" width="20" height="11" rx="4" fill="#032d42" opacity="0.85" />
      <text x="50" y="78.5" textAnchor="middle" fontSize="7" fontWeight="800" fill="#62d84e">
        {'</>'}
      </text>

      {/* head */}
      <rect x="18" y="22" width="64" height="44" rx="20" fill="url(#bot-head)" stroke="#bfe9d1" strokeWidth="1.5" />
      <rect x="15" y="36" width="6" height="14" rx="3" fill="#14a89a" />
      <rect x="79" y="36" width="6" height="14" rx="3" fill="#14a89a" />
      <rect x="25" y="29" width="50" height="30" rx="14" fill="url(#bot-face)" />

      {/* eyes */}
      <g className="bot-blink">
        <ellipse cx={39 + look.x} cy={43 + look.y} rx="5" ry="6" fill="#62d84e" />
        <ellipse cx={61 + look.x} cy={43 + look.y} rx="5" ry="6" fill="#62d84e" />
        <circle cx={40.5 + look.x} cy={41 + look.y} r="1.8" fill="#ffffff" />
        <circle cx={62.5 + look.x} cy={41 + look.y} r="1.8" fill="#ffffff" />
      </g>
      {/* smile + cheeks */}
      <path d="M44 52 Q50 56.5 56 52" stroke="#62d84e" strokeWidth="2" fill="none" strokeLinecap="round" />
      <ellipse cx="31" cy="51" rx="3.2" ry="2" fill="#f472b6" opacity="0.55" />
      <ellipse cx="69" cy="51" rx="3.2" ry="2" fill="#f472b6" opacity="0.55" />
      {/* head shine */}
      <path d="M26 27 Q34 24 42 25" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" fill="none" opacity="0.9" />
    </svg>
  );
}
