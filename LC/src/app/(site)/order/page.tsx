import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { OrderWizard, type WizardCustomer } from "@/components/order/order-wizard";
import { Container } from "@/components/site/sections";
import { getCustomerSession } from "@/lib/auth";
import { createServiceClient } from "@/lib/supabase/server";
import { getSiteMedia } from "@/lib/data/public";

export const metadata: Metadata = {
  title: "Start Your Stitching Order",
  description: "Design your suit, choose how we measure you, book a rider pickup and pay by bank, JazzCash, Easypaisa or Raast.",
};

async function WizardForVisitor() {
  const [session, media] = await Promise.all([getCustomerSession(), getSiteMedia()]);
  let customer: WizardCustomer = null;
  if (session?.customer) {
    const { data: profiles } = await createServiceClient()
      .from("measurement_profiles")
      .select("id, name, source, fit")
      .eq("customer_id", session.customer.id)
      .eq("archived", false)
      .order("created_at", { ascending: false });
    customer = { ...session.customer, name: session.customer.full_name, profiles: profiles ?? [] };
  }
  return (
    <>
      {!customer && (
        <p className="mb-8 text-sm text-muted">
          Ordered before?{" "}
          <Link href="/account/login?next=/order" className="text-plum underline">
            Sign in
          </Link>{" "}
          to use your saved measurements.
        </p>
      )}
      <OrderWizard customer={customer} media={media} />
    </>
  );
}

export default function OrderPage() {
  return (
    <section className="pt-32 pb-24 md:pt-40">
      <Container>
        <p className="eyebrow">New order</p>
        <h1 className="mt-3 mb-12 text-[clamp(2.2rem,5vw,3.8rem)] leading-[1.05] text-plum">
          Let&rsquo;s stitch something <em className="text-wine">beautiful.</em>
        </h1>
        <Suspense fallback={<div className="h-96 animate-pulse rounded-[var(--radius-lg)] bg-cream" />}>
          <WizardForVisitor />
        </Suspense>
      </Container>
    </section>
  );
}
