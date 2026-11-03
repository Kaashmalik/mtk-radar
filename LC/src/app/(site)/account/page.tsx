import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { BadgeCheck, LogOut, Star } from "lucide-react";
import { requireCustomer } from "@/lib/auth";
import { getAccountData } from "@/lib/data/account";
import { deleteProfile, signOutCustomer } from "@/lib/actions/account";
import { Container } from "@/components/site/sections";
import { LinkAccountForm, NewProfile, ProfileForm } from "@/components/account/account-forms";
import { ActionButton } from "@/components/admin/controls";
import { ButtonLink } from "@/components/ui/button";
import { garments, orderStatuses, statusLabel } from "@/lib/config";
import { cn, rs } from "@/lib/utils";

export const metadata: Metadata = { title: "My account", robots: { index: false } };

function garmentNames(s: string) {
  return s.replace(/(\d+)× (\w+)/g, (_, q, slug) => `${q}× ${garments.find((g) => g.slug === slug)?.name ?? slug}`);
}

async function AccountHome() {
  const session = await requireCustomer();

  if (!session.customer) {
    return (
      <>
        <h1 className="text-4xl text-plum">One last step</h1>
        <p className="mt-3 mb-8 max-w-lg text-muted">Add your WhatsApp number so we can link your orders and send updates.</p>
        <LinkAccountForm />
      </>
    );
  }

  const { orders, profiles } = await getAccountData(session.customer.id);
  const active = orders.filter((o) => !["completed", "cancelled", "delivered"].includes(o.status));
  const past = orders.filter((o) => ["completed", "cancelled", "delivered"].includes(o.status));

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">My Laraib</p>
          <h1 className="mt-2 text-4xl text-plum">Salam, {session.customer.full_name.split(" ")[0]}</h1>
        </div>
        <div className="flex gap-2">
          <ButtonLink href="/order">New order</ButtonLink>
          <form action={signOutCustomer}>
            <button className="grid size-11 place-items-center rounded-full border border-line text-muted hover:text-plum" aria-label="Sign out">
              <LogOut className="size-4" />
            </button>
          </form>
        </div>
      </div>

      <section className="mt-12">
        <h2 className="text-2xl text-plum">Active orders</h2>
        {active.length === 0 && <p className="mt-4 text-muted">Nothing in the workshop right now.</p>}
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          {active.map((o) => {
            const idx = orderStatuses.findIndex((s) => s.value === o.status);
            return (
              <article key={o.id} className="rounded-[var(--radius-lg)] border border-line bg-white/60 p-6">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold tracking-wider text-muted">{o.orderNo}</p>
                    <p className="font-display mt-1 text-2xl text-plum">{statusLabel(o.status)}</p>
                    <p className="text-sm text-muted">{garmentNames(o.garments)}</p>
                  </div>
                  <div className="text-right text-sm">
                    <p>{rs(o.total)}</p>
                    {o.total > o.paid && <p className="text-wine">Due {rs(o.total - o.paid)}</p>}
                  </div>
                </div>
                <div className="mt-4 flex gap-1">
                  {orderStatuses.map((s, i) => (
                    <span key={s.value} className={cn("h-1 flex-1 rounded-full", i <= idx ? "bg-gold" : "bg-line")} />
                  ))}
                </div>
                {o.promisedDate && <p className="mt-2 text-xs text-muted">Promised delivery: {o.promisedDate}</p>}
                {o.visits.map((v) => (
                  <div key={v.type + v.date} className="mt-4 flex items-center justify-between rounded-[var(--radius-md)] bg-plum px-4 py-3 text-ivory">
                    <span className="text-sm capitalize">
                      Rider {v.type === "measurement" ? "visit" : v.type} · {v.date}
                      {v.slot && <span className="block text-xs text-ivory/60">{v.slot}</span>}
                    </span>
                    <span className="font-display text-2xl tracking-[0.3em] text-gold-soft">{v.code}</span>
                  </div>
                ))}
              </article>
            );
          })}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl text-plum">Measurement profiles</h2>
        <p className="mt-1 text-sm text-muted">Saved for the whole family — choose one when you order.</p>
        <div className="mt-6 space-y-4">
          {profiles.map((p) => (
            <details key={p.id} className="group rounded-[var(--radius-lg)] border border-line bg-white/60">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5">
                <span>
                  <span className="font-display text-xl text-plum">{p.name}</span>
                  {p.verified && (
                    <span className="ml-2 inline-flex items-center gap-1 text-xs text-success">
                      <BadgeCheck className="size-3.5" /> Verified by Laraib
                    </span>
                  )}
                  <span className="block text-xs text-muted capitalize">
                    {p.source.replace(/_/g, " ")} · {p.fit} fit {p.data.size && `· size ${p.data.size}`}
                  </span>
                </span>
                <span className="text-sm text-plum group-open:hidden">Edit</span>
              </summary>
              <div className="border-t border-line p-5">
                <ProfileForm profile={p} />
                <div className="mt-4">
                  <ActionButton action={deleteProfile.bind(null, p.id)} success="Profile removed" variant="ghost" confirm={`Remove “${p.name}”?`}>
                    Remove profile
                  </ActionButton>
                </div>
              </div>
            </details>
          ))}
          <NewProfile />
        </div>
      </section>

      {past.length > 0 && (
        <section className="mt-16">
          <h2 className="text-2xl text-plum">Past orders</h2>
          <ul className="mt-6 divide-y divide-line border-y border-line">
            {past.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 py-4 text-sm">
                <span>
                  <strong>{o.orderNo}</strong> · {garmentNames(o.garments)}
                  <span className="block text-xs text-muted">
                    {new Date(o.createdAt).toLocaleDateString("en-PK")} · {statusLabel(o.status)} · {rs(o.total)}
                  </span>
                </span>
                <span className="flex gap-2">
                  {o.reviewUrl && (
                    <Link href={o.reviewUrl} className="inline-flex items-center gap-1 rounded-full bg-gold/15 px-4 py-2 text-[#7a5b26]">
                      <Star className="size-3.5" /> Review
                    </Link>
                  )}
                  <Link href={`/order?garment=${o.garments.match(/× (\w+)/)?.[1] ?? "simple"}`} className="rounded-full border border-line px-4 py-2 hover:border-plum">
                    Order again
                  </Link>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

export default function AccountPage() {
  return (
    <section className="pt-32 pb-24 md:pt-40">
      <Container>
        <Suspense fallback={<div className="h-64 animate-pulse rounded-[var(--radius-lg)] bg-cream" />}>
          <AccountHome />
        </Suspense>
      </Container>
    </section>
  );
}
