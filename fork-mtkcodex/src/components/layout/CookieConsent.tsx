'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Cookie, X } from 'lucide-react';
import { OPEN_SETTINGS_EVENT, applyConsent, readConsent, writeConsent } from '@/lib/consent';

function Toggle({ checked, onChange, disabled, label }: { checked: boolean; onChange?: (v: boolean) => void; disabled?: boolean; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? 'bg-cta' : 'bg-line-strong'} ${disabled ? 'opacity-60' : ''}`}
    >
      <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`} />
    </button>
  );
}

/** GDPR-style consent banner. Choice is stored in a first-party cookie and sent to Google Consent Mode. */
export default function CookieConsent() {
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [ads, setAds] = useState(false);

  useEffect(() => {
    const saved = readConsent();
    if (saved) {
      applyConsent(saved);
      setAnalytics(saved.analytics);
      setAds(saved.ads);
    } else {
      setOpen(true);
    }
    const reopen = () => {
      const c = readConsent();
      setAnalytics(!!c?.analytics);
      setAds(!!c?.ads);
      setDetails(true);
      setOpen(true);
    };
    window.addEventListener(OPEN_SETTINGS_EVENT, reopen);
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, reopen);
  }, []);

  const save = (c: { analytics: boolean; ads: boolean }) => {
    writeConsent(c);
    setOpen(false);
    setDetails(false);
  };

  if (!open) return null;

  return (
    <div role="dialog" aria-modal="false" aria-labelledby="cookie-title" className="fixed inset-x-3 bottom-3 z-[70] sm:inset-x-auto sm:bottom-5 sm:left-5 sm:max-w-md">
      <div className="card word-in p-5 shadow-float">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
            <Cookie className="size-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="cookie-title" className="font-sans text-base font-semibold tracking-normal">
              We value your privacy
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-fg-muted">
              We use essential cookies to run this site and, with your permission, analytics and advertising cookies to improve it and show relevant ads.
              Read our{' '}
              <Link href="/cookies" className="font-medium text-brand underline-offset-2 hover:underline">
                Cookie Policy
              </Link>
              .
            </p>
          </div>
          <button type="button" aria-label="Reject non-essential cookies and close" onClick={() => save({ analytics: false, ads: false })} className="text-fg-subtle hover:text-fg">
            <X className="size-4" />
          </button>
        </div>

        {details && (
          <ul className="mt-4 space-y-3 rounded-xl bg-muted p-4 text-sm">
            <li className="flex items-center justify-between gap-3">
              <span>
                <strong className="font-semibold">Essential</strong>
                <span className="block text-xs text-fg-subtle">Theme, security and your consent choice. Always on.</span>
              </span>
              <Toggle checked disabled label="Essential cookies" />
            </li>
            <li className="flex items-center justify-between gap-3">
              <span>
                <strong className="font-semibold">Analytics</strong>
                <span className="block text-xs text-fg-subtle">Anonymous usage stats (Google Analytics).</span>
              </span>
              <Toggle checked={analytics} onChange={setAnalytics} label="Analytics cookies" />
            </li>
            <li className="flex items-center justify-between gap-3">
              <span>
                <strong className="font-semibold">Advertising</strong>
                <span className="block text-xs text-fg-subtle">Personalised ads (Google AdSense).</span>
              </span>
              <Toggle checked={ads} onChange={setAds} label="Advertising cookies" />
            </li>
          </ul>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={() => save({ analytics: true, ads: true })} className="h-10 flex-1 rounded-full bg-cta px-4 text-sm font-semibold text-on-cta hover:bg-cta-hover">
            Accept all
          </button>
          <button type="button" onClick={() => save({ analytics: false, ads: false })} className="h-10 flex-1 rounded-full border border-line-strong px-4 text-sm font-semibold hover:border-brand hover:text-brand">
            Reject non-essential
          </button>
          {details ? (
            <button type="button" onClick={() => save({ analytics, ads })} className="h-10 w-full rounded-full px-4 text-sm font-semibold text-brand hover:bg-brand-soft">
              Save my choices
            </button>
          ) : (
            <button type="button" onClick={() => setDetails(true)} className="h-10 w-full rounded-full px-4 text-sm font-semibold text-brand hover:bg-brand-soft">
              Customise
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
