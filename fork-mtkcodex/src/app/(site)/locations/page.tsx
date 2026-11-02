import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Globe2, MapPin } from 'lucide-react';
import { fullAddress, site } from '@/data/site';
import { breadcrumbs, JsonLd, pageMeta } from '@/lib/seo';
import PageHeader from '@/components/ui/PageHeader';
import LocationMap from '@/components/location/LocationMap';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Locations',
  description: `${site.name} is headquartered in Lahore, Pakistan and serves clients across Pakistan, the UAE, Saudi Arabia, the UK, Europe and North America.`,
  path: '/locations',
  keywords: ['MTK Codex location', 'MTK Codex address', 'software company Pakistan', 'remote software development team'],
});

export default function LocationsPage() {
  return (
    <>
      <JsonLd data={breadcrumbs([{ name: 'Locations', path: '/locations' }])} />
      <PageHeader
        eyebrow="Locations"
        title={
          <>
            Where to <span className="text-gradient">find us.</span>
          </>
        }
        text="One headquarters, clients on four continents. Visit us in Lahore or work with us remotely — your time zone is covered."
      />

      <section className="container-x grid gap-5 pt-20 md:grid-cols-2">
        <Link href="/locations/lahore" className="card spotlight group p-7 transition hover:-translate-y-1 hover:border-brand">
          <MapPin className="size-6 text-brand" />
          <h2 className="mt-4 text-2xl font-bold group-hover:text-brand">Lahore, Pakistan · Headquarters</h2>
          <p className="mt-2 text-fg-muted">{fullAddress}</p>
          <p className="mt-1 text-sm text-fg-subtle">{site.openingHours.label}</p>
          <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-brand">
            Lahore office details <ArrowRight className="size-4" />
          </span>
        </Link>
        <div className="card p-7">
          <Globe2 className="size-6 text-brand" />
          <h2 className="mt-4 text-2xl font-bold">Remote, worldwide</h2>
          <ul className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            {site.serviceAreas.map((a) => (
              <li key={a.code} className="rounded-xl bg-muted px-3 py-2">
                <span className="font-semibold">{a.name}</span>
                <span className="block text-xs text-fg-subtle">{a.note}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <LocationMap />
      <CtaBand />
    </>
  );
}
