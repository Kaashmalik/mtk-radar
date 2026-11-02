import { createHmac } from 'node:crypto';
import type { AnalyticsSummary } from '@/lib/analytics-types';
import { rpc, supabase, supabaseConfigured } from '@/lib/supabase';

/**
 * First-party, cookieless website analytics.
 *
 * We intentionally do not store cookies or anything on the visitor's device.
 * The visitor id is an HMAC of (day, IP, user agent, session secret), so it is
 * pseudonymous, cannot be reversed into an IP and rotates every day in
 * Asia/Karachi. The admin dashboard reads aggregates through a SQL function.
 */

function hashSecret(): string {
  return (process.env.ADMIN_SESSION_SECRET || '').trim();
}

/**
 * Needs the database and a real secret: without the secret the visitor hash
 * would use a guessable key and could be linked back to an IP.
 */
export function analyticsEnabled(): boolean {
  return supabaseConfigured() && Boolean(hashSecret());
}

/** YYYY-MM-DD in the owner's timezone (Asia/Karachi). */
export function localDay(date: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Karachi',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

export function visitorHash(ip: string, userAgent: string, day: string = localDay()): string {
  return createHmac('sha256', hashSecret()).update(`${day}|${ip}|${userAgent}`).digest('hex').slice(0, 24);
}

const BOT_RE =
  /bot|crawler|spider|crawling|slurp|bingpreview|facebookexternalhit|embedly|pinterest|slack|discord|telegram|whatsapp|headlesschrome|lighthouse|pagespeed|pingdom|uptime|monitor|curl|wget|axios|python-requests/i;

export function isBot(userAgent: string): boolean {
  return !userAgent || BOT_RE.test(userAgent);
}

export function deviceFromUserAgent(userAgent: string): 'mobile' | 'tablet' | 'desktop' {
  if (/ipad|tablet|playbook|silk|(android(?!.*mobile))/i.test(userAgent)) return 'tablet';
  if (/mobi|iphone|ipod|android.*mobile|windows phone|blackberry|opera mini/i.test(userAgent)) return 'mobile';
  return 'desktop';
}

/** Hostname only, so we never store full referrer URLs (which can contain query data). */
export function referrerHost(value: string | undefined): string {
  if (!value) return '';
  try {
    return new URL(value).hostname.replace(/^www\./, '').slice(0, 120);
  } catch {
    return '';
  }
}

export type PageViewInput = {
  path: string;
  referrerHost: string;
  country: string;
  city: string;
  region: string;
  timezone: string;
  lat: number | null;
  lng: number | null;
  device: string;
  kind: 'view' | 'ping';
  visitorId: string;
};

export async function recordPageView(view: PageViewInput): Promise<void> {
  if (!analyticsEnabled()) return;
  // PostgREST uses the table's snake_case column names.
  await supabase('page_views', {
    method: 'POST',
    headers: { Prefer: 'return=minimal' },
    body: JSON.stringify({
      path: view.path,
      referrer_host: view.referrerHost,
      country: view.country,
      city: view.city,
      region: view.region,
      timezone: view.timezone,
      lat: view.lat,
      lng: view.lng,
      device: view.device,
      kind: view.kind,
      visitor_id: view.visitorId,
    }),
  });
}

export async function getAnalyticsSummary(): Promise<AnalyticsSummary | null> {
  if (!analyticsEnabled()) return null;
  return rpc<AnalyticsSummary>('analytics_summary');
}
