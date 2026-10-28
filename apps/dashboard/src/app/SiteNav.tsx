"use client";

/** App shell sidebar — routes grouped by the pipeline stage they serve
 * (discover → produce → publish → system). Active-route state needs the
 * URL, so this is a client island. Below 900px it collapses to a drawer. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { clientFetch } from "@/lib/api-client";

import IdentityBadge from "./IdentityBadge";
import ThemeToggle from "./ThemeToggle";

type IconName =
  | "home" | "inbox" | "radar" | "check" | "list" | "alert" | "film"
  | "calendar" | "chart" | "database" | "plug" | "gear";

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
      ["/review", "Review", "check"],
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

const PATHS: Record<IconName, string> = {
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  inbox: "M3 13h5l1.5 3h5L16 13h5M5 5h14l2 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-6z",
  radar: "M12 12l6-6M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5",
  check: "M9 12l2 2 4-4M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z",
  list: "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  alert: "M12 9v4M12 17h.01M10.3 3.9L2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  film: "M4 4h16v16H4zM8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  plug: "M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
};

function NavIcon({ name }: { name: IconName }) {
  return (
    <svg
      className="nav-icon"
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

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
          <span className="brand-mark" aria-hidden="true" />
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
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <path d={open ? "M6 6l12 12M18 6L6 18" : "M4 7h16M4 12h16M4 17h16"} />
          </svg>
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
                    <NavIcon name={icon} />
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
