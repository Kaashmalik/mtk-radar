"use client";
import { useState } from "react";
import Image, { type ImageLoaderProps } from "next/image";
import { cloudinaryUrl } from "@/lib/media";
import { cn } from "@/lib/utils";

const cloudinaryLoader = ({ src, width }: ImageLoaderProps) => cloudinaryUrl(src, width);

/**
 * Responsive photo with a fade-in. Cloudinary URLs are resized by Cloudinary
 * (f_auto/q_auto); other URLs go through Next's optimizer. Without a `src`
 * it renders a quiet linen-toned placeholder instead of stand-in artwork.
 */
export function MediaImage({
  src,
  alt,
  sizes = "(min-width: 1024px) 50vw, 100vw",
  priority = false,
  className,
  imgClassName,
  tone = 0,
}: {
  src?: string | null;
  alt: string;
  sizes?: string;
  priority?: boolean;
  className?: string;
  imgClassName?: string;
  tone?: number;
}) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div className={cn("relative h-full w-full overflow-hidden", className)}>
      <Placeholder tone={tone} faded={loaded} />
      {src && (
        <Image
          src={src}
          alt={alt}
          fill
          sizes={sizes}
          priority={priority}
          loader={src.includes("res.cloudinary.com") ? cloudinaryLoader : undefined}
          onLoad={() => setLoaded(true)}
          className={cn("object-cover transition-[opacity,transform] duration-[1.2s] ease-[var(--ease-silk)]", loaded ? "opacity-100" : "opacity-0", imgClassName)}
        />
      )}
    </div>
  );
}

const tones = [
  ["#efe6d8", "#e2d5c1"],
  ["#ece3e0", "#d9c9c4"],
  ["#e7e3da", "#d4cdbd"],
  ["#f1e9df", "#e0d0bb"],
];

function Placeholder({ tone, faded }: { tone: number; faded: boolean }) {
  const [a, b] = tones[tone % tones.length];
  return (
    <div
      aria-hidden
      className={cn("absolute inset-0 grid place-items-center transition-opacity duration-700", faded && "opacity-0")}
      style={{
        background: `radial-gradient(120% 80% at 30% 20%, ${a} 0%, ${b} 100%)`,
      }}
    >
      {/* fine woven texture */}
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(59,31,43,.05) 0 1px, transparent 1px 4px), repeating-linear-gradient(90deg, rgba(59,31,43,.04) 0 1px, transparent 1px 4px)",
        }}
      />
      <svg viewBox="0 0 40 40" className="relative size-10 text-plum/20">
        <path d="M15 9v19.5c0 1.4 1.1 2.5 2.5 2.5H27" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeDasharray="2.6 2.2" />
        <ellipse cx="27.5" cy="12" rx="1.6" ry="3.4" fill="none" stroke="currentColor" strokeWidth="1.2" />
      </svg>
    </div>
  );
}
