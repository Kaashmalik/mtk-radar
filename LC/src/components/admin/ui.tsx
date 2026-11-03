import { cn } from "@/lib/utils";

export function PageTitle({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl text-plum">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
      </div>
      {children}
    </div>
  );
}

export function Panel({ className, title, action, children }: { className?: string; title?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className={cn("rounded-[var(--radius-lg)] border border-line bg-white", className)}>
      {title && (
        <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <h2 className="font-sans text-sm font-semibold tracking-normal text-ink">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone = "default" }: { label: string; value: string; hint?: string; tone?: "default" | "good" | "bad" | "warn" }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-line bg-white p-5">
      <p className="text-xs font-semibold tracking-[0.14em] text-muted uppercase">{label}</p>
      <p
        className={cn(
          "font-display mt-2 text-3xl tabular-nums",
          tone === "good" && "text-success",
          tone === "bad" && "text-danger",
          tone === "warn" && "text-wine",
          tone === "default" && "text-plum",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

const tones: Record<string, string> = {
  pending_payment: "bg-sand text-muted",
  payment_verification: "bg-gold/20 text-[#7a5b26]",
  pending: "bg-gold/20 text-[#7a5b26]",
  pending_approval: "bg-gold/20 text-[#7a5b26]",
  confirmed: "bg-plum/10 text-plum",
  ready: "bg-success/15 text-success",
  delivered: "bg-success/15 text-success",
  approved: "bg-success/15 text-success",
  verified: "bg-success/15 text-success",
  cancelled: "bg-danger/10 text-danger",
  rejected: "bg-danger/10 text-danger",
  new: "bg-wine/10 text-wine",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", tones[value] ?? "bg-cream text-ink/70")}>
      {label ?? value.replace(/_/g, " ")}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-10 text-center text-sm text-muted">{children}</p>;
}
