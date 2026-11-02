import { createHash, createHmac, timingSafeEqual } from 'node:crypto';
import { cookies } from 'next/headers';
import { clearRateLimit, rateLimited } from '@/lib/rate-limit';

export const ADMIN_COOKIE = 'mtk_admin';
export const ADMIN_SESSION_HOURS = 8;

export type AdminSession = { email: string; exp: number };

export function adminEmail(): string {
  return (process.env.ADMIN_EMAIL || 'kaash0542@gmail.com').trim().toLowerCase();
}

function adminPassword(): string {
  // Env values pasted through dashboards/CLIs often carry a trailing newline.
  return (process.env.ADMIN_PASSWORD || '').trim();
}

function sessionSecret(): string {
  return (process.env.ADMIN_SESSION_SECRET || '').trim();
}

export function adminConfigured(): boolean {
  return Boolean(adminPassword() && sessionSecret());
}

/** Constant-time string compare that does not leak lengths. */
function safeEqual(a: string, b: string): boolean {
  const da = createHash('sha256').update(a).digest();
  const db = createHash('sha256').update(b).digest();
  return timingSafeEqual(da, db);
}

export function checkCredentials(email: string, password: string): boolean {
  if (!adminConfigured()) return false;
  return safeEqual(email.trim().toLowerCase(), adminEmail()) && safeEqual(password, adminPassword());
}

function sign(payload: string): string {
  return createHmac('sha256', sessionSecret()).update(payload).digest('base64url');
}

export function createSessionToken(email: string, now = Date.now()): string {
  const payload = Buffer.from(
    JSON.stringify({ email, exp: now + ADMIN_SESSION_HOURS * 60 * 60 * 1000 } satisfies AdminSession),
  ).toString('base64url');
  return `${payload}.${sign(payload)}`;
}

export function verifySessionToken(token: string | undefined | null): AdminSession | null {
  if (!token || !adminConfigured()) return null;
  const [payload, signature] = token.split('.');
  if (!payload || !signature) return null;
  const expected = sign(payload);
  if (expected.length !== signature.length) return null;
  if (!timingSafeEqual(Buffer.from(expected), Buffer.from(signature))) return null;
  try {
    const session = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')) as AdminSession;
    if (!session.email || typeof session.exp !== 'number' || session.exp < Date.now()) return null;
    return session;
  } catch {
    return null;
  }
}

export async function getAdminSession(): Promise<AdminSession | null> {
  const store = await cookies();
  return verifySessionToken(store.get(ADMIN_COOKIE)?.value);
}

export function sessionCookieOptions() {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: ADMIN_SESSION_HOURS * 60 * 60,
  };
}

const LOGIN_WINDOW_MS = 10 * 60 * 1000;
const LOGIN_MAX_ATTEMPTS = 8;

/** Shared across serverless instances when Supabase is connected (see rate-limit.ts). */
export function loginThrottled(ip: string): Promise<boolean> {
  return rateLimited(`login:${ip}`, LOGIN_WINDOW_MS, LOGIN_MAX_ATTEMPTS);
}

export function clearLoginAttempts(ip: string): Promise<void> {
  return clearRateLimit(`login:${ip}`);
}

/**
 * Guards an admin API route: valid session, and for state-changing requests
 * an Origin that matches the host (defence in depth on top of SameSite=Lax).
 * Returns the session, or a Response to send back as-is.
 */
export async function requireAdmin(req: Request): Promise<AdminSession | Response> {
  if (!['GET', 'HEAD'].includes(req.method)) {
    const origin = req.headers.get('origin');
    const host = req.headers.get('x-forwarded-host') || req.headers.get('host');
    if (origin && host) {
      let originHost = '';
      try {
        originHost = new URL(origin).host;
      } catch {
        // fall through to the mismatch response
      }
      if (originHost !== host) return Response.json({ error: 'Cross-site request blocked' }, { status: 403 });
    }
  }
  const session = await getAdminSession();
  if (!session) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  return session;
}
