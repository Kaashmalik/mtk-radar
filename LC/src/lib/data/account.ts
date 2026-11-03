import "server-only";
import { createServiceClient } from "@/lib/supabase/server";
import { handoverCode, reviewToken } from "@/lib/handover";

export type AccountOrder = {
  id: string;
  orderNo: string;
  status: string;
  total: number;
  paid: number;
  promisedDate: string | null;
  createdAt: string;
  garments: string;
  visits: { type: string; date: string; slot: string | null; code: string }[];
  reviewUrl: string | null;
};

export type AccountProfile = { id: string; name: string; source: string; fit: string; verified: boolean; data: Record<string, string>; version: number };

/** Everything the signed-in customer sees. Always scoped by their own customer id. */
export async function getAccountData(customerId: string) {
  const db = createServiceClient();
  const [{ data: orders }, { data: profiles }, { data: reviewed }] = await Promise.all([
    db
      .from("orders")
      .select("id, order_no, status, total, paid, promised_date, created_at, items:order_items(garment_slug, qty), jobs:rider_jobs(id, type, scheduled_date, slot, status)")
      .eq("customer_id", customerId)
      .order("created_at", { ascending: false })
      .limit(50),
    db.from("measurement_profiles").select("id, name, source, fit, verified, data, version").eq("customer_id", customerId).eq("archived", false).order("created_at"),
    db.from("reviews").select("order_id").eq("customer_id", customerId),
  ]);

  const reviewedIds = new Set((reviewed ?? []).map((r) => r.order_id));
  const list: AccountOrder[] = (orders ?? []).map((o) => ({
    id: o.id,
    orderNo: o.order_no,
    status: o.status,
    total: o.total,
    paid: o.paid,
    promisedDate: o.promised_date,
    createdAt: o.created_at,
    garments: (o.items as { garment_slug: string; qty: number }[]).map((i) => `${i.qty}× ${i.garment_slug}`).join(", "),
    visits: (o.jobs as { id: string; type: string; scheduled_date: string; slot: string | null; status: string }[])
      .filter((j) => ["assigned", "en_route", "arrived", "rescheduled"].includes(j.status))
      .map((j) => ({ type: j.type, date: j.scheduled_date, slot: j.slot, code: handoverCode(j.id) })),
    reviewUrl:
      ["delivered", "completed"].includes(o.status) && !reviewedIds.has(o.id) ? `/review/${o.order_no}?t=${reviewToken(o.id)}` : null,
  }));

  return { orders: list, profiles: (profiles as AccountProfile[]) ?? [] };
}
