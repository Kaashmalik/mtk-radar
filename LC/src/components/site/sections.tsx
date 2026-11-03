import Link from "next/link";
import { ArrowUpRight, BadgeCheck, Camera, Clock3, MapPin, Ruler, ShieldCheck, Star } from "lucide-react";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/reveal";
import { ButtonLink } from "@/components/ui/button";
import { MediaImage } from "@/components/brand/media-image";
import { garments, measurementMethods, zones, brand, whatsappLink } from "@/lib/config";
import type { PublicReview } from "@/lib/data/public";
import type { SiteMedia } from "@/lib/media";
import { cn, rs } from "@/lib/utils";

export function SectionHeading({
  eyebrow,
  title,
  body,
  align = "left",
  className,
}: {
  eyebrow: string;
  title: React.ReactNode;
  body?: string;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <Reveal className={cn(align === "center" && "mx-auto text-center", "max-w-2xl", className)}>
      <p className="eyebrow">{eyebrow}</p>
      <h2 className="mt-4 text-[clamp(2rem,4.5vw,3.4rem)] leading-[1.05] text-plum">{title}</h2>
      {body && <p className="mt-5 text-lg leading-relaxed text-muted">{body}</p>}
    </Reveal>
  );
}

export function PageHero({ eyebrow, title, body }: { eyebrow: string; title: React.ReactNode; body?: string }) {
  return (
    <section className="grain border-b border-line pt-36 pb-16 md:pt-44 md:pb-20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <SectionHeading eyebrow={eyebrow} title={title} body={body} className="max-w-3xl" />
      </div>
    </section>
  );
}

export function Container({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mx-auto max-w-7xl px-4 sm:px-6 lg:px-10", className)} {...props} />;
}

const promises = [
  { icon: Clock3, title: "A date, not a guess", body: "Your delivery date is fixed when you order — the calendar only offers dates our workshop can truly meet." },
  { icon: Camera, title: "Photo proof at every handover", body: "Fabric photographed at your door and again when your suit passes quality check." },
  { icon: Ruler, title: "Measurements you never repeat", body: "Saved profiles for you, Ammi and your sisters. Re-order in two taps." },
  { icon: ShieldCheck, title: "Fit guarantee", body: "If it doesn't fit, our rider collects it and we alter it free within 7 days." },
];

export function Promises() {
  return (
    <section className="py-24 md:py-32">
      <Container className="grid gap-16 lg:grid-cols-[1fr_1.3fr]">
        <SectionHeading
          eyebrow="Why Laraib"
          title={
            <>
              Not another tailor. <em className="text-wine">A promise kept.</em>
            </>
          }
          body="Lahore has thousands of tailors. What it doesn't have is certainty — on dates, on fit, on what happens to your fabric. That's what we built."
        />
        <Stagger className="grid gap-px overflow-hidden rounded-[var(--radius-lg)] border border-line bg-line sm:grid-cols-2">
          {promises.map(({ icon: Icon, title, body }) => (
            <StaggerItem key={title} className="bg-ivory p-8 transition-colors duration-500 hover:bg-cream">
              <Icon className="size-6 text-gold" strokeWidth={1.4} />
              <h3 className="mt-6 text-xl text-plum">{title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>
    </section>
  );
}

export function ServicesGrid({ media }: { media: SiteMedia }) {
  return (
    <Stagger className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {garments.map((g, i) => (
        <StaggerItem key={g.slug}>
          <Link
            href={`/order?garment=${g.slug}`}
            className="group block overflow-hidden rounded-[var(--radius-lg)] border border-line bg-white/40 transition-shadow duration-500 hover:shadow-[0_30px_60px_-35px_rgba(59,31,43,0.5)]"
          >
            <div className="aspect-[4/3] overflow-hidden">
              <MediaImage
                src={media[`service.${g.slug}`]?.url}
                alt={media[`service.${g.slug}`]?.alt || g.name}
                sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 100vw"
                tone={i}
                imgClassName="group-hover:scale-[1.05]"
              />
            </div>
            <div className="flex items-end justify-between gap-4 p-6">
              <div>
                <h3 className="text-2xl text-plum">{g.name}</h3>
                <p className="mt-1.5 text-sm text-muted">{g.blurb}</p>
                <p className="mt-4 text-sm">
                  <span className="text-muted">From </span>
                  <span className="font-semibold text-ink">{rs(g.basePrice)}</span>
                  <span className="text-muted"> · {g.days} days</span>
                </p>
              </div>
              <span className="grid size-11 shrink-0 place-items-center rounded-full border border-line text-plum transition-all duration-500 group-hover:rotate-45 group-hover:border-plum group-hover:bg-plum group-hover:text-ivory">
                <ArrowUpRight className="size-4" />
              </span>
            </div>
          </Link>
        </StaggerItem>
      ))}
    </Stagger>
  );
}

export function MeasurementOptions() {
  return (
    <section className="bg-cream/60 py-24 md:py-32">
      <Container>
        <SectionHeading
          eyebrow="Measurements, your way"
          title={
            <>
              Six ways to a <em className="text-wine">perfect fit.</em>
            </>
          }
          body="Pick whatever is easiest for you. Every option becomes a saved profile you can reuse on your next order."
        />
        <Stagger className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {measurementMethods.map((m, i) => (
            <StaggerItem
              key={m.value}
              className="relative rounded-[var(--radius-lg)] border border-line bg-ivory p-7 transition-transform duration-500 hover:-translate-y-1"
            >
              <span className="font-display text-sm text-gold italic">0{i + 1}</span>
              {m.badge && (
                <span className="absolute top-6 right-6 rounded-full bg-plum px-3 py-1 text-[0.68rem] font-semibold tracking-wider text-ivory uppercase">
                  {m.badge}
                </span>
              )}
              <h3 className="mt-4 text-xl text-plum">{m.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{m.desc}</p>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>
    </section>
  );
}

export function ZonesSection() {
  return (
    <section className="py-24 md:py-32">
      <Container className="grid gap-14 lg:grid-cols-[1fr_1.4fr]">
        <div>
          <SectionHeading
            eyebrow="Laraib riders"
            title={
              <>
                Our own riders. <em className="text-wine">Your fabric, sealed.</em>
              </>
            }
            body="No unknown couriers. A uniformed Laraib rider collects your fabric in a sealed, QR-tagged bag and hands back your suit only after you share your delivery code."
          />
          <Reveal delay={0.2} className="mt-8 flex items-start gap-3 text-sm text-muted">
            <MapPin className="mt-0.5 size-4 shrink-0 text-gold" />
            <span>
              Studio & warehouse: {brand.address}. Drop-off welcome during {brand.hours.toLowerCase()}.
            </span>
          </Reveal>
        </div>
        <Stagger className="space-y-4">
          {zones.map((z) => (
            <StaggerItem
              key={z.code}
              className="grid gap-4 rounded-[var(--radius-lg)] border border-line p-6 sm:grid-cols-[auto_1fr_auto] sm:items-center"
            >
              <span className="font-display grid size-14 place-items-center rounded-full bg-plum text-2xl text-ivory">
                {z.code}
              </span>
              <div>
                <p className="font-semibold text-ink">
                  {z.name} zone <span className="font-normal text-muted">· {z.note}</span>
                </p>
                <p className="mt-1 text-sm text-muted">{z.areas.join(" · ")}</p>
              </div>
              <div className="text-sm sm:text-right">
                <p className="font-semibold text-ink">{rs(z.fee)} / trip</p>
                <p className="text-muted">Free above {rs(z.freeAbove)}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </Container>
    </section>
  );
}

export function Stars({ value, className }: { value: number; className?: string }) {
  return (
    <span className={cn("inline-flex gap-0.5", className)} aria-label={`${value} out of 5 stars`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Star key={i} className={cn("size-4", i < value ? "fill-gold text-gold" : "text-line")} strokeWidth={1.2} />
      ))}
    </span>
  );
}

export function ReviewsGrid({ reviews, preview }: { reviews: PublicReview[]; preview: boolean }) {
  if (reviews.length === 0) {
    return (
      <Reveal className="rounded-[var(--radius-lg)] border border-dashed border-line p-12 text-center">
        <BadgeCheck className="mx-auto size-8 text-gold" strokeWidth={1.3} />
        <p className="font-display mt-4 text-2xl text-plum">Verified reviews are on their way</p>
        <p className="mx-auto mt-2 max-w-md text-muted">
          Only customers whose order has been delivered can leave a review — so every review here is real.
        </p>
      </Reveal>
    );
  }
  return (
    <Stagger className="columns-1 gap-5 sm:columns-2 lg:columns-3 [&>*]:mb-5">
      {reviews.map((r) => (
        <StaggerItem key={r.id} className="break-inside-avoid rounded-[var(--radius-lg)] border border-line bg-white/50 p-7">
          <div className="flex items-center justify-between">
            <Stars value={r.rating} />
            {preview ? (
              <span className="rounded-full bg-sand px-2.5 py-1 text-[0.65rem] font-semibold tracking-wider text-muted uppercase">
                Preview
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-success">
                <BadgeCheck className="size-3.5" /> Verified order
              </span>
            )}
          </div>
          <p className="font-display mt-5 text-lg leading-snug text-ink">&ldquo;{r.body}&rdquo;</p>
          <p className="mt-5 text-sm text-muted">
            {r.customer_name}
            {r.area && ` · ${r.area}`}
          </p>
          {r.reply && <p className="mt-4 border-l-2 border-gold pl-4 text-sm text-muted">Laraib: {r.reply}</p>}
        </StaggerItem>
      ))}
    </Stagger>
  );
}

/** Editorial "inside the workshop" band — the craft and the rider promise, told with real photos. */
export function CraftSection({ media }: { media: SiteMedia }) {
  return (
    <section className="py-24 md:py-32">
      <Container className="grid items-center gap-12 lg:grid-cols-[1.25fr_1fr] lg:gap-20">
        <Reveal className="relative">
          <div className="aspect-[16/11] overflow-hidden rounded-[var(--radius-lg)]">
            <MediaImage src={media["home.workshop"]?.url} alt={media["home.workshop"]?.alt || "Master tailor at the Laraib workshop"} sizes="(min-width: 1024px) 55vw, 100vw" tone={2} />
          </div>
          <div className="absolute -bottom-10 -right-4 hidden aspect-[4/3] w-[42%] overflow-hidden rounded-[var(--radius-lg)] border-[6px] border-ivory shadow-xl md:block">
            <MediaImage src={media["home.rider"]?.url} alt={media["home.rider"]?.alt || "Laraib rider with a sealed fabric bag"} sizes="25vw" tone={3} />
          </div>
        </Reveal>
        <div>
          <SectionHeading
            eyebrow="Inside the workshop"
            title={
              <>
                Cut by hand. <em className="text-wine">Checked twice.</em>
              </>
            }
            body="Every order is cut by a master tailor at our Garhi Shahu workshop, stitched by one karigar from start to finish, then pressed and checked against your measurements before it leaves."
          />
          <Stagger className="mt-10 grid grid-cols-3 gap-6 border-t border-line pt-8">
            {[
              ["1", "karigar per suit, start to finish"],
              ["2", "quality checks before dispatch"],
              ["7", "day free alteration window"],
            ].map(([n, t]) => (
              <StaggerItem key={t}>
                <p className="font-display text-5xl text-plum">{n}</p>
                <p className="mt-2 text-sm text-muted">{t}</p>
              </StaggerItem>
            ))}
          </Stagger>
        </div>
      </Container>
    </section>
  );
}

export function CtaBand() {
  return (
    <section className="px-4 pb-24 sm:px-6 lg:px-10">
      <Reveal className="grain relative mx-auto max-w-7xl overflow-hidden rounded-[28px] bg-plum px-8 py-16 text-ivory md:px-16 md:py-20">
        <div className="relative z-10 grid items-end gap-10 md:grid-cols-[1.5fr_1fr]">
          <div>
            <p className="eyebrow !text-gold-soft">Eid & wedding season fills up fast</p>
            <h2 className="mt-4 text-[clamp(2rem,4.5vw,3.6rem)] leading-[1.05]">
              Book your stitching slot <em className="text-gold-soft">before the rush.</em>
            </h2>
          </div>
          <div className="flex flex-wrap gap-3 md:justify-end">
            <ButtonLink href="/order" variant="gold" size="lg">
              Start an order
            </ButtonLink>
            <a
              href={whatsappLink("Assalam o Alaikum, I'd like to book a stitching slot.")}
              className="inline-flex h-14 items-center rounded-full border border-ivory/30 px-8 text-ivory transition-colors hover:bg-ivory hover:text-plum"
            >
              Ask on WhatsApp
            </a>
          </div>
        </div>
        <svg className="absolute -right-20 -bottom-24 size-[420px] text-ivory/[0.06]" viewBox="0 0 200 200" aria-hidden>
          <circle cx="100" cy="100" r="98" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="4 6" />
          <circle cx="100" cy="100" r="70" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="4 6" />
        </svg>
      </Reveal>
    </section>
  );
}
