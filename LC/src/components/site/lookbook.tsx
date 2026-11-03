"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { MediaImage } from "@/components/brand/media-image";
import type { Design } from "@/lib/data/public";
import { designOptions } from "@/lib/config";
import { cn, rs } from "@/lib/utils";

const occasions = [
  { value: "all", label: "All looks" },
  { value: "everyday", label: "Everyday" },
  { value: "eid", label: "Eid" },
  { value: "party", label: "Party" },
  { value: "formal", label: "Formal" },
  { value: "bridal", label: "Bridal" },
];

/** Builds an /order link that pre-selects the garment and design options of a look. */
export function orderLinkFor(design: Design) {
  const params = new URLSearchParams();
  if (design.garment) params.set("garment", design.garment);
  for (const group of designOptions) {
    const v = design.options[group.key];
    if (v && group.options.some((o) => o.value === v)) params.set(group.key, v);
  }
  params.set("look", design.title);
  return `/order?${params}`;
}

export function Lookbook({ designs }: { designs: Design[] }) {
  const [occasion, setOccasion] = useState("all");
  const shown = useMemo(() => (occasion === "all" ? designs : designs.filter((d) => d.occasion === occasion)), [designs, occasion]);

  return (
    <>
      <div className="mb-10 flex flex-wrap gap-2">
        {occasions.map((o) => (
          <button
            key={o.value}
            onClick={() => setOccasion(o.value)}
            className={cn("relative rounded-full border px-5 py-2 text-sm transition-colors", occasion === o.value ? "border-plum text-ivory" : "border-line hover:border-plum/50")}
          >
            {occasion === o.value && <motion.span layoutId="occasion" className="absolute inset-0 rounded-full bg-plum" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
            <span className="relative">{o.label}</span>
          </button>
        ))}
      </div>

      <motion.div layout className="grid gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
        <AnimatePresence mode="popLayout">
          {shown.map((d, i) => (
            <motion.article
              layout
              key={d.id}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              className="group"
            >
              <Link href={orderLinkFor(d)} className="block">
                <div className="relative aspect-[4/5] overflow-hidden rounded-[var(--radius-lg)]">
                  <MediaImage src={d.image_url ?? d.images[0]} alt={d.title} sizes="(min-width: 1024px) 30vw, 50vw" tone={i} imgClassName="group-hover:scale-[1.04]" />
                  {d.images[1] && (
                    // second photo cross-fades in on hover
                    <div className="absolute inset-0 opacity-0 transition-opacity duration-700 group-hover:opacity-100">
                      <MediaImage src={d.images[1]} alt="" sizes="30vw" />
                    </div>
                  )}
                  <span className="absolute top-4 left-4 rounded-full bg-ivory/90 px-3 py-1 text-[0.68rem] font-semibold tracking-wider text-plum uppercase">{d.occasion}</span>
                  <span className="absolute right-4 bottom-4 grid size-12 translate-y-3 place-items-center rounded-full bg-ivory text-plum opacity-0 shadow-lg transition-all duration-500 group-hover:translate-y-0 group-hover:opacity-100">
                    <ArrowUpRight className="size-5" />
                  </span>
                </div>
                <div className="mt-4 flex items-baseline justify-between gap-4">
                  <h3 className="text-xl text-plum">{d.title}</h3>
                  <p className="shrink-0 text-sm text-muted">from {rs(d.price_from)}</p>
                </div>
                {d.description && <p className="mt-1 text-sm text-muted">{d.description}</p>}
                <p className="mt-2 text-sm text-plum underline-offset-4 group-hover:underline">Order this look</p>
              </Link>
            </motion.article>
          ))}
        </AnimatePresence>
      </motion.div>
      {shown.length === 0 && <p className="py-16 text-center text-muted">New looks for this occasion are coming soon.</p>}
    </>
  );
}
