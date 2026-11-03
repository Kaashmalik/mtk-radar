"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, ArrowRight, Camera, X } from "lucide-react";
import { MediaImage } from "@/components/brand/media-image";
import type { GalleryItem } from "@/lib/data/public";
import { cn } from "@/lib/utils";

const ease = [0.22, 1, 0.36, 1] as const;

/** Fabric → finished suit comparison. Drag (or use arrow keys) to reveal. */
export function BeforeAfter({ before, after, alt }: { before: string; after: string; alt: string }) {
  const [pos, setPos] = useState(50);
  return (
    <div className="relative h-full w-full select-none">
      <MediaImage src={after} alt={alt} sizes="90vw" />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <MediaImage src={before} alt={`${alt} — fabric before stitching`} sizes="90vw" />
      </div>
      <div className="pointer-events-none absolute inset-y-0" style={{ left: `${pos}%` }}>
        <div className="h-full w-px bg-ivory" />
        <span className="absolute top-1/2 left-1/2 grid size-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-ivory text-plum shadow-lg">
          ↔
        </span>
      </div>
      <span className="absolute top-4 left-4 rounded-full bg-ink/60 px-3 py-1 text-xs text-ivory">Fabric</span>
      <span className="absolute top-4 right-4 rounded-full bg-ink/60 px-3 py-1 text-xs text-ivory">Stitched</span>
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label="Compare fabric and stitched suit"
        className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
      />
    </div>
  );
}

export function GalleryGrid({ items, filters = true, limit }: { items: GalleryItem[]; filters?: boolean; limit?: number }) {
  const tags = useMemo(() => ["All", ...new Set(items.flatMap((i) => i.tags))], [items]);
  const [tag, setTag] = useState("All");
  const [open, setOpen] = useState<number | null>(null);
  const shown = useMemo(() => {
    const list = tag === "All" ? items : items.filter((i) => i.tags.includes(tag));
    return limit ? list.slice(0, limit) : list;
  }, [items, tag, limit]);

  const go = useCallback((d: number) => setOpen((i) => (i === null ? i : (i + d + shown.length) % shown.length)), [shown.length]);

  useEffect(() => {
    if (open === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, go]);

  if (items.length === 0) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4 md:gap-6">
        {Array.from({ length: limit ?? 8 }).map((_, i) => (
          <div key={i} className={cn("overflow-hidden rounded-[var(--radius-lg)]", i % 5 === 0 ? "aspect-[3/4] md:row-span-2 md:aspect-auto" : "aspect-[3/4]")}>
            <MediaImage alt="" tone={i} />
          </div>
        ))}
        <p className="col-span-full flex items-center justify-center gap-2 pt-2 text-sm text-muted">
          <Camera className="size-4" /> Photos of real customer orders appear here as they are delivered.
        </p>
      </div>
    );
  }

  const current = open !== null ? shown[open] : null;

  return (
    <>
      {filters && tags.length > 2 && (
        <div className="mb-8 flex flex-wrap gap-2">
          {tags.map((t) => (
            <button
              key={t}
              onClick={() => setTag(t)}
              className={cn(
                "relative rounded-full border px-4 py-1.5 text-sm transition-colors",
                tag === t ? "border-plum text-ivory" : "border-line text-ink hover:border-plum/50",
              )}
            >
              {tag === t && <motion.span layoutId="gallery-tag" className="absolute inset-0 rounded-full bg-plum" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
              <span className="relative">{t}</span>
            </button>
          ))}
        </div>
      )}

      <motion.div layout className="grid grid-cols-2 gap-4 md:grid-cols-3 md:gap-6 lg:grid-cols-4">
        <AnimatePresence mode="popLayout">
          {shown.map((t, i) => (
            <motion.button
              layout
              key={t.id}
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.5, ease }}
              onClick={() => setOpen(i)}
              className={cn("group relative overflow-hidden rounded-[var(--radius-lg)] text-left", i % 7 === 0 ? "aspect-[3/4] md:row-span-2 md:aspect-auto" : "aspect-[3/4]")}
            >
              <MediaImage src={t.image_url} alt={t.title} sizes="(min-width: 1024px) 25vw, 50vw" imgClassName="group-hover:scale-105" tone={i} />
              {t.before_url && <span className="absolute top-3 left-3 rounded-full bg-ivory/90 px-2.5 py-1 text-[0.65rem] font-semibold tracking-wider text-plum uppercase">Before / after</span>}
              <span className="absolute inset-x-0 bottom-0 translate-y-2 bg-gradient-to-t from-plum/85 to-transparent p-5 pt-16 text-ivory opacity-0 transition-all duration-500 group-hover:translate-y-0 group-hover:opacity-100">
                <span className="font-display block text-lg">{t.title}</span>
                <span className="text-xs tracking-wider text-ivory/70 uppercase">{t.tags.join(" · ")}</span>
              </span>
            </motion.button>
          ))}
        </AnimatePresence>
      </motion.div>

      <AnimatePresence>
        {current && (
          <motion.div
            className="fixed inset-0 z-[60] flex flex-col bg-ink/95 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            role="dialog"
            aria-modal="true"
            aria-label={current.title}
          >
            <div className="flex items-center justify-between px-4 py-4 text-ivory sm:px-8">
              <p className="text-sm text-ivory/70">
                {open! + 1} / {shown.length}
              </p>
              <button onClick={() => setOpen(null)} className="grid size-11 place-items-center rounded-full bg-ivory/10" aria-label="Close">
                <X className="size-5" />
              </button>
            </div>
            <div className="relative flex flex-1 items-center justify-center px-4 pb-4 sm:px-20">
              <AnimatePresence mode="wait">
                <motion.div
                  key={current.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  transition={{ duration: 0.4, ease }}
                  className="relative aspect-[3/4] h-full max-h-[75vh] overflow-hidden rounded-[var(--radius-lg)]"
                >
                  {current.before_url ? (
                    <BeforeAfter before={current.before_url} after={current.image_url} alt={current.title} />
                  ) : (
                    <MediaImage src={current.image_url} alt={current.title} sizes="80vw" />
                  )}
                </motion.div>
              </AnimatePresence>
              <button onClick={() => go(-1)} className="absolute left-2 grid size-12 place-items-center rounded-full bg-ivory/10 text-ivory sm:left-6" aria-label="Previous">
                <ArrowLeft className="size-5" />
              </button>
              <button onClick={() => go(1)} className="absolute right-2 grid size-12 place-items-center rounded-full bg-ivory/10 text-ivory sm:right-6" aria-label="Next">
                <ArrowRight className="size-5" />
              </button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 border-t border-ivory/10 px-4 py-5 text-ivory sm:px-8">
              <div>
                <p className="font-display text-2xl">{current.title}</p>
                <p className="text-xs tracking-wider text-ivory/60 uppercase">{current.tags.join(" · ")}</p>
              </div>
              <Link href="/order" className="rounded-full bg-gold px-6 py-3 text-sm font-medium text-ink hover:bg-gold-soft" onClick={() => setOpen(null)}>
                Order a look like this
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
