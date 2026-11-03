"use client";
import { use, useActionState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { sendLoginCode, verifyLoginCode } from "@/lib/actions/account";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";

export function LoginFlow({ nextPromise }: { nextPromise: Promise<string> }) {
  const next = use(nextPromise);
  const [sent, sendAction, sending] = useActionState(sendLoginCode, null);
  const [verified, verifyAction, verifying] = useActionState(verifyLoginCode, null);
  const email = sent?.ok ? sent.email : null;

  return (
    <AnimatePresence mode="wait">
      {!email ? (
        <motion.form key="email" action={sendAction} className="space-y-4" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
          <div>
            <Label htmlFor="email">Email address</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          {sent && !sent.ok && <p className="text-sm text-danger">{sent.error}</p>}
          <Button type="submit" size="lg" className="w-full" disabled={sending}>
            {sending ? "Sending code…" : "Email me a sign-in code"}
          </Button>
        </motion.form>
      ) : (
        <motion.form key="code" action={verifyAction} className="space-y-4" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
          <input type="hidden" name="email" value={email} />
          <input type="hidden" name="next" value={next} />
          <p className="text-sm text-muted">
            We sent a code to <strong className="text-ink">{email}</strong>.
          </p>
          <div>
            <Label htmlFor="code">Sign-in code</Label>
            <Input id="code" name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} required className="font-display text-center text-2xl tracking-[0.4em]" />
          </div>
          {verified && !verified.ok && <p className="text-sm text-danger">{verified.error}</p>}
          <Button type="submit" size="lg" className="w-full" disabled={verifying}>
            {verifying ? "Checking…" : "Sign in"}
          </Button>
        </motion.form>
      )}
    </AnimatePresence>
  );
}
