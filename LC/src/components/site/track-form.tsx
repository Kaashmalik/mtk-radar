"use client";
import { useActionState } from "react";
import { motion } from "motion/react";
import { trackOrder } from "@/lib/actions/public";
import { orderStatuses, statusLabel } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";
import { cn } from "@/lib/utils";

export function TrackForm() {
  const [state, action, pending] = useActionState(trackOrder, null);
  const order = state?.ok ? state.data : null;
  const current = order ? orderStatuses.findIndex((s) => s.value === order.status) : -1;

  return (
    <div className="grid gap-14 lg:grid-cols-[1fr_1.3fr]">
      <form action={action} className="space-y-5">
        <div>
          <Label htmlFor="orderNo">Order number</Label>
          <Input id="orderNo" name="orderNo" placeholder="LC-1042" required className="uppercase" />
        </div>
        <div>
          <Label htmlFor="phone">Mobile number used for the order</Label>
          <Input id="phone" name="phone" placeholder="0300 1234567" inputMode="tel" required />
        </div>
        {state && !state.ok && <p className="text-sm text-danger">{state.error}</p>}
        <Button type="submit" size="lg" disabled={pending}>
          {pending ? "Finding your order…" : "Track order"}
        </Button>
      </form>

      {order && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="rounded-[var(--radius-lg)] border border-line bg-white/50 p-8">
          <p className="text-xs font-semibold tracking-[0.2em] text-muted uppercase">{order.orderNo}</p>
          <p className="font-display mt-1 text-3xl text-plum">{statusLabel(order.status)}</p>
          {order.promisedDate && <p className="mt-1 text-sm text-muted">Promised delivery: {order.promisedDate}</p>}

          {order.visits.map((v) => (
            <div key={v.type + v.date} className="mt-5 flex items-center justify-between gap-4 rounded-[var(--radius-md)] bg-plum p-4 text-ivory">
              <div className="text-sm">
                <p className="font-semibold capitalize">Rider {v.type === "measurement" ? "visit" : v.type}</p>
                <p className="text-ivory/70">
                  {v.date} {v.slot && `· ${v.slot}`}
                </p>
              </div>
              <div className="text-right">
                <p className="text-[0.65rem] tracking-[0.2em] text-ivory/60 uppercase">Handover code</p>
                <p className="font-display text-3xl tracking-[0.3em] text-gold-soft">{v.code}</p>
              </div>
            </div>
          ))}
          {order.visits.length > 0 && <p className="mt-2 text-xs text-muted">Only share this code with the Laraib rider when you hand over or receive your suit.</p>}

          <ol className="relative mt-8 space-y-5 border-l border-line pl-7">
            {/* the needle travels down the timeline to the current stage */}
            <motion.span
              className="absolute -left-[5px] top-0 block size-2.5 rounded-full bg-gold shadow-[0_0_0_4px_rgba(176,141,87,0.2)]"
              initial={{ top: 0 }}
              animate={{ top: `${(Math.max(current, 0) / (orderStatuses.length - 1)) * 100}%` }}
              transition={{ duration: 1.4, ease: [0.65, 0, 0.35, 1] }}
            />
            {orderStatuses.map((s, i) => {
              const done = i <= current;
              const at = order.history.find((h) => h.to_status === s.value);
              return (
                <li key={s.value} className={cn("text-sm", done ? "text-ink" : "text-muted/60")}>
                  <span className={cn(done && "font-semibold", i === current && "text-plum")}>{s.label}</span>
                  {at && <span className="ml-2 text-xs text-muted">{new Date(at.created_at).toLocaleDateString("en-PK")}</span>}
                </li>
              );
            })}
          </ol>
        </motion.div>
      )}
    </div>
  );
}
