/** Server-side loader that keeps an outage visible.
 *
 * Pages used to swallow API failures into fallback values, so an unreachable
 * API rendered as "nothing queued" or as a default policy that looked live.
 * `loadJson` still returns the fallback (pages can render) but reports
 * whether the data is real, so the page can say "unavailable" honestly. */

import { apiFetch } from "@/lib/api";

export type Loaded<T> = { data: T; ok: boolean };

export async function loadJson<T>(path: string, fallback: T): Promise<Loaded<T>> {
  try {
    const res = await apiFetch(path, { cache: "no-store" });
    if (!res.ok) return { data: fallback, ok: false };
    return { data: (await res.json()) as T, ok: true };
  } catch {
    return { data: fallback, ok: false };
  }
}

/** Human list of the sections whose live data could not be loaded. */
export function unavailableSections(sections: Record<string, Loaded<unknown>>): string[] {
  return Object.entries(sections)
    .filter(([, loaded]) => !loaded.ok)
    .map(([name]) => name);
}
