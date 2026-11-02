'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { readConsent } from '@/lib/consent';

/**
 * Sends one page view per navigation, plus a heartbeat while the tab stays open
 * so "live now" reflects people actually reading. Cookieless: no storage on the
 * visitor's device. Honours an explicit "analytics off" choice, Do Not Track and
 * Global Privacy Control.
 */

const DEBUG = process.env.NEXT_PUBLIC_ANALYTICS_DEBUG === '1';

function allowed(): boolean {
  if (typeof window === 'undefined') return false;
  if (!DEBUG && ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)) return false;
  const consent = readConsent();
  if (consent && consent.analytics === false) return false;
  const nav = navigator as Navigator & { globalPrivacyControl?: boolean };
  if (navigator.doNotTrack === '1' || nav.globalPrivacyControl) return false;
  return true;
}

function send(path: string, kind: 'view' | 'ping') {
  void fetch('/api/track', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, kind, referrer: kind === 'view' ? document.referrer : '' }),
    keepalive: true,
  }).catch(() => {
    // Analytics must never affect the page.
  });
}

export default function AnalyticsBeacon() {
  const pathname = usePathname();

  useEffect(() => {
    if (!allowed()) return;
    send(pathname, 'view');

    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') send(pathname, 'ping');
    }, 60_000);

    const onVisible = () => {
      if (document.visibilityState === 'visible') send(pathname, 'ping');
    };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [pathname]);

  return null;
}
