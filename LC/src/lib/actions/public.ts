"use server";
import { z } from "zod";
import { createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";
import { uploadFile } from "@/lib/cloudinary";
import { couponDiscount, estimateDelivery, quote, type Coupon, type OrderSelection } from "@/lib/pricing";
import { allow, TOO_MANY } from "@/lib/rate-limit";
import { garments, tiers } from "@/lib/config";
import { getCustomerSession } from "@/lib/auth";
import { ensureRiderJob, nextServiceDate } from "@/lib/dispatch";
import { checkReviewToken, handoverCode } from "@/lib/handover";
import { notifyOrderReceived } from "@/lib/notify";

export type ActionResult<T = undefined> = { ok: true; data: T } | { ok: false; error: string };

const phone = z
  .string()
  .trim()
  .regex(/^(\+92|0)?3\d{2}[\s-]?\d{7}$/, "Enter a valid Pakistani mobile number, e.g. 0300 1234567");

const orderSchema = z.object({
  name: z.string().trim().min(2, "Please enter your name"),
  phone,
  email: z.string().trim().email().optional().or(z.literal("")),
  address: z.string().trim().optional(),
  landmark: z.string().trim().optional(),
  area: z.string().trim().optional(),
  garment: z.enum(garments.map((g) => g.slug) as [string, ...string[]]),
  options: z.record(z.string(), z.string()),
  addons: z.array(z.string()),
  qty: z.coerce.number().int().min(1).max(20),
  tier: z.enum(tiers.map((t) => t.value) as [string, ...string[]]),
  fabricMethod: z.enum(["rider_pickup", "courier", "dropoff"]),
  zone: z.enum(["A", "B", "C"]).optional(),
  pickupDate: z.string().optional(),
  pickupSlot: z.string().optional(),
  measurementMethod: z.enum(["home_visit", "sample_suit", "standard_size", "brand_match", "self", "video_call"]),
  measurement: z.record(z.string(), z.string()),
  paymentMethod: z.enum(["bank", "jazzcash", "easypaisa", "raast", "whatsapp"]),
  txnId: z.string().trim().optional(),
  notes: z.string().trim().optional(),
  showcaseConsent: z.boolean(),
  savedProfileId: z.string().uuid().optional(),
  profileName: z.string().trim().max(40).optional(),
  couponCode: z.string().trim().toUpperCase().max(30).optional(),
  look: z.string().trim().max(120).optional(),
  website: z.string().optional(),
});

async function findCoupon(code: string): Promise<Coupon | null> {
  const normalized = code.trim().toUpperCase();
  if (!isSupabaseConfigured) return normalized === "LARAIB10" ? { code: "LARAIB10", kind: "percent", value: 10, min_order: 2000, max_discount: 1000 } : null;
  const today = new Date(Date.now() + 5 * 3600 * 1000).toISOString().slice(0, 10);
  const { data } = await createServiceClient()
    .from("coupons")
    .select("code, kind, value, min_order, max_discount, starts_on, ends_on, usage_limit, used_count")
    .eq("code", normalized)
    .eq("is_active", true)
    .maybeSingle();
  if (!data) return null;
  if ((data.starts_on && data.starts_on > today) || (data.ends_on && data.ends_on < today)) return null;
  if (data.usage_limit !== null && data.used_count >= data.usage_limit) return null;
  return { code: data.code, kind: data.kind, value: data.value, min_order: data.min_order, max_discount: data.max_discount };
}

/** Live coupon check for the order form. */
export async function checkCoupon(code: string, subtotal: number): Promise<ActionResult<{ coupon: Coupon; label: string }>> {
  if (!(await allow("coupon", 20, 600))) return { ok: false, error: TOO_MANY };
  const coupon = await findCoupon(code);
  if (!coupon) return { ok: false, error: "That code isn't valid" };
  if (couponDiscount(coupon, subtotal) === 0) return { ok: false, error: `This code works on orders above Rs ${coupon.min_order.toLocaleString()}` };
  const label = coupon.kind === "percent" ? `${coupon.value}% off` : `Rs ${coupon.value.toLocaleString()} off`;
  return { ok: true, data: { coupon, label } };
}

export type OrderInput = z.infer<typeof orderSchema>;

function normalisePhone(p: string) {
  const digits = p.replace(/\D/g, "");
  return digits.startsWith("92") ? `+${digits}` : `+92${digits.replace(/^0/, "")}`;
}

/** Public order intake. Slip and reference images arrive as files in FormData. */
export async function createOrder(
  formData: FormData,
): Promise<ActionResult<{ orderNo: string; total: number; advance: number; pickupCode: string | null }>> {
  const raw = formData.get("payload");
  if (typeof raw !== "string") return { ok: false, error: "Invalid request" };

  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { ok: false, error: "Invalid request" };
  }
  const parsed = orderSchema.safeParse(json);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Please check the form" };
  const input = parsed.data;
  if (input.website) return { ok: false, error: "Invalid request" }; // honeypot: bots fill hidden fields

  if (input.fabricMethod === "rider_pickup" && (!input.zone || !input.address)) {
    return { ok: false, error: "Please add your pickup area and address" };
  }
  if (!(await allow("order", 6, 3600))) return { ok: false, error: TOO_MANY };

  const coupon = input.couponCode ? await findCoupon(input.couponCode) : null;
  if (input.couponCode && !coupon) return { ok: false, error: "That coupon code is not valid any more" };
  const price = quote(input as OrderSelection, coupon);
  const fabricDate = input.fabricMethod === "rider_pickup" && input.pickupDate ? input.pickupDate : nextServiceDate(null);
  const promisedDate = estimateDelivery(input as OrderSelection, fabricDate);

  if (!isSupabaseConfigured) {
    // Preview mode — lets the flow be tested before the database is connected.
    return {
      ok: true,
      data: { orderNo: "LC-PREVIEW", total: price.total, advance: price.advance, pickupCode: input.fabricMethod === "rider_pickup" ? "4821" : null },
    };
  }

  try {
    const db = createServiceClient();

    if (coupon) {
      const { data: claimed } = await db.rpc("claim_coupon", { p_code: coupon.code });
      if (!claimed) return { ok: false, error: "That coupon has been fully used" };
    }

    const slip = formData.get("slip");
    const references = formData.getAll("references").filter((f): f is File => f instanceof File && f.size > 0);
    const [slipUrl, ...referenceUrls] = await Promise.all([
      slip instanceof File ? uploadFile(slip, "laraib/slips") : Promise.resolve(null),
      ...references.slice(0, 4).map((f) => uploadFile(f, "laraib/references")),
    ]);

    const session = await getCustomerSession();
    const phoneNo = normalisePhone(input.phone);
    const contact = {
      full_name: input.name,
      email: input.email || null,
      area: input.area || null,
      address: input.address || null,
      landmark: input.landmark || null,
    };

    let customerId: string;
    if (session?.customer) {
      // signed-in customer: keep their account's phone, refresh contact details
      customerId = session.customer.id;
      await db.from("customers").update(contact).eq("id", customerId);
    } else {
      const { data: existing } = await db.from("customers").select("id").eq("phone", phoneNo).maybeSingle();
      if (existing) {
        customerId = existing.id;
        await db.from("customers").update(contact).eq("id", customerId);
      } else {
        // a brand-new phone number can be linked to the signed-in account straight away
        const { data: created, error } = await db
          .from("customers")
          .insert({ ...contact, phone: phoneNo, user_id: session?.userId ?? null })
          .select("id")
          .single();
        if (error) throw error;
        customerId = created.id;
      }
    }

    let profileId: string | null = null;
    let snapshot: Record<string, unknown> = { method: input.measurementMethod, ...input.measurement };
    if (input.savedProfileId && session?.customer) {
      const { data: saved } = await db
        .from("measurement_profiles")
        .select("id, name, source, fit, data")
        .eq("id", input.savedProfileId)
        .eq("customer_id", customerId)
        .maybeSingle();
      if (saved) {
        profileId = saved.id;
        snapshot = { method: saved.source, profile: saved.name, fit: saved.fit, ...(saved.data as object), notes: input.measurement.notes };
      }
    }
    if (!profileId) {
      const { data: profile } = await db
        .from("measurement_profiles")
        .insert({
          customer_id: customerId,
          name: input.profileName || "Me",
          source: input.measurementMethod,
          data: input.measurement,
          fit: input.measurement.fit ?? "regular",
        })
        .select("id")
        .single();
      profileId = profile?.id ?? null;
    }

    const hasSlip = Boolean(slipUrl) || Boolean(input.txnId);
    const { data: order, error: orderErr } = await db
      .from("orders")
      .insert({
        customer_id: customerId,
        status: hasSlip ? "payment_verification" : "pending_payment",
        tier: input.tier,
        fabric_method: input.fabricMethod,
        zone_code: input.fabricMethod === "rider_pickup" ? input.zone : null,
        pickup_date: input.pickupDate || null,
        pickup_slot: input.pickupSlot || null,
        measurement_profile_id: profileId,
        subtotal: price.subtotal,
        urgency_fee: price.urgencyFee,
        delivery_fee: price.deliveryFee,
        discount: price.discount,
        coupon_code: coupon?.code ?? null,
        promised_date: promisedDate,
        total: price.total,
        showcase_consent: input.showcaseConsent,
        notes: input.notes || null,
      })
      .select("id, order_no")
      .single();
    if (orderErr) throw orderErr;

    await db.from("order_items").insert({
      order_id: order.id,
      garment_slug: input.garment,
      options: { ...input.options, addons: input.addons, ...(input.look ? { look: input.look } : {}) },
      measurement_snapshot: snapshot,
      reference_images: referenceUrls.filter(Boolean),
      price: price.unit,
      qty: input.qty,
    });

    if (hasSlip && input.paymentMethod !== "whatsapp") {
      await db.from("payments").insert({
        order_id: order.id,
        method: input.paymentMethod,
        amount: price.advance,
        kind: "advance",
        txn_id: input.txnId || null,
        sender_name: input.name,
        proof_url: slipUrl,
        submitted_via: "website",
      });
    }

    await db.from("order_status_history").insert({
      order_id: order.id,
      to_status: hasSlip ? "payment_verification" : "pending_payment",
      note: "Order placed on website",
    });

    let pickupCode: string | null = null;
    if (input.fabricMethod === "rider_pickup") {
      const jobId = await ensureRiderJob(db, {
        orderId: order.id,
        type: input.measurementMethod === "home_visit" ? "measurement" : "pickup",
        date: input.pickupDate || nextServiceDate(input.zone ?? null),
        slot: input.pickupSlot,
        notes: [
          input.measurementMethod === "home_visit" && "Take measurements and collect fabric",
          input.measurementMethod === "sample_suit" && "Collect sample suit with the fabric (QR tag it)",
        ]
          .filter(Boolean)
          .join(" · ") || null,
      });
      pickupCode = handoverCode(jobId);
    }

    await notifyOrderReceived(order.id, price.advance);
    return { ok: true, data: { orderNo: order.order_no, total: price.total, advance: price.advance, pickupCode } };
  } catch (e) {
    console.error("createOrder failed", e);
    return { ok: false, error: "We couldn't save your order. Please try again or message us on WhatsApp." };
  }
}

const inquirySchema = z.object({
  type: z.enum(["general", "bridal", "bulk", "alteration"]),
  name: z.string().trim().min(2, "Please enter your name"),
  phone,
  message: z.string().trim().min(5, "Please tell us a little more"),
});

export async function submitInquiry(_: unknown, formData: FormData): Promise<ActionResult> {
  if (formData.get("website")) return { ok: false, error: "Invalid request" }; // honeypot
  if (!(await allow("inquiry", 5, 3600))) return { ok: false, error: TOO_MANY };
  const parsed = inquirySchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Please check the form" };
  if (!isSupabaseConfigured) return { ok: true, data: undefined };

  const images = formData.getAll("images").filter((f): f is File => f instanceof File && f.size > 0);
  const urls = await Promise.all(images.slice(0, 4).map((f) => uploadFile(f, "laraib/inquiries")));
  const { error } = await createServiceClient()
    .from("inquiries")
    .insert({ ...parsed.data, phone: normalisePhone(parsed.data.phone), images: urls.filter(Boolean) });
  if (error) return { ok: false, error: "Couldn't send your message. Please try WhatsApp." };
  return { ok: true, data: undefined };
}

export type TrackedOrder = {
  orderNo: string;
  status: string;
  promisedDate: string | null;
  createdAt: string;
  history: { to_status: string; created_at: string; note: string | null }[];
  visits: { type: string; date: string; slot: string | null; code: string }[];
};

export async function trackOrder(_: unknown, formData: FormData): Promise<ActionResult<TrackedOrder>> {
  const orderNo = String(formData.get("orderNo") ?? "").trim().toUpperCase();
  const phoneRaw = String(formData.get("phone") ?? "");
  if (!/^LC-\d+$/.test(orderNo)) return { ok: false, error: "Order numbers look like LC-1042" };
  if (!(await allow("track", 20, 900))) return { ok: false, error: TOO_MANY };
  const phoneCheck = phone.safeParse(phoneRaw);
  if (!phoneCheck.success) return { ok: false, error: phoneCheck.error.issues[0].message };

  if (!isSupabaseConfigured) {
    return {
      ok: true,
      data: {
        orderNo,
        status: "stitching",
        promisedDate: null,
        createdAt: "2026-11-01",
        history: [
          { to_status: "confirmed", created_at: "2026-11-01T10:00:00Z", note: "Preview data" },
          { to_status: "fabric_received", created_at: "2026-11-02T13:00:00Z", note: null },
          { to_status: "cutting", created_at: "2026-11-03T09:00:00Z", note: null },
          { to_status: "stitching", created_at: "2026-11-04T11:00:00Z", note: null },
        ],
        visits: [{ type: "delivery", date: "2026-11-12", slot: "3:00 pm – 5:00 pm", code: "4821" }],
      },
    };
  }

  const db = createServiceClient();
  const { data } = await db
    .from("orders")
    .select("id, order_no, status, promised_date, created_at, customers!inner(phone)")
    .eq("order_no", orderNo)
    .eq("customers.phone", normalisePhone(phoneRaw))
    .maybeSingle();
  if (!data) return { ok: false, error: "We couldn't find that order for this phone number." };

  const [{ data: history }, { data: jobs }] = await Promise.all([
    db.from("order_status_history").select("to_status, created_at, note").eq("order_id", data.id).order("created_at"),
    db
      .from("rider_jobs")
      .select("id, type, scheduled_date, slot")
      .eq("order_id", data.id)
      .in("status", ["assigned", "en_route", "arrived", "rescheduled"]),
  ]);

  return {
    ok: true,
    data: {
      orderNo: data.order_no,
      status: data.status,
      promisedDate: data.promised_date,
      createdAt: data.created_at,
      history: history ?? [],
      visits: (jobs ?? []).map((j) => ({ type: j.type, date: j.scheduled_date, slot: j.slot, code: handoverCode(j.id) })),
    },
  };
}

// ───────── Reviews (token link sent on WhatsApp after delivery) ─────────

const reviewSchema = z.object({
  orderNo: z.string().regex(/^LC-\d+$/),
  token: z.string().min(10),
  rating: z.coerce.number().int().min(1).max(5),
  fit: z.coerce.number().int().min(1).max(5),
  finishing: z.coerce.number().int().min(1).max(5),
  onTime: z.coerce.number().int().min(1).max(5),
  body: z.string().trim().min(10, "Please write at least a sentence").max(1200),
});

export async function submitReview(_: unknown, formData: FormData): Promise<ActionResult> {
  const parsed = reviewSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;
  if (!isSupabaseConfigured) return { ok: true, data: undefined };

  const db = createServiceClient();
  const { data: order } = await db
    .from("orders")
    .select("id, status, customer_id, customer:customers(full_name, area)")
    .eq("order_no", v.orderNo)
    .maybeSingle();
  if (!order || !checkReviewToken(order.id, v.token)) return { ok: false, error: "This review link is not valid." };
  if (!["delivered", "completed", "alteration"].includes(order.status)) return { ok: false, error: "You can review once your order is delivered." };

  const photos = formData.getAll("photos").filter((f): f is File => f instanceof File && f.size > 0);
  const media = await Promise.all(photos.slice(0, 4).map((f) => uploadFile(f, "laraib/reviews", false)));
  const customer = order.customer as unknown as { full_name: string; area: string | null } | null;
  const first = customer?.full_name.split(" ")[0] ?? "Customer";
  const initial = customer?.full_name.split(" ")[1]?.[0];

  const { error } = await db.from("reviews").insert({
    order_id: order.id,
    customer_id: order.customer_id,
    customer_name: initial ? `${first} ${initial}.` : first,
    area: customer?.area ?? null,
    rating: v.rating,
    fit: v.fit,
    finishing: v.finishing,
    on_time: v.onTime,
    body: v.body,
    media: media.filter(Boolean),
  });
  if (error) return { ok: false, error: error.code === "23505" ? "You've already reviewed this order — thank you!" : "Couldn't save your review." };
  return { ok: true, data: undefined };
}
