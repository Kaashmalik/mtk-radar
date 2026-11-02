'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Sparkles, X } from 'lucide-react';

const KEY = 'mtk-announcement-dismissed-v1';

export default function AnnouncementBar() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try {
      setOpen(localStorage.getItem(KEY) !== '1');
    } catch {
      setOpen(true);
    }
  }, []);

  if (!open) return null;

  return (
    <div className="relative bg-[linear-gradient(90deg,#032d42,#075058,#1f7a3a)] text-white">
      <div className="container-x flex min-h-10 items-center justify-center gap-2 py-2 pr-10 text-center text-[13px]">
        <Sparkles className="size-4 shrink-0" aria-hidden />
        <span>
          <strong className="font-semibold">Free code & security audit</strong> for new clients this quarter.{' '}
          <Link href="/contact?service=audit" className="font-semibold underline underline-offset-2 hover:no-underline">
            Claim yours →
          </Link>
        </span>
      </div>
      <button
        type="button"
        aria-label="Dismiss announcement"
        onClick={() => {
          setOpen(false);
          try {
            localStorage.setItem(KEY, '1');
          } catch {}
        }}
        className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full hover:bg-white/15"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
