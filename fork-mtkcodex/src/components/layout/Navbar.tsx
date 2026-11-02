'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Menu, X, ArrowRight, BookOpen, Briefcase, Building2, Quote, LogIn, MapPin } from 'lucide-react';
import { products } from '@/data/products';
import { services } from '@/data/services';
import { industries } from '@/data/content';
import { Logo, Button } from '@/components/ui/primitives';
import ThemeToggle from './ThemeToggle';
import ServiceIcon from '@/components/ui/ServiceIcon';

type MenuId = 'products' | 'services' | 'industries' | 'resources' | null;

function ProductsMenu() {
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
      <div className="grid gap-1 sm:grid-cols-2">
        {products.map((p) => (
          <Link
            key={p.slug}
            href={`/products/${p.slug}`}
            className="group flex gap-3 rounded-xl p-3 transition hover:bg-muted"
          >
            <span className="mt-0.5 size-9 shrink-0 rounded-lg" style={{ background: `${p.accent}22`, boxShadow: `inset 0 0 0 1px ${p.accent}55` }}>
              <span className="m-auto mt-[13px] block size-2.5 rounded-full" style={{ background: p.accent }} />
            </span>
            <span>
              <span className="block text-sm font-semibold group-hover:text-brand">{p.name}</span>
              <span className="block text-xs text-fg-subtle">{p.cloud} · {p.category}</span>
            </span>
          </Link>
        ))}
      </div>
      <div className="rounded-2xl bg-[linear-gradient(140deg,var(--brand-soft),var(--accent-soft))] p-5">
        <p className="eyebrow">Platform</p>
        <p className="mt-2 font-display text-lg font-bold leading-snug">One team. Seven platforms. Built to scale.</p>
        <p className="mt-2 text-sm text-fg-muted">Explore live demos of every MTK Codex product.</p>
        <Link href="/products" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-brand">
          View all products <ArrowRight className="size-4" />
        </Link>
      </div>
    </div>
  );
}

function ServicesMenu() {
  return (
    <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-5">
      {services.map((s) => (
        <Link key={s.id} href={`/services/${s.id}`} className="group rounded-xl p-3 transition hover:bg-muted">
          <ServiceIcon name={s.icon} className="size-5 text-brand" />
          <span className="mt-2 block text-sm font-semibold group-hover:text-brand">{s.title}</span>
          <span className="mt-1 line-clamp-2 block text-xs text-fg-subtle">{s.summary}</span>
        </Link>
      ))}
    </div>
  );
}

function IndustriesMenu() {
  return (
    <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
      {industries.map((i) => (
        <Link key={i.id} href={`/industries/${i.id}`} className="group rounded-xl p-3 transition hover:bg-muted">
          <span className="block text-sm font-semibold group-hover:text-brand">{i.name}</span>
          <span className="mt-1 block text-xs text-fg-subtle">{i.headline}</span>
        </Link>
      ))}
    </div>
  );
}

const resources = [
  { href: '/blog', label: 'Insights & blog', text: 'Engineering notes, guides and case studies', icon: BookOpen },
  { href: '/customers', label: 'Customer stories', text: 'How clients run on MTK Codex software', icon: Quote },
  { href: '/about', label: 'Company', text: 'Our story, values and leadership', icon: Building2 },
  { href: '/careers', label: 'Careers', text: 'Join the MTK Codex talent network', icon: Briefcase },
  { href: '/locations', label: 'Locations', text: 'Lahore HQ & where we serve', icon: MapPin },
  { href: '/login', label: 'Client login', text: 'Sign in to your MTK Codex product', icon: LogIn },
];

function ResourcesMenu() {
  return (
    <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-6">
      {resources.map((r) => (
        <Link key={r.href} href={r.href} className="group rounded-xl p-3 transition hover:bg-muted">
          <r.icon className="size-5 text-brand" />
          <span className="mt-2 block text-sm font-semibold group-hover:text-brand">{r.label}</span>
          <span className="mt-1 block text-xs text-fg-subtle">{r.text}</span>
        </Link>
      ))}
    </div>
  );
}

const menus: { id: Exclude<MenuId, null>; label: string; Panel: () => React.ReactElement }[] = [
  { id: 'products', label: 'Products', Panel: ProductsMenu },
  { id: 'services', label: 'Services', Panel: ServicesMenu },
  { id: 'industries', label: 'Industries', Panel: IndustriesMenu },
  { id: 'resources', label: 'Resources', Panel: ResourcesMenu },
];

const links = [
  { href: '/platform', label: 'Platform' },
  { href: '/pricing', label: 'Pricing' },
];

export default function Navbar() {
  const [menu, setMenu] = useState<MenuId>(null);
  const [mobile, setMobile] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();
  const closeTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMenu(null);
    setMobile(false);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && (setMenu(null), setMobile(false));
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    document.body.style.overflow = mobile ? 'hidden' : '';
  }, [mobile]);

  const open = (id: MenuId) => {
    clearTimeout(closeTimer.current);
    setMenu(id);
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setMenu(null), 120);
  };

  const ActivePanel = menus.find((m) => m.id === menu)?.Panel;

  return (
    <header
      className={`sticky top-0 z-50 border-b transition-all ${
        scrolled || menu ? 'border-line bg-bg/85 backdrop-blur-xl' : 'border-transparent bg-transparent'
      }`}
      onMouseLeave={scheduleClose}
    >
      <nav className="container-x flex h-16 items-center justify-between gap-4" aria-label="Main">
        <Link href="/" aria-label="MTK Codex home">
          <Logo />
        </Link>

        <ul className="hidden items-center gap-1 lg:flex">
          {menus.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                aria-expanded={menu === m.id}
                onMouseEnter={() => open(m.id)}
                onClick={() => setMenu(menu === m.id ? null : m.id)}
                className={`flex items-center gap-1 rounded-full px-3.5 py-2 text-sm font-medium transition ${
                  menu === m.id ? 'bg-muted text-fg' : 'text-fg-muted hover:text-fg'
                }`}
              >
                {m.label}
                <ChevronDown className={`size-4 transition-transform ${menu === m.id ? 'rotate-180' : ''}`} />
              </button>
            </li>
          ))}
          {links.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                onMouseEnter={() => open(null)}
                className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                  pathname === l.href ? 'text-fg' : 'text-fg-muted hover:text-fg'
                }`}
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login" className="hidden items-center gap-1.5 px-3 text-sm font-semibold text-fg-muted hover:text-fg xl:flex">
            <LogIn className="size-4" /> Log in
          </Link>
          <Link href="/contact" className="hidden px-3 text-sm font-semibold text-fg-muted hover:text-fg md:block">
            Contact
          </Link>
          <span className="hidden sm:block">
            <Button href="/contact?intent=demo">Book a demo</Button>
          </span>
          <button
            type="button"
            className="grid size-10 place-items-center rounded-full border border-line lg:hidden"
            aria-label={mobile ? 'Close menu' : 'Open menu'}
            aria-expanded={mobile}
            onClick={() => setMobile(!mobile)}
          >
            {mobile ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </nav>

      {/* Desktop mega menu */}
      {ActivePanel && (
        <div
          className="absolute inset-x-0 top-full hidden border-b border-line bg-elevated shadow-float lg:block"
          onMouseEnter={() => open(menu)}
        >
          <div className="container-x py-8">
            <ActivePanel />
          </div>
        </div>
      )}

      {/* Mobile drawer */}
      {mobile && (
        <div className="fixed inset-x-0 bottom-0 top-16 z-40 overflow-y-auto border-t border-line bg-bg lg:hidden">
          <div className="container-x space-y-2 py-6">
            {menus.map((m) => (
              <details key={m.id} className="group rounded-2xl border border-line bg-elevated">
                <summary className="flex cursor-pointer list-none items-center justify-between p-4 font-semibold">
                  {m.label}
                  <ChevronDown className="size-5 transition-transform group-open:rotate-180" />
                </summary>
                <div className="border-t border-line p-2">
                  <m.Panel />
                </div>
              </details>
            ))}
            {[...links, { href: '/contact', label: 'Contact' }, { href: '/login', label: 'Log in' }].map((l) => (
              <Link key={l.href} href={l.href} className="block rounded-2xl border border-line bg-elevated p-4 font-semibold">
                {l.label}
              </Link>
            ))}
            <Button href="/contact?intent=demo" size="lg" className="mt-4 w-full" arrow>
              Book a demo
            </Button>
          </div>
        </div>
      )}
    </header>
  );
}
