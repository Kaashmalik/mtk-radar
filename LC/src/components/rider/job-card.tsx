"use client";
import { useState, useTransition } from "react";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";
import { Camera, Check, MapPin, MessageCircle, Navigation, Phone, X } from "lucide-react";
import { arriveJob, completeJob, failJob, startJob } from "@/lib/actions/rider";
import type { RiderAppJob } from "@/lib/data/rider";
import { Button } from "@/components/ui/button";
import { compressFormData } from "@/lib/client-image";
import { Input } from "@/components/ui/field";
import { cn, rs } from "@/lib/utils";

const typeLabel: Record<string, string> = {
  pickup: "Fabric pickup",
  delivery: "Delivery",
  measurement: "Measure + pickup",
  alteration_return: "Alteration pickup",
};

const failReasons = ["Customer not home", "Phone not answering", "Wrong address", "Customer asked to reschedule", "Fabric not ready", "Refused delivery"];

export function JobCard({ job }: { job: RiderAppJob }) {
  const [mode, setMode] = useState<"none" | "complete" | "fail">("none");
  const [photo, setPhoto] = useState<File | null>(null);
  const [pending, start] = useTransition();
  const [submitting, startSubmit] = useTransition();

  const submit = (action: typeof completeJob, success: string) => (formData: FormData) =>
    startSubmit(async () => {
      const res = await action(null, await compressFormData(formData));
      if (!res.ok) return void toast.error(res.error);
      toast.success(success);
      setMode("none");
    });
  const doneAction = submit(completeJob, "Handover complete ✓");
  const failAction = submit(failJob, "Marked as not completed — office will reschedule");

  const c = job.order?.customer;
  const closed = job.status === "done" || job.status === "failed";
  const mapsQuery = encodeURIComponent([c?.address, c?.area, "Lahore"].filter(Boolean).join(", "));
  const run = (fn: (id: string) => Promise<{ ok: boolean; error?: string }>, msg: string) =>
    start(async () => {
      const res = await fn(job.id);
      if (res.ok) toast.success(msg);
      else toast.error(res.error ?? "Something went wrong");
    });

  return (
    <motion.article
      layout
      className={cn("overflow-hidden rounded-[var(--radius-lg)] border bg-white", closed ? "border-line opacity-60" : "border-line shadow-sm", job.status === "en_route" && "border-gold")}
    >
      <div className="flex items-start justify-between gap-3 p-4">
        <div>
          <p className="text-xs font-semibold tracking-wider text-gold uppercase">{typeLabel[job.type] ?? job.type}</p>
          <p className="font-display mt-1 text-xl text-plum">{c?.full_name}</p>
          <p className="text-xs text-muted">
            {job.order?.order_no} · {job.slot ?? "Any time"} {job.scheduled_date && `· ${job.scheduled_date}`}
          </p>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-[0.7rem] font-semibold capitalize",
            job.status === "done" ? "bg-success/15 text-success" : job.status === "failed" ? "bg-danger/10 text-danger" : "bg-cream text-plum",
          )}
        >
          {job.status.replace("_", " ")}
        </span>
      </div>

      <div className="space-y-1 px-4 pb-3 text-sm">
        <p className="flex gap-2">
          <MapPin className="mt-0.5 size-4 shrink-0 text-gold" />
          <span>
            {c?.address} {c?.area && `· ${c.area}`}
            {c?.landmark && <span className="block text-xs text-muted">Landmark: {c.landmark}</span>}
          </span>
        </p>
        {job.notes && <p className="rounded-[var(--radius-sm)] bg-wine/10 px-2 py-1 text-xs text-wine">{job.notes}</p>}
        {job.cash_to_collect > 0 && !closed && <p className="text-base font-semibold text-wine">Collect {rs(job.cash_to_collect)} cash</p>}
        {job.order && ["pending_payment", "payment_verification"].includes(job.order.status) && (
          <p className="text-xs text-muted">Advance not verified yet — confirm with office before pickup.</p>
        )}
      </div>

      {!closed && (
        <div className="grid grid-cols-3 border-t border-line text-xs">
          <a href={`tel:${c?.phone}`} className="flex flex-col items-center gap-1 py-3 text-plum">
            <Phone className="size-4" /> Call
          </a>
          <a href={`https://wa.me/${c?.phone.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer" className="flex flex-col items-center gap-1 border-x border-line py-3 text-[#1f7a4d]">
            <MessageCircle className="size-4" /> WhatsApp
          </a>
          <a href={`https://www.google.com/maps/search/?api=1&query=${mapsQuery}`} target="_blank" rel="noopener noreferrer" className="flex flex-col items-center gap-1 py-3 text-plum">
            <Navigation className="size-4" /> Map
          </a>
        </div>
      )}

      {!closed && (
        <div className="border-t border-line p-4">
          {mode === "none" && (
            <div className="grid grid-cols-2 gap-2">
              {job.status === "assigned" || job.status === "rescheduled" ? (
                <Button className="col-span-2" size="lg" disabled={pending} onClick={() => run(startJob, "Customer notified you're on the way")}>
                  Start — I&rsquo;m on the way
                </Button>
              ) : job.status === "en_route" ? (
                <Button className="col-span-2" size="lg" disabled={pending} onClick={() => run(arriveJob, "Marked as arrived")}>
                  I&rsquo;ve arrived
                </Button>
              ) : (
                <Button className="col-span-2" size="lg" variant="gold" onClick={() => setMode("complete")}>
                  <Check className="size-4" /> Complete handover
                </Button>
              )}
              {job.status !== "assigned" && job.status !== "rescheduled" && job.status !== "arrived" && (
                <Button variant="outline" className="col-span-2" onClick={() => setMode("complete")}>
                  Complete handover
                </Button>
              )}
              <Button variant="ghost" className="col-span-2 text-danger" onClick={() => setMode("fail")}>
                Couldn&rsquo;t complete
              </Button>
            </div>
          )}

          <AnimatePresence>
            {mode === "complete" && (
              <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} action={doneAction} className="space-y-3">
                <input type="hidden" name="jobId" value={job.id} />
                <label className="block text-sm font-medium">
                  Customer&rsquo;s 4-digit code
                  <Input name="code" inputMode="numeric" pattern="\d{4}" maxLength={4} required className="mt-1 text-center font-display text-2xl tracking-[0.5em]" />
                </label>
                <label className={cn("flex h-14 cursor-pointer items-center justify-center gap-2 rounded-[var(--radius-md)] border border-dashed text-sm", photo ? "border-success text-success" : "border-line text-muted")}>
                  <Camera className="size-5" /> {photo ? "Photo added ✓" : job.type === "delivery" ? "Photo of suit handed over" : "Photo of fabric collected"}
                  <input name="photo" type="file" accept="image/*" capture="environment" required className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
                </label>
                {job.cash_to_collect > 0 && (
                  <label className="block text-sm font-medium">
                    Cash collected (Rs)
                    <Input name="cash" type="number" min={0} defaultValue={job.cash_to_collect} className="mt-1" />
                  </label>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <Button type="button" variant="ghost" onClick={() => setMode("none")}>
                    <X className="size-4" /> Cancel
                  </Button>
                  <Button type="submit" disabled={submitting}>
                    {submitting ? "Saving…" : "Confirm"}
                  </Button>
                </div>
              </motion.form>
            )}
            {mode === "fail" && (
              <motion.form initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} action={failAction} className="space-y-2">
                <input type="hidden" name="jobId" value={job.id} />
                {failReasons.map((r) => (
                  <label key={r} className="flex items-center gap-2 rounded-[var(--radius-sm)] border border-line px-3 py-2.5 text-sm">
                    <input type="radio" name="reason" value={r} required className="accent-[var(--color-plum)]" /> {r}
                  </label>
                ))}
                <div className="grid grid-cols-2 gap-2 pt-1">
                  <Button type="button" variant="ghost" onClick={() => setMode("none")}>
                    Back
                  </Button>
                  <Button type="submit" variant="outline" disabled={submitting}>
                    Submit
                  </Button>
                </div>
              </motion.form>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.article>
  );
}
