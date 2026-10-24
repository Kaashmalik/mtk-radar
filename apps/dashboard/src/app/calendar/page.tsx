import "./styles.css";
import BatchApprove from "./BatchApprove";
import HeldReconcile from "./HeldReconcile";
import ScheduleActions from "./ScheduleActions";
import { apiFetch } from "@/lib/api";

/**
 * Content calendar (week 9, master plan §17): per-platform schedules displayed
 * in Asia/Karachi by default, with operator pause/cancel controls and the
 * reapproval rule surfaced on hash mismatch.
 * Week 10 (§6): publishing account health — credential references only, token
 * expiry surfaced so the operator can recover dead sessions.
 */

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

async function getSchedules(): Promise<ScheduleRow[] | null> {
  try {
    const res = await apiFetch(`/schedules?limit=200`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
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
    const res = await apiFetch(`/platform-accounts`, { cache: "no-store" });
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
  for (const row of rows ?? []) {
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

      {rows && rows.length > 0 && (
        <BatchApprove
          rows={rows.map((s) => ({
            id: s.id,
            platform: s.platform,
            offer_title: s.offer_title,
            local_time: s.local_time,
            state: s.state,
          }))}
        />
      )}

      {rows === null ? (
        <section className="card">
          <p className="muted" style={{ color: "var(--warn)" }}>
            Calendar unavailable — the API did not answer. Nothing is shown rather
            than an empty calendar: an outage must not read as “nothing scheduled”.
          </p>
        </section>
      ) : rows.length === 0 ? (
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
                let held = false;
                let openAttempt = false;
                if (s.outcome_detail) {
                  try {
                    const parsed = JSON.parse(s.outcome_detail);
                    outcome = parsed?.detail ?? null;
                    // v0.23: a held post waits for a human (unknown upload
                    // outcome) — it must be obvious on the calendar.
                    held = Boolean(parsed?.hold);
                    // v0.31: an attempt marker without a result means the worker
                    // may have uploaded before dying. It is equally unsafe to
                    // retry until a human reconciles it.
                    openAttempt = Boolean(parsed?.attempt);
                  } catch {}
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
                        {(held || openAttempt) && (
                          <div className="small" style={{ color: "#f0883e" }}>
                            ⚠ {held ? "HELD" : "UNKNOWN UPLOAD"} — needs operator review:
                            check the platform before re-queueing (a previous upload may
                            already be live).
                          </div>
                        )}
                      </div>
                      <span
                        className="badge"
                        style={{ color: STATE_COLORS[s.state] ?? "#8b949e", borderColor: STATE_COLORS[s.state] ?? "#8b949e" }}
                      >
                        {s.state}
                      </span>
                    </div>
                    {(held || openAttempt) && (
                      <HeldReconcile scheduleId={s.id} remotePostId={s.remote_post_id} />
                    )}
                    <ScheduleActions scheduleId={s.id} state={s.state} />
                  </article>
                );
              })}
            </div>
          </section>
        ))
      )}

    </main>
  );
}
