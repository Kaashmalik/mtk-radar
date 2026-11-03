"use server";
import { z } from "zod";
import { redirect } from "next/navigation";
import { refresh, updateTag } from "next/cache";
import { createClient, createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";
import { getStaff, requireDispatch, requireFinance } from "@/lib/auth";
import { ensureRiderJob, nextServiceDate } from "@/lib/dispatch";
import { notifyConfirmed, notifyStatus } from "@/lib/notify";
import { mediaSlots } from "@/lib/media";
import { uploadFile } from "@/lib/cloudinary";
import { monthRange } from "@/lib/data/admin";

type Result = { ok: true } | { ok: false; error: string };
const PREVIEW: Result = { ok: false, error: "Preview mode — connect Supabase to save changes." };

async function audit(action: string, entity: string, entityId: string, diff?: unknown) {
  const staff = await getStaff();
  const db = await createClient();
  await db.from("audit_logs").insert({ actor_id: staff.id, action, entity, entity_id: entityId, diff: diff ?? null });
}

// ───────── Auth ─────────

export async function signIn(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) redirect("/admin");
  const db = await createClient();
  const { data, error } = await db.auth.signInWithPassword({
    email: String(formData.get("email") ?? ""),
    password: String(formData.get("password") ?? ""),
  });
  if (error) return { ok: false, error: "Incorrect email or password" };
  const { data: profile } = await db.from("profiles").select("role").eq("id", data.user.id).maybeSingle();
  if (!profile) {
    await db.auth.signOut();
    return { ok: false, error: "This account is not a staff account" };
  }
  redirect(profile.role === "rider" ? "/rider" : "/admin");
}

export async function signOut() {
  if (isSupabaseConfigured) {
    const db = await createClient();
    await db.auth.signOut();
  }
  redirect("/admin/login");
}

// ───────── Orders ─────────

const statusSchema = z.enum([
  "pending_payment", "payment_verification", "confirmed", "awaiting_fabric", "fabric_received", "cutting", "stitching",
  "finishing", "quality_check", "ready", "dispatched", "delivered", "alteration", "completed", "cancelled",
]);

export async function updateOrderStatus(orderId: string, status: string, note?: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const parsed = statusSchema.safeParse(status);
  if (!parsed.success) return { ok: false, error: "Unknown status" };

  const db = await createClient();
  const { data: before } = await db.from("orders").select("status, fabric_method, zone_code, total, paid, pickup_slot").eq("id", orderId).single();
  if (!before) return { ok: false, error: "Order not found" };
  const { error } = await db.from("orders").update({ status: parsed.data, updated_at: new Date().toISOString() }).eq("id", orderId);
  if (error) return { ok: false, error: error.message };
  await db.from("order_status_history").insert({ order_id: orderId, from_status: before.status, to_status: parsed.data, note: note ?? null, changed_by: staff.id });

  // Ready suits picked up by our riders go back the same way: queue the delivery run.
  if (parsed.data === "ready" && before.fabric_method === "rider_pickup") {
    await ensureRiderJob(db, {
      orderId,
      type: "delivery",
      date: nextServiceDate(before.zone_code),
      slot: before.pickup_slot,
      cashToCollect: Math.max(0, before.total - before.paid),
    });
  }
  await notifyStatus(orderId, parsed.data);
  refresh();
  return { ok: true };
}

export async function setPromisedDate(orderId: string, date: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return { ok: false, error: "Invalid date" };
  const db = await createClient();
  const { error } = await db.from("orders").update({ promised_date: date }).eq("id", orderId);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

/** Warehouse intake: photograph the fabric bag on arrival and start production. */
export async function receiveFabric(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const orderId = String(formData.get("orderId") ?? "");
  const note = String(formData.get("note") ?? "").trim() || null;
  const photo = formData.get("photo");
  const photoUrl = photo instanceof File ? await uploadFile(photo, "laraib/fabric") : null;

  const db = await createClient();
  const { data: order } = await db.from("orders").select("status").eq("id", orderId).single();
  if (!order) return { ok: false, error: "Order not found" };
  await db.from("custody_events").insert({ order_id: orderId, event: "received_warehouse", actor_id: staff.id, photo_url: photoUrl, note });
  if (["confirmed", "awaiting_fabric", "payment_verification", "pending_payment"].includes(order.status)) {
    await db.from("orders").update({ status: "fabric_received" }).eq("id", orderId);
    await db.from("order_status_history").insert({ order_id: orderId, from_status: order.status, to_status: "fabric_received", note: note ?? "Fabric received at warehouse", photo_url: photoUrl, changed_by: staff.id });
    await notifyStatus(orderId, "fabric_received");
  }
  refresh();
  return { ok: true };
}

/** Quality-check photo of the finished suit; optionally published to the gallery (only with consent). */
export async function addFinishedPhoto(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const orderId = String(formData.get("orderId") ?? "");
  const photo = formData.get("photo");
  if (!(photo instanceof File) || photo.size === 0) return { ok: false, error: "Choose a photo" };

  const db = await createClient();
  const { data: order } = await db.from("orders").select("status, showcase_consent").eq("id", orderId).single();
  if (!order) return { ok: false, error: "Order not found" };

  const publish = formData.get("publish") === "on";
  if (publish && !order.showcase_consent) return { ok: false, error: "The customer did not consent to showcase this order" };

  // gallery photos are public assets; QC-only photos stay private
  const url = await uploadFile(photo, publish ? "laraib/gallery" : "laraib/qc", !publish);
  await db.from("order_status_history").insert({ order_id: orderId, from_status: order.status, to_status: order.status, note: "Finished suit photo", photo_url: url, changed_by: staff.id });

  if (publish && url) {
    const tags = String(formData.get("tags") ?? "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await db.from("gallery_items").insert({
      order_id: orderId,
      title: String(formData.get("title") ?? "").trim() || "Stitched by Laraib",
      image_url: url,
      tags,
      consent_verified: true,
    });
    updateTag("gallery");
  }
  refresh();
  return { ok: true };
}

// ───────── Dispatch & riders ─────────

export async function createRiderJob(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireDispatch();
  const schema = z.object({
    orderId: z.string().uuid(),
    type: z.enum(["pickup", "delivery", "measurement", "alteration_return"]),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    slot: z.string().optional(),
    riderId: z.string().uuid().optional().or(z.literal("")),
    cash: z.coerce.number().int().min(0).default(0),
    notes: z.string().trim().optional(),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;
  const db = await createClient();
  await ensureRiderJob(db, { orderId: v.orderId, type: v.type, date: v.date, slot: v.slot, riderId: v.riderId || null, cashToCollect: v.cash, notes: v.notes || null });
  refresh();
  return { ok: true };
}

export async function assignRider(jobId: string, riderId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireDispatch();
  const db = await createClient();
  const { error } = await db.from("rider_jobs").update({ rider_id: riderId || null }).eq("id", jobId);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

export async function rescheduleJob(jobId: string, date: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireDispatch();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return { ok: false, error: "Invalid date" };
  const db = await createClient();
  const { error } = await db.from("rider_jobs").update({ scheduled_date: date, status: "assigned", fail_reason: null }).eq("id", jobId);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

/** Adds a rider and (optionally) creates their app login. */
export async function addRider(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireDispatch();
  const schema = z.object({
    fullName: z.string().trim().min(2),
    phone: z.string().trim().min(10),
    cnic: z.string().trim().optional(),
    bikeNo: z.string().trim().optional(),
    zones: z.string().optional(),
    email: z.string().trim().email().optional().or(z.literal("")),
    password: z.string().optional(),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;

  let profileId: string | null = null;
  if (v.email) {
    if (!v.password || v.password.length < 8) return { ok: false, error: "Rider login password must be at least 8 characters" };
    const admin = createServiceClient();
    const { data, error } = await admin.auth.admin.createUser({ email: v.email, password: v.password, email_confirm: true });
    if (error) return { ok: false, error: error.message };
    profileId = data.user.id;
    await admin.from("profiles").insert({ id: profileId, full_name: v.fullName, phone: v.phone, role: "rider" });
  }

  const db = await createClient();
  const zones = (formData.getAll("zones") as string[]).filter((z) => ["A", "B", "C"].includes(z));
  const { error } = await db.from("riders").insert({
    full_name: v.fullName,
    phone: v.phone,
    cnic: v.cnic || null,
    bike_no: v.bikeNo || null,
    zones,
    profile_id: profileId,
  });
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

export async function setRiderActive(riderId: string, active: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireDispatch();
  const db = await createClient();
  const { error } = await db.from("riders").update({ is_active: active }).eq("id", riderId);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

export async function verifyCashClosing(closingId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await requireDispatch();
  const db = await createClient();
  const { error } = await db.from("rider_cash_closings").update({ verified_by: staff.id }).eq("id", closingId);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

// ───────── Reviews & gallery moderation ─────────

export async function moderateReview(reviewId: string, status: "published" | "hidden"): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("reviews").update({ status }).eq("id", reviewId);
  if (error) return { ok: false, error: error.message };
  await audit(status, "review", reviewId);
  updateTag("reviews");
  refresh();
  return { ok: true };
}

export async function featureReview(reviewId: string, featured: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("reviews").update({ featured }).eq("id", reviewId);
  if (error) return { ok: false, error: error.message };
  updateTag("reviews");
  refresh();
  return { ok: true };
}

export async function replyToReview(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const id = String(formData.get("id") ?? "");
  const reply = String(formData.get("reply") ?? "").trim();
  const db = await createClient();
  const { error } = await db.from("reviews").update({ reply: reply || null }).eq("id", id);
  if (error) return { ok: false, error: error.message };
  updateTag("reviews");
  refresh();
  return { ok: true };
}

export async function setGalleryFeatured(itemId: string, featured: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("gallery_items").update({ featured }).eq("id", itemId);
  if (error) return { ok: false, error: error.message };
  updateTag("gallery");
  refresh();
  return { ok: true };
}

export async function removeGalleryItem(itemId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("gallery_items").update({ consent_verified: false }).eq("id", itemId);
  if (error) return { ok: false, error: error.message };
  await audit("unpublish", "gallery_item", itemId);
  updateTag("gallery");
  refresh();
  return { ok: true };
}

// ───────── Payments (slip verification) ─────────

export async function verifyPayment(paymentId: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const db = await createClient();

  const { data: payment, error } = await db
    .from("payments")
    .update({ status: "verified", verified_by: staff.id, verified_at: new Date().toISOString() })
    .eq("id", paymentId)
    .eq("status", "pending")
    .select("order_id, amount")
    .single();
  if (error || !payment) return { ok: false, error: "Payment already handled" };

  const { data: order } = await db.from("orders").select("paid, status").eq("id", payment.order_id).single();
  const nextStatus = order && ["pending_payment", "payment_verification"].includes(order.status) ? "confirmed" : order?.status;
  await db.from("orders").update({ paid: (order?.paid ?? 0) + payment.amount, status: nextStatus }).eq("id", payment.order_id);
  if (nextStatus !== order?.status) {
    await db.from("order_status_history").insert({ order_id: payment.order_id, from_status: order?.status, to_status: nextStatus, note: "Payment verified", changed_by: staff.id });
  }
  await audit("verify", "payment", paymentId, { amount: payment.amount });
  if (nextStatus === "confirmed" && order?.status !== "confirmed") await notifyConfirmed(payment.order_id);
  refresh();
  return { ok: true };
}

export async function rejectPayment(paymentId: string, reason: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const db = await createClient();
  const { error } = await db
    .from("payments")
    .update({ status: "rejected", reject_reason: reason || "Slip unclear", verified_by: staff.id, verified_at: new Date().toISOString() })
    .eq("id", paymentId);
  if (error) return { ok: false, error: error.message };
  await audit("reject", "payment", paymentId, { reason });
  refresh();
  return { ok: true };
}

/** Record cash or WhatsApp-received payments against an order (verified immediately). */
export async function recordPayment(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const schema = z.object({
    orderNo: z.string().trim().toUpperCase(),
    method: z.enum(["bank", "jazzcash", "easypaisa", "raast", "cash_rider", "cash_shop"]),
    amount: z.coerce.number().int().positive(),
    txnId: z.string().trim().optional(),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };

  const db = await createClient();
  const { data: order } = await db.from("orders").select("id, paid").eq("order_no", parsed.data.orderNo).maybeSingle();
  if (!order) return { ok: false, error: "Order not found" };

  const slip = formData.get("slip");
  const proofUrl = slip instanceof File ? await uploadFile(slip, "laraib/slips") : null;
  const { error } = await db.from("payments").insert({
    order_id: order.id,
    method: parsed.data.method,
    amount: parsed.data.amount,
    kind: "balance",
    txn_id: parsed.data.txnId || null,
    proof_url: proofUrl,
    submitted_via: parsed.data.method.startsWith("cash") ? "rider" : "whatsapp",
    status: "verified",
    verified_by: staff.id,
    verified_at: new Date().toISOString(),
  });
  if (error) return { ok: false, error: error.code === "23505" ? "This transaction ID was already used" : error.message };
  await db.from("orders").update({ paid: order.paid + parsed.data.amount }).eq("id", order.id);
  refresh();
  return { ok: true };
}

// ───────── Expenses ─────────

const APPROVAL_THRESHOLD = 10000;

export async function addExpense(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await requireFinance();
  const schema = z.object({
    spentOn: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    categoryId: z.string().uuid("Choose a category"),
    amount: z.coerce.number().int().positive("Enter an amount"),
    vendor: z.string().trim().optional(),
    notes: z.string().trim().optional(),
    paidByPartnerId: z.string().uuid().optional().or(z.literal("")),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;

  const receipt = formData.get("receipt");
  if (v.amount >= APPROVAL_THRESHOLD && !(receipt instanceof File && receipt.size > 0)) {
    return { ok: false, error: `A receipt photo is required for expenses of Rs ${APPROVAL_THRESHOLD.toLocaleString()} or more` };
  }
  const receiptUrl = receipt instanceof File ? await uploadFile(receipt, "laraib/receipts") : null;

  const db = await createClient();
  const { data, error } = await db
    .from("expenses")
    .insert({
      spent_on: v.spentOn,
      category_id: v.categoryId,
      amount: v.amount,
      vendor: v.vendor || null,
      notes: v.notes || null,
      paid_by_partner_id: v.paidByPartnerId || null,
      receipt_url: receiptUrl,
      // large expenses wait for the other partner's approval
      status: v.amount >= APPROVAL_THRESHOLD ? "pending_approval" : "approved",
      added_by: staff.id,
    })
    .select("id")
    .single();
  if (error) return { ok: false, error: error.message };

  if (v.paidByPartnerId) {
    await db.from("partner_transactions").insert({
      partner_id: v.paidByPartnerId,
      type: "reimbursement",
      amount: v.amount,
      happened_on: v.spentOn,
      notes: `Paid business expense: ${v.vendor ?? "expense"}`,
    });
  }
  await audit("create", "expense", data.id, v);
  refresh();
  return { ok: true };
}

export async function reviewExpense(expenseId: string, approve: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await requireFinance();
  const db = await createClient();
  const { data: expense } = await db.from("expenses").select("added_by").eq("id", expenseId).single();
  if (expense?.added_by === staff.id) return { ok: false, error: "The other partner must approve this expense" };
  const { error } = await db
    .from("expenses")
    .update({ status: approve ? "approved" : "rejected", approved_by: staff.id })
    .eq("id", expenseId)
    .eq("status", "pending_approval");
  if (error) return { ok: false, error: error.message };
  await audit(approve ? "approve" : "reject", "expense", expenseId);
  refresh();
  return { ok: true };
}

// ───────── Partnership ─────────

export async function addPartnerTxn(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireFinance();
  const schema = z.object({
    partnerId: z.string().uuid(),
    type: z.enum(["capital", "drawing"]),
    amount: z.coerce.number().int().positive(),
    happenedOn: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    notes: z.string().trim().optional(),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const db = await createClient();
  const { data, error } = await db
    .from("partner_transactions")
    .insert({ partner_id: parsed.data.partnerId, type: parsed.data.type, amount: parsed.data.amount, happened_on: parsed.data.happenedOn, notes: parsed.data.notes || null })
    .select("id")
    .single();
  if (error) return { ok: false, error: error.message };
  await audit("create", "partner_transaction", data.id, parsed.data);
  refresh();
  return { ok: true };
}

/**
 * Month-end close: computes net profit from verified income and approved
 * expenses, applies the agreed reserve, and splits the rest by share percent.
 * The first partner to close creates the draft; the second partner's approval locks it.
 */
export async function closeMonth(month: string, reservePercent: number): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await requireFinance();
  if (!/^\d{4}-\d{2}$/.test(month)) return { ok: false, error: "Invalid month" };

  const db = await createClient();
  const { data: existing } = await db.from("monthly_settlements").select("*").eq("month", month).maybeSingle();
  if (existing?.status === "closed") return { ok: false, error: "This month is already closed" };

  const { data: partners } = await db.from("partners").select("id, profile_id, role, share_percent").order("role", { ascending: false });
  if (!partners || partners.length < 2) return { ok: false, error: "Two partners must be set up first" };
  const [a, b] = partners;

  if (existing) {
    const isA = a.profile_id === staff.id;
    const isB = b.profile_id === staff.id;
    if (!isA && !isB) return { ok: false, error: "Only partners can approve a settlement" };
    const patch = isA ? { approved_a_at: new Date().toISOString() } : { approved_b_at: new Date().toISOString() };
    const bothApproved = (existing.approved_a_at || isA) && (existing.approved_b_at || isB);
    await db.from("monthly_settlements").update({ ...patch, status: bothApproved ? "closed" : "draft" }).eq("month", month);
    if (bothApproved) {
      const kind = existing.distributable >= 0 ? "profit_share" : "loss_share";
      await db.from("partner_transactions").insert([
        { partner_id: a.id, type: kind, amount: Math.abs(existing.share_a), happened_on: monthRange(month).end, settlement_month: month },
        { partner_id: b.id, type: kind, amount: Math.abs(existing.share_b), happened_on: monthRange(month).end, settlement_month: month },
      ]);
    }
    await audit("approve", "settlement", month);
    refresh();
    return { ok: true };
  }

  const { data: row } = await db.from("monthly_pnl").select("revenue, expenses, net_profit").eq("month", month).maybeSingle();
  const revenue = row?.revenue ?? 0;
  const expensesTotal = row?.expenses ?? 0;
  const net = row?.net_profit ?? 0;
  const reserve = net > 0 ? Math.round((net * Math.min(Math.max(reservePercent, 0), 50)) / 100) : 0;
  const distributable = net - reserve;
  const shareA = Math.round((distributable * Number(a.share_percent)) / 100);
  const shareB = distributable - shareA;

  const isA = a.profile_id === staff.id;
  const { error } = await db.from("monthly_settlements").insert({
    month,
    revenue,
    expenses: expensesTotal,
    net_profit: net,
    reserve,
    distributable,
    share_a: shareA,
    share_b: shareB,
    approved_a_at: isA ? new Date().toISOString() : null,
    approved_b_at: !isA && b.profile_id === staff.id ? new Date().toISOString() : null,
  });
  if (error) return { ok: false, error: error.message };
  await audit("create", "settlement", month, { net, reserve, shareA, shareB });
  refresh();
  return { ok: true };
}

// ───────── Inquiries ─────────

export async function setInquiryStatus(id: string, status: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("inquiries").update({ status }).eq("id", id);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}

// ───────── Site media (photos on the public site) ─────────

export async function saveSiteMedia(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  const staff = await getStaff();
  const key = String(formData.get("key") ?? "");
  if (!mediaSlots.some((s) => s.key === key)) return { ok: false, error: "Unknown photo slot" };
  const alt = String(formData.get("alt") ?? "").trim();
  const file = formData.get("photo");

  const db = await createClient();
  if (file instanceof File && file.size > 0) {
    const url = await uploadFile(file, "laraib/site", false);
    if (!url) return { ok: false, error: "Upload failed — check Cloudinary settings" };
    const { error } = await db.from("site_media").upsert({ key, url, alt, updated_by: staff.id, updated_at: new Date().toISOString() });
    if (error) return { ok: false, error: error.message };
  } else {
    const { error } = await db.from("site_media").update({ alt }).eq("key", key);
    if (error) return { ok: false, error: "Choose a photo first" };
  }
  updateTag("media");
  refresh();
  return { ok: true };
}

export async function removeSiteMedia(key: string): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("site_media").delete().eq("key", key);
  if (error) return { ok: false, error: error.message };
  updateTag("media");
  refresh();
  return { ok: true };
}

// ───────── Lookbook designs ─────────

const designSchema = z.object({
  id: z.string().uuid().optional().or(z.literal("")),
  title: z.string().trim().min(3, "Add a title"),
  garment: z.string().min(1),
  occasion: z.enum(["everyday", "eid", "party", "formal", "bridal"]),
  priceFrom: z.coerce.number().int().positive("Add a starting price"),
  description: z.string().trim().max(400).optional(),
  tags: z.string().optional(),
});

export async function saveDesign(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const parsed = designSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;

  const db = await createClient();
  const { data: garment } = await db.from("garment_types").select("id").eq("slug", v.garment).maybeSingle();
  const options: Record<string, string> = {};
  for (const key of ["neckline", "sleeves", "daman", "trouser"]) {
    const val = String(formData.get(key) ?? "");
    if (val) options[key] = val;
  }

  const files = formData.getAll("photos").filter((f): f is File => f instanceof File && f.size > 0).slice(0, 4);
  const uploaded = (await Promise.all(files.map((f) => uploadFile(f, "laraib/designs", false)))).filter((u): u is string => Boolean(u));

  const row = {
    title: v.title,
    garment_type_id: garment?.id ?? null,
    occasion: v.occasion,
    price_from: v.priceFrom,
    description: v.description || null,
    tags: (v.tags ?? "").split(",").map((t) => t.trim()).filter(Boolean),
    options,
    featured: formData.get("featured") === "on",
  };

  if (v.id) {
    const { data: current } = await db.from("designs").select("images").eq("id", v.id).single();
    const images = uploaded.length ? uploaded : (current?.images ?? []);
    const { error } = await db.from("designs").update({ ...row, images, image_url: images[0] ?? null }).eq("id", v.id);
    if (error) return { ok: false, error: error.message };
  } else {
    const slug = `${v.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}-${Date.now().toString(36).slice(-4)}`;
    const { error } = await db.from("designs").insert({ ...row, slug, images: uploaded, image_url: uploaded[0] ?? null });
    if (error) return { ok: false, error: error.message };
  }
  updateTag("designs");
  refresh();
  return { ok: true };
}

export async function setDesignActive(id: string, active: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await getStaff();
  const db = await createClient();
  const { error } = await db.from("designs").update({ is_active: active }).eq("id", id);
  if (error) return { ok: false, error: error.message };
  updateTag("designs");
  refresh();
  return { ok: true };
}

// ───────── Coupons ─────────

export async function saveCoupon(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireFinance();
  const schema = z.object({
    code: z.string().trim().toUpperCase().regex(/^[A-Z0-9]{3,20}$/, "Codes use 3–20 letters/numbers"),
    description: z.string().trim().optional(),
    kind: z.enum(["percent", "flat"]),
    value: z.coerce.number().int().positive(),
    minOrder: z.coerce.number().int().min(0).default(0),
    maxDiscount: z.coerce.number().int().positive().optional().or(z.literal("")),
    startsOn: z.string().optional(),
    endsOn: z.string().optional(),
    usageLimit: z.coerce.number().int().positive().optional().or(z.literal("")),
  });
  const parsed = schema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;
  if (v.kind === "percent" && v.value > 50) return { ok: false, error: "Percentage coupons are capped at 50%" };

  const db = await createClient();
  const { error } = await db.from("coupons").upsert({
    code: v.code,
    description: v.description || null,
    kind: v.kind,
    value: v.value,
    min_order: v.minOrder,
    max_discount: v.maxDiscount || null,
    starts_on: v.startsOn || null,
    ends_on: v.endsOn || null,
    usage_limit: v.usageLimit || null,
  });
  if (error) return { ok: false, error: error.message };
  await audit("save", "coupon", v.code, v);
  refresh();
  return { ok: true };
}

export async function setCouponActive(code: string, active: boolean): Promise<Result> {
  if (!isSupabaseConfigured) return PREVIEW;
  await requireFinance();
  const db = await createClient();
  const { error } = await db.from("coupons").update({ is_active: active }).eq("code", code);
  if (error) return { ok: false, error: error.message };
  refresh();
  return { ok: true };
}
