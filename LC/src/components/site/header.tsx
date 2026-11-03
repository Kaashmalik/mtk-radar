"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { Menu, UserRound, X } from "lucide-react";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/services", label: "Services" },
  { href: "/designs", label: "Lookbook" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/gallery", label: "Gallery" },
  { href: "/reviews", label: "Reviews" },
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Visit us" },
];

function NavLinks({ pathname }: { pathname?: string }) {
  return nav.map((item) => (
    <Link
      key={item.href}
      href={item.href}
      className={cn("link-thread pb-0.5 text-sm text-ink/80 hover:text-plum", pathname === item.href && "bg-[length:100%_1px] text-plum")}
    >
      {item.label}
    </Link>
  ));
}

function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

export function Header() {
  const [scrolled, setScrolled] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState(false);
  const { scrollY } = useScroll();

  useMotionValueEvent(scrollY, "change", (y) => {
    const prev = scrollY.getPrevious() ?? 0;
    setScrolled(y > 24);
    setHidden(y > 320 && y > prev && !open);
  });

  return (
    <>
      <motion.header
        animate={{ y: hidden ? "-110%" : 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          "fixed inset-x-0 top-0 z-50 transition-[background-color,border-color,backdrop-filter] duration-500",
          scrolled ? "border-b border-line/70 bg-ivory/85 backdrop-blur-md" : "border-b border-transparent",
        )}
      >
        <div className="mx-auto flex h-18 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-10">
          <Link href="/" className="text-plum" aria-label="Laraib Creative home">
            <Logo />
          </Link>

          <nav className="hidden items-center gap-8 lg:flex" aria-label="Main">
            {/* the active-link underline needs the URL, which streams in on dynamic routes */}
            <Suspense fallback={<NavLinks />}>
              <ActiveNavLinks />
            </Suspense>
          </nav>

          <div className="flex items-center gap-2">
            <Link href="/track" className="hidden text-sm text-ink/70 hover:text-plum sm:block">
              Track order
            </Link>
            <Link href="/account" aria-label="My account" className="hidden size-10 place-items-center rounded-full text-ink/70 hover:bg-plum/5 hover:text-plum sm:grid">
              <UserRound className="size-[18px]" strokeWidth={1.6} />
            </Link>
            <ButtonLink href="/order" size="sm" className="ml-3 hidden sm:inline-flex">
              Start an order
            </ButtonLink>
            <button
              type="button"
              className="grid size-11 place-items-center rounded-full text-plum lg:hidden"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-label={open ? "Close menu" : "Open menu"}
            >
              {open ? <X className="size-5" /> : <Menu className="size-5" />}
            </button>
          </div>
        </div>
      </motion.header>

      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-40 bg-plum text-ivory lg:hidden"
            initial={{ clipPath: "circle(0% at 92% 4%)" }}
            animate={{ clipPath: "circle(150% at 92% 4%)" }}
            exit={{ clipPath: "circle(0% at 92% 4%)" }}
            transition={{ duration: 0.7, ease: [0.65, 0, 0.35, 1] }}
          >
            <nav className="flex h-full flex-col justify-center gap-2 px-8" aria-label="Mobile">
              {[...nav, { href: "/track", label: "Track order" }, { href: "/account", label: "My account" }].map((item, i) => (
                <motion.div
                  key={item.href}
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 + i * 0.05, duration: 0.6 }}
                >
                  <Link href={item.href} onClick={() => setOpen(false)} className="font-display block py-2 text-4xl">
                    {item.label}
                  </Link>
                </motion.div>
              ))}
              <ButtonLink href="/order" variant="gold" size="lg" className="mt-8 self-start" onClick={() => setOpen(false)}>
                Start an order
              </ButtonLink>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
