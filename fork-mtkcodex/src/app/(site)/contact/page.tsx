import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { Suspense } from 'react';
import { Clock, Mail, MapPin, Phone } from 'lucide-react';
import { site, whatsappLink } from '@/data/site';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import ContactForm from './ContactForm';
import LocationMap from '@/components/location/LocationMap';

export const metadata: Metadata = pageMeta({
  title: 'Contact & Book a Demo',
  description: 'Book a product demo, request a fixed quote or claim a free code & security audit. MTK Codex replies within 12 hours.',
  path: '/contact',
  keywords: ['contact software company', 'book demo', 'free code audit', 'hire developers Pakistan'],
});

const channels = [
  { icon: Mail, label: 'Email', value: site.email, href: `mailto:${site.email}` },
  { icon: Phone, label: 'Phone', value: site.phone, href: `tel:${site.phone.replace(/\s/g, '')}` },
  { icon: MapPin, label: 'Office', value: site.location },
  { icon: Clock, label: 'Hours', value: site.hours },
];

export default function ContactPage() {
  return (
    <>
    <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
      <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <div className="container-x grid gap-12 py-16 sm:py-24 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <p className="eyebrow">Contact us</p>
          <h1 className="mt-4 text-4xl font-extrabold leading-[1.05] sm:text-5xl">
            Let&apos;s build something <span className="text-gradient">great together.</span>
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-fg-muted">
            Book a demo, request a fixed quote or claim your free code &amp; security audit. You&apos;ll speak directly with the engineer who
            builds your product.
          </p>
          <ul className="mt-10 space-y-4">
            {channels.map((c) => (
              <li key={c.label} className="flex items-center gap-4">
                <span className="grid size-11 place-items-center rounded-xl bg-brand-soft text-brand">
                  <c.icon className="size-5" />
                </span>
                <div>
                  <p className="text-xs text-fg-subtle">{c.label}</p>
                  {c.href ? (
                    <a href={c.href} className="font-semibold hover:text-brand">
                      {c.value}
                    </a>
                  ) : (
                    <p className="font-semibold">{c.value}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <a
            href={whatsappLink()}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-10 inline-flex items-center gap-3 rounded-2xl bg-[#25d366] px-5 py-4 font-semibold text-white transition hover:brightness-105"
          >
            <WhatsappIcon className="size-6" /> Chat instantly on WhatsApp
          </a>
        </div>
        <Suspense fallback={<div className="card h-[640px]" />}>
          <ContactForm />
        </Suspense>
      </div>
    </section>
    <LocationMap />
    </>
  );
}
