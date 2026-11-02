'use client';

import { useEffect, useMemo, useState } from 'react';
import { MapPin, Monitor, Smartphone, Tablet } from 'lucide-react';
import { feature } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';
import type { Feature, MultiPolygon, Polygon, Position } from 'geojson';
import type { LiveVisitor, MapPoint } from '@/lib/analytics-types';
import { flagEmoji, localTime, placeLabel, timeAgo } from '@/lib/lead-types';

/**
 * Live visitors on a world map. Equirectangular projection, drawn as plain
 * SVG paths from Natural Earth (world-atlas, 110m), loaded only on admin pages.
 */

const W = 960;
const H = 440;
const LAT_TOP = 84;
const LAT_BOTTOM = -58; // crop Antarctica

const project = (lng: number, lat: number): [number, number] => [
  ((lng + 180) / 360) * W,
  ((LAT_TOP - lat) / (LAT_TOP - LAT_BOTTOM)) * H,
];

function ringPath(ring: Position[]): string {
  let d = '';
  let previous: number | null = null;
  for (const [lng, lat] of ring) {
    const [x, y] = project(lng, lat);
    // Break the line where a ring wraps around the antimeridian.
    const jump = previous !== null && Math.abs(lng - previous) > 180;
    d += `${d && !jump ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
    previous = lng;
  }
  return `${d}Z`;
}

function featurePath(geometry: Polygon | MultiPolygon): string {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  return polygons.map((rings) => rings.map(ringPath).join('')).join('');
}

let worldCache: string[] | null = null;

function useWorld() {
  const [paths, setPaths] = useState<string[] | null>(worldCache);
  useEffect(() => {
    if (worldCache) return;
    let cancelled = false;
    import('world-atlas/countries-110m.json').then((mod) => {
      const topology = (mod.default || mod) as unknown as Topology<{ countries: GeometryCollection }>;
      const collection = feature(topology, topology.objects.countries) as unknown as { features: Feature<Polygon | MultiPolygon>[] };
      worldCache = collection.features.filter((f) => f.geometry).map((f) => featurePath(f.geometry));
      if (!cancelled) setPaths(worldCache);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return paths;
}

const DeviceIcon = ({ device }: { device: string }) =>
  device === 'mobile' ? <Smartphone className="size-3" /> : device === 'tablet' ? <Tablet className="size-3" /> : <Monitor className="size-3" />;

export default function LiveMap({
  live,
  points,
  compact = false,
}: {
  live: LiveVisitor[];
  points: MapPoint[];
  compact?: boolean;
}) {
  const world = useWorld();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const maxVisitors = useMemo(() => Math.max(1, ...points.map((p) => p.visitors)), [points]);
  const located = live.filter((v) => v.lat !== null && v.lng !== null);

  return (
    <div className={`grid gap-4 ${compact ? '' : 'lg:grid-cols-[1.6fr_1fr]'}`}>
      <div className="relative overflow-hidden rounded-xl border border-line bg-muted/40">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`World map with ${live.length} live visitors`}>
          <g className="fill-line/70 stroke-elevated" strokeWidth={0.5}>
            {world?.map((d, i) => <path key={i} d={d} />)}
          </g>
          {points.map((p) => {
            const [x, y] = project(p.lng, p.lat);
            return (
              <circle key={`${p.lat},${p.lng}`} cx={x} cy={y} r={2 + (p.visitors / maxVisitors) * 6} className="fill-sky-500/35 stroke-sky-500/60" strokeWidth={0.6}>
                <title>{`${p.city || 'Unknown city'}, ${p.country}: ${p.visitors} visitor${p.visitors > 1 ? 's' : ''} in 24h`}</title>
              </circle>
            );
          })}
          {located.map((v) => {
            const [x, y] = project(Number(v.lng), Number(v.lat));
            return (
              <g key={v.id}>
                <circle cx={x} cy={y} r={10} className="animate-ping fill-emerald-500/40" style={{ transformOrigin: `${x}px ${y}px` }} />
                <circle cx={x} cy={y} r={4.5} className="fill-emerald-500 stroke-elevated" strokeWidth={1.5}>
                  <title>{`${placeLabel(v) || v.country} · ${v.path}`}</title>
                </circle>
              </g>
            );
          })}
        </svg>
        {!world && <p className="absolute inset-0 grid place-items-center text-xs text-fg-subtle">Loading map…</p>}
        <div className="absolute bottom-2 left-2 flex items-center gap-3 rounded-full bg-elevated/90 px-3 py-1 text-[10px] text-fg-muted shadow-sm">
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-full bg-emerald-500" /> Live now ({live.length})
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-full bg-sky-500/60" /> Last 24h
          </span>
        </div>
      </div>

      {!compact && (
        <div className="min-w-0">
          <h3 className="flex items-center gap-1.5 text-sm font-bold">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
            On the site now
          </h3>
          {live.length === 0 ? (
            <p className="mt-3 text-sm text-fg-muted">Nobody in the last 5 minutes.</p>
          ) : (
            <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto pr-1">
              {live.map((v) => (
                <li key={v.id} className="rounded-lg border border-line bg-elevated px-3 py-2 text-xs">
                  <p className="flex items-center gap-1.5 font-semibold">
                    <span aria-hidden>{flagEmoji(v.country)}</span>
                    <span className="truncate">{placeLabel(v) || 'Unknown location'}</span>
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-fg-subtle">
                    <span className="inline-flex items-center gap-1 font-mono">
                      <MapPin className="size-3" /> {v.path}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <DeviceIcon device={v.device} /> {v.device}
                    </span>
                    {localTime(v.timezone, new Date(now)) && <span>their time {localTime(v.timezone, new Date(now))}</span>}
                    <span>{timeAgo(v.last_seen, now)}</span>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
