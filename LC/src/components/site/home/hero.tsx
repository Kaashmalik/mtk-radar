"use client";
import { useRef } from "react";
import { motion, useScroll, useTransform } from "motion/react";
import { ArrowRight, CalendarCheck, Scissors, Truck } from "lucide-react";
import { ButtonLink } from "@/components/ui/button";
import { MaskedHeadline } from "@/components/motion/reveal";
import { Magnetic } from "@/components/motion/magnetic";
import { MediaImage } from "@/components/brand/media-image";
import type { SiteMedia } from "@/lib/media";

const ease = [0.22, 1, 0.36, 1] as const;

export function Hero({ media }: { media: SiteMedia }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const yBack = useTransform(scrollYProgress, [0, 1], [0, -60]);
  const yFront = useTransform(scrollYProgress, [0, 1], [0, -160]);
  const rotate = useTransform(scrollYProgress, [0, 1], [-4, -10]);

  return (
    <section ref={ref} className="grain relative overflow-hidden pt-28 pb-20 md:pt-36 lg:min-h-[100svh]">
      <div className="mx-auto grid max-w-7xl items-center gap-14 px-4 sm:px-6 lg:grid-cols-[1.15fr_1fr] lg:px-10">
        <div>
          <motion.p
            className="eyebrow"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease }}
          >
            Ladies tailoring house · Lahore
          </motion.p>
          <h1 className="mt-6 text-[clamp(2.7rem,7vw,5.6rem)] leading-[0.98] text-plum">
            <MaskedHeadline text="Couture stitching," />
            <br />
            <MaskedHeadline text="collected from" delay={0.35} />{" "}
            <em className="text-wine">
              <MaskedHeadline text="your door." delay={0.5} />
            </em>
          </h1>
          <motion.p
            className="mt-7 max-w-xl text-lg leading-relaxed text-muted"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease, delay: 0.8 }}
          >
            Our rider picks up your fabric, our master tailors stitch it to your saved measurements, and you follow every
            stage until it&rsquo;s back at your door — on the date we promised.
          </motion.p>

          <motion.div
            className="mt-10 flex flex-wrap items-center gap-4"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease, delay: 0.95 }}
          >
            <Magnetic>
              <ButtonLink href="/order" size="lg">
                Start your order <ArrowRight className="size-4" />
              </ButtonLink>
            </Magnetic>
            <ButtonLink href="/how-it-works" variant="ghost" size="lg">
              See how it works
            </ButtonLink>
          </motion.div>

          <motion.ul
            className="mt-14 grid max-w-xl gap-5 border-t border-line pt-7 text-sm sm:grid-cols-3"
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: 0.1, delayChildren: 1.1 } } }}
          >
            {[
              { icon: Truck, text: "Free rider pickup in core Lahore" },
              { icon: CalendarCheck, text: "Delivery date promised upfront" },
              { icon: Scissors, text: "Free alteration within 7 days" },
            ].map(({ icon: Icon, text }) => (
              <motion.li
                key={text}
                className="flex items-start gap-3 text-ink/80"
                variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-gold" strokeWidth={1.6} />
                {text}
              </motion.li>
            ))}
          </motion.ul>
        </div>

        {/* composition */}
        <div className="relative mx-auto aspect-[4/5] w-full max-w-md lg:max-w-none">
          <motion.div
            style={{ y: yBack }}
            initial={{ opacity: 0, clipPath: "inset(12% 12% 12% 12% round 18px)" }}
            animate={{ opacity: 1, clipPath: "inset(0% 0% 0% 0% round 18px)" }}
            transition={{ duration: 1.6, ease, delay: 0.2 }}
            className="absolute top-0 right-0 h-[82%] w-[72%] overflow-hidden rounded-[var(--radius-lg)] shadow-[0_40px_80px_-40px_rgba(59,31,43,0.55)]"
          >
            <MediaImage
              src={media["hero.main"]?.url}
              alt={media["hero.main"]?.alt || "Suit stitched by Laraib Creative"}
              priority
              sizes="(min-width: 1024px) 34vw, 70vw"
              imgClassName="scale-[1.04]"
            />
          </motion.div>
          <motion.div
            style={{ y: yFront, rotate }}
            initial={{ opacity: 0, y: 60 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1.4, ease, delay: 0.45 }}
            className="absolute bottom-[4%] left-0 h-[50%] w-[44%] overflow-hidden rounded-[var(--radius-lg)] border-[6px] border-ivory shadow-[0_30px_60px_-30px_rgba(59,31,43,0.6)]"
          >
            <MediaImage src={media["hero.detail"]?.url} alt={media["hero.detail"]?.alt || "Embroidery detail"} sizes="(min-width: 1024px) 20vw, 45vw" tone={1} />
          </motion.div>
          {/* gold stitch ring */}
          <motion.svg
            viewBox="0 0 120 120"
            className="absolute -top-6 left-[18%] size-28 text-gold"
            initial={{ opacity: 0, rotate: -40 }}
            animate={{ opacity: 1, rotate: 0 }}
            transition={{ duration: 2, ease, delay: 0.9 }}
            aria-hidden
          >
            <circle cx="60" cy="60" r="56" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 5" />
            <text fontSize="9.5" letterSpacing="3" fill="currentColor" className="font-sans uppercase">
              <textPath href="#ring">
                Est. Lahore · Stitched to measure · Garhi Shahu ·
              </textPath>
            </text>
            <path id="ring" d="M60 14a46 46 0 1 1 0 92a46 46 0 1 1 0-92" fill="none" />
          </motion.svg>

          {/* live tracking card */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 1, ease, delay: 1.2 }}
            className="absolute right-[-4%] bottom-[14%] w-56 rounded-[var(--radius-md)] border border-line bg-ivory/95 p-4 shadow-xl backdrop-blur sm:right-[2%]"
          >
            <p className="text-[0.7rem] font-semibold tracking-[0.2em] text-muted uppercase">Order LC-1042</p>
            <p className="font-display mt-1 text-lg text-plum">In stitching</p>
            <div className="mt-3 flex gap-1">
              {Array.from({ length: 8 }).map((_, i) => (
                <motion.span
                  key={i}
                  className={`h-1 flex-1 rounded-full ${i < 5 ? "bg-gold" : "bg-line"}`}
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ delay: 1.5 + i * 0.08, duration: 0.4 }}
                  style={{ originX: 0 }}
                />
              ))}
            </div>
            <p className="mt-3 text-xs text-muted">Arrives Thu, 12 Nov · Rider: Ali</p>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
