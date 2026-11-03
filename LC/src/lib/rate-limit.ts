import "server-only";
import { headers } from "next/headers";
import { createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";

/**
 * Database-backed rate limit for public forms. Returns true when the caller may
 * proceed. Fails open if the limiter itself errors, so customers are never
 * blocked by an infrastructure hiccup.
 */
export async function allow(action: string, max: number, windowSeconds: number, extraKey?: string) {
  if (!isSupabaseConfigured) return true;
  const h = await headers();
  const ip = h.get("x-real-ip") ?? h.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  const bucket = `${action}:${extraKey ?? ip}`;
  const { data, error } = await createServiceClient().rpc("hit_rate_limit", { p_bucket: bucket, p_max: max, p_window_seconds: windowSeconds });
  if (error) {
    console.error("rate limit check failed", error.message);
    return true;
  }
  return data === true;
}

export const TOO_MANY = "Too many attempts. Please wait a few minutes or message us on WhatsApp.";
