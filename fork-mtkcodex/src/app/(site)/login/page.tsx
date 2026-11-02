import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowUpRight, KeyRound, LifeBuoy, LogIn } from 'lucide-react';
import { products } from '@/data/products';
import { site, whatsappLink } from '@/data/site';
import { Logo, StatusBadge } from '@/components/ui/primitives';
import { Aurora } from '@/components/motion/Effects';

export const metadata: Metadata = {
  title: 'Log in',
  description: 'Sign in to your MTK Codex product.',
  robots: { index: false },
};

/**
 * Product chooser: each MTK Codex product has its own sign-in, so this page routes
 * clients to the right one instead of collecting credentials here.
 */
export default function LoginPage() {
  return (
    <section className="relative isolate min-h-[80vh] overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
      <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <Aurora />
      <div className="container-x max-w-4xl py-16 sm:py-20">
        <div className="text-center">
          <Logo className="justify-center" />
          <h1 className="mt-8 text-3xl font-extrabold sm:text-5xl">Log in to your product</h1>
          <p className="mx-auto mt-4 max-w-xl text-fg-muted">
            Each MTK Codex platform has its own secure sign-in. Choose the product your organisation uses.
          </p>
        </div>

        <ul className="mt-12 grid gap-3 sm:grid-cols-2">
          {products.map((p) => {
            const live = !!p.liveUrl;
            const href = live ? p.liveUrl! : `/contact?intent=demo&product=${p.slug}`;
            const inner = (
              <>
                <span className="grid size-11 shrink-0 place-items-center rounded-xl" style={{ background: `${p.accent}1f`, color: p.accent }}>
                  {live ? <LogIn className="size-5" /> : <KeyRound className="size-5" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-semibold group-hover:text-brand">{p.name}</span>
                    <StatusBadge status={p.status} />
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-fg-subtle">{live ? `Sign in at ${new URL(p.liveUrl!).host}` : 'Access by invitation — request it here'}</span>
                </span>
                <ArrowUpRight className="size-4 shrink-0 text-fg-subtle transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-brand" />
              </>
            );
            const cls = 'card spotlight group flex items-center gap-4 p-4 transition hover:-translate-y-0.5 hover:border-brand';
            return (
              <li key={p.slug}>
                {live ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
                    {inner}
                  </a>
                ) : (
                  <Link href={href} className={cls}>
                    {inner}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>

        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          <div className="card p-6">
            <h2 className="font-sans text-base font-semibold tracking-normal">Custom project client?</h2>
            <p className="mt-1 text-sm text-fg-muted">Use the preview link and credentials shared in your project kickoff email.</p>
          </div>
          <div className="card flex items-start gap-3 p-6">
            <LifeBuoy className="mt-0.5 size-5 shrink-0 text-accent" />
            <div>
              <h2 className="font-sans text-base font-semibold tracking-normal">Trouble signing in?</h2>
              <p className="mt-1 text-sm text-fg-muted">
                Email{' '}
                <a className="font-medium text-brand" href={`mailto:${site.email}`}>
                  {site.email}
                </a>{' '}
                or{' '}
                <a className="font-medium text-brand" href={whatsappLink('Hello MTK Codex, I need help signing in to my product account.')} target="_blank" rel="noopener noreferrer">
                  message us on WhatsApp
                </a>
                .
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
