"use client";

/** A client-side API helper for interactive islands. v0.16: attaches the
 * reviewer's PERSONAL token (minted with services/api/scripts/mint_reviewer,
 * stored via lib/identity) so the API can bind every action to a reviewer.
 * The shared worker token is never sent from the browser. Dev mode (API auth
 * disabled) works without a token. */

import { getReviewerToken } from "@/lib/identity";

export const CLIENT_API =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function clientFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getReviewerToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${CLIENT_API}${path}`, { ...init, headers });
}
