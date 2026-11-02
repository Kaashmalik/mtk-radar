/**
 * MTK Spider: an octagonal web with a spider that crawls its threads,
 * "searching" each junction it reaches (a pulse fires on arrival).
 * Pure SVG + SMIL, rendered inside a parent <svg>. Pass `still` to freeze it
 * for visitors who prefer reduced motion.
 */

type Point = [number, number];

const SPOKES = 8;
const RINGS = [0.36, 0.68, 1];
/** Crawl route as [ring index, spoke index] junctions; it loops back to the start. */
const ROUTE: [number, number][] = [
  [1, 0], [1, 1], [0, 1], [0, 2], [0, 3], [2, 3], [2, 4], [2, 5], [1, 5], [1, 6], [2, 6], [2, 7], [1, 7], [0, 7], [0, 0], [1, 0],
];
const SECONDS_PER_UNIT = 0.022; // crawl speed: seconds per SVG unit of thread

function junction(cx: number, cy: number, r: number, ring: number, spoke: number): Point {
  const angle = (spoke / SPOKES) * Math.PI * 2 - Math.PI / 2;
  return [cx + Math.cos(angle) * r * RINGS[ring], cy + Math.sin(angle) * r * RINGS[ring]];
}

const fmt = (n: number) => Number(n.toFixed(2));

/** A spider drawn facing +x, centred on the origin. Legs paddle in two alternating sets. */
function SpiderBody({ color, scale, still }: { color: string; scale: number; still: boolean }) {
  // Attach point, knee, foot for one side; mirrored for the other.
  const legs: [Point, Point, Point][] = [
    [[2, 2], [6, 7], [11, 9]],
    [[0, 2.5], [1, 9], [4, 13]],
    [[-2, 2.5], [-5, 9], [-4, 14]],
    [[-4, 2], [-10, 7], [-13, 11]],
  ];
  return (
    <g transform={`scale(${scale})`}>
      {[1, -1].map((side) =>
        legs.map(([a, k, f], i) => {
          const d = `M${a[0]},${a[1] * side} L${k[0]},${k[1] * side} L${f[0]},${f[1] * side}`;
          const swing = (i + (side === 1 ? 0 : 1)) % 2 === 0 ? 12 : -12;
          return (
            <path key={`${side}-${i}`} d={d} fill="none" stroke={color} strokeWidth={1.3} strokeLinecap="round" strokeLinejoin="round">
              {!still && (
                <animateTransform
                  attributeName="transform"
                  type="rotate"
                  values={`0 ${a[0]} ${a[1] * side}; ${swing} ${a[0]} ${a[1] * side}; 0 ${a[0]} ${a[1] * side}`}
                  dur="0.36s"
                  repeatCount="indefinite"
                />
              )}
            </path>
          );
        }),
      )}
      <ellipse cx={-7} cy={0} rx={7} ry={5.4} fill={color} />
      <ellipse cx={-8} cy={0} rx={3.2} ry={2.2} fill="#032d42" opacity={0.35} />
      <circle cx={2.5} cy={0} r={3.6} fill={color} />
      <circle cx={4.6} cy={-1.3} r={0.9} fill="#032d42" />
      <circle cx={4.6} cy={1.3} r={0.9} fill="#032d42" />
    </g>
  );
}

export function SpiderWeb({
  cx,
  cy,
  r,
  color = '#62d84e',
  accent = '#2dd4bf',
  still = false,
  label = true,
}: {
  cx: number;
  cy: number;
  r: number;
  color?: string;
  accent?: string;
  still?: boolean;
  label?: boolean;
}) {
  const spokes = Array.from({ length: SPOKES }, (_, s) => junction(cx, cy, r, RINGS.length - 1, s));
  const rings = RINGS.map((_, ring) =>
    Array.from({ length: SPOKES }, (_, s) => junction(cx, cy, r, ring, s))
      .map(([x, y]) => `${fmt(x)},${fmt(y)}`)
      .join(' '),
  );

  const points = ROUTE.map(([ring, spoke]) => junction(cx, cy, r, ring, spoke));
  const lengths = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  const dur = total * SECONDS_PER_UNIT;
  const route = `M${points.map(([x, y]) => `${fmt(x)},${fmt(y)}`).join(' L')}`;
  // Fraction of the loop at which the spider reaches each junction (skip the closing duplicate).
  const arrivals = points.slice(0, -1).map((_, i) => lengths.slice(0, i).reduce((a, b) => a + b, 0) / total);
  const scale = r / 70;

  return (
    <g>
      {/* web */}
      <g stroke={color} strokeOpacity={0.35} strokeWidth={1} fill="none">
        {spokes.map(([x, y], i) => (
          <line key={i} x1={cx} y1={cy} x2={fmt(x)} y2={fmt(y)} />
        ))}
        {rings.map((pts, i) => (
          <polygon key={i} points={pts} strokeOpacity={0.22 + i * 0.1} />
        ))}
      </g>
      <circle cx={cx} cy={cy} r={r + 14} fill="none" stroke={color} strokeOpacity={0.18} strokeDasharray="3 9">
        {!still && <animateTransform attributeName="transform" type="rotate" from={`0 ${cx} ${cy}`} to={`360 ${cx} ${cy}`} dur="40s" repeatCount="indefinite" />}
      </circle>

      {/* the route it is walking right now */}
      <path id={`spider-route-${cx}-${cy}`} d={route} fill="none" stroke={accent} strokeOpacity={0.5} strokeWidth={1.2} className={still ? undefined : 'flow-line'} />

      {/* "search" pulses as the spider reaches each junction */}
      {points.slice(0, -1).map(([x, y], i) => {
        const at = Math.min(Math.max(arrivals[i], 0.005), 0.88);
        return (
          <circle key={i} cx={fmt(x)} cy={fmt(y)} r={2.5} fill={accent} opacity={still ? 0.5 : 0}>
            {!still && (
              <>
                <animate attributeName="opacity" values="0;0;0.95;0;0" keyTimes={`0;${fmt(at)};${fmt(at + 0.02)};${fmt(at + 0.1)};1`} dur={`${fmt(dur)}s`} repeatCount="indefinite" />
                <animate attributeName="r" values="2.5;2.5;9;2.5;2.5" keyTimes={`0;${fmt(at)};${fmt(at + 0.02)};${fmt(at + 0.1)};1`} dur={`${fmt(dur)}s`} repeatCount="indefinite" />
              </>
            )}
          </circle>
        );
      })}

      <circle cx={cx} cy={cy} r={4} fill={color} />

      {/* the spider */}
      {still ? (
        <g transform={`translate(${fmt(points[0][0])} ${fmt(points[0][1])})`}>
          <SpiderBody color="#ffffff" scale={scale} still />
        </g>
      ) : (
        <g>
          <animateMotion dur={`${fmt(dur)}s`} repeatCount="indefinite" rotate="auto">
            <mpath href={`#spider-route-${cx}-${cy}`} />
          </animateMotion>
          <SpiderBody color="#ffffff" scale={scale} still={false} />
        </g>
      )}

      {label && (
        <>
          <text x={cx} y={cy + r + 34} textAnchor="middle" fill="#ffffff" fontSize={16} fontWeight={800}>
            MTK Spider
          </text>
          <text x={cx} y={cy + r + 52} textAnchor="middle" fill={color} fontSize={11} fontWeight={700} letterSpacing={2}>
            CRAWL · CLEAN · DEDUPE · ENRICH
          </text>
        </>
      )}
    </g>
  );
}
