import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  SESSION_COOKIE,
  clientIp,
  cookieOptions,
  createSessionCookie,
  requestIsSecure,
  sessionSecret,
  verifySessionCookie,
} from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// ---- login brute-force throttle (in-process, no dependencies) -------------
//
// The sign-in exchange is the one unauthenticated POST on the dashboard, so
// failed attempts count per client address in a sliding window; past the
// budget the address gets a 429 + Retry-After. A valid sign-in clears its
// record, an unreachable API (503) does not count as a failed guess, and the
// map is bounded so it can never grow without limit. In-process by design:
// one dashboard container, no shared state store — the API side runs the same
// concept in services/api/api_hardening.py.
const LOGIN_FAILURE_LIMIT = 5;
const LOGIN_FAILURE_WINDOW_MS = 60_000;
const LOGIN_FAILURES_MAX_KEYS = 10_000;
const LOGIN_FAILURES = new Map<string, number[]>();

/** Sliding-window failures for one address, pruned as a side effect. */
function recentFailures(ip: string, now: number): number[] {
  const hits = (LOGIN_FAILURES.get(ip) ?? []).filter((t) => now - t < LOGIN_FAILURE_WINDOW_MS);
  if (hits.length) LOGIN_FAILURES.set(ip, hits);
  else LOGIN_FAILURES.delete(ip);
  return hits;
}

function loginBlocked(ip: string): boolean {
  return recentFailures(ip, Date.now()).length >= LOGIN_FAILURE_LIMIT;
}

/** Seconds until the oldest failure in the window expires (Retry-After). */
function loginRetryAfter(ip: string): number {
  const hits = recentFailures(ip, Date.now());
  const oldest = hits.length ? Math.min(...hits) : Date.now();
  return Math.max(1, Math.ceil((oldest + LOGIN_FAILURE_WINDOW_MS - Date.now()) / 1000));
}

function loginFailure(ip: string): void {
  const now = Date.now();
  const hits = recentFailures(ip, now);
  hits.push(now);
  if (LOGIN_FAILURES.has(ip) || LOGIN_FAILURES.size < LOGIN_FAILURES_MAX_KEYS) {
    LOGIN_FAILURES.set(ip, hits);
  } else if (LOGIN_FAILURES.size) {
    // Map full and address unseen: evict the address with the oldest failure
    // instead of growing forever.
    let oldestKey: string | null = null;
    let oldestTime = Infinity;
    for (const [key, times] of LOGIN_FAILURES) {
      if (times[0] < oldestTime) {
        oldestTime = times[0];
        oldestKey = key;
      }
    }
    if (oldestKey) LOGIN_FAILURES.delete(oldestKey);
    LOGIN_FAILURES.set(ip, hits);
  }
}

/** Current dashboard identity, derived only from the signed HttpOnly cookie. */
export async function GET() {
  const secret = sessionSecret();
  if (!secret) {
    return NextResponse.json(
      { detail: "dashboard auth is not configured (MTK_SESSION_SECRET)" },
      { status: 503 },
    );
  }
  const store = await cookies();
  const session = await verifySessionCookie(store.get(SESSION_COOKIE)?.value, secret);
  if (!session) {
    return NextResponse.json({ detail: "not signed in" }, { status: 401 });
  }
  return NextResponse.json({
    actor: session.actor,
    expires_at: new Date(session.exp).toISOString(),
  });
}

/**
 * Exchange a personal reviewer token for an HttpOnly session cookie.
 *
 * The token is validated against the real /whoami endpoint before any cookie is
 * issued, so service/worker tokens and revoked reviewer tokens never become a
 * dashboard session. The token itself is never returned to browser JavaScript.
 */
export async function POST(request: Request) {
  const secret = sessionSecret();
  if (!secret) {
    return NextResponse.json(
      {
        detail:
          "dashboard auth is not configured; set MTK_SESSION_SECRET to a random value of at least 32 characters",
      },
      { status: 503 },
    );
  }

  const ip = clientIp(request);
  if (loginBlocked(ip)) {
    return NextResponse.json(
      { detail: "too many failed sign-ins from this address — wait a minute and try again" },
      { status: 429, headers: { "Retry-After": String(loginRetryAfter(ip)) } },
    );
  }

  const body = await request.json().catch(() => null) as { token?: unknown } | null;
  const token = typeof body?.token === "string" ? body.token.trim() : "";
  if (token.length < 20 || token.length > 512) {
    loginFailure(ip);
    return NextResponse.json({ detail: "a personal reviewer token is required" }, { status: 400 });
  }

  let whoami: Response;
  try {
    whoami = await fetch(`${API_URL}/whoami`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    return NextResponse.json(
      { detail: "API is unreachable; try again once it is online" },
      { status: 503 },
    );
  }

  if (!whoami.ok) {
    loginFailure(ip);
    return NextResponse.json(
      { detail: "token invalid or revoked — mint a fresh reviewer token" },
      { status: 401 },
    );
  }

  const identity = await whoami.json().catch(() => null) as
    | { actor?: unknown; auth?: unknown }
    | null;
  if (identity?.auth !== "reviewer" || typeof identity.actor !== "string"
      || identity.actor.trim().length < 2) {
    loginFailure(ip);
    return NextResponse.json(
      {
        detail:
          "that is not a personal reviewer token; service, worker and extension credentials cannot sign in to the dashboard",
      },
      { status: 403 },
    );
  }

  const actor = identity.actor.trim();
  const cookie = await createSessionCookie(actor, token, secret);
  const response = NextResponse.json({ actor });
  response.cookies.set(SESSION_COOKIE, cookie, cookieOptions(requestIsSecure(request)));
  // A valid sign-in clears the address's failure record.
  LOGIN_FAILURES.delete(ip);
  return response;
}

/** Sign out. The reviewer token remains valid until revoked server-side. */
export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
