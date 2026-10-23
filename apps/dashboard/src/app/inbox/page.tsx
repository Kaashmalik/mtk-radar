/**
 * Inbox (plan §6 P0) — the full review queue, not just the overview preview.
 *
 * Three things this page adds over the home-page card:
 * - search (`q`): the API matches title and URL;
 * - filter tabs: unprocessed / processed / all;
 * - keyset pagination ("Older items"): the cursor header is opaque — a link,
 *   not state, so the inbox tail is reachable without JavaScript.
 */

import "../styles.css";
import Link from "next/link";

import { InboxActions } from "../InboxActions";
import { apiFetch } from "@/lib/api";

export const dynamic = "force-dynamic";

type ItemRow = {
  id: string;
  url: string;
  canonical_url: string | null;
  title: string | null;
  observed_at: string;
  published_at: string | null;
  duplicate_group: string | null;
  processed: boolean;
  source_provider: string | null;
  source_category: string | null;
  trust_tier: string | null;
};

const FILTERS: [string, string][] = [
  ["unprocessed", "Unprocessed"],
  ["processed", "Processed"],
  ["all", "All"],
];

function filterParam(filter: string): string | null {
  if (filter === "processed") return "true";
  if (filter === "all") return null;
  return "false";
}

async function getInbox(q: string | undefined, filter: string, cursor: string | undefined) {
  const params = new URLSearchParams({ limit: "50" });
  const processed = filterParam(filter);
  if (processed) params.set("processed", processed);
  if (q) params.set("q", q);
  if (cursor) params.set("cursor", cursor);
  try {
    const res = await apiFetch(`/items?${params.toString()}`, { cache: "no-store" });
    if (!res.ok) return { items: null, next: null as string | null };
    const next = res.headers.get("X-Next-Cursor");
    return { items: (await res.json()) as ItemRow[], next };
  } catch {
    return { items: null, next: null };
  }
}

function buildHref(q: string | undefined, filter: string, cursor?: string | null): string {
  const params = new URLSearchParams();
  params.set("filter", filter);
  if (q) params.set("q", q);
  if (cursor) params.set("cursor", cursor);
  return `/inbox?${params.toString()}`;
}

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const first = (key: string): string | undefined => {
    const value = sp[key];
    return Array.isArray(value) ? value[0] : value;
  };
  const q = first("q")?.slice(0, 200);
  const filter = FILTERS.some(([f]) => f === first("filter")) ? first("filter")! : "unprocessed";
  const cursor = first("cursor");

  const { items, next } = await getInbox(q, filter, cursor);

  return (
    <main className="page">
      <section className="panel">
        <div className="panel-head">
          <div>
            <span className="eyebrow">Review queue</span>
            <h2 style={{ marginTop: "0.45rem" }}>Inbox</h2>
            <p>
              Discovered candidates waiting for a human. Promote starts a tracked
              offer; it still has to earn <strong>verified</strong> on the review desk.
            </p>
          </div>
        </div>

        <form method="GET" action="/inbox" className="inbox-controls" role="search">
          <input type="hidden" name="filter" value={filter} />
          <input
            type="search"
            name="q"
            defaultValue={q ?? ""}
            placeholder="Search title or URL…"
            aria-label="Search inbox"
            maxLength={200}
          />
          <button type="submit" className="btn">Search</button>
          {q ? (
            <Link href={buildHref(undefined, filter)} className="btn btn-ghost">Clear</Link>
          ) : null}
        </form>

        <div className="inbox-tabs" role="tablist" aria-label="Inbox filter">
          {FILTERS.map(([value, label]) => (
            <Link
              key={value}
              href={buildHref(q, value)}
              className={`btn ${filter === value ? "btn-primary" : "btn-ghost"}`}
              aria-current={filter === value ? "true" : undefined}
            >
              {label}
            </Link>
          ))}
        </div>

        {items === null ? (
          <div className="empty-state">
            Inbox unavailable — the API did not answer. This is deliberately not
            “inbox is clear”: refresh once the API is reachable.
          </div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            {q
              ? <>Nothing matches “{q}” in this filter.</>
              : filter === "unprocessed"
                ? "Inbox is clear — nothing is waiting for review."
                : "No items in this view."}
          </div>
        ) : (
          <div className="inbox-list">
            {items.map((item) => (
              <div className="trend-row" key={item.id}>
                <div>
                  <h3 className="truncate">
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.title ?? item.url}
                    </a>
                  </h3>
                  <p>
                    <span className={`tag ${item.trust_tier === "official" ? "tag-ok" : ""}`}>
                      {item.trust_tier ?? "unknown tier"}
                    </span>{" "}
                    {item.source_provider ?? "unknown source"}
                    {item.duplicate_group ? <> · duplicate group</> : null}
                    {item.processed ? <> · processed</> : null}
                    {" · "}
                    {new Date(item.observed_at).toLocaleString()}
                  </p>
                </div>
                {!item.processed ? (
                  <InboxActions
                    itemId={item.id}
                    provider={item.source_provider}
                    category={item.source_category}
                  />
                ) : (
                  <span className="tag">done</span>
                )}
              </div>
            ))}
          </div>
        )}

        {next ? (
          <div style={{ marginTop: "0.8rem" }}>
            <Link href={buildHref(q, filter, next)} className="btn">
              Older items →
            </Link>
          </div>
        ) : null}
      </section>
    </main>
  );
}
