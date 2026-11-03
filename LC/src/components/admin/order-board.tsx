"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "motion/react";
import { MessageCircle } from "lucide-react";
import { orderStatuses } from "@/lib/config";
import { updateOrderStatus } from "@/lib/actions/admin";
import type { AdminOrder } from "@/lib/data/admin";
import { StatusSelect } from "./controls";
import { cn, rs } from "@/lib/utils";

const columns = [
  { key: "payment", label: "Payment", statuses: ["pending_payment", "payment_verification"] },
  { key: "intake", label: "Fabric intake", statuses: ["confirmed", "awaiting_fabric", "fabric_received"] },
  { key: "workshop", label: "In workshop", statuses: ["cutting", "stitching", "finishing", "quality_check"] },
  { key: "out", label: "Ready & delivery", statuses: ["ready", "dispatched", "delivered", "alteration"] },
];

const allStatuses = [...orderStatuses, { value: "alteration", label: "Alteration" }, { value: "completed", label: "Completed" }, { value: "cancelled", label: "Cancelled" }] as const;

export function OrderBoard({ orders }: { orders: AdminOrder[] }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return orders;
    return orders.filter((o) => [o.order_no, o.customer?.full_name, o.customer?.phone, o.customer?.area].some((v) => v?.toLowerCase().includes(t)));
  }, [orders, q]);

  return (
    <>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search order #, name, phone or area…"
        className="mb-6 h-11 w-full max-w-md rounded-full border border-line bg-white px-5 text-sm focus:border-plum focus:outline-none"
      />
      <div className="grid gap-4 lg:grid-cols-4">
        {columns.map((col) => {
          const list = filtered.filter((o) => col.statuses.includes(o.status));
          return (
            <section key={col.key} className="rounded-[var(--radius-lg)] bg-sand/40 p-3">
              <header className="mb-3 flex items-center justify-between px-1">
                <h2 className="font-sans text-sm font-semibold tracking-normal">{col.label}</h2>
                <span className="rounded-full bg-white px-2 text-xs text-muted">{list.length}</span>
              </header>
              <div className="space-y-3">
                <AnimatePresence initial={false}>
                  {list.map((o) => (
                    <motion.article
                      key={o.id}
                      layout
                      initial={{ opacity: 0, scale: 0.96 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.96 }}
                      className={cn("rounded-[var(--radius-md)] border border-line bg-white p-4 shadow-sm", o.tier === "express" && "border-l-4 border-l-wine")}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <Link href={`/admin/orders/${o.id}`} className="text-xs font-semibold text-plum underline-offset-2 hover:underline">
                            {o.order_no}
                          </Link>
                          <p className="text-sm font-medium">{o.customer?.full_name}</p>
                          <p className="text-xs text-muted">
                            {o.customer?.area ?? "—"} {o.zone_code && `· Zone ${o.zone_code}`}
                          </p>
                        </div>
                        {o.customer?.phone && (
                          <a
                            href={`https://wa.me/${o.customer.phone.replace(/\D/g, "")}?text=${encodeURIComponent(`Assalam o Alaikum, update on your order ${o.order_no}:`)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="grid size-8 place-items-center rounded-full bg-[#1f7a4d]/10 text-[#1f7a4d]"
                            aria-label="WhatsApp customer"
                          >
                            <MessageCircle className="size-4" />
                          </a>
                        )}
                      </div>
                      <p className="mt-2 text-xs text-muted">
                        {o.items.map((i) => `${i.qty}× ${i.garment_slug}`).join(", ")} · <span className="capitalize">{o.tier}</span>
                      </p>
                      <div className="mt-2 flex justify-between text-xs">
                        <span>{rs(o.total)}</span>
                        <span className={o.paid >= o.total ? "text-success" : "text-wine"}>{o.paid >= o.total ? "Paid" : `Due ${rs(o.total - o.paid)}`}</span>
                      </div>
                      <div className="mt-3">
                        <StatusSelect value={o.status} options={allStatuses} onChange={(s) => updateOrderStatus(o.id, s)} success="Status updated — customer notified" />
                      </div>
                    </motion.article>
                  ))}
                </AnimatePresence>
                {list.length === 0 && <p className="py-6 text-center text-xs text-muted">Nothing here</p>}
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
}
