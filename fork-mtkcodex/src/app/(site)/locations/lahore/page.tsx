import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { fullAddress, maps, site } from '@/data/site';
import { products } from '@/data/products';
import { services } from '@/data/services';
import { breadcrumbs, JsonLd, ORG_ID, absoluteUrl, pageMeta } from '@/lib/seo';
import PageHeader from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/primitives';
import ServiceIcon from '@/components/ui/ServiceIcon';
import LocationMap from '@/components/location/LocationMap';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Software House in Lahore — SaaS, Web & App Development',
  description:
    'MTK Codex is a Lahore software house building SaaS platforms, custom web and mobile apps, CRMs, web scraping and business automation for Pakistani and international businesses.',
  path: '/locations/lahore',
  keywords: ['software house in Lahore', 'software company Lahore', 'SaaS development Lahore', 'web development Lahore', 'app development Lahore', 'IT company Lahore', 'MTK Codex Lahore'],
});

const localFaqs = [
  {
    q: 'Can I meet the MTK Codex team in Lahore?',
    a: 'Yes. Clients in Lahore can book an in-person meeting during office hours; everyone else meets us on video calls. Message us on WhatsApp to arrange a time.',
  },
  {
    q: 'Do you support Pakistani payment gateways?',
    a: 'Yes — JazzCash, EasyPaisa, XPay, bank transfer and cash-on-delivery workflows, alongside Stripe for international payments.',
  },
  {
    q: 'Do you build bilingual English/Urdu software?',
    a: 'Yes. Our platforms support English and Urdu (right-to-left) interfaces, which MTK Dairy already uses in production.',
  },
  {
    q: 'Which Lahore businesses do you work with?',
    a: 'Retailers, installment businesses, schools, farms, fashion brands and sports organisers — plus startups and agencies that need a reliable engineering partner.',
  },
];

export default function LahorePage() {
  return (
    <>
      <JsonLd
        data={[
          breadcrumbs([
            { name: 'Locations', path: '/locations' },
            { name: 'Lahore', path: '/locations/lahore' },
          ]),
          {
            '@context': 'https://schema.org',
            '@type': 'ProfessionalService',
            '@id': absoluteUrl('/locations/lahore#place'),
            name: `${site.name} — Lahore`,
            parentOrganization: { '@id': ORG_ID },
            url: absoluteUrl('/locations/lahore'),
            telephone: site.phone,
            email: site.email,
            image: absoluteUrl('/opengraph-image'),
            priceRange: '$$',
            address: {
              '@type': 'PostalAddress',
              ...(site.address.street ? { streetAddress: site.address.street } : {}),
              addressLocality: site.address.city,
              addressRegion: site.address.region,
              postalCode: site.address.postalCode,
              addressCountry: site.address.countryCode,
            },
            geo: { '@type': 'GeoCoordinates', latitude: site.geo.lat, longitude: site.geo.lng },
            hasMap: maps.open,
            openingHoursSpecification: [{ '@type': 'OpeningHoursSpecification', dayOfWeek: site.openingHours.days, opens: site.openingHours.opens, closes: site.openingHours.closes }],
            areaServed: [{ '@type': 'City', name: 'Lahore' }, { '@type': 'Country', name: 'Pakistan' }],
          },
          {
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            mainEntity: localFaqs.map((f) => ({ '@type': 'Question', name: f.q, acceptedAnswer: { '@type': 'Answer', text: f.a } })),
          },
        ]}
      />

      <PageHeader
        eyebrow="Lahore, Pakistan"
        title={
          <>
            A software house in Lahore, <span className="text-gradient">built for scale.</span>
          </>
        }
        text={`${site.name} designs, builds and runs SaaS platforms, custom software and automations from Lahore — for local businesses and clients worldwide.`}
      >
        <Button href="/contact?intent=call" size="lg" arrow>
          Meet us in Lahore
        </Button>
        <Button href={maps.directions} external size="lg" variant="secondary">
          Get directions
        </Button>
      </PageHeader>

      <LocationMap heading={false} />

      <section className="container-x grid gap-10 pb-20 lg:grid-cols-2">
        <div>
          <h2 className="text-3xl font-bold">Why Lahore businesses choose MTK Codex</h2>
          <ul className="mt-6 space-y-3">
            {[
              'Production SaaS built and run from Lahore — MTK Dairy, InstalEase, LaraibCreative and more',
              'Local payments: JazzCash, EasyPaisa, XPay, COD and bank-slip verification',
              'English + Urdu (RTL) interfaces and WhatsApp-first automation',
              'Fixed quotes, weekly demos and 100% source-code ownership',
              'Same engineering standards we deliver to international clients',
            ].map((t) => (
              <li key={t} className="flex gap-3">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-accent" /> <span className="text-fg-muted">{t}</span>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-sm text-fg-subtle">Address: {fullAddress}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {services.slice(0, 8).map((s) => (
            <Link key={s.id} href={`/services/${s.id}`} className="card spotlight group flex items-center gap-3 p-4 transition hover:border-brand">
              <ServiceIcon name={s.icon} className="size-5 shrink-0 text-brand" />
              <span className="text-sm font-semibold group-hover:text-brand">{s.title}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="container-x pb-20">
        <h2 className="text-3xl font-bold">SaaS projects built in Lahore</h2>
        <div className="mt-6 flex flex-wrap gap-3">
          {products.map((p) => (
            <Link key={p.slug} href={`/products/${p.slug}`} className="inline-flex items-center gap-2 rounded-full border border-line bg-elevated px-4 py-2 text-sm font-semibold transition hover:border-brand hover:text-brand">
              <span className="size-2 rounded-full" style={{ background: p.accent }} /> {p.name} <ArrowRight className="size-3.5" />
            </Link>
          ))}
        </div>
      </section>

      <section className="container-x pb-20">
        <h2 className="text-3xl font-bold">Lahore FAQs</h2>
        <div className="mt-6 divide-y divide-line rounded-[20px] border border-line bg-elevated">
          {localFaqs.map((f) => (
            <details key={f.q} className="group p-6">
              <summary className="cursor-pointer list-none font-semibold">{f.q}</summary>
              <p className="mt-3 text-fg-muted">{f.a}</p>
            </details>
          ))}
        </div>
      </section>

      <CtaBand title="Let's build something great in Lahore." />
    </>
  );
}
