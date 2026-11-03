"use client";
import { useActionState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2 } from "lucide-react";
import { submitInquiry } from "@/lib/actions/public";
import { compressFormData } from "@/lib/client-image";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/field";

export function InquiryForm() {
  const [state, action, pending] = useActionState(
    async (prev: Awaited<ReturnType<typeof submitInquiry>> | null, fd: FormData) => submitInquiry(prev, await compressFormData(fd)),
    null,
  );

  return (
    <AnimatePresence mode="wait">
      {state?.ok ? (
        <motion.div
          key="done"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-[var(--radius-lg)] border border-line bg-white/60 p-10 text-center"
        >
          <CheckCircle2 className="mx-auto size-10 text-success" strokeWidth={1.4} />
          <p className="font-display mt-4 text-2xl text-plum">Thank you — we&rsquo;ll call you shortly.</p>
          <p className="mt-2 text-sm text-muted">Usually within working hours on the same day.</p>
        </motion.div>
      ) : (
        <motion.form key="form" action={action} className="space-y-5" exit={{ opacity: 0 }}>
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <Label htmlFor="name">Your name</Label>
              <Input id="name" name="name" required autoComplete="name" />
            </div>
            <div>
              <Label htmlFor="phone">Mobile number</Label>
              <Input id="phone" name="phone" required inputMode="tel" placeholder="0300 1234567" autoComplete="tel" />
            </div>
          </div>
          <div>
            <Label htmlFor="type">I&rsquo;m asking about</Label>
            <Select id="type" name="type" defaultValue="general">
              <option value="general">General question</option>
              <option value="bridal">Bridal / formal consultation</option>
              <option value="bulk">Bulk or family order</option>
              <option value="alteration">Alteration quote</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="message">Details</Label>
            <Textarea id="message" name="message" required placeholder="Event date, fabric, design ideas, budget…" />
          </div>
          <div>
            <Label htmlFor="images">Reference pictures (optional)</Label>
            <input
              id="images"
              name="images"
              type="file"
              accept="image/*"
              multiple
              className="block w-full text-sm text-muted file:mr-4 file:rounded-full file:border-0 file:bg-cream file:px-4 file:py-2 file:text-plum"
            />
          </div>
          {state && !state.ok && <p className="text-sm text-danger">{state.error}</p>}
          <Button type="submit" size="lg" disabled={pending}>
            {pending ? "Sending…" : "Send inquiry"}
          </Button>
        </motion.form>
      )}
    </AnimatePresence>
  );
}
