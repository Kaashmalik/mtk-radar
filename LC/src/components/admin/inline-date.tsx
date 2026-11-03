"use client";
import { useTransition } from "react";
import { toast } from "sonner";

type Result = { ok: true } | { ok: false; error: string };

/** Date input that saves on change through a server action. */
export function InlineDate({ value, onSave, min }: { value: string | null; onSave: (date: string) => Promise<Result>; min?: string }) {
  const [pending, start] = useTransition();
  return (
    <input
      type="date"
      defaultValue={value ?? ""}
      min={min}
      disabled={pending}
      onChange={(e) => {
        const date = e.target.value;
        if (!date) return;
        start(async () => {
          const res = await onSave(date);
          if (res.ok) toast.success("Saved");
          else toast.error(res.error);
        });
      }}
      className="h-8 rounded-[var(--radius-sm)] border border-line bg-white px-2 text-xs"
    />
  );
}
