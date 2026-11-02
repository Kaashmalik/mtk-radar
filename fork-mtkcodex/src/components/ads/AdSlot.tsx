'use client';

import { useEffect, useRef } from 'react';

const CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT;

/**
 * Responsive AdSense unit. Renders nothing until NEXT_PUBLIC_ADSENSE_CLIENT and a slot id are set,
 * so the site stays ad-free (and AdSense-review friendly) until approval.
 */
export default function AdSlot({ slot = process.env.NEXT_PUBLIC_ADSENSE_SLOT, className = '' }: { slot?: string; className?: string }) {
  const pushed = useRef(false);

  useEffect(() => {
    if (!CLIENT || !slot || pushed.current) return;
    pushed.current = true;
    try {
      ((window as unknown as { adsbygoogle?: unknown[] }).adsbygoogle ||= []).push({});
    } catch {}
  }, [slot]);

  if (!CLIENT || !slot) return null;

  return (
    <aside aria-label="Advertisement" className={`my-10 ${className}`}>
      <p className="mb-1 text-center text-[10px] uppercase tracking-widest text-fg-subtle">Advertisement</p>
      <ins className="adsbygoogle block" style={{ display: 'block' }} data-ad-client={CLIENT} data-ad-slot={slot} data-ad-format="auto" data-full-width-responsive="true" />
    </aside>
  );
}
