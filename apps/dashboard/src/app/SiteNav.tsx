"use client";

/** App shell nav — active-route state needs the URL, so this is a client island. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { clientFetch } from "@/lib/api-client";
import { getReviewerName } from "@/lib/identity";

import IdentityBadge from "./IdentityBadge";

const LINKS: [string, string][] = [
  ["/", "Inbox"],
  ["/review", "Review desk"],
  ["/calendar", "Calendar"],
  ["/analytics", "Analytics"],
];

function HealthDot() {
  const [up, setUp] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const res = await clientFetch("/health", { signal: AbortSignal.timeout(4000) });
        if (alive) setUp(res.ok);
      } catch {
        if (alive) setUp(false);
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <span
      role="status"
      aria-label={up === null ? "API status unknown" : up ? "API online" : "API unreachable"}
      title={up === null ? "API status unknown" : up ? "API online" : "API unreachable"}
      style={{
        width: 9,
        height: 9,
        borderRadius: "50%",
        background: up === null ? "var(--text-muted)" : up ? "var(--ok)" : "var(--danger)",
        boxShadow: `0 0 0 3px color-mix(in srgb, currentColor 15%, transparent)`,
        flexShrink: 0,
      }}
    />
  );
}

export default function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <Link href="/" className="brand">
        <span className="brand-mark" aria-hidden="true" />
        MTK&nbsp;RADAR
      </Link>
      <nav aria-label="Primary">
        <div className="site-nav">
          {LINKS.map(([href, label]) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined}>
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
      <div className="nav-spacer" />
      <IdentityBadge />
      <HealthDot />
    </header>
  );
}
