import type { Place } from '@/lib/lead-types';

/**
 * Visitor location from the hosting edge, free on every provider we support:
 *   - Netlify:    `x-nf-geo` (base64 JSON)
 *   - Vercel:     `x-vercel-ip-*`
 *   - Cloudflare: `cf-ipcity`, `cf-region-code`, … ("Add visitor location headers"
 *                 managed transform; only `cf-ipcountry` is on by default)
 * City level only; coordinates are rounded to one decimal (~10 km) before storage.
 * Local development has no headers, so everything comes back empty.
 */
export type Geo = Place & { lat: number | null; lng: number | null };

const EMPTY: Geo = { city: '', region: '', country: '', timezone: '', lat: null, lng: null };

function header(req: Request, name: string): string {
  const value = req.headers.get(name) || '';
  try {
    // Vercel URL-encodes city names ("S%C3%A3o%20Paulo").
    return decodeURIComponent(value).trim();
  } catch {
    return value.trim();
  }
}

function coordinate(value: unknown, limit: number): number | null {
  const parsed = Number(value);
  if (value === '' || value === null || value === undefined || !Number.isFinite(parsed) || Math.abs(parsed) > limit) return null;
  return Math.round(parsed * 10) / 10;
}

/** Guards against junk before the value reaches Intl or the database. */
export function isTimeZone(value: string): boolean {
  if (!value || value.length > 64 || !/^[A-Za-z_]+(?:\/[A-Za-z0-9_+-]+){0,2}$/.test(value)) return false;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value });
    return true;
  } catch {
    return false;
  }
}

function clean(raw: { city?: unknown; region?: unknown; country?: unknown; timezone?: unknown; lat?: unknown; lng?: unknown }): Geo {
  const timezone = String(raw.timezone || '').trim();
  const country = String(raw.country || '').toUpperCase();
  return {
    city: String(raw.city || '').trim().slice(0, 80),
    // ISO 3166-2 codes arrive as "US-CA" on some edges; keep the subdivision part.
    region: String(raw.region || '').toUpperCase().replace(/^[A-Z]{2}-/, '').slice(0, 8),
    // Cloudflare uses XX (unknown) and T1 (Tor).
    country: /^[A-Z]{2}$/.test(country) && country !== 'XX' && country !== 'T1' ? country : '',
    timezone: isTimeZone(timezone) ? timezone : '',
    lat: coordinate(raw.lat, 90),
    lng: coordinate(raw.lng, 180),
  };
}

function fromNetlify(req: Request): Geo | null {
  const encoded = req.headers.get('x-nf-geo');
  if (!encoded) return null;
  try {
    const data = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8')) as {
      city?: string;
      country?: { code?: string };
      subdivision?: { code?: string };
      timezone?: string;
      latitude?: number;
      longitude?: number;
    };
    return clean({
      city: data.city,
      region: data.subdivision?.code,
      country: data.country?.code,
      timezone: data.timezone,
      lat: data.latitude,
      lng: data.longitude,
    });
  } catch {
    return null;
  }
}

function fromVercel(req: Request): Geo | null {
  if (!req.headers.get('x-vercel-ip-country')) return null;
  return clean({
    city: header(req, 'x-vercel-ip-city'),
    region: header(req, 'x-vercel-ip-country-region'),
    country: header(req, 'x-vercel-ip-country'),
    timezone: header(req, 'x-vercel-ip-timezone'),
    lat: header(req, 'x-vercel-ip-latitude'),
    lng: header(req, 'x-vercel-ip-longitude'),
  });
}

function fromCloudflare(req: Request): Geo | null {
  if (!req.headers.get('cf-ipcountry')) return null;
  return clean({
    city: header(req, 'cf-ipcity'),
    region: header(req, 'cf-region-code'),
    country: header(req, 'cf-ipcountry'),
    timezone: header(req, 'cf-timezone'),
    lat: header(req, 'cf-iplatitude'),
    lng: header(req, 'cf-iplongitude'),
  });
}

export function geoFromRequest(req: Request): Geo {
  return fromNetlify(req) || fromVercel(req) || fromCloudflare(req) || { ...EMPTY };
}
