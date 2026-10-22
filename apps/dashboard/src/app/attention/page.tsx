/**
 * Needs You (v0.30) — one inbox for every human gate.
 *
 * The API aggregates redaction, approval, render/publish failures, expiries,
 * connections, budget and worker liveness. This page is deliberately a read
 * model: quick approval is offered only for the two approval gates; all other
 * actions open the screen where the required evidence is visible.
 */

import "../styles.css";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

import AttentionActions from "./AttentionActions";

export const dynamic = "force-dynamic";

type Item = {
  id: string;
  kind: string;
  severity: "error" | "warning" | "info";
  title: string;
  detail: string;
  href: string;
  action: string;
  entity_id: string | null;
  at: string | null;
};

type KindSummary = {
  count: number;
  severity: "error" | "warning" | "info";
  href: string;
  label: string;
};

type Worker = {
  name: string;
  label: string;
  state: string;
  online: boolean;
  age_s: number | null;
  stale_after_s: number;
  detail: string | null;
  expected: boolean;
};

type Attention = {
  generated_at: string;
  total: number;
  severity: "ok" | "error" | "warning";
  counts: Record<string, number>;
  by_kind: Record<string, KindSummary>;
  items: Item[];
  workers: {
    expected_count: number;
    online_count: number;
    all_online: boolean;
    workers: Worker[];
  };
  budget: { used_today: number; limit_per_day: number; remaining: number; exhausted: boolean };
  policy: { mode: string; paused: boolean; stages: Record<string, string> };
};

async function getAttention(): Promise<Attention | null> {
  try {
    const res = await apiFetch("/attention", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Attention;
  } catch {
    return null;
  }
}

function severityClass(severity: string): string {
  if (severity === "error") return "tag tag-hot";
  if (severity === "warning") return "tag tag-warn";
  return "tag tag-accent";
}

export default async function AttentionPage() {
  const data = await getAttention();

  if (!data) {
    return (
      <main className="page">
        <Link href="/" className="back">← Overview</Link>
        <h1>Needs You</h1>
        <div className="card">
          <p className="down">The API did not return the attention inbox.</p>
          <p className="muted small">Check the API health dot, then refresh. The monitor also reads this endpoint.</p>
        </div>
      </main>
    );
  }

  const kinds = Object.entries(data.by_kind)
    .filter(([, summary]) => summary.count > 0)
    .sort((a, b) => {
      const rank = { error: 0, warning: 1, info: 2 } as Record<string, number>;
      return (rank[a[1].severity] ?? 9) - (rank[b[1].severity] ?? 9);
    });

  const offline = data.workers.workers.filter((w) => w.expected && !w.online);

  return (
    <main className="page attention-page">
      <Link href="/" className="back">← Overview</Link>
      <div className="header">
        <div>
          <h1>Needs You</h1>
          <p className="tagline">
            The gates automation cannot pass: redaction, approval, exceptions and
            worker health. Nothing on this page is a demo number.
          </p>
        </div>
        <span className={severityClass(data.severity === "ok" ? "info" : data.severity)}>
          {data.severity === "ok" ? "clear" : data.severity}
        </span>
      </div>

      <div className="card">
        <div className="attention-kpis">
          <div><strong>{data.total}</strong><span>open items</span></div>
          <div><strong>{data.workers.online_count}/{data.workers.expected_count}</strong><span>workers online</span></div>
          <div><strong>{data.budget.used_today}/{data.budget.limit_per_day}</strong><span>auto posts today</span></div>
          <div><strong>{data.policy.paused ? "Paused" : data.policy.mode}</strong><span>automation</span></div>
        </div>
      </div>

      {offline.length > 0 && (
        <div className="card attention-worker-card">
          <h2>Worker health</h2>
          <p className="muted small">
            Start the host launcher with <code>scripts/mtk-start.sh</code>. The
            browser cannot start Docker; a sleeping laptop cannot alert you, so
            keep an external uptime check too.
          </p>
          <table>
            <thead><tr><th>Worker</th><th>State</th><th>Last beat</th><th>Detail</th></tr></thead>
            <tbody>
              {data.workers.workers.filter((w) => w.expected).map((w) => (
                <tr key={w.name}>
                  <td>{w.label}</td>
                  <td className={w.online ? "ok" : "down"}>{w.state}</td>
                  <td className="muted small">
                    {w.age_s === null ? "never" : `${Math.round(w.age_s)}s ago`}
                    <span className="muted"> / limit {w.stale_after_s}s</span>
                  </td>
                  <td className="muted small">{w.detail ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {kinds.length === 0 ? (
        <div className="card">
          <h2>Nothing needs you</h2>
          <p className="muted">Approvals, redaction reviews and failures are clear.</p>
        </div>
      ) : (
        kinds.map(([kind, summary]) => {
          const rows = data.items.filter((item) => item.kind === kind);
          return (
            <section className="card" key={kind}>
              <div className="attention-group-head">
                <div>
                  <h2>{summary.label}</h2>
                  <p className="muted small">{summary.count} item{summary.count === 1 ? "" : "s"}</p>
                </div>
                <span className={severityClass(summary.severity)}>{summary.severity}</span>
              </div>
              <div className="attention-list">
                {rows.map((item) => (
                  <article className="attention-item" key={item.id}>
                    <div className="attention-item-copy">
                      <h3>{item.title}</h3>
                      <p>{item.detail}</p>
                      {item.at && (
                        <span className="muted small">
                          {new Date(item.at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} PKT
                        </span>
                      )}
                    </div>
                    <div className="attention-item-actions">
                      <AttentionActions kind={item.kind} entityId={item.entity_id} action={item.action} />
                      <Link href={item.href} className="btn btn-ghost btn-small">
                        {item.kind === "offer_approval" || item.kind === "schedule_approval" ? "Open" : item.action}
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          );
        })
      )}

      <p className="muted small">
        Generated {new Date(data.generated_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} PKT.
        Approval pins the exact script/render hash; re-rendering is required after a QC failure.
      </p>
    </main>
  );
}
