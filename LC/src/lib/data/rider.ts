import "server-only";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/server";
import * as demo from "./demo";

export type RiderAppJob = {
  id: string;
  type: string;
  scheduled_date: string;
  slot: string | null;
  status: string;
  cash_to_collect: number;
  cash_collected: number;
  notes: string | null;
  order: {
    id: string;
    order_no: string;
    status: string;
    zone_code: string | null;
    customer: { full_name: string; phone: string; area: string | null; address: string | null; landmark: string | null } | null;
  } | null;
};

/** Jobs for one rider: everything open up to `date`, plus what they finished that day. */
export async function getJobsForRider(riderId: string, date: string): Promise<RiderAppJob[]> {
  if (!isSupabaseConfigured) {
    return demo.riderJobs
      .filter((j) => j.rider_id === "r1")
      .map((j, i) => ({
        id: j.id,
        type: j.type,
        scheduled_date: j.scheduled_date,
        slot: j.slot,
        status: j.status,
        cash_to_collect: j.cash_to_collect,
        cash_collected: 0,
        notes: j.notes,
        order: {
          id: `o${i}`,
          order_no: j.order!.order_no,
          status: "confirmed",
          zone_code: j.order!.zone_code,
          customer: { ...j.order!.customer!, phone: "+923001112233", landmark: "Near the park" },
        },
      }));
  }

  const db = await createClient();
  const select =
    "id, type, scheduled_date, slot, status, cash_to_collect, cash_collected, notes, order:orders(id, order_no, status, zone_code, customer:customers(full_name, phone, area, address, landmark))";
  const [{ data: open }, { data: done }] = await Promise.all([
    db.from("rider_jobs").select(select).eq("rider_id", riderId).lte("scheduled_date", date).in("status", ["assigned", "en_route", "arrived", "rescheduled"]).order("scheduled_date").order("slot"),
    db.from("rider_jobs").select(select).eq("rider_id", riderId).eq("scheduled_date", date).in("status", ["done", "failed"]),
  ]);
  return [...((open as unknown as RiderAppJob[]) ?? []), ...((done as unknown as RiderAppJob[]) ?? [])];
}
