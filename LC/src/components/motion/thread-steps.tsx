"use client";
import { useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

type Step = { n: string; title: string; body: string };

/**
 * Signature section: a gold thread is "stitched" down the page as the
 * visitor scrolls, connecting each step of the order journey.
 */
export function ThreadSteps({ steps }: { steps: Step[] }) {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const path = root.current?.querySelector<SVGPathElement>("[data-thread]");
      if (!path) return;
      const length = path.getTotalLength();
      gsap.set(path, { strokeDasharray: `${length}`, strokeDashoffset: length });
      gsap.to(path, {
        strokeDashoffset: 0,
        ease: "none",
        scrollTrigger: { trigger: root.current, start: "top 70%", end: "bottom 60%", scrub: 0.6 },
      });

      gsap.utils.toArray<HTMLElement>("[data-step]").forEach((el) => {
        gsap.from(el, {
          opacity: 0,
          x: el.dataset.side === "left" ? -40 : 40,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 80%" },
        });
        const knot = el.querySelector("[data-knot]");
        if (knot)
          gsap.from(knot, {
            scale: 0,
            duration: 0.6,
            ease: "back.out(3)",
            scrollTrigger: { trigger: el, start: "top 65%" },
          });
      });
    },
    { scope: root },
  );

  return (
    <div ref={root} className="relative mx-auto max-w-5xl">
      <svg
        className="pointer-events-none absolute left-6 top-0 h-full w-8 md:left-1/2 md:-translate-x-1/2"
        viewBox="0 0 32 1000"
        preserveAspectRatio="none"
        aria-hidden
      >
        <path
          d="M16 0 C 30 120, 2 220, 16 330 S 30 560, 16 660 S 2 880, 16 1000"
          fill="none"
          stroke="var(--color-line)"
          strokeWidth="1.5"
          strokeDasharray="6 6"
          vectorEffect="non-scaling-stroke"
        />
        <path
          data-thread
          d="M16 0 C 30 120, 2 220, 16 330 S 30 560, 16 660 S 2 880, 16 1000"
          fill="none"
          stroke="var(--color-gold)"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      <ol className="relative space-y-16 md:space-y-24">
        {steps.map((s, i) => {
          const left = i % 2 === 0;
          return (
            <li
              key={s.n}
              data-step
              data-side={left ? "left" : "right"}
              className={`relative pl-16 md:w-1/2 md:pl-0 ${left ? "md:pr-16 md:text-right" : "md:ml-auto md:pl-16"}`}
            >
              <span
                data-knot
                className={`absolute top-1 left-[17px] grid size-6 place-items-center rounded-full border border-gold bg-ivory md:left-auto ${
                  left ? "md:-right-3" : "md:-left-3"
                }`}
              >
                <span className="size-2 rounded-full bg-plum" />
              </span>
              <span className="font-display text-5xl text-gold/70 italic">{s.n}</span>
              <h3 className="mt-2 text-2xl text-plum md:text-3xl">{s.title}</h3>
              <p className="mt-3 text-muted leading-relaxed">{s.body}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
