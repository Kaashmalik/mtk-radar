/**
 * Sources (v0.20) — the feeds the collector polls. Registering a source used
 * to need curl; without it the collectors had nothing to do, so this page is
 * part of making the system work end-to-end. It also shows source health
 * (last poll, cadence, tier) — the same signal the analytics page charts.
 */

import "./styles.css";
import SourceActions from "./SourceActions";
import SourceForm from "./SourceForm";
import { apiFetch } from "@/lib/api";

type Source = {
  id: string;
  provider: string;
  canonical_domain: string | null;
  account_handle: string | null;
  category: string;
  adapter: string;
  config: Record<string, unknown> | null;
  enabled: boolean;
  polling_cadence: string;
  trust_tier: string;
  last_checked_at: string | null;
  tos_reviewed_at: string | null;
  tos_reviewer: string | null;
  tos_reference: string | null;
  tos_expires_at: string | null;
  tos_valid: boolean;
};

const TIER_COLORS: Record<string, string> = {
  A_provider_owned: "#3fb950",
  B_discovery_lead: "#d29922",
  C_excluded: "#f85149",
};

export default async function SourcesPage() {
  let sources: Source[] = [];
  let apiDown = false;
  try {
    const res = await apiFetch("/sources", { cache: "no-store" });
    if (res.ok) {
      sources = await res.json();
    } else {
      apiDown = true;
    }
  } catch {
    apiDown = true;
  }

  const enabled = sources.filter((s) => s.enabled);
  const tierA = sources.filter((s) => s.trust_tier === "A_provider_owned");

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Sources</h1>
      <p className="tagline">
        Where discovery starts. Tier A sources can back a verified offer (§3);
        tier B only produces candidates.
      </p>

      {apiDown ? (
        <section className="card">
          <p className="muted">API unreachable — start the stack (pnpm dev).</p>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>Registered sources ({sources.length})</h2>
            <div className="stats">
              <div><strong>{enabled.length}</strong><span>enabled</span></div>
              <div><strong>{tierA.length}</strong><span>tier A (can verify)</span></div>
              <div>
                <strong>
                  {sources.filter((s) => s.last_checked_at).length}
                </strong>
                <span>polled at least once</span>
              </div>
            </div>
            {sources.length === 0 ? (
              <p className="muted small">
                No sources yet — the collector polls nothing. Register one below
                (or run <code>python services/api/scripts/seed_sources.py</code>).
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>provider</th><th>domain</th><th>adapter</th><th>tier</th>
                    <th>cadence</th><th>last poll</th><th>state</th><th>permission</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.id}>
                      <td>{s.provider}</td>
                      <td className="small">{s.canonical_domain ?? "–"}</td>
                      <td className="small">
                        {s.adapter}
                        {s.config?.feed_url ? (
                          <div className="muted small">{String(s.config.feed_url)}</div>
                        ) : s.config?.repo ? (
                          <div className="muted small">{String(s.config.repo)}</div>
                        ) : null}
                      </td>
                      <td>
                        <span style={{ color: TIER_COLORS[s.trust_tier] ?? "#8b949e" }}>
                          {s.trust_tier.replace(/^[ABC]_/, "")}
                        </span>
                      </td>
                      <td className="small">{s.polling_cadence}</td>
                      <td className="small">
                        {s.last_checked_at
                          ? new Date(s.last_checked_at).toLocaleString("en-GB", {
                              timeZone: "Asia/Karachi",
                            })
                          : "never"}
                      </td>
                      <td>
                        <span style={{ color: s.enabled ? "#3fb950" : "#8b949e" }}>
                          {s.enabled ? "enabled" : "disabled"}
                        </span>
                      </td>
                      <td><SourceActions source={s} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Register a source</h2>
            <SourceForm />
          </section>
        </>
      )}
    </main>
  );
}
