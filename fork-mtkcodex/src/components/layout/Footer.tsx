import Link from 'next/link';
import { ArrowRight, Mail, MapPin, Phone } from 'lucide-react';
import { fullAddress, maps, site } from '@/data/site';
import { products } from '@/data/products';
import { services } from '@/data/services';
import { industries } from '@/data/content';
import { Logo } from '@/components/ui/primitives';
import { GithubIcon, LinkedinIcon } from '@/components/ui/BrandIcons';
import CookieSettingsButton from './CookieSettingsButton';

const columns = [
  { title: 'Products', links: products.map((p) => ({ href: `/products/${p.slug}`, label: p.name })) },
  { title: 'Services', links: services.map((s) => ({ href: `/services/${s.id}`, label: s.title })) },
  { title: 'Industries', links: industries.map((i) => ({ href: `/industries/${i.id}`, label: i.name })) },
  {
    title: 'Company',
    links: [
      { href: '/platform', label: 'Platform' },
      { href: '/about', label: 'About MTK Codex' },
      { href: '/about#founder', label: 'Leadership' },
      { href: '/customers', label: 'Customer stories' },
      { href: '/pricing', label: 'Pricing' },
      { href: '/blog', label: 'Insights & blog' },
      { href: '/careers', label: 'Careers' },
      { href: '/locations', label: 'Locations' },
      { href: '/contact', label: 'Contact' },
    ],
  },
  {
    title: 'Get started',
    links: [
      { href: '/contact?intent=demo', label: 'Book a demo' },
      { href: '/contact?service=audit', label: 'Free code audit' },
      { href: '/contact?intent=quote', label: 'Request a quote' },
      { href: '/login', label: 'Client login' },
      { href: site.social.portfolio, label: 'Founder portfolio' },
    ],
  },
];

export default function Footer() {
  return (
    <footer className="border-t border-line bg-elevated">
      <div className="container-x grid gap-x-12 gap-y-10 py-14 lg:grid-cols-[1.1fr_3fr]">
        <div>
          <Logo />
          <p className="mt-4 font-display text-lg font-semibold">{site.slogan}</p>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-fg-muted">{site.tagline}</p>
          <ul className="mt-6 space-y-3 text-sm text-fg-muted">
            <li className="flex items-center gap-3">
              <Mail className="size-4 text-brand" />
              <a href={`mailto:${site.email}`} className="hover:text-fg">{site.email}</a>
            </li>
            <li className="flex items-center gap-3">
              <Phone className="size-4 text-brand" />
              <a href={`tel:${site.phone.replace(/\s/g, '')}`} className="hover:text-fg">{site.phone}</a>
            </li>
            <li className="flex items-center gap-3">
              <MapPin className="size-4 shrink-0 text-brand" />
              <a href={maps.open} target="_blank" rel="noopener noreferrer" className="hover:text-fg">
                {fullAddress}
              </a>
            </li>
          </ul>
          <div className="mt-6 flex gap-2">
            <a href={site.social.github} target="_blank" rel="noopener noreferrer" aria-label="GitHub" className="grid size-10 place-items-center rounded-full border border-line text-fg-muted hover:border-brand hover:text-brand">
              <GithubIcon className="size-[18px]" />
            </a>
            <a href={site.social.linkedin} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn" className="grid size-10 place-items-center rounded-full border border-line text-fg-muted hover:border-brand hover:text-brand">
              <LinkedinIcon className="size-[18px]" />
            </a>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 md:grid-cols-3 xl:grid-cols-5">
          {columns.map((col) => (
            <div key={col.title}>
              <h3 className="font-sans text-sm font-semibold tracking-normal">{col.title}</h3>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l.href + l.label}>
                    <Link href={l.href} className="text-sm text-fg-muted transition hover:text-brand">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {/* Fills the empty grid cell left by the 5th column group on 2–3 column layouts. */}
          <div className="flex flex-col justify-center rounded-2xl border border-brand/30 bg-brand-soft p-5 xl:col-span-5 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <p className="font-display text-lg font-bold">Ready to scale your business?</p>
              <p className="mt-1 text-sm text-fg-muted">Book a free demo — we respond within 12 hours, worldwide.</p>
            </div>
            <Link
              href="/contact?intent=demo"
              className="mt-4 inline-flex shrink-0 items-center gap-2 self-start rounded-full bg-cta px-5 py-2.5 text-sm font-semibold text-on-cta transition hover:bg-cta-hover xl:mt-0 xl:self-auto"
            >
              Book a free demo <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </div>
      <div className="border-t border-line">
        <div className="container-x flex flex-col items-center justify-between gap-3 py-6 text-xs text-fg-subtle sm:flex-row">
          <p>© {new Date().getFullYear()} MTK Codex. All rights reserved.</p>
          <nav aria-label="Legal" className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <Link href="/privacy" className="hover:text-brand">Privacy</Link>
            <Link href="/terms" className="hover:text-brand">Terms</Link>
            <Link href="/cookies" className="hover:text-brand">Cookies</Link>
            <Link href="/disclaimer" className="hover:text-brand">Disclaimer</Link>
            <CookieSettingsButton className="hover:text-brand" />
          </nav>
        </div>
      </div>
    </footer>
  );
}
