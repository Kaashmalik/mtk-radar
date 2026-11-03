"use client";
import { useActionState, useState } from "react";
import { motion } from "motion/react";
import { CheckCircle2, ImagePlus, Star } from "lucide-react";
import { submitReview } from "@/lib/actions/public";
import { compressFormData } from "@/lib/client-image";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/field";
import { cn } from "@/lib/utils";

function StarInput({ name, label }: { name: string; label: string }) {
  const [value, setValue] = useState(5);
  const [hover, setHover] = useState(0);
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm">{label}</span>
      <input type="hidden" name={name} value={value} />
      <div className="flex" onMouseLeave={() => setHover(0)}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" aria-label={`${n} star${n > 1 ? "s" : ""}`} onClick={() => setValue(n)} onMouseEnter={() => setHover(n)} className="p-1">
            <motion.span whileTap={{ scale: 1.4 }} className="block">
              <Star className={cn("size-6 transition-colors", n <= (hover || value) ? "fill-gold text-gold" : "text-line")} strokeWidth={1.2} />
            </motion.span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ReviewForm({ orderNo, token }: { orderNo: string; token: string }) {
  const [state, action, pending] = useActionState(
    async (prev: Awaited<ReturnType<typeof submitReview>> | null, fd: FormData) => submitReview(prev, await compressFormData(fd)),
    null,
  );
  const [photos, setPhotos] = useState(0);

  if (state?.ok) {
    return (
      <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="rounded-[var(--radius-lg)] border border-line bg-white/60 p-10 text-center">
        <CheckCircle2 className="mx-auto size-10 text-success" strokeWidth={1.4} />
        <p className="font-display mt-4 text-2xl text-plum">Shukriya! Your review is in.</p>
        <p className="mt-2 text-sm text-muted">It will appear on our site after a quick check.</p>
      </motion.div>
    );
  }

  return (
    <form action={action} className="space-y-6">
      <input type="hidden" name="orderNo" value={orderNo} />
      <input type="hidden" name="token" value={token} />
      <div className="space-y-2 rounded-[var(--radius-lg)] border border-line bg-white/60 p-5">
        <StarInput name="rating" label="Overall" />
        <StarInput name="fit" label="Fit" />
        <StarInput name="finishing" label="Stitching & finishing" />
        <StarInput name="onTime" label="On time" />
      </div>
      <div>
        <Label htmlFor="body">Tell other customers about it</Label>
        <Textarea id="body" name="body" required minLength={10} placeholder="How was the fit, the stitching, the pickup and delivery?" />
      </div>
      <label className="flex h-12 cursor-pointer items-center gap-2 rounded-[var(--radius-md)] border border-dashed border-line px-4 text-sm text-muted hover:border-plum">
        <ImagePlus className="size-4" /> {photos ? `${photos} photo(s) added` : "Add photos of your suit (optional, up to 4)"}
        <input name="photos" type="file" accept="image/*" multiple className="sr-only" onChange={(e) => setPhotos(Math.min(4, e.target.files?.length ?? 0))} />
      </label>
      {state && !state.ok && <p className="text-sm text-danger">{state.error}</p>}
      <Button type="submit" size="lg" disabled={pending}>
        {pending ? "Sending…" : "Publish review"}
      </Button>
    </form>
  );
}
