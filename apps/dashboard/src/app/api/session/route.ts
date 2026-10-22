import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  SESSION_COOKIE,
  cookieOptions,
  createSessionCookie,
  requestIsSecure,
  sessionSecret,
  verifySessionCookie,
} from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

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

  const body = await request.json().catch(() => null) as { token?: unknown } | null;
  const token = typeof body?.token === "string" ? body.token.trim() : "";
  if (token.length < 20 || token.length > 512) {
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
