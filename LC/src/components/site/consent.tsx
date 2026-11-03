"use client";
import { useEffect, useRef, useSyncExternalStore } from "react";
import Script from "next/script";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";

const KEY = "laraib-consent"; // "all" | "essential"
const EVENT = "laraib-consent-change";
const ADSENSE_CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT; // ca-pub-…

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}
function read() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return "essential";
  }
}
function save(value: "all" | "essential") {
  try {
    localStorage.setItem(KEY, value);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

export function useConsent() {
  // server snapshot "pending" keeps the banner out of the prerendered HTML
  return useSyncExternalStore(subscribe, read, () => "pending");
}

/** Cookie banner + consent-gated AdSense loader. Ads never load without "Accept all". */
export function ConsentAndAds() {
  const consent = useConsent();
  return (
    <>
      {consent === "all" && ADSENSE_CLIENT && (
        <Script
          id="adsense"
          async
          strategy="lazyOnload"
          crossOrigin="anonymous"
          src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`}
        />
      )}
      <AnimatePresence>
        {consent === null && (
          <motion.div
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 40, opacity: 0 }}
            transition={{ delay: 1.2, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            role="dialog"
            aria-label="Cookie preferences"
            className="fixed inset-x-3 bottom-3 z-[55] mx-auto max-w-xl rounded-[var(--radius-lg)] border border-line bg-ivory/95 p-5 shadow-2xl backdrop-blur sm:bottom-6"
          >
            <p className="text-sm text-ink">
              We use essential cookies to run the site and, with your permission, advertising cookies from Google.{" "}
              <Link href="/privacy" className="text-plum underline">
                Privacy policy
              </Link>
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => save("essential")} className="rounded-full px-4 py-2 text-sm text-muted hover:text-plum">
                Essential only
              </button>
              <button onClick={() => save("all")} className="rounded-full bg-plum px-5 py-2 text-sm text-ivory hover:bg-wine">
                Accept all
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/** A responsive AdSense unit. Renders nothing until ads are configured and consented. */
export function AdSlot({ slot, className }: { slot: string; className?: string }) {
  const consent = useConsent();
  const pushed = useRef(false);
  const active = consent === "all" && Boolean(ADSENSE_CLIENT) && Boolean(slot);

  useEffect(() => {
    if (!active || pushed.current) return;
    pushed.current = true;
    try {
      ((window as unknown as { adsbygoogle: unknown[] }).adsbygoogle ||= []).push({});
    } catch {}
  }, [active]);

  if (!active) return null;
  return (
    <aside className={className} aria-label="Advertisement">
      <p className="mb-1 text-center text-[0.65rem] tracking-[0.2em] text-muted uppercase">Advertisement</p>
      <ins className="adsbygoogle block" style={{ display: "block" }} data-ad-client={ADSENSE_CLIENT} data-ad-slot={slot} data-ad-format="auto" data-full-width-responsive="true" />
    </aside>
  );
}
