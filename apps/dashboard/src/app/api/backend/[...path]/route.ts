import { NextResponse } from "next/server";

import { SESSION_COOKIE, sessionSecret, verifySessionCookie } from "@/lib/session";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);

/**
 * Same-origin API proxy for interactive dashboard islands.
 *
 * The reviewer token lives only in the signed HttpOnly session cookie. Browser
 * JavaScript calls /api/backend/... and this handler attaches the token
 * server-side, so an XSS bug cannot read the credential from localStorage.
 * Authorization is still enforced by the API on every request.
 */
async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  if (!ALLOWED_METHODS.has(request.method.toUpperCase())) {
    return NextResponse.json({ detail: "method not allowed" }, { status: 405 });
  }

  const secret = sessionSecret();
  if (!secret) {
    return NextResponse.json(
      { detail: "dashboard auth is not configured (MTK_SESSION_SECRET)" },
      { status: 503 },
    );
  }

  const session = await verifySessionCookie(
    readCookie(request, SESSION_COOKIE),
    secret,
  );
  if (!session) {
    return NextResponse.json(
      { detail: "dashboard session expired — sign in again" },
      { status: 401 },
    );
  }

  const { path } = await context.params;
  const target = new URL(request.url);
  const upstream = `${API_URL.replace(/\/+$/, "")}/${path.map(encodeURIComponent).join("/")}${target.search}`;

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${session.token}`);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  for (const name of ["accept", "range", "if-range"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const method = request.method.toUpperCase();
  const init: RequestInit = { method, headers, cache: "no-store" };
  if (method !== "GET" && method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let response: Response;
  try {
    response = await fetch(upstream, init);
  } catch {
    return NextResponse.json({ detail: "API is unreachable" }, { status: 502 });
  }

  const outHeaders = new Headers();
  // Media playback needs the byte-range contract end to end: without these
  // headers the browser receives a 206 it cannot interpret and seeking fails.
  for (const name of [
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "etag",
    "last-modified",
    "content-disposition",
  ]) {
    const value = response.headers.get(name);
    if (value) outHeaders.set(name, value);
  }
  outHeaders.set("Cache-Control", "no-store");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outHeaders,
  });
}

function readCookie(request: Request, name: string): string | undefined {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key === name) return decodeURIComponent(value.join("="));
  }
  return undefined;
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
