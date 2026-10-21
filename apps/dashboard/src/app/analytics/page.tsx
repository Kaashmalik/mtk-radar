/**
 * Analytics (week 12, master plan §7): aggregate pipeline + publishing health.
 * "Use data to prioritize topics and improve packaging, not to weaken
 * verification." Read-only — refresh the page for fresh numbers.
 */

import "./styles.css";

const API = process.env.API_URL ?? "http://localhost:8000";

type Analytics = {
  items_total: number;
  offers_by_state: { state: string; n: number }[];
  verification: {
    live_offers: number;
    retired_offers: number;
    corrections: number;
    evidence_per_offer: number | null;
    recheck_due: number;
  } | null;
  schedules_by_state: { state: string; n: number }[];
  schedules_by_platform: { platform: string; state: string; n: number }[];
  publishing: {
    published: number;
    failed: number;
    paused: number;
    auto_paused: number;
  } | null;
  source_freshness: {
    id: string;
    name: string;
    provider: string;
    enabled: boolean;
    hours_since_poll: number | null;
    item_count: number;
  }[];
  account_health: { platform: string; status: string; last_error: string | null }[];
};

async function getAnalytics(): Promise<Analytics | null> {
  try {
    const res = await fetch(`${API}/analytics`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

const STATE_COLORS: Record<string, string> = {
  candidate: "#8b949e",
  evidence_needed: "#d29922",
  verified: "#3fb950",
  approved_for_video: "#58a6ff",
  published: "#bc8cff",
  expired: "#f85149",
  corrected: "#f0883e",
  failed: "#f85149",
  paused: "#f0883e",
  draft: "#8b949e",
  needs_approval: "#d29922",
  scheduled: "#58a6ff",
};

function n(v: number | null | undefined): string {
  return v === null || v === undefined ? "–" : String(v);
}

export default async function AnalyticsPage() {
  const data = await getAnalytics();

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Analytics</h1>
      <p className="tagline">
        Pipeline health, verification load, publishing outcomes, source freshness (§7).
      </p>

      {!data ? (
        <section className="card">
          <p className="muted">API unreachable — start the stack (pnpm dev).</p>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>Pipeline</h2>
            <div className="stats">
              <div><strong>{n(data.items_total)}</strong><span>inbox items</span></div>
              {(data.offers_by_state ?? []).map((s) => (
                <div key={s.state}>
                  <strong style={{ color: STATE_COLORS[s.state] ?? "#8b949e" }}>{n(s.n)}</strong>
                  <span>{s.state.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="card">
            <h2>Verification desk</h2>
            <div className="stats">
              <div><strong>{n(data.verification?.live_offers)}</strong><span>live offers</span></div>
              <div><strong>{n(data.verification?.retired_offers)}</strong><span>retired</span></div>
              <div><strong>{n(data.verification?.corrections)}</strong><span>corrections</span></div>
              <div>
                <strong>
                  {data.verification?.evidence_per_offer != null
                    ? data.verification.evidence_per_offer.toFixed(1)
                    : "–"}
                </strong>
                <span>evidence / offer</span>
              </div>
              <div>
                <strong style={{ color: (data.verification?.recheck_due ?? 0) > 0 ? "#d29922" : undefined }}>
                  {n(data.verification?.recheck_due)}
                </strong>
                <span>recheck due</span>
              </div>
            </div>
          </section>

          <section className="card">
            <h2>Publishing</h2>
            <div className="stats">
              <div><strong>{n(data.publishing?.published)}</strong><span>published</span></div>
              <div><strong>{n(data.publishing?.failed)}</strong><span>failed</span></div>
              <div><strong>{n(data.publishing?.paused)}</strong><span>paused</span></div>
              <div>
                <strong style={{ color: (data.publishing?.auto_paused ?? 0) > 0 ? "#f0883e" : undefined }}>
                  {n(data.publishing?.auto_paused)}
                </strong>
                <span>auto-paused (expiry/changes)</span>
              </div>
            </div>
            {(data.schedules_by_platform ?? []).length > 0 && (
              <table>
                <thead>
                  <tr><th>platform</th><th>state</th><th>count</th></tr>
                </thead>
                <tbody>
                  {data.schedules_by_platform.map((r) => (
                    <tr key={`${r.platform}-${r.state}`}>
                      <td>{r.platform}</td>
                      <td style={{ color: STATE_COLORS[r.state] ?? "#8b949e" }}>{r.state}</td>
                      <td>{r.n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Source freshness</h2>
            {(data.source_freshness ?? []).length === 0 ? (
              <p className="muted small">No sources registered yet.</p>
            ) : (
              <table>
                <thead>
                  <tr><th>source</th><th>provider</th><th>items</th><th>last poll</th></tr>
                </thead>
                <tbody>
                  {data.source_freshness.map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}{!s.enabled && <span className="muted small"> (disabled)</span>}</td>
                      <td>{s.provider}</td>
                      <td>{s.item_count}</td>
                      <td className={stale(s.hours_since_poll)}>
                        {s.hours_since_poll == null
                          ? "–"
                          : `${s.hours_since_poll.toFixed(0)}h ago`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Platform accounts</h2>
            {(data.account_health ?? []).length === 0 ? (
              <p className="muted small">No platform accounts registered yet.</p>
            ) : (
              <ul>
                {data.account_health.map((a, i) => (
                  <li key={i} className="small">
                    <strong>{a.platform}</strong> —{" "}
                    <span style={{ color: a.status === "active" ? "#3fb950" : "#f85149" }}>
                      {a.status}
                    </span>
                    {a.last_error && <span className="muted small"> · {a.last_error}</span>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

    </main>
  );
}

function stale(hours: number | null): string {
  if (hours == null) return "stale-ok";
  if (hours > 72) return "stale-bad";
  if (hours > 24) return "stale-warn";
  return "stale-ok";
}
