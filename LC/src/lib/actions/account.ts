"use server";
import { z } from "zod";
import { redirect } from "next/navigation";
import { refresh } from "next/cache";
import { createClient, createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";
import { requireCustomer } from "@/lib/auth";

type Result = { ok: true } | { ok: false; error: string };

const email = z.string().trim().toLowerCase().email("Enter a valid email address");

/** Step 1: email a 6-digit sign-in code (Supabase Auth email OTP). */
export async function sendLoginCode(_: unknown, formData: FormData): Promise<Result & { email?: string }> {
  if (!isSupabaseConfigured) return { ok: false, error: "Accounts are available once the database is connected." };
  const parsed = email.safeParse(formData.get("email"));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const db = await createClient();
  const { error } = await db.auth.signInWithOtp({ email: parsed.data, options: { shouldCreateUser: true } });
  if (error) return { ok: false, error: "Couldn't send the code. Please try again in a minute." };
  return { ok: true, email: parsed.data };
}

/** Step 2: verify the code and sign in. */
export async function verifyLoginCode(_: unknown, formData: FormData): Promise<Result> {
  if (!isSupabaseConfigured) return { ok: false, error: "Accounts are available once the database is connected." };
  const parsedEmail = email.safeParse(formData.get("email"));
  const token = String(formData.get("code") ?? "").trim();
  if (!parsedEmail.success || !/^\d{6,8}$/.test(token)) return { ok: false, error: "Enter the code from your email" };
  const db = await createClient();
  const { error } = await db.auth.verifyOtp({ email: parsedEmail.data, token, type: "email" });
  if (error) return { ok: false, error: "That code is incorrect or expired" };
  const next = String(formData.get("next") ?? "");
  redirect(next === "/order" ? "/order" : "/account");
}

export async function signOutCustomer() {
  if (isSupabaseConfigured) {
    const db = await createClient();
    await db.auth.signOut();
  }
  redirect("/");
}

function normalisePhone(p: string) {
  const digits = p.replace(/\D/g, "");
  return digits.startsWith("92") ? `+${digits}` : `+92${digits.replace(/^0/, "")}`;
}

const linkSchema = z.object({
  name: z.string().trim().min(2, "Please enter your name"),
  phone: z
    .string()
    .trim()
    .regex(/^(\+92|0)?3\d{2}[\s-]?\d{7}$/, "Enter a valid mobile number, e.g. 0300 1234567"),
  orderNo: z.string().trim().toUpperCase().optional(),
});

/**
 * Connects the signed-in account to a customer record. If the phone number has
 * ordered before, the customer must prove it with one of those order numbers.
 */
export async function linkAccount(_: unknown, formData: FormData): Promise<Result> {
  const session = await requireCustomer();
  if (session.customer) return { ok: true };
  const parsed = linkSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const { name, orderNo } = parsed.data;
  const phone = normalisePhone(parsed.data.phone);

  const db = createServiceClient();
  const { data: existing } = await db.from("customers").select("id, user_id").eq("phone", phone).maybeSingle();

  if (existing) {
    if (existing.user_id) return { ok: false, error: "This number is already linked to another account." };
    if (!orderNo) return { ok: false, error: "This number has ordered before — enter one of its order numbers (e.g. LC-1042) to link it." };
    const { data: order } = await db.from("orders").select("id").eq("order_no", orderNo).eq("customer_id", existing.id).maybeSingle();
    if (!order) return { ok: false, error: "That order number doesn't match this phone number." };
    await db.from("customers").update({ user_id: session.userId, email: session.email }).eq("id", existing.id);
  } else {
    const { error } = await db.from("customers").insert({ full_name: name, phone, email: session.email, user_id: session.userId });
    if (error) return { ok: false, error: "Couldn't create your profile." };
  }
  refresh();
  return { ok: true };
}

const profileSchema = z.object({
  id: z.string().uuid().optional().or(z.literal("")),
  name: z.string().trim().min(1, "Give this profile a name").max(40),
  fit: z.enum(["slim", "regular", "comfort"]),
  size: z.string().optional(),
});

const MEASURE_KEYS = ["chest", "waist", "hip", "shoulder", "sleeve", "length", "trouser", "armhole", "neck", "bottom"];

export async function saveProfile(_: unknown, formData: FormData): Promise<Result> {
  const session = await requireCustomer();
  if (!session.customer) return { ok: false, error: "Link your phone number first" };
  const parsed = profileSchema.safeParse(Object.fromEntries(formData));
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0].message };
  const v = parsed.data;

  const data: Record<string, string> = {};
  for (const key of MEASURE_KEYS) {
    const raw = String(formData.get(key) ?? "").trim();
    if (!raw) continue;
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0 || n > 80) return { ok: false, error: `Check the ${key} measurement` };
    data[key] = String(n);
  }
  if (v.size) data.size = v.size;
  const source = Object.keys(data).some((k) => k !== "size") ? "self" : "standard_size";

  const db = createServiceClient();
  if (v.id) {
    const { data: current } = await db.from("measurement_profiles").select("version, verified").eq("id", v.id).eq("customer_id", session.customer.id).maybeSingle();
    if (!current) return { ok: false, error: "Profile not found" };
    // editing a staff-verified profile means it is no longer verified
    await db
      .from("measurement_profiles")
      .update({ name: v.name, fit: v.fit, data, source, version: current.version + 1, verified: false })
      .eq("id", v.id);
  } else {
    await db.from("measurement_profiles").insert({ customer_id: session.customer.id, name: v.name, fit: v.fit, data, source });
  }
  refresh();
  return { ok: true };
}

export async function deleteProfile(profileId: string): Promise<Result> {
  const session = await requireCustomer();
  if (!session.customer) return { ok: false, error: "Not allowed" };
  const db = createServiceClient();
  const { count } = await db.from("orders").select("id", { count: "exact", head: true }).eq("measurement_profile_id", profileId);
  if (count) {
    // keep it for past orders, just hide it from the customer
    await db.from("measurement_profiles").update({ archived: true }).eq("id", profileId).eq("customer_id", session.customer.id);
  } else {
    await db.from("measurement_profiles").delete().eq("id", profileId).eq("customer_id", session.customer.id);
  }
  refresh();
  return { ok: true };
}
