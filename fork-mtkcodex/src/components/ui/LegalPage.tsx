import Link from 'next/link';
import { site } from '@/data/site';

export const LEGAL_UPDATED = 'October 31, 2026';

const legalLinks = [
  { href: '/privacy', label: 'Privacy Policy' },
  { href: '/terms', label: 'Terms of Service' },
  { href: '/cookies', label: 'Cookie Policy' },
  { href: '/disclaimer', label: 'Disclaimer' },
];

export default function LegalPage({ title, intro, children, current }: { title: string; intro: string; children: React.ReactNode; current: string }) {
  return (
    <section className="container-x grid gap-10 py-16 lg:grid-cols-[220px_1fr]">
      <nav aria-label="Legal" className="lg:sticky lg:top-24 lg:self-start">
        <p className="eyebrow">Legal</p>
        <ul className="mt-4 flex flex-wrap gap-2 lg:flex-col lg:gap-1">
          {legalLinks.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                aria-current={current === l.href ? 'page' : undefined}
                className={`block rounded-lg px-3 py-2 text-sm font-medium transition ${current === l.href ? 'bg-brand-soft text-brand' : 'text-fg-muted hover:bg-muted hover:text-fg'}`}
              >
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <article className="max-w-3xl">
        <h1 className="text-4xl font-extrabold sm:text-5xl">{title}</h1>
        <p className="mt-3 text-sm text-fg-subtle">Last updated: {LEGAL_UPDATED}</p>
        <p className="mt-6 text-lg leading-relaxed text-fg-muted">{intro}</p>
        <div className="prose-mtk mt-6">{children}</div>
        <div className="mt-12 rounded-2xl border border-line bg-muted p-6 text-sm text-fg-muted">
          Questions about this policy? Contact {site.name} at{' '}
          <a className="font-medium text-brand" href={`mailto:${site.email}`}>
            {site.email}
          </a>{' '}
          or {site.phone}. {site.location}.
        </div>
      </article>
    </section>
  );
}
