"use client";

/** Client-side API helper for interactive islands — attaches the bearer token
 * when NEXT_PUBLIC_API_TOKEN is set (inlined at build time, non-secret by
 * definition; the API enforces the actual gate). */

export const CLIENT_API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function clientFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = process.env.NEXT_PUBLIC_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${CLIENT_API}${path}`, { ...init, headers });
}
