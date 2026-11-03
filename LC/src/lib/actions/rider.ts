"use server";
import { z } from "zod";
import { refresh } from "next/cache";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/server";
import { getRider } from "@/lib/auth";
import { uploadFile } from "@/lib/cloudinary";
import { checkHandoverCode } from "@/lib/handover";
import { notifyDelivered, notifyRiderOnTheWay } from "@/lib/notify";
import { currentMonth } from "@/lib/finance";

type Result = { ok: true } | { ok: false; error: string };
const PREVIEW: Result = { ok: false, error: "Preview mode — connect Supabase to use the rider app." };

/** Loads a job only if it belongs to the signed-in rider. */
async function ownJob(jobId: string) {
  const rider = await getRider();
  const db = await createClient();
  const { data: job } = await db
    .from("rider_jobs")
    .select("id, type, status, order_id, cash_to_collect, order:orders(status, paid, total)")
    .eq("id", jobId)
    .eq("rider_id", rider.riderId)
    .maybeSingle();
  return { rider, db, job: job as (typeof job & { order: { status: string; paid: number; total: number } | null }) | null };
}

export async function startJob(jobId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const { rider, db, job } = await ownJob(jobId);
  if (!job) return { ok: false, error: "Job not found" };
  await db.from("rider_jobs").update({ status: "en_route", started_at: new Date().toISOString() }).eq("id", jobId);
  await notifyRiderOnTheWay(job.order_id, jobId, rider.name.split(" ")[0]);
  refresh();
  return { ok: true };
}

export async function arriveJob(jobId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const { db, job } = await ownJob(jobId);
  if (!job) return { ok: false, error: "Job not found" };
  await db.from("rider_jobs").update({ status: "arrived", arrived_at: new Date().toISOString() }).eq("id", jobId);
  refresh();
  return { ok: true };
}

const completeSchema = z.object({
  jobId: z.string().uuid(),
  code: z.string().trim().regex(/^\d{4}$/, "Enter the customer's 4-digit code"),
  cash: z.coerce.number().int().min(0).default(0),
});

/** Handover: customer code + photo proof (+ cash). Updates the order and chain of custody. */
export async function completeJob(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const parsed = completeSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const { jobId, code, cash } = parsed.data;

  const { rider, db, job } = await ownJob(jobId);
  if (!job || ["done", "failed"].includes(job.status)) return { ok: false, error: "Job not found or already closed" };

  if (!checkHandoverCode(jobId, code)) {
    await db.from("audit_logs").insert({ actor_id: rider.profileId, action: "wrong_code", entity: "rider_job", entity_id: jobId });
    return { ok: false, error: "Code does not match. Ask the customer to check the code on WhatsApp or the Track page." };
  }

  const photo = formData.get("photo");
  if (!(photo instanceof File) || photo.size === 0) return { ok: false, error: "Take a photo of the handover" };
  const photoUrl = await uploadFile(photo, "laraib/handovers");

  const now = new Date().toISOString();
  await db.from("rider_jobs").update({ status: "done", completed_at: now, cash_collected: cash, proof_photos: photoUrl ? [photoUrl] : [] }).eq("id", jobId);

  const order = job.order;
  const event = job.type === "delivery" || job.type === "alteration_return" ? "delivered" : "picked_up";
  await db.from("custody_events").insert({ order_id: job.order_id, event, actor_id: rider.profileId, rider_job_id: jobId, photo_url: photoUrl });

  if (cash > 0) {
    await db.from("payments").insert({
      order_id: job.order_id,
      method: "cash_rider",
      amount: cash,
      kind: "balance",
      submitted_via: "rider",
      status: "verified",
      verified_by: rider.profileId,
      verified_at: now,
    });
    await db.from("orders").update({ paid: (order?.paid ?? 0) + cash }).eq("id", job.order_id);
  }

  if (job.type === "delivery" && order) {
    await db.from("orders").update({ status: "delivered" }).eq("id", job.order_id);
    await db.from("order_status_history").insert({ order_id: job.order_id, from_status: order.status, to_status: "delivered", note: `Delivered by ${rider.name}`, photo_url: photoUrl, changed_by: rider.profileId });
    await notifyDelivered(job.order_id);
  } else if ((job.type === "pickup" || job.type === "measurement") && order && order.status === "confirmed") {
    await db.from("orders").update({ status: "awaiting_fabric" }).eq("id", job.order_id);
    await db.from("order_status_history").insert({ order_id: job.order_id, from_status: order.status, to_status: "awaiting_fabric", note: `Fabric collected by ${rider.name} — on the way to the workshop`, photo_url: photoUrl, changed_by: rider.profileId });
  }

  refresh();
  return { ok: true };
}

export async function failJob(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const jobId = String(formData.get("jobId") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  if (!reason) return { ok: false, error: "Choose a reason" };
  const { db, job } = await ownJob(jobId);
  if (!job) return { ok: false, error: "Job not found" };
  await db.from("rider_jobs").update({ status: "failed", fail_reason: reason, completed_at: new Date().toISOString() }).eq("id", jobId);
  refresh();
  return { ok: true };
}

export async function submitCashClosing(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const rider = await getRider();
  const deposited = z.coerce.number().int().min(0).safeParse(formData.get("deposited"));
  if (!deposited.success) return { ok: false, error: "Enter the amount you are handing over" };
  const date = String(formData.get("date") ?? "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !date.startsWith(currentMonth().slice(0, 4))) return { ok: false, error: "Invalid date" };

  // cash counted by when it was collected (Pakistan time), not when the job was scheduled
  const start = new Date(`${date}T00:00:00+05:00`);
  const end = new Date(start.getTime() + 86400000);
  const db = await createClient();
  const { data: jobs } = await db
    .from("rider_jobs")
    .select("cash_collected")
    .eq("rider_id", rider.riderId)
    .eq("status", "done")
    .gte("completed_at", start.toISOString())
    .lt("completed_at", end.toISOString());
  const expected = (jobs ?? []).reduce((s, j) => s + j.cash_collected, 0);
  const { error } = await db
    .from("rider_cash_closings")
    .upsert({ rider_id: rider.riderId, closing_date: date, expected, deposited: deposited.data }, { onConflict: "rider_id,closing_date" });
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}
