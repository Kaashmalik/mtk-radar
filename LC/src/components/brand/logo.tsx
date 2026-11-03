import { cn } from "@/lib/utils";

/** Monogram: an "L" drawn as a single thread ending in a needle eye. */
export function Logo({ className, light = false }: { className?: string; light?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 40 40" className="size-9" aria-hidden>
        <circle cx="20" cy="20" r="19" fill="none" stroke="currentColor" strokeOpacity=".25" />
        <path
          d="M15 9v19.5c0 1.4 1.1 2.5 2.5 2.5H27"
          fill="none"
          stroke={light ? "#d9c39a" : "#b08d57"}
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeDasharray="2.6 2.2"
        />
        <ellipse cx="27.5" cy="12" rx="1.6" ry="3.4" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M27.5 15.5v6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span className="leading-none">
        <span className="font-display block text-[1.35rem] tracking-tight">Laraib</span>
        <span className="block text-[0.6rem] font-semibold uppercase tracking-[0.38em] opacity-70">Creative</span>
      </span>
    </span>
  );
}
