"use client";

/** App shell sidebar — routes grouped by the pipeline stage they serve
 * (discover → produce → publish → system). Active-route state needs the
 * URL, so this is a client island. Below 900px it collapses to a drawer. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { clientFetch } from "@/lib/api-client";

import Icon, { BrandMark, type IconName } from "./Icon";
import IdentityBadge from "./IdentityBadge";
import ThemeToggle from "./ThemeToggle";

const GROUPS: { label: string; links: [string, string, IconName][] }[] = [
  {
    label: "Discover",
    links: [
      ["/", "Overview", "home"],
      ["/inbox", "Inbox", "inbox"],
      ["/radar", "Radar", "radar"],
    ],
  },
  {
    label: "Produce",
    links: [
      ["/review", "Review", "check-circle"],
      ["/queue", "Queue", "list"],
      ["/attention", "Needs You", "alert"],
      ["/studio", "Studio", "film"],
    ],
  },
  {
    label: "Publish",
    links: [
      ["/calendar", "Calendar", "calendar"],
      ["/analytics", "Growth", "chart"],
    ],
  },
  {
    label: "System",
    links: [
      ["/sources", "Sources", "database"],
      ["/connections", "Connections", "plug"],
      ["/settings", "Settings", "gear"],
    ],
  },
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

  const label = up === null ? "API status unknown" : up ? "API online" : "API unreachable";
  const state = up === null ? "unknown" : up ? "up" : "down";
  return (
    <span className="health" data-state={state}>
      <span className="health-dot" role="status" aria-label={label} title={label} />
      <span className="health-label">{up === null ? "Checking…" : up ? "API online" : "API offline"}</span>
    </span>
  );
}

export default function SiteNav({ actor }: { actor: string }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the mobile drawer after navigating.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className="site-header" data-open={open || undefined}>
      <div className="sidebar-top">
        <Link href="/" className="brand">
          <BrandMark />
          MTK&nbsp;RADAR
        </Link>
        <button
          type="button"
          className="icon-btn menu-btn"
          aria-expanded={open}
          aria-controls="primary-nav"
          aria-label={open ? "Close navigation" : "Open navigation"}
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name="menu" size={18} strokeWidth={1.8} />
        </button>
      </div>

      <nav aria-label="Primary" id="primary-nav" className="sidebar-nav">
        <div className="site-nav">
          {GROUPS.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-group-label">{group.label}</p>
              {group.links.map(([href, label, icon]) => {
                const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
                return (
                  <Link key={href} href={href} aria-current={active ? "page" : undefined}>
                    <Icon name={icon} size={17} strokeWidth={1.8} className="nav-icon" />
                    <span>{label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </div>
      </nav>

      <div className="sidebar-foot">
        <HealthDot />
        <div className="sidebar-foot-row">
          <IdentityBadge actor={actor} />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
