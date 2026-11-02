'use client';

import { useEffect, useState } from 'react';
import { Clock, Mail, MapPin, Navigation, Phone, Star } from 'lucide-react';
import { fullAddress, maps, site, whatsappLink } from '@/data/site';
import { SectionHeading } from '@/components/ui/primitives';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import GlobalReach, { useOfficeStatus } from './GlobalReach';

/** "Find us" block: live Google Map, NAP details, live office status and global reach. */
export default function LocationMap({ heading = true }: { heading?: boolean }) {
  const { time, open } = useOfficeStatus();
  const [mapLoaded, setMapLoaded] = useState(false);
  // Mount the iframe after hydration so its onLoad can never fire before React is listening.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  return (
    <section id="location" className="container-x scroll-mt-24 py-20">
      {heading && (
        <SectionHeading
          eyebrow="Find us"
          title={
            <>
              Lahore HQ. <span className="text-gradient">Clients worldwide.</span>
            </>
          }
          text="Meet us in Lahore or work with us remotely from anywhere — with real overlap across Pakistan, the Gulf, Europe and North America."
        />
      )}

      <div className={`${heading ? 'mt-12' : ''} grid gap-6 lg:grid-cols-[1.4fr_1fr]`}>
        <div className="card relative min-h-[380px] overflow-hidden">
          {/* Drawn placeholder: shown while Google Maps loads, or if it is blocked. */}
          <svg viewBox="0 0 600 400" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden>
            <rect width="600" height="400" fill="var(--bg-muted)" />
            <g stroke="var(--border-strong)" strokeWidth="10" fill="none" strokeLinecap="round">
              <path d="M-20 120 Q200 90 320 170 T640 210" />
              <path d="M120 -20 Q160 200 110 420" />
              <path d="M420 -20 Q380 160 470 420" />
            </g>
            <g stroke="var(--border)" strokeWidth="4" fill="none">
              <path d="M-20 300 L640 260" />
              <path d="M260 -20 L300 420" />
              <path d="M0 40 L600 70" />
            </g>
            <path d="M-20 350 Q150 300 260 340 T640 300" stroke="#38bdf8" strokeOpacity="0.45" strokeWidth="16" fill="none" />
            <text x="300" y="248" textAnchor="middle" fontSize="16" fontWeight="700" fill="var(--fg-muted)">
              Lahore, Pakistan
            </text>
          </svg>
          <MapPin className="absolute left-1/2 top-1/2 size-10 -translate-x-1/2 -translate-y-full fill-cta text-on-cta" aria-hidden />
          {mounted && (
          <iframe
            onLoad={() => setMapLoaded(true)}
            title={`${site.name} location on Google Maps — ${fullAddress}`}
            src={maps.embed}
            className={`absolute inset-0 h-full w-full border-0 transition-opacity duration-700 [filter:saturate(0.9)] dark:[filter:invert(0.9)_hue-rotate(180deg)_saturate(0.7)] ${mapLoaded ? 'opacity-100' : 'opacity-0'}`}
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
            allowFullScreen
          />
          )}
          <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-2 rounded-full bg-elevated/95 px-3 py-1.5 text-xs font-semibold shadow-card backdrop-blur">
            <span className="pulse-dot size-2 rounded-full bg-cta text-cta" /> {site.name} · {site.address.city}
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <address className="card not-italic p-6">
            <div className="flex items-center justify-between gap-3">
              <p className="font-display text-lg font-bold">{site.name}</p>
              {open !== null && (
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                    open ? 'bg-accent-soft text-accent' : 'bg-muted text-fg-muted'
                  }`}
                >
                  <span className={`size-1.5 rounded-full ${open ? 'pulse-dot bg-accent text-accent' : 'bg-fg-subtle'}`} />
                  {open ? 'Open now' : 'Closed now'}
                </span>
              )}
            </div>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="flex gap-3">
                <MapPin className="mt-0.5 size-4 shrink-0 text-brand" /> {fullAddress}
              </li>
              <li className="flex gap-3">
                <Clock className="mt-0.5 size-4 shrink-0 text-brand" />
                <span>
                  {site.openingHours.label}
                  <span className="block text-xs text-fg-subtle tabular-nums">Local time in Lahore: {time}</span>
                </span>
              </li>
              <li className="flex gap-3">
                <Phone className="mt-0.5 size-4 shrink-0 text-brand" />
                <a href={`tel:${site.phone.replace(/\s/g, '')}`} className="hover:text-brand">
                  {site.phone}
                </a>
              </li>
              <li className="flex gap-3">
                <Mail className="mt-0.5 size-4 shrink-0 text-brand" />
                <a href={`mailto:${site.email}`} className="hover:text-brand">
                  {site.email}
                </a>
              </li>
            </ul>
            <div className="mt-5 flex flex-wrap gap-2">
              <a href={maps.directions} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full bg-cta px-4 text-sm font-semibold text-on-cta hover:bg-cta-hover">
                <Navigation className="size-4" /> Get directions
              </a>
              <a href={maps.open} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm font-semibold hover:border-brand hover:text-brand">
                <MapPin className="size-4" /> Open in Google Maps
              </a>
              <a href={whatsappLink()} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm font-semibold hover:border-brand hover:text-brand">
                <WhatsappIcon className="size-4 text-[#25d366]" /> WhatsApp
              </a>
              {site.googleReviewUrl && (
                <a href={site.googleReviewUrl} target="_blank" rel="noopener noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm font-semibold hover:border-brand hover:text-brand">
                  <Star className="size-4 text-amber-500" /> Review us on Google
                </a>
              )}
            </div>
          </address>

          <div className="night grid flex-1 items-center gap-4 rounded-[20px] p-6 sm:grid-cols-[150px_1fr]">
            <GlobalReach />
            <div>
              <p className="font-display text-lg font-bold">Serving clients in</p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {site.serviceAreas.map((a) => (
                  <li key={a.code} className="flex items-center justify-between gap-3">
                    <span className="text-white/90">{a.name}</span>
                    <span className="text-xs text-white/50">{a.note}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
