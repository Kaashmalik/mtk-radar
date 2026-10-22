import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, sessionSecret, verifySessionCookie } from "@/lib/session";

/**
 * Dashboard access gate.
 *
 * Every page and every /api/backend request requires a valid signed session.
 * Unauthenticated browsers are redirected to /login with a same-origin `next`
 * path. The login form and the session endpoints are the only public routes.
 *
 * If MTK_SESSION_SECRET is missing or too short, this fails closed: no request
 * can be authenticated and the login page explains the misconfiguration.
 */
export default async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === "/login" || pathname.startsWith("/api/session")) {
    return NextResponse.next();
  }

  const secret = sessionSecret();
  if (!secret) {
    return redirectToLogin(request, "not_configured");
  }

  const rawCookie = request.cookies.get(SESSION_COOKIE)?.value;
  const session = await verifySessionCookie(rawCookie, secret);
  if (!session) {
    // Fetching islands expect JSON, not a redirected HTML login page.
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { detail: "dashboard session expired — reload and sign in again" },
        { status: 401 },
      );
    }
    const response = redirectToLogin(request, rawCookie ? "expired" : "signin");
    response.cookies.delete(SESSION_COOKIE);
    return response;
  }

  return NextResponse.next();
}

function redirectToLogin(request: NextRequest, reason: string): NextResponse {
  const url = request.nextUrl.clone();
  const target = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  url.pathname = "/login";
  url.search = "";
  if (target !== "/") url.searchParams.set("next", target);
  url.searchParams.set("reason", reason);
  return NextResponse.redirect(url);
}

export const config = {
  // Public: the login page, session endpoints, Next internals, and static
  // assets. Everything else (pages and /api/backend) is authenticated.
  matcher: [
    "/((?!api/session|login|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
