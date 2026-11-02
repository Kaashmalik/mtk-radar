/** Shared line-icon set: one 24px grid, round caps/joins, drawn in
 * currentColor so every icon follows the theme and its surrounding text.
 *
 * Icons are decorative by default (aria-hidden) because they sit next to a
 * text label; pass `label` only when the icon is the sole content that
 * carries meaning. Controls that show nothing but an icon should name
 * themselves with aria-label on the button instead.
 *
 * Motion lives in globals.css (the "icons" block). Moving parts carry an
 * `m-*` class that names their micro-animation; it plays when the nearest
 * link, enabled button, pill or tag is hovered or focused, and all of it is
 * gated on prefers-reduced-motion: no-preference. Server-safe (no hooks), so
 * server pages can use it directly. */

import type { CSSProperties, ReactNode } from "react";

/** Stagger index for multi-part animations (read as var(--i) in CSS). */
const at = (i: number) => ({ "--i": i }) as CSSProperties;

type IconDef = {
  body: ReactNode;
  /** Whole-icon motion class, applied to the <svg> itself. */
  motion?: string;
};

const ICONS = {
  // ---- navigation ----
  home: {
    body: (
      <>
        <path className="m-lift" d="M3 11l9-7 9 7" />
        <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
      </>
    ),
  },
  inbox: {
    body: (
      <>
        <path d="M5 5h14l2 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z" />
        <path className="m-dip" d="M3 13h5l1.5 3h5L16 13h5" />
      </>
    ),
  },
  radar: {
    body: (
      <>
        <path d="M12 3a9 9 0 1 0 9 9" />
        <path d="M12 7a5 5 0 1 0 5 5" />
        <path className="m-sweep" d="M12 12l6-6" />
        <circle className="m-blip" cx="18.5" cy="9" r="0.6" />
      </>
    ),
  },
  "check-circle": {
    body: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path className="m-draw" pathLength={1} d="M8.5 12.2l2.4 2.4 4.6-4.8" />
      </>
    ),
  },
  list: {
    body: (
      <>
        <path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
        <path className="m-grow-x" style={at(0)} d="M8 6h13" />
        <path className="m-grow-x" style={at(1)} d="M8 12h13" />
        <path className="m-grow-x" style={at(2)} d="M8 18h13" />
      </>
    ),
  },
  alert: {
    body: (
      <>
        <path d="M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
        <path d="M12 9v4M12 17h.01" />
      </>
    ),
    motion: "m-shake",
  },
  film: {
    body: (
      <>
        <path d="M4 11h16v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" />
        <path className="m-clap" d="M4 7h16v4H4zM8.5 7l2 4M14 7l2 4" />
      </>
    ),
  },
  calendar: {
    body: (
      <>
        <rect x="4" y="5" width="16" height="15" rx="2" />
        <path d="M4 10h16" />
        <path className="m-hop" d="M8 3v4M16 3v4" />
        <path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" />
      </>
    ),
  },
  chart: {
    body: (
      <>
        <path d="M3 20h18" />
        <path className="m-grow-y" style={at(0)} d="M6 20v-9" />
        <path className="m-grow-y" style={at(1)} d="M12 20V5" />
        <path className="m-grow-y" style={at(2)} d="M18 20v-6" />
      </>
    ),
  },
  database: {
    body: (
      <>
        <ellipse className="m-lift" cx="12" cy="6" rx="8" ry="3" />
        <path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
        <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
      </>
    ),
  },
  plug: {
    body: (
      <>
        <path className="m-lift" d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0z" />
        <path d="M12 17v5" />
      </>
    ),
  },
  gear: {
    body: (
      <g className="m-turn">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
      </g>
    ),
  },

  // ---- actions & status ----
  check: { body: <path className="m-draw" pathLength={1} d="M5 12.5l4.5 4.5L19 7.5" /> },
  x: { body: <path d="M6 6l12 12M18 6L6 18" />, motion: "m-turn-self" },
  exclaim: { body: <path d="M12 6v7M12 18h.01" />, motion: "m-shake" },
  play: {
    body: <path d="M7 4.9v14.2a1 1 0 0 0 1.5.86l11.6-7.1a1 1 0 0 0 0-1.72L8.5 4.04A1 1 0 0 0 7 4.9z" />,
    motion: "m-nudge-r",
  },
  pause: {
    body: (
      <>
        <path className="m-squish" style={at(0)} d="M8 5v14" />
        <path className="m-squish" style={at(1)} d="M16 5v14" />
      </>
    ),
  },
  refresh: {
    body: (
      <g className="m-spin-once">
        <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 3v5h5" />
        <path d="M4 13a8 8 0 0 0 14.3 4.9L20 16M20 21v-5h-5" />
      </g>
    ),
  },
  spinner: {
    body: (
      <>
        <circle cx="12" cy="12" r="9" opacity="0.25" />
        <path d="M21 12a9 9 0 0 0-9-9" />
      </>
    ),
    motion: "m-spinning",
  },
  zap: { body: <path d="M13 2L4.5 14H11l-1 8 8.5-12H12z" />, motion: "m-flicker" },
  pin: {
    body: (
      <g className="m-press">
        <path d="M9 3h6l-1 6.5 3 3V14H7v-1.5l3-3z" />
        <path d="M12 14v7" />
      </g>
    ),
  },
  flame: {
    body: (
      <g className="m-flame">
        <path d="M12 21a6 6 0 0 0 6-6c0-4-3-6-4.5-9.5C12.4 7.4 11 9 10 10.5 9.3 9.6 9 8.6 9 7.5 7.2 9.4 6 11.9 6 15a6 6 0 0 0 6 6z" />
        <path d="M12 21a2.5 2.5 0 0 1-2.5-2.5c0-1.5 1.2-2.4 2.5-4 1.3 1.6 2.5 2.5 2.5 4A2.5 2.5 0 0 1 12 21z" />
      </g>
    ),
  },
  layers: {
    body: (
      <>
        <path className="m-lift" d="M12 3l9 5-9 5-9-5z" />
        <path d="M3 12.5l9 5 9-5" />
        <path className="m-sink" d="M3 16.5l9 5 9-5" />
      </>
    ),
  },
  flask: {
    body: (
      <>
        <path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7 15h10" />
        <circle className="m-bubble" style={at(0)} cx="10.5" cy="18" r="0.5" />
        <circle className="m-bubble" style={at(1)} cx="13.5" cy="18" r="0.5" />
      </>
    ),
  },
  hourglass: {
    body: (
      <path d="M6 3h12M6 21h12M7 3v2a5 5 0 0 0 10 0V3M7 21v-2a5 5 0 0 1 10 0v2" />
    ),
    motion: "m-flip",
  },
  "calendar-plus": {
    body: (
      <>
        <rect x="4" y="5" width="16" height="15" rx="2" />
        <path d="M4 10h16" />
        <path className="m-hop" d="M8 3v4M16 3v4" />
        <path className="m-turn" style={{ transformOrigin: "12px 15px" }} d="M12 12.5v5M9.5 15h5" />
      </>
    ),
  },
  timer: {
    body: (
      <>
        <circle cx="12" cy="13" r="8" />
        <path d="M10 2h4M12 2v3M19 6l1.5-1.5" />
        <path className="m-spin-once" style={{ transformOrigin: "12px 13px" }} d="M12 13V9" />
      </>
    ),
  },
  "trend-up": { body: <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />, motion: "m-nudge-ur" },
  "trend-down": { body: <path d="M3 7l6 6 4-4 8 8M15 17h6v-6" />, motion: "m-nudge-dr" },
  external: {
    body: (
      <>
        <path className="m-nudge-ur" d="M14 4h6v6M20 4l-9 9" />
        <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
      </>
    ),
  },
  "arrow-up": { body: <path d="M12 19V5M5.5 11.5L12 5l6.5 6.5" />, motion: "m-nudge-u" },
  "arrow-down": { body: <path d="M12 5v14M5.5 12.5L12 19l6.5-6.5" />, motion: "m-nudge-d" },
  "arrow-left": { body: <path d="M19 12H5M11.5 5.5L5 12l6.5 6.5" />, motion: "m-nudge-l" },
  "arrow-right": { body: <path d="M5 12h14M12.5 5.5L19 12l-6.5 6.5" />, motion: "m-nudge-r" },
  logout: {
    body: (
      <>
        <path d="M9 21H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h4" />
        <path className="m-nudge-r" d="M16 17l5-5-5-5M21 12H9" />
      </>
    ),
  },
  menu: {
    body: (
      <>
        <path className="m-bar-1" d="M4 7h16" />
        <path className="m-bar-2" d="M4 12h16" />
        <path className="m-bar-3" d="M4 17h16" />
      </>
    ),
  },

  // ---- theme ----
  sun: {
    body: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path
          className="m-rays"
          d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
        />
      </>
    ),
  },
  moon: {
    body: (
      <>
        <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />
        <path className="m-twinkle" d="M17.5 3v3M16 4.5h3" />
      </>
    ),
  },
  monitor: {
    body: (
      <>
        <rect x="3" y="4" width="18" height="12" rx="2" />
        <path d="M8 20h8M12 16v4" />
        <path className="m-scan" d="M6.5 8h5" />
      </>
    ),
  },
} satisfies Record<string, IconDef>;

export type IconName = keyof typeof ICONS;

type IconProps = {
  name: IconName;
  /** Pixel number or any CSS length; defaults to the surrounding font size. */
  size?: number | string;
  strokeWidth?: number;
  /** Accessible name. Omit for decorative icons next to visible text. */
  label?: string;
  /** Ongoing motion: "spin" for busy states, "pulse" to draw the eye. */
  motion?: "spin" | "pulse";
  className?: string;
};

export default function Icon({ name, size = "1em", strokeWidth = 2, label, motion, className }: IconProps) {
  const def: IconDef = ICONS[name];
  const classes = [
    "icon",
    def.motion,
    motion === "spin" && "m-spinning",
    motion === "pulse" && "m-pulse",
    className,
  ].filter(Boolean).join(" ");
  return (
    <svg
      className={classes}
      data-icon={name}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      {def.body}
    </svg>
  );
}

/** Animated MTK RADAR mark for the app shell: rings, a sweeping beam and
 * two pinging blips on the brand gradient tile (the tile is CSS). */
export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" focusable="false">
        <circle cx="12" cy="12" r="8.5" className="bm-ring" />
        <circle cx="12" cy="12" r="5" className="bm-ring" />
        <path className="bm-beam" d="M12 12L12 3.5A8.5 8.5 0 0 1 19.4 7.8Z" />
        <circle cx="12" cy="12" r="1.4" className="bm-core" />
        <circle cx="16.4" cy="8.2" r="1" className="bm-blip" />
        <circle cx="8" cy="15.2" r="0.8" className="bm-blip" style={at(1)} />
      </svg>
    </span>
  );
}
