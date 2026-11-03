import "server-only";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/server";
import * as demo from "./demo";

export type AdminOrder = {
  id: string;
  order_no: string;
  status: string;
  tier: string;
  fabric_method: string;
  zone_code: string | null;
  pickup_date: string | null;
  pickup_slot: string | null;
  total: number;
  paid: number;
  created_at: string;
  customer: { full_name: string; phone: string; area: string | null } | null;
  items: { garment_slug: string; qty: number }[];
};

export type AdminPayment = {
  id: string;
  order_id: string;
  method: string;
  amount: number;
  kind: string;
  txn_id: string | null;
  sender_name: string | null;
  proof_url: string | null;
  submitted_via: string;
  status: string;
  created_at: string;
  order: { order_no: string; total: number } | null;
};

export type Expense = {
  id: string;
  spent_on: string;
  amount: number;
  vendor: string | null;
  notes: string | null;
  receipt_url: string | null;
  status: string;
  category: { grp: string; name: string } | null;
  partner: { name: string } | null;
};

export type Category = { id: string; grp: string; name: string };
export type Partner = { id: string; name: string; role: string; share_percent: number };
export type PartnerTxn = { id: string; partner_id: string; type: string; amount: number; happened_on: string; notes: string | null };
export type MonthRow = { month: string; revenue: number; expenses: number; net_profit: number };
export type Settlement = { month: string; status: string; share_a: number; share_b: number; distributable: number; reserve: number };

export function monthRange(month: string) {
  const [y, m] = month.split("-").map(Number);
  const start = `${month}-01`;
  const end = new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10);
  return { start, end };
}

export async function getOrders(): Promise<AdminOrder[]> {
  if (!isSupabaseConfigured) return demo.orders;
  const db = await createClient();
  const { data } = await db
    .from("orders")
    .select(
      "id, order_no, status, tier, fabric_method, zone_code, pickup_date, pickup_slot, total, paid, created_at, customer:customers(full_name, phone, area), items:order_items(garment_slug, qty)",
    )
    .not("status", "in", "(completed,cancelled)")
    .order("created_at", { ascending: false })
    .limit(300);
  return (data as unknown as AdminOrder[]) ?? [];
}

export async function getPendingPayments(): Promise<AdminPayment[]> {
  if (!isSupabaseConfigured) return demo.payments;
  const db = await createClient();
  const { data } = await db
    .from("payments")
    .select("id, order_id, method, amount, kind, txn_id, sender_name, proof_url, submitted_via, status, created_at, order:orders(order_no, total)")
    .eq("status", "pending")
    .order("created_at");
  return (data as unknown as AdminPayment[]) ?? [];
}

export async function getExpenses(month: string): Promise<Expense[]> {
  if (!isSupabaseConfigured) return demo.expenses;
  const { start, end } = monthRange(month);
  const db = await createClient();
  const { data } = await db
    .from("expenses")
    .select("id, spent_on, amount, vendor, notes, receipt_url, status, category:expense_categories(grp, name), partner:partners(name)")
    .gte("spent_on", start)
    .lt("spent_on", end)
    .order("spent_on", { ascending: false });
  return (data as unknown as Expense[]) ?? [];
}

export async function getCategories(): Promise<Category[]> {
  if (!isSupabaseConfigured) return demo.categories;
  const db = await createClient();
  const { data } = await db.from("expense_categories").select("id, grp, name").eq("is_active", true).order("grp").order("name");
  return data ?? [];
}

export async function getPartners(): Promise<Partner[]> {
  if (!isSupabaseConfigured) return demo.partners;
  const db = await createClient();
  const { data } = await db.from("partners").select("id, name, role, share_percent").order("role", { ascending: false });
  return data ?? [];
}

export async function getPartnerTxns(): Promise<PartnerTxn[]> {
  if (!isSupabaseConfigured) return demo.partnerTxns;
  const db = await createClient();
  const { data } = await db.from("partner_transactions").select("id, partner_id, type, amount, happened_on, notes").order("happened_on", { ascending: false }).limit(200);
  return data ?? [];
}

export async function getMonthlyPnl(): Promise<MonthRow[]> {
  if (!isSupabaseConfigured) return demo.pnl;
  const db = await createClient();
  const { data } = await db.from("monthly_pnl").select("month, revenue, expenses, net_profit").order("month").limit(24);
  return data ?? [];
}

export async function getSettlement(month: string): Promise<Settlement | null> {
  if (!isSupabaseConfigured) return null;
  const db = await createClient();
  const { data } = await db.from("monthly_settlements").select("month, status, share_a, share_b, distributable, reserve").eq("month", month).maybeSingle();
  return data;
}

export type RiderJob = {
  id: string;
  type: string;
  scheduled_date: string;
  slot: string | null;
  status: string;
  cash_to_collect: number;
  rider_id: string | null;
  notes: string | null;
  rider: { full_name: string } | null;
  order: { order_no: string; zone_code: string | null; customer: { full_name: string; area: string | null; address: string | null } | null } | null;
};

export async function getRiderJobs(): Promise<RiderJob[]> {
  if (!isSupabaseConfigured) return demo.riderJobs;
  const db = await createClient();
  const { data } = await db
    .from("rider_jobs")
    .select(
      "id, type, scheduled_date, slot, status, cash_to_collect, rider_id, notes, rider:riders(full_name), order:orders(order_no, zone_code, customer:customers(full_name, area, address))",
    )
    .in("status", ["assigned", "en_route", "arrived", "rescheduled"])
    .order("scheduled_date")
    .limit(200);
  return (data as unknown as RiderJob[]) ?? [];
}

export type OrderDetail = Omit<AdminOrder, "customer" | "items"> & {
  urgency_fee: number;
  delivery_fee: number;
  subtotal: number;
  promised_date: string | null;
  showcase_consent: boolean;
  notes: string | null;
  customer: { id: string; full_name: string; phone: string; area: string | null; address: string | null; landmark: string | null } | null;
  items: { id: string; garment_slug: string; qty: number; price: number; options: Record<string, unknown>; measurement_snapshot: Record<string, unknown>; reference_images: string[] }[];
  payments: { id: string; method: string; amount: number; kind: string; status: string; proof_url: string | null; created_at: string }[];
  history: { id: number; from_status: string | null; to_status: string; note: string | null; photo_url: string | null; created_at: string }[];
  jobs: { id: string; type: string; scheduled_date: string; slot: string | null; status: string; cash_to_collect: number; rider_id: string | null; proof_photos: string[] }[];
  custody: { id: number; event: string; photo_url: string | null; note: string | null; created_at: string }[];
};

export async function getOrderDetail(id: string): Promise<OrderDetail | null> {
  if (!isSupabaseConfigured) return demo.orderDetail(id);
  const db = await createClient();
  const { data } = await db
    .from("orders")
    .select(
      `id, order_no, status, tier, fabric_method, zone_code, pickup_date, pickup_slot, total, paid, created_at,
       subtotal, urgency_fee, delivery_fee, promised_date, showcase_consent, notes,
       customer:customers(id, full_name, phone, area, address, landmark),
       items:order_items(id, garment_slug, qty, price, options, measurement_snapshot, reference_images),
       payments(id, method, amount, kind, status, proof_url, created_at),
       history:order_status_history(id, from_status, to_status, note, photo_url, created_at),
       jobs:rider_jobs(id, type, scheduled_date, slot, status, cash_to_collect, rider_id, proof_photos),
       custody:custody_events(id, event, photo_url, note, created_at)`,
    )
    .eq("id", id)
    .maybeSingle();
  if (!data) return null;
  const d = data as unknown as OrderDetail;
  d.history.sort((a, b) => a.created_at.localeCompare(b.created_at));
  d.custody.sort((a, b) => a.created_at.localeCompare(b.created_at));
  return d;
}

export type Rider = { id: string; full_name: string; phone: string; zones: string[]; is_active: boolean; bike_no: string | null; profile_id: string | null };

export async function getRiders(): Promise<Rider[]> {
  if (!isSupabaseConfigured) return demo.riders;
  const db = await createClient();
  const { data } = await db.from("riders").select("id, full_name, phone, zones, is_active, bike_no, profile_id").order("full_name");
  return data ?? [];
}

export type CashClosing = { id: string; closing_date: string; expected: number; deposited: number; difference: number; rider: { full_name: string } | null };

export async function getCashClosings(): Promise<CashClosing[]> {
  if (!isSupabaseConfigured) return [];
  const db = await createClient();
  const { data } = await db
    .from("rider_cash_closings")
    .select("id, closing_date, expected, deposited, difference, rider:riders(full_name)")
    .order("closing_date", { ascending: false })
    .limit(30);
  return (data as unknown as CashClosing[]) ?? [];
}

export type AdminReview = {
  id: string;
  customer_name: string;
  area: string | null;
  rating: number;
  fit: number | null;
  finishing: number | null;
  on_time: number | null;
  body: string;
  media: string[];
  status: string;
  reply: string | null;
  featured: boolean;
  created_at: string;
  order: { order_no: string } | null;
};

export async function getReviews(): Promise<AdminReview[]> {
  if (!isSupabaseConfigured) return demo.reviews;
  const db = await createClient();
  const { data } = await db
    .from("reviews")
    .select("id, customer_name, area, rating, fit, finishing, on_time, body, media, status, reply, featured, created_at, order:orders(order_no)")
    .order("created_at", { ascending: false })
    .limit(200);
  return (data as unknown as AdminReview[]) ?? [];
}

export type AdminGalleryItem = { id: string; title: string; image_url: string; tags: string[]; featured: boolean; consent_verified: boolean; order: { order_no: string } | null };

export async function getGalleryAdmin(): Promise<AdminGalleryItem[]> {
  if (!isSupabaseConfigured) return [];
  const db = await createClient();
  const { data } = await db
    .from("gallery_items")
    .select("id, title, image_url, tags, featured, consent_verified, order:orders(order_no)")
    .order("created_at", { ascending: false })
    .limit(120);
  return (data as unknown as AdminGalleryItem[]) ?? [];
}

export async function getSiteMediaAdmin(): Promise<Record<string, { url: string; alt: string; updated_at: string }>> {
  if (!isSupabaseConfigured) return {};
  const db = await createClient();
  const { data } = await db.from("site_media").select("key, url, alt, updated_at");
  return Object.fromEntries((data ?? []).map((m) => [m.key, m]));
}

export type AdminDesign = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  occasion: string;
  price_from: number;
  image_url: string | null;
  images: string[];
  tags: string[];
  options: Record<string, string>;
  featured: boolean;
  is_active: boolean;
  garment: { slug: string } | null;
};

export async function getDesignsAdmin(): Promise<AdminDesign[]> {
  if (!isSupabaseConfigured) return [];
  const db = await createClient();
  const { data } = await db
    .from("designs")
    .select("id, slug, title, description, occasion, price_from, image_url, images, tags, options, featured, is_active, garment:garment_types(slug)")
    .order("is_active", { ascending: false })
    .order("featured", { ascending: false })
    .order("created_at", { ascending: false });
  return (data as unknown as AdminDesign[]) ?? [];
}

export type AdminCoupon = {
  code: string;
  description: string | null;
  kind: "percent" | "flat";
  value: number;
  min_order: number;
  max_discount: number | null;
  starts_on: string | null;
  ends_on: string | null;
  usage_limit: number | null;
  used_count: number;
  is_active: boolean;
};

export async function getCoupons(): Promise<AdminCoupon[]> {
  if (!isSupabaseConfigured) {
    return [{ code: "LARAIB10", description: "Preview coupon", kind: "percent", value: 10, min_order: 2000, max_discount: 1000, starts_on: null, ends_on: null, usage_limit: 100, used_count: 12, is_active: true }];
  }
  const db = await createClient();
  const { data } = await db.from("coupons").select("*").order("created_at", { ascending: false });
  return (data as AdminCoupon[]) ?? [];
}

export type Inquiry = { id: string; type: string; name: string; phone: string; message: string; status: string; created_at: string };

export async function getInquiries(): Promise<Inquiry[]> {
  if (!isSupabaseConfigured) return demo.inquiries;
  const db = await createClient();
  const { data } = await db.from("inquiries").select("id, type, name, phone, message, status, created_at").order("created_at", { ascending: false }).limit(200);
  return data ?? [];
}
