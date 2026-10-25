/**
 * Studio overview (v0.27) — the operator's first screen.
 *
 * It answers four questions in one glance: is the system healthy, what is on
 * the radar, what needs a human, and what is publishing? Everything below is
 * a real API read; no demo numbers are invented.
 */

import "./styles.css";
import Link from "next/link";
import { redirect } from "next/navigation";

import AutomationCard from "./AutomationCard";
import { InboxActions } from "./InboxActions";
import RadarScope, { type RadarCandidate } from "./RadarScope";
import { apiFetch } from "@/lib/api";

type ItemRow = {
  id: string;
  url: string;
  canonical_url: string | null;
  title: string | null;
  observed_at: string;
  duplicate_group: string | null;
  source_provider: string | null;
  source_category: string | null;
  trust_tier: string | null;
};

type Analytics = {
  items_total: number;
  offers_by_state: { state: string; n: number }[];
  verification: { live_offers: number; recheck_due: number } | null;
  schedules_by_state: { state: string; n: number }[];
  publishing: { published: number; failed: number; paused: number } | null;
  metrics_totals: { posts_measured: number; views: number | string } | null;
  growth: { score: number; recommendations: { priority: string; title: string }[] } | null;
  trend_summary: { total: number; hot: number; shortlisted: number; average_score: number } | null;
};

type Trends = {
  candidates: RadarCandidate[];
  summary: { total: number; hot: number; shortlisted: number; average_score: number };
};

type Attention = {
  total: number;
  severity: "ok" | "warning" | "error";
  counts: Record<string, number>;
};

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await apiFetch(path, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

function big(value: number | string | null | undefined): string {
  if (value == null) return "–";
  const number = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(number)) return "–";
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return number.toLocaleString();
}

export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  // Old extension builds opened `/?saved_item=<id>`; keep those links working.
  const sp = (await searchParams) ?? {};
  const rawSaved = sp.saved_item;
  const saved = Array.isArray(rawSaved) ? rawSaved[0] : rawSaved;
  if (saved) redirect(`/inbox?saved_item=${encodeURIComponent(saved)}`);

  const [health, items, analytics, trends, attention] = await Promise.all([
    getJson<{ status?: string }>("/health", {}),
    getJson<ItemRow[] | null>("/items?processed=false&limit=12", null),
    getJson<Analytics | null>("/analytics", null),
    getJson<Trends | null>("/trends", null),
    getJson<Attention | null>("/attention", null),
  ]);

  const offers = analytics?.offers_by_state ?? [];
  const reviewCount = offers
    .filter((row) => ["candidate", "evidence_needed"].includes(row.state))
    .reduce((sum, row) => sum + Number(row.n), 0);
  const scheduled = (analytics?.schedules_by_state ?? [])
    .filter((row) => ["approved", "scheduled", "needs_approval"].includes(row.state))
    .reduce((sum, row) => sum + Number(row.n), 0);
  // An outage must never read as "0 pending": show the counts only when at
  // least one of the sources actually answered.
  const attentionKnown = attention !== null || analytics !== null;
  const needsYou = attention ? attention.total : reviewCount;
  // A missing composite score ("–") is different from a measured 0.0/100.
  const growth = analytics ? analytics?.growth?.score ?? null : null;
  const topRecommendation = analytics?.growth?.recommendations?.[0];

  return (
    <main className="page">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Operator console</span>
          <h1>Truth-first content radar.</h1>
          <p>
            Discover what is moving, verify it against official evidence, then produce
            English-first walkthroughs with optional Urdu voiceover under the exact same
            approval contract. Automation handles the mechanical work; a human still owns
            every claim and every publish.
          </p>
          <div className="hero-actions">
            <Link href="/radar" className="btn btn-primary">Open radar →</Link>
            <Link href="/review" className="btn">Review desk</Link>
            <Link href="/attention" className="btn btn-ghost">Needs You{needsYou ? ` · ${needsYou}` : ""}</Link>
          </div>
        </div>
        <aside className="panel">
          <div className="panel-head">
            <div>
              <span className="eyebrow">Live system</span>
              <h2 style={{ marginTop: "0.45rem" }}>Pipeline pulse</h2>
            </div>
            <span className={`tag ${health.status === "ok" ? "tag-ok" : "tag-hot"}`}>
              {health.status === "ok" ? "API online" : "API unreachable"}
            </span>
          </div>
          <div className="metric-row">
            <span>Radar leads</span>
            <strong>{trends ? trends.summary.total : "–"}</strong>
          </div>
          <div className="metric-row"><span>Hot leads</span><strong>{trends ? trends.summary.hot : "–"}</strong></div>
          <div className="metric-row">
            <span>Awaiting a human</span>
            <strong>{attentionKnown ? needsYou : "–"}</strong>
          </div>
          <div className="metric-row"><span>Scheduled / approval</span><strong>{scheduled}</strong></div>
          <div className="metric-row">
            <span title="Internal directional blend of measured fields, not a platform metric">
              Growth score <span className="muted small">(internal)</span>
            </span>
            <strong>
              {growth == null ? "–" : growth.toFixed(1)}
              <span className="muted small">/100</span>
            </strong>
          </div>
          {topRecommendation && (
            <p className="small muted" style={{ marginTop: "0.8rem", marginBottom: 0 }}>
              <strong style={{ color: "var(--text)" }}>Next move:</strong> {topRecommendation.title}
            </p>
          )}
        </aside>
      </section>

      <AutomationCard />

      <section className="kpi-grid" aria-label="Key metrics">
        <div className="kpi"><strong>{analytics?.items_total ?? "–"}</strong><span>Inbox items</span><small>discovery pool</small></div>
        <div className="kpi"><strong>{analytics?.verification?.live_offers ?? "–"}</strong><span>Live offers</span><small>{analytics?.verification?.recheck_due ?? 0} recheck due</small></div>
        <div className="kpi"><strong>{trends ? trends.summary.hot : "–"}</strong><span>Hot radar</span><small>score ≥ 78</small></div>
        <div className="kpi"><strong>{scheduled}</strong><span>In queue</span><small>approval → publish</small></div>
        <div className="kpi"><strong>{big(analytics?.publishing?.published)}</strong><span>Published</span><small>{big(analytics?.metrics_totals?.views)} measured views</small></div>
        <div className="kpi">
          <strong>{growth == null ? "–" : growth.toFixed(1)}</strong>
          <span>Growth loop</span>
          <small>{analytics?.metrics_totals?.posts_measured ?? 0} posts measured</small>
        </div>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Radar</h2>
              <p>Explainable demand, freshness and competition signals.</p>
            </div>
            <Link href="/radar" className="btn btn-ghost">Full radar</Link>
          </div>
          {trends === null ? (
            <div className="empty-state">
              Radar unavailable — the API did not answer. Refresh once the stack
              is reachable; scores are never invented to fill the gap.
            </div>
          ) : trends.candidates.length === 0 ? (
            <div className="empty-state">
              No scored leads yet. Open the radar and run a scan to turn the inbox into
              ranked topics.
            </div>
          ) : (
            <>
              <RadarScope candidates={trends.candidates} compact label="Topic radar preview" />
              <div style={{ marginTop: "0.8rem" }}>
                {trends.candidates.slice(0, 4).map((candidate) => {
                  const score = Number(candidate.score) || 0;
                  return (
                    <div className="trend-row" key={candidate.id}>
                      <div>
                        <h3 className="truncate">{candidate.title}</h3>
                        <p>{candidate.source_provider ?? "unknown source"}</p>
                      </div>
                      <div className="score-bar" title={`${score.toFixed(1)}/100`}>
                        <span style={{ width: `${score}%` }} />
                      </div>
                      <span className={`tag ${score >= 78 ? "tag-hot" : score >= 55 ? "tag-accent" : ""}`}>
                        {score.toFixed(1)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Pipeline</h2>
              <p>Every stage is gated; no number here bypasses verification.</p>
            </div>
            <Link href="/queue" className="btn btn-ghost">Queue</Link>
          </div>
          {offers.length === 0 ? (
            <div className="empty-state">
              {analytics === null
                ? "Pipeline unavailable — the API did not answer. Counts are never faked."
                : "No offers yet — promote a reviewed item to start."}
            </div>
          ) : (
            offers.map((row) => {
              const max = Math.max(...offers.map((entry) => Number(entry.n)), 1);
              return (
                <div key={row.state} style={{ margin: "0.55rem 0" }}>
                  <div className="metric-row" style={{ border: 0, padding: "0.15rem 0" }}>
                    <span>{row.state.replace(/_/g, " ")}</span>
                    <strong>{row.n}</strong>
                  </div>
                  <div className="score-bar"><span style={{ width: `${(Number(row.n) / max) * 100}%` }} /></div>
                </div>
              );
            })
          )}
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <Link href="/analytics" className="btn btn-ghost">Growth briefing</Link>
            <Link href="/settings" className="btn btn-ghost">Automation policy</Link>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="panel-head">
          <div>
            <h2>Review inbox</h2>
            <p>Unprocessed candidates from trusted sources and saved links, exactly once.</p>
          </div>
          <span className="tag">{items === null ? "– shown" : `${items.length} shown`}</span>
        </div>
        {items === null ? (
          <div className="empty-state">
            Inbox unavailable — the API did not answer. Refresh once the collector
            and API are reachable.
          </div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            No candidates yet. Run the collector worker or save a page with the extension.
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Source</th>
                  <th>Tier</th>
                  <th>Observed</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.title ?? item.url}
                      </a>
                      <div className="muted small truncate" style={{ maxWidth: 520 }}>{item.canonical_url}</div>
                    </td>
                    <td>
                      {item.source_provider}
                      <div className="muted small">{item.source_category}</div>
                    </td>
                    <td>
                      <span className={`tag ${item.trust_tier?.startsWith("A") ? "tag-ok" : ""}`}>
                        {item.trust_tier?.split("_")[0] ?? "?"}
                      </span>
                    </td>
                    <td className="muted small">
                      {new Date(item.observed_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })}
                    </td>
                    <td>
                      <InboxActions
                        itemId={item.id}
                        provider={item.source_provider}
                        category={item.source_category}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
