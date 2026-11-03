import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { zones } from "@/lib/config";

type JobType = "pickup" | "delivery" | "measurement" | "alteration_return";

/** Next date a zone is served (zone C runs on fixed weekdays). */
export function nextServiceDate(zoneCode: string | null, from = new Date()) {
  const zone = zones.find((z) => z.code === zoneCode);
  const fixed = zone?.code === "C" ? [2, 5] : null; // Tue, Fri
  const d = new Date(from.getTime() + 5 * 3600 * 1000); // PKT
  d.setUTCDate(d.getUTCDate() + 1);
  while (fixed && !fixed.includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** Creates a rider job unless an open one of the same type already exists for the order. */
export async function ensureRiderJob(
  db: SupabaseClient,
  job: { orderId: string; type: JobType; date: string; slot?: string | null; cashToCollect?: number; riderId?: string | null; notes?: string | null },
) {
  const { data: open } = await db
    .from("rider_jobs")
    .select("id")
    .eq("order_id", job.orderId)
    .eq("type", job.type)
    .in("status", ["assigned", "en_route", "arrived", "rescheduled"])
    .maybeSingle();
  if (open) return open.id as string;

  const { data, error } = await db
    .from("rider_jobs")
    .insert({
      order_id: job.orderId,
      type: job.type,
      scheduled_date: job.date,
      slot: job.slot ?? null,
      cash_to_collect: job.cashToCollect ?? 0,
      rider_id: job.riderId ?? null,
      notes: job.notes ?? null,
    })
    .select("id")
    .single();
  if (error) throw error;
  return data.id as string;
}
