import "server-only";
import { cache } from "react";
import { redirect } from "next/navigation";
import { createClient, createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";

export type Staff = { id: string; name: string; role: string; preview: boolean };

const FINANCE_ROLES = ["partner", "admin", "accountant"];
const DISPATCH_ROLES = ["partner", "admin", "manager"];

const getSessionUser = cache(async () => {
  const db = await createClient();
  const { data } = await db.auth.getClaims();
  return data?.claims ? { id: data.claims.sub, email: (data.claims.email as string | undefined) ?? null } : null;
});

const getProfile = cache(async (userId: string) => {
  const db = await createClient();
  const { data } = await db.from("profiles").select("full_name, role").eq("id", userId).maybeSingle();
  return data;
});

/** Office staff for the admin dashboard. Riders are sent to their own app. */
export const getStaff = cache(async (): Promise<Staff> => {
  if (!isSupabaseConfigured) return { id: "preview", name: "Preview partner", role: "partner", preview: true };

  const user = await getSessionUser();
  if (!user) redirect("/admin/login");
  const profile = await getProfile(user.id);
  if (!profile) redirect("/admin/login?error=not-staff");
  if (profile.role === "rider") redirect("/rider");
  return { id: user.id, name: profile.full_name, role: profile.role, preview: false };
});

export async function requireFinance() {
  const staff = await getStaff();
  if (!FINANCE_ROLES.includes(staff.role)) redirect("/admin?error=finance-only");
  return staff;
}

export async function requireDispatch() {
  const staff = await getStaff();
  if (!DISPATCH_ROLES.includes(staff.role)) redirect("/admin?error=not-allowed");
  return staff;
}

export function canSeeFinance(role: string) {
  return FINANCE_ROLES.includes(role);
}

export type RiderSession = { profileId: string; riderId: string; name: string; preview: boolean };

/** Signed-in rider (role `rider` with a linked `riders` row). */
export const getRider = cache(async (): Promise<RiderSession> => {
  if (!isSupabaseConfigured) return { profileId: "preview", riderId: "preview", name: "Ali (preview)", preview: true };

  const user = await getSessionUser();
  if (!user) redirect("/admin/login?next=/rider");
  const profile = await getProfile(user.id);
  if (!profile) redirect("/admin/login?error=not-staff");

  const db = await createClient();
  const { data: rider } = await db.from("riders").select("id, full_name").eq("profile_id", user.id).eq("is_active", true).maybeSingle();
  if (!rider) redirect(profile.role === "rider" ? "/admin/login?error=no-rider" : "/admin/riders");
  return { profileId: user.id, riderId: rider.id, name: rider.full_name, preview: false };
});

export type CustomerSession = {
  userId: string;
  email: string | null;
  customer: { id: string; full_name: string; phone: string; email: string | null; area: string | null; address: string | null } | null;
};

/** Signed-in customer. `customer` is null until the account is linked to a phone number. */
export const getCustomerSession = cache(async (): Promise<CustomerSession | null> => {
  if (!isSupabaseConfigured) return null;
  const user = await getSessionUser();
  if (!user) return null;
  const { data } = await createServiceClient()
    .from("customers")
    .select("id, full_name, phone, email, area, address")
    .eq("user_id", user.id)
    .maybeSingle();
  return { userId: user.id, email: user.email, customer: data };
});

export async function requireCustomer() {
  if (!isSupabaseConfigured) redirect("/account/login?preview=1");
  const session = await getCustomerSession();
  if (!session) redirect("/account/login");
  return session;
}
