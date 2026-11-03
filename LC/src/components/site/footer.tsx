import Link from "next/link";
import { Logo } from "@/components/brand/logo";
import { brand } from "@/lib/config";

const columns = [
  {
    title: "Stitching",
    links: [
      { href: "/services", label: "All services" },
      { href: "/designs", label: "Lookbook" },
      { href: "/pricing", label: "Pricing" },
      { href: "/size-guide", label: "Size & measurement guide" },
      { href: "/order", label: "Start an order" },
    ],
  },
  {
    title: "Laraib",
    links: [
      { href: "/about", label: "About us" },
      { href: "/how-it-works", label: "How it works" },
      { href: "/gallery", label: "Stitched by Laraib" },
      { href: "/reviews", label: "Reviews" },
      { href: "/journal", label: "Style Journal" },
      { href: "/tailor", label: "Areas we serve" },
    ],
  },
  {
    title: "Help",
    links: [
      { href: "/track", label: "Track your order" },
      { href: "/account", label: "My account" },
      { href: "/contact#inquiry", label: "Bridal & custom quote" },
      { href: "/contact", label: "Contact" },
      { href: "/refund-policy", label: "Refunds & alterations" },
    ],
  },
];

const popularAreas = [
  { href: "/tailor/gulberg", label: "Gulberg" },
  { href: "/tailor/dha-lahore", label: "DHA" },
  { href: "/tailor/cantt", label: "Cantt" },
  { href: "/tailor/model-town", label: "Model Town" },
  { href: "/tailor/johar-town", label: "Johar Town" },
  { href: "/tailor/bahria-town", label: "Bahria Town" },
];

const year = new Date().getFullYear();

export function Footer() {
  return (
    <footer className="grain mt-auto bg-plum text-ivory">
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-10">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <Logo light />
            <p className="font-display mt-6 max-w-sm text-2xl leading-snug text-ivory/90 italic">{brand.tagline}</p>
            <address className="mt-6 not-italic text-sm leading-relaxed text-ivory/70">
              {brand.address}
              <br />
              {brand.hours}
            </address>
          </div>
          {columns.map((col) => (
            <div key={col.title}>
              <p className="eyebrow !text-gold-soft">{col.title}</p>
              <ul className="mt-5 space-y-3 text-sm">
                {col.links.map((l) => (
                  <li key={l.href}>
                    <Link href={l.href} className="link-thread text-ivory/80 hover:text-ivory">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-12 text-xs leading-relaxed text-ivory/50">
          Ladies tailor with pickup in{" "}
          {popularAreas.map((a, i) => (
            <span key={a.href}>
              <Link href={a.href} className="hover:text-ivory">
                {a.label}
              </Link>
              {i < popularAreas.length - 1 ? " · " : ""}
            </span>
          ))}{" "}
          and across Lahore.
        </p>
        <div className="stitch-rule mt-8 opacity-40" />
        <div className="mt-6 flex flex-col justify-between gap-4 text-xs text-ivory/60 sm:flex-row">
          <p>
            © {year} Laraib Creative ·{" "}
            <Link href="/privacy" className="hover:text-ivory">Privacy</Link> ·{" "}
            <Link href="/terms" className="hover:text-ivory">Terms</Link>
          </p>
          <div className="flex gap-5">
            <a href={brand.instagram} className="hover:text-ivory">Instagram</a>
            <a href={brand.facebook} className="hover:text-ivory">Facebook</a>
            <a href={brand.tiktok} className="hover:text-ivory">TikTok</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
