"use client";
import { useActionState, useEffect, useRef, useTransition } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { compressFormData } from "@/lib/client-image";
import { cn } from "@/lib/utils";

type Result = { ok: true } | { ok: false; error: string };

/** Button that runs a server action and reports the result as a toast. */
export function ActionButton({
  action,
  success,
  children,
  variant = "primary",
  confirm,
  className,
}: {
  action: () => Promise<Result>;
  success: string;
  children: React.ReactNode;
  variant?: "primary" | "outline" | "ghost" | "gold";
  confirm?: string;
  className?: string;
}) {
  const [pending, start] = useTransition();
  return (
    <Button
      size="sm"
      variant={variant}
      disabled={pending}
      className={className}
      onClick={() => {
        if (confirm && !window.confirm(confirm)) return;
        start(async () => {
          const res = await action();
          if (res.ok) toast.success(success);
          else toast.error(res.error);
        });
      }}
    >
      {pending ? "…" : children}
    </Button>
  );
}

/** Form wired to a `(prevState, formData)` server action; resets on success. */
export function ActionForm({
  action,
  success,
  children,
  className,
}: {
  action: (state: unknown, formData: FormData) => Promise<Result>;
  success: string;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLFormElement>(null);
  const [state, formAction, pending] = useActionState(async (prev: unknown, fd: FormData) => action(prev, await compressFormData(fd)), null);
  useEffect(() => {
    if (!state) return;
    if (state.ok) {
      toast.success(success);
      ref.current?.reset();
    } else toast.error(state.error);
  }, [state, success]);
  return (
    <form ref={ref} action={formAction} className={cn(className, pending && "pointer-events-none opacity-70")}>
      {children}
    </form>
  );
}

export function StatusSelect({
  value,
  options,
  onChange,
  success = "Saved",
}: {
  value: string;
  options: readonly { value: string; label: string }[];
  onChange: (value: string) => Promise<Result>;
  success?: string;
}) {
  const [pending, start] = useTransition();
  return (
    <select
      value={value}
      disabled={pending}
      onChange={(e) => {
        const next = e.target.value;
        start(async () => {
          const res = await onChange(next);
          if (res.ok) toast.success(success);
          else toast.error(res.error);
        });
      }}
      className="h-8 w-full rounded-[var(--radius-sm)] border border-line bg-white px-2 text-xs"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
