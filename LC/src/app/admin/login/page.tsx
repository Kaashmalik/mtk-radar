"use client";
import { useActionState } from "react";
import { motion } from "motion/react";
import { signIn } from "@/lib/actions/admin";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/field";

export default function LoginPage() {
  const [state, action, pending] = useActionState(signIn, null);
  return (
    <div className="grain grid min-h-screen place-items-center bg-plum px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm rounded-[var(--radius-lg)] bg-ivory p-8 shadow-2xl"
      >
        <Logo className="text-plum" />
        <h1 className="mt-8 text-2xl text-plum">Staff sign in</h1>
        <form action={action} className="mt-6 space-y-4">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div>
            <Label htmlFor="password">Password</Label>
            <Input id="password" name="password" type="password" autoComplete="current-password" required />
          </div>
          {state && !state.ok && <p className="text-sm text-danger">{state.error}</p>}
          <Button type="submit" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </motion.div>
    </div>
  );
}
