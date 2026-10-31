/**
 * Queue (v0.19) — the automation's work list. The workers do everything
 * around the human gates; this page shows what is moving on its own and what
 * is waiting for a person (verification, redaction review, approval).
 */

import "./styles.css";
import { apiFetch } from "@/lib/api";

import { QueueRowActions } from "./QueueRowActions";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await apiFetch(path, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

// The production queue answers "what to make next" — a truncated page would
// bury rows the operator was supposed to see. Follow X-Next-Cursor to
// exhaustion (bounded) like every other growing collection.
const QUEUE_MAX_PAGES = 40;
const QUEUE_PAGE_LIMIT = 200;

type QueueRow = {
  id: string;
  offer_id: string | null;
  trend_id: string | null;
  title: string;
  provider: string | null;
  category: string | null;
  kind: string;
  offer_state: string | null;
  expires_at: string | null;
  trend_snapshot: string;
  trend_score: number | null;
  velocity: number | null;
  corroboration: number | null;
  evidence_count: number;
  preset_fit: number | null;
  rank_pinned: number | null;
  rank: number;
  /** EP-03 track: decides capture/render requirements and copy rules. */
  content_type?: string | null;
};

const TRACK_LABEL: Record<string, string> = {
  explainer: "Explainer",
  tested_tutorial: "Tested tutorial",
  claim_walkthrough: "Claim walkthrough",
  offer: "Offer",
};

/** `status` distinguishes a genuinely empty queue from an outage (nothing
 * loaded) and a partial read (a later page failed or the page cap hit). */
type QueueLoad = { rows: QueueRow[]; status: "complete" | "partial" | "unavailable" };

async function getQueueAll(): Promise<QueueLoad> {
  const rows: QueueRow[] = [];
  let cursor: string | null = null;
  let pagesRead = 0;
  try {
    for (let page = 0; page < QUEUE_MAX_PAGES; page += 1) {
      const res = await apiFetch(
        `/production-queue?limit=${QUEUE_PAGE_LIMIT}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as { queue: QueueRow[] };
      rows.push(...(body.queue ?? []));
      pagesRead += 1;
      cursor = res.headers.get("X-Next-Cursor");
      if (!cursor) return { rows, status: "complete" };
    }
    return { rows, status: "partial" }; // page cap reached with more to read
  } catch {
    return { rows, status: pagesRead === 0 ? "unavailable" : "partial" };
  }
}

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.ceil(ms / 86_400_000);
}

/** One primary action per offer state — the queue row tells the operator
 * which human gate the topic is actually waiting on. */
function primaryAction(row: QueueRow): { href: string; label: string } {
  if (!row.offer_id) return { href: "/radar", label: "Find the trend ↗" };
  switch (row.offer_state) {
    case "candidate":
      return { href: `/offers/${row.offer_id}`, label: "Start verification →" };
    case "evidence_needed":
      return { href: `/offers/${row.offer_id}`, label: "Verify evidence →" };
    case "verified":
      return { href: `/offers/${row.offer_id}`, label: "Prepare capture →" };
    case "approved_for_video":
      return { href: "/offers", label: "Check the render list →" };
    case "published":
      return { href: "/analytics", label: "Measure it →" };
    case "expired":
      return { href: `/offers/${row.offer_id}`, label: "Recheck →" };
    default:
      return { href: `/offers/${row.offer_id}`, label: "Open offer →" };
  }
}


// The queue page answers "what still needs a person" — a truncated page
// silently under-counts every gate. Follow X-Next-Cursor to exhaustion
// (bounded) instead of filtering the first page.
const MAX_PAGES = 40;
const PAGE_LIMIT = 200;

async function getJsonAll<T>(path: string, fallback: readonly T[]): Promise<T[]> {
  const rows: T[] = [];
  let cursor: string | null = null;
  try {
    for (let page = 0; page < MAX_PAGES; page += 1) {
      const sep = path.includes("?") ? "&" : "?";
      const cursorPart = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
      const res = await apiFetch(`${path}${sep}limit=${PAGE_LIMIT}${cursorPart}`, {
        cache: "no-store",
      });
      if (!res.ok) return rows.length ? rows : [...fallback];
      const items = (await res.json()) as T[];
      rows.push(...items);
      cursor = res.headers.get("X-Next-Cursor");
      if (!cursor || items.length === 0) return rows;
    }
    // MAX_PAGES exhausted: return what we have rather than looping forever.
    return rows;
  } catch {
    return rows.length ? rows : [...fallback];
  }
}

type Candidate = {
  offer_id: string;
  title: string;
  provider: string;
  state: string;
  language: string;
  script_version: number;
  capture_id: string;
  capture_created_at: string;
};

type Capture = {
  id: string;
  offer_id: string;
  offer_title: string;
  redaction_reviewed: boolean;
  created_at: string;
};

type PolicySummary = {
  state: string;
  mode: string;
  automation_stages: string[];
  human_stages: string[];
};

type RenderDeadLetterItem = {
  id: string;
  offer_id: string;
  offer_title: string;
  preset: string;
  language: string;
  status: string;
  qc_status: string;
  qc_report: string | { errors?: string[]; warnings?: string[] } | null;
  video_path: string;
  duration_s: string | null;
  qc_checked_at: string | null;
  created_at: string;
};

type RenderDeadLetter = {
  counts: {
    qc_passed?: number;
    qc_failed?: number;
    render_failed?: number;
    not_checked?: number;
    total?: number;
  };
  items: RenderDeadLetterItem[];
};

function qcErrors(report: RenderDeadLetterItem["qc_report"]): string[] {
  if (!report) return [];
  if (typeof report === "string") {
    try {
      const parsed = JSON.parse(report) as { errors?: string[] };
      return parsed.errors ?? [];
    } catch {
      return [];
    }
  }
  return report.errors ?? [];
}

export default async function QueuePage() {
  const [queueLoad, candidates, captures, offers, schedules, policy, deadLetter] =
    await Promise.all([
      getQueueAll(),
      getJsonAll<Candidate>("/render-candidates", []),
      getJsonAll<Capture>("/captures", []),
      getJsonAll<{ id: string; title: string; state: string; official_evidence: number }>(
        "/offers",
        [],
    ),
    getJsonAll<{ id: string; state: string; platform: string }>("/schedules", []),
    getJson<{ summary?: PolicySummary }>("/automation/policy", {}),
    getJson<RenderDeadLetter>("/render-dead-letter", { counts: {}, items: [] }),
  ]);
  const queue = queueLoad.rows;

  const summary = policy.summary ?? {
    state: "unknown",
    mode: "unknown",
    automation_stages: [],
    human_stages: [],
  };

  const awaitingVerification = offers.filter(
    (o) => o.state === "evidence_needed" && o.official_evidence > 0,
  );
  const awaitingRedaction = captures.filter((c) => !c.redaction_reviewed);
  const awaitingApproval = schedules.filter((s) => s.state === "needs_approval");
  const renderFailures =
    (deadLetter.counts.qc_failed ?? 0) + (deadLetter.counts.render_failed ?? 0);

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Queue</h1>
      <p className="tagline">
        What the workers handle by themselves, and what still needs a person.
      </p>

      <section className="card">
        <h2>Automation policy</h2>
        <p className="small" style={{ marginTop: 0 }}>
          <span className="pill pill-accent">{summary.state}</span>{" "}
          mode <strong>{summary.mode}</strong> · automation:{" "}
          {summary.automation_stages.length ? summary.automation_stages.join(", ") : "none"} ·{" "}
          human: {summary.human_stages.length ? summary.human_stages.join(", ") : "none"}
          {" · "}
          <a href="/settings">change in Settings →</a>
        </p>
      </section>

      <section className="card">
        <h2>At a glance</h2>
        <div className="stats">
          <div>
            <strong style={{ color: "var(--accent)" }}>{queueLoad.status === "unavailable" ? "—" : queue.length}</strong>
            <span>videos to make</span>
          </div>
          <div>
            <strong style={{ color: "var(--accent)" }}>{candidates.length}</strong>
            <span>rendering automatically</span>
          </div>
          <div>
            <strong style={{ color: "var(--warn)" }}>{awaitingVerification.length}</strong>
            <span>awaiting verification</span>
          </div>
          <div>
            <strong style={{ color: "var(--warn)" }}>{awaitingRedaction.length}</strong>
            <span>awaiting redaction review</span>
          </div>
          <div>
            <strong style={{ color: "var(--warn)" }}>{awaitingApproval.length}</strong>
            <span>awaiting approval</span>
          </div>
          <div>
            <strong style={{ color: renderFailures ? "var(--danger)" : "var(--ok)" }}>
              {renderFailures}
            </strong>
            <span>render QC / failures</span>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Production queue — videos to make ({queue.length})</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          Ranked by the documented formula: 35% trend momentum + 30% evidence +
          20% freshness + 15% preset fit — recomputed from evidence on every
          load, never stored. Pins are operator overrides.
        </p>
        {queueLoad.status === "unavailable" && (
          <div className="notice notice-danger" role="alert">
            Queue unavailable — the API did not answer. This is not an empty
            queue; reload once the stack is reachable.
          </div>
        )}
        {queueLoad.status === "partial" && (
          <div className="notice" role="status">
            Partial list — {queue.length} rows loaded before a later page failed
            or the page cap was reached. Counts below may be low.
          </div>
        )}
        {queueLoad.status === "unavailable" ? null : queue.length === 0 ? (
          <p className="muted small">
            Empty. Promote a rising topic from the{" "}
            <a href="/radar">radar</a> — an offer candidate and its queue row
            appear together, and verification decides the rest.
          </p>
        ) : (
          <div id="production-queue-list" data-ids={JSON.stringify(queue.map((q) => q.id))}>
            {queue.map((row) => {
              const days = daysUntil(row.expires_at);
              const action = primaryAction(row);
              return (
                <div className="pq-row" key={row.id}>
                  <span className="pq-rank">
                    {row.rank_pinned !== null ? `📌 ${row.rank_pinned}` : row.rank.toFixed(0)}
                  </span>
                  <div className="pq-main">
                    <strong>
                      {row.offer_id ? <a href={`/offers/${row.offer_id}#research`}>{row.title}</a> : row.title}
                    </strong>
                    <span className="muted small">
                      {row.provider ?? "unknown"} · {row.kind} · rank {row.rank.toFixed(0)}
                      {row.offer_state ? ` · ${row.offer_state}` : ""}
                    </span>
                    <span className="pq-chips">
                      {row.content_type && (
                        <span className="tag tag-accent" title="Content track (research brief)">
                          {TRACK_LABEL[row.content_type] ?? row.content_type}
                        </span>
                      )}
                      {(row.velocity ?? 0) > 0 && (
                        <span className="pill pill-accent" title="Score gained per hour between radar observations">
                          🔥 {(row.velocity as number).toFixed(1)}/h
                        </span>
                      )}
                      {(row.corroboration ?? 0) >= 2 && (
                        <span className="pill" title="Independent sources on this story">
                          🧵 {row.corroboration} sources
                        </span>
                      )}
                      {(row.evidence_count ?? 0) > 0 && (
                        <span className="pill" style={{ color: "var(--ok)" }} title="Evidence snapshots on the offer">
                          🧪 {row.evidence_count}
                        </span>
                      )}
                      {days !== null && (
                        <span
                          className="pill"
                          style={{ color: days <= 3 ? "var(--danger)" : undefined }}
                          title="Freshness deadline"
                        >
                          {days < 0 ? "⏳ overdue" : `⏳ ${days}d`}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="pq-actions">
                    <a className="btn btn-primary" href={action.href}>{action.label}</a>
                    <QueueRowActions id={row.id} pinned={row.rank_pinned} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Render QC &amp; dead letter ({renderFailures})</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          Measured QC blocks publishing. Failed attempts stay visible here until
          an operator fixes the cause and re-renders.
        </p>
        {deadLetter.items.length === 0 ? (
          <p className="muted small">No failed or rejected renders.</p>
        ) : (
          <table>
            <thead>
              <tr><th>offer</th><th>output</th><th>status</th><th>reason</th><th>when</th></tr>
            </thead>
            <tbody>
              {deadLetter.items.map((item) => {
                const errors = qcErrors(item.qc_report);
                return (
                  <tr key={item.id}>
                    <td><a href={`/offers/${item.offer_id}`}>{item.offer_title}</a></td>
                    <td>{item.preset} · {item.language}</td>
                    <td>
                      <span className="pill" style={{ color: "var(--danger)" }}>
                        {item.status} / {item.qc_status}
                      </span>
                    </td>
                    <td className="small">
                      {errors.length ? errors.join(" · ") : "see the QC report"}
                    </td>
                    <td className="small">
                      {new Date(item.created_at).toLocaleString("en-GB", {
                        timeZone: "Asia/Karachi",
                      })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Rendering automatically ({candidates.length})</h2>
        {candidates.length === 0 ? (
          <p className="muted small">
            Nothing queued — a candidate needs a generated script and a capture
            that passed redaction review.
          </p>
        ) : (
          <table>
            <thead>
              <tr><th>offer</th><th>provider</th><th>voiceover</th><th>script</th><th>captured</th></tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={`${c.offer_id}-${c.language}`}>
                  <td><a href={`/offers/${c.offer_id}`}>{c.title}</a></td>
                  <td>{c.provider}</td>
                  <td>{c.language === "ur" ? "Urdu" : "English"}</td>
                  <td>v{c.script_version}</td>
                  <td className="small">
                    {new Date(c.capture_created_at).toLocaleDateString("en-GB", {
                      timeZone: "Asia/Karachi",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Waiting on you</h2>
        <div style={{ display: "grid", gap: "0.8rem" }}>
          <div>
            <h3 style={{ fontSize: "0.95rem", margin: "0 0 0.3rem" }}>
              Verification (§3)
            </h3>
            {awaitingVerification.length === 0 ? (
              <p className="muted small">Nothing waiting.</p>
            ) : (
              <ul>
                {awaitingVerification.map((o) => (
                  <li key={o.id} className="small">
                    <a href={`/offers/${o.id}`}>{o.title}</a> — {o.official_evidence}{" "}
                    official source(s) collected
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 style={{ fontSize: "0.95rem", margin: "0 0 0.3rem" }}>
              Redaction review (§4)
            </h3>
            {awaitingRedaction.length === 0 ? (
              <p className="muted small">Nothing waiting.</p>
            ) : (
              <ul>
                {awaitingRedaction.map((c) => (
                  <li key={c.id} className="small">
                    <a href={`/offers/${c.offer_id}`}>{c.offer_title}</a> — capture{" "}
                    {new Date(c.created_at).toLocaleDateString("en-GB", {
                      timeZone: "Asia/Karachi",
                    })}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 style={{ fontSize: "0.95rem", margin: "0 0 0.3rem" }}>
              Publish approval (§17)
            </h3>
            {awaitingApproval.length === 0 ? (
              <p className="muted small">Nothing waiting.</p>
            ) : (
              <ul>
                {awaitingApproval.map((s) => (
                  <li key={s.id} className="small">
                    <a href="/calendar">{s.platform} post</a> — needs a named reviewer
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
