import { NextResponse } from 'next/server';
import {
  analyticsEnabled,
  deviceFromUserAgent,
  isBot,
  recordPageView,
  referrerHost,
  visitorHash,
} from '@/lib/analytics';
import { clientIp } from '@/lib/rate-limit';
import { geoFromRequest } from '@/lib/geo';
import { trackablePath } from '@/lib/site-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/**
 * Public beacon used by the marketing site. Deliberately quiet: it always
 * answers 204 so a tracking failure can never affect a visitor's page.
 */

const WINDOW_MS = 60_000;
const MAX_EVENTS = 90;
const hits = new Map<string, { count: number; resetAt: number }>();

// Kept in memory on purpose: a database round trip per page view is not worth it here.
function rateLimited(key: string): boolean {
  const now = Date.now();
  const entry = hits.get(key);
  if (!entry || now > entry.resetAt) {
    hits.set(key, { count: 1, resetAt: now + WINDOW_MS });
    if (hits.size > 5_000) {
      for (const [k, v] of hits) if (now > v.resetAt) hits.delete(k);
    }
    return false;
  }
  entry.count += 1;
  return entry.count > MAX_EVENTS;
}

export async function POST(req: Request) {
  if (!analyticsEnabled()) return new NextResponse(null, { status: 204 });

  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return new NextResponse(null, { status: 204 });
  }

  const path = trackablePath(body.path);
  const kind = body.kind === 'ping' ? 'ping' : 'view';
  if (!path) return new NextResponse(null, { status: 204 });

  const userAgent = req.headers.get('user-agent') || '';
  if (isBot(userAgent)) return new NextResponse(null, { status: 204 });

  const ip = clientIp(req);

  if (rateLimited(ip)) return new NextResponse(null, { status: 204 });

  try {
    await recordPageView({
      path,
      referrerHost: kind === 'view' ? referrerHost(typeof body.referrer === 'string' ? body.referrer : '') : '',
      ...geoFromRequest(req),
      device: deviceFromUserAgent(userAgent),
      kind,
      visitorId: visitorHash(ip, userAgent),
    });
  } catch (error) {
    // Never surface tracking failures to the visitor; log for the server only.
    console.error('analytics: failed to record page view', error instanceof Error ? error.message : error);
  }

  return new NextResponse(null, { status: 204 });
}
