import ScheduleActions from "./ScheduleActions";

/**
 * Content calendar (week 9, master plan §17): per-platform schedules displayed
 * in Asia/Karachi by default, with operator pause/cancel controls and the
 * reapproval rule surfaced on hash mismatch.
 * Week 10 (§6): publishing account health — credential references only, token
 * expiry surfaced so the operator can recover dead sessions.
 */

const API = process.env.API_URL ?? "http://localhost:8000";
const DISPLAY_TZ = "Asia/Karachi";

type ScheduleRow = {
  id: string;
  offer_id: string;
  offer_title: string;
  offer_provider: string;
  platform: string;
  state: string;
  local_time: string;
  timezone: string;
  privacy: string;
  approved_by: string | null;
  version_hash: string | null;
  remote_post_id: string | null;
  outcome_detail: string | null;
};

export const dynamic = "force-dynamic";

async function getSchedules(): Promise<ScheduleRow[]> {
  try {
    const res = await fetch(`${API}/schedules?limit=200`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

type AccountRow = {
  id: string;
  platform: string;
  account_handle: string;
  credential_source: string;
  status: string;
  expires_at: string | null;
  last_refreshed_at: string | null;
  last_error: string | null;
};

async function getAccounts(): Promise<AccountRow[]> {
  try {
    const res = await fetch(`${API}/platform-accounts`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

const STATE_COLORS: Record<string, string> = {
  draft: "#8b949e",
  needs_approval: "#d29922",
  approved: "#3fb950",
  scheduled: "#58a6ff",
  published: "#bc8cff",
  failed: "#f85149",
  paused: "#f0883e",
};

function dayKey(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { timeZone: DISPLAY_TZ });
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    timeZone: DISPLAY_TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function CalendarPage() {
  const [rows, accounts] = await Promise.all([getSchedules(), getAccounts()]);

  const byDay = new Map<string, ScheduleRow[]>();
  for (const row of rows) {
    const key = dayKey(row.local_time);
    byDay.set(key, [...(byDay.get(key) ?? []), row]);
  }
  const days = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b));

  return (
    <main className="page">
      <a href="/review" className="back">← Review desk</a>
      <a href="/analytics" className="back" style={{ marginLeft: "0.9rem" }}>Analytics →</a>
      <h1>Content calendar</h1>
      <p className="tagline">
        Per-platform schedules · {DISPLAY_TZ} display timezone · pause/resume with
        hash revalidation (edited content stays paused until reapproved).
      </p>

      <section className="card">
        <h2>Publishing accounts</h2>
        {accounts.length === 0 ? (
          <p className="muted small">
            No platform accounts registered. Register credential references
            (env prefixes or vault paths — never raw tokens) via
            <code> POST /platform-accounts</code>.
          </p>
        ) : (
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {accounts.map((a) => {
              const color =
                a.status === "active" ? "#3fb950"
                : a.status === "token_expired" ? "#f85149"
                : "#8b949e";
              return (
                <article key={a.id} className="entry">
                  <div className="entry-head">
                    <div>
                      <strong>{a.platform}</strong> — {a.account_handle}
                      <div className="muted small">
                        {a.credential_source}
                        {a.expires_at && (
                          <> · token expires {timeLabel(a.expires_at)} {dayKey(a.expires_at)}</>
                        )}
                        {a.last_refreshed_at && (
                          <> · last refreshed {dayKey(a.last_refreshed_at)}</>
                        )}
                        {a.last_error && <> · ⚠ {a.last_error}</>}
                      </div>
                    </div>
                    <span
                      className="badge"
                      style={{ color, borderColor: color }}
                    >
                      {a.status}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {rows.length === 0 ? (
        <section className="card">
          <p className="muted">
            Nothing scheduled yet. Open an offer and schedule a private test post.
          </p>
        </section>
      ) : (
        days.map(([day, items]) => (
          <section className="card" key={day}>
            <h2>{day}</h2>
            <div style={{ display: "grid", gap: "0.7rem" }}>
              {items.map((s) => {
                let outcome: string | null = null;
                if (s.outcome_detail) {
                  try { outcome = JSON.parse(s.outcome_detail)?.detail ?? null; } catch {}
                }
                return (
                  <article key={s.id} className="entry">
                    <div className="entry-head">
                      <div>
                        <span className="time">{timeLabel(s.local_time)}</span>{" "}
                        <strong>{s.platform}</strong> —{" "}
                        <a href={`/offers/${s.offer_id}`}>{s.offer_title}</a>
                        <div className="muted small">
                          {s.privacy} · {s.timezone}
                          {s.approved_by && <> · approved by {s.approved_by}</>}
                          {s.remote_post_id && <> · post {s.remote_post_id}</>}
                          {outcome && <> · {outcome}</>}
                        </div>
                      </div>
                      <span
                        className="badge"
                        style={{ color: STATE_COLORS[s.state] ?? "#8b949e", borderColor: STATE_COLORS[s.state] ?? "#8b949e" }}
                      >
                        {s.state}
                      </span>
                    </div>
                    <ScheduleActions scheduleId={s.id} state={s.state} />
                  </article>
                );
              })}
            </div>
          </section>
        ))
      )}

      <style jsx global>{`
        .page {
          max-width: 960px;
          margin: 0 auto;
          padding: 2rem 1.25rem;
          font-family: system-ui, sans-serif;
          color: #e8eaf0;
          background: #0d1117;
          min-height: 100vh;
        }
        .back {
          color: #58a6ff;
          text-decoration: none;
          font-size: 0.85rem;
        }
        h1 {
          margin: 0.4rem 0 0;
          font-size: 1.6rem;
        }
        .tagline {
          color: #8b949e;
          margin-top: 0.3rem;
          font-size: 0.85rem;
        }
        .card {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 10px;
          padding: 1.1rem 1.25rem;
          margin-top: 1.25rem;
        }
        .card h2 {
          margin: 0 0 0.6rem;
          font-size: 1.02rem;
          color: #c9d1d9;
        }
        .entry {
          border: 1px solid #21262d;
          border-radius: 8px;
          padding: 0.7rem 0.9rem;
        }
        .entry-head {
          display: flex;
          justify-content: space-between;
          gap: 0.8rem;
          align-items: flex-start;
          margin-bottom: 0.45rem;
        }
        .time {
          font-family: ui-monospace, monospace;
          color: #58a6ff;
          font-size: 0.85rem;
        }
        .badge {
          border: 1px solid;
          border-radius: 999px;
          padding: 0.1rem 0.55rem;
          font-size: 0.72rem;
          font-weight: 600;
          white-space: nowrap;
        }
        .muted {
          color: #8b949e;
        }
        .small {
          font-size: 0.76rem;
        }
        a {
          color: #58a6ff;
          text-decoration: none;
        }
      `}</style>
    </main>
  );
}
