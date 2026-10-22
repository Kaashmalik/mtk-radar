"use client";

/**
 * Interactive API helper (v0.31). Browser JavaScript never holds a token:
 * calls go to the same-origin /api/backend proxy, which reads the HttpOnly
 * session cookie and attaches the reviewer credential server-side.
 *
 * The API still authorizes every request; this helper is only transport.
 */
export async function clientFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const target = path.startsWith("/") ? path : `/${path}`;
  return fetch(`/api/backend${target}`, {
    ...init,
    headers: new Headers(init.headers),
    credentials: "same-origin",
  });
}
