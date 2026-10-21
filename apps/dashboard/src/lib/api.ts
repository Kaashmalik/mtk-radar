/** Server-side API helper for RSC pages — attaches the shared bearer token
 * when MTK_API_TOKEN is configured (matches services/api/api_hardening.py). */

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = process.env.MTK_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}
