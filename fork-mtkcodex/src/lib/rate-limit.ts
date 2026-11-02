import { createHash } from 'node:crypto';
import { rpc, supabase, supabaseConfigured } from '@/lib/supabase';

/**
 * Fixed-window rate limiting.
 *
 * With Supabase connected the counter lives in Postgres (`rate_limit_hit`), so
 * every serverless instance shares it. Without a database, or if the call
 * fails, it falls back to a per-instance in-memory window.
 */

const memory = new Map<string, { count: number; resetAt: number }>();

function memoryHit(key: string, windowMs: number, max: number): boolean {
  const now = Date.now();
  const entry = memory.get(key);
  if (!entry || entry.resetAt < now) {
    memory.set(key, { count: 1, resetAt: now + windowMs });
    if (memory.size > 5_000) {
      for (const [k, v] of memory) if (v.resetAt < now) memory.delete(k);
    }
    return false;
  }
  entry.count += 1;
  return entry.count > max;
}

/** Keys are hashed so raw IPs never reach the database. */
function hashKey(key: string): string {
  return createHash('sha256').update(key).digest('hex').slice(0, 40);
}

/** Records one hit for `key` and returns true when it is over `max` in the window. */
export async function rateLimited(key: string, windowMs: number, max: number): Promise<boolean> {
  const hashed = hashKey(key);
  if (supabaseConfigured()) {
    try {
      return await rpc<boolean>('rate_limit_hit', {
        p_key: hashed,
        p_window_seconds: Math.ceil(windowMs / 1000),
        p_max: max,
      });
    } catch (error) {
      console.error('rate-limit: database unavailable, using memory', error instanceof Error ? error.message : error);
    }
  }
  return memoryHit(hashed, windowMs, max);
}

export async function clearRateLimit(key: string): Promise<void> {
  const hashed = hashKey(key);
  memory.delete(hashed);
  if (!supabaseConfigured()) return;
  try {
    await supabase(`rate_limits?key=eq.${hashed}`, { method: 'DELETE' });
  } catch {
    // The window expires on its own.
  }
}

/**
 * Best client IP. Provider headers come first because the edge sets them itself
 * (Netlify, Cloudflare); x-forwarded-for is the fallback (Vercel, plain proxies).
 */
export function clientIp(req: Request): string {
  return (
    req.headers.get('x-nf-client-connection-ip') ||
    req.headers.get('cf-connecting-ip') ||
    req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    req.headers.get('x-real-ip') ||
    'unknown'
  );
}
