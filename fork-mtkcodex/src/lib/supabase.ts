/**
 * Minimal PostgREST client for server code. The secret key bypasses RLS, so
 * this module must never be imported from a client component.
 */

const SUPABASE_URL = (process.env.SUPABASE_URL || '').trim().replace(/\/+$/, '');
const SUPABASE_KEY = (process.env.SUPABASE_SERVICE_ROLE_KEY || '').trim();

export function supabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_KEY);
}

export async function supabase<T>(pathAndQuery: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${pathAndQuery}`, {
    ...init,
    headers: {
      // Newer `sb_secret_…` keys are not JWTs, so send them in both headers.
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    cache: 'no-store',
  });
  const text = await res.text().catch(() => '');
  if (!res.ok) throw new Error(`Supabase ${res.status}: ${text.slice(0, 300)}`);
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Calls a SQL function exposed through PostgREST (`/rest/v1/rpc/<name>`). */
export function rpc<T>(name: string, args: Record<string, unknown> = {}): Promise<T> {
  return supabase<T>(`rpc/${name}`, { method: 'POST', body: JSON.stringify(args) });
}

/** Builds a PostgREST `in.(...)` filter value with every item quoted. */
export function inList(values: string[]): string {
  return `in.(${values.map((value) => `"${value.replace(/(["\\])/g, '\\$1')}"`).join(',')})`;
}
