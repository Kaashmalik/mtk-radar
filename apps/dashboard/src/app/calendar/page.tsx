import "./styles.css";
import BatchApprove from "./BatchApprove";
import HeldReconcile from "./HeldReconcile";
import ScheduleActions from "./ScheduleActions";
import { apiFetch } from "@/lib/api";

/**
 * Content calendar (week 9, master plan §17; WP-H polish 2026-10-24).
 *
 * WP-H: the week grid groups schedules per platform/day in publish windows,
 * SAME-PLATFORM-SAME-WINDOW conflicts are flagged BEFORE a human approves
 * (server-side `_annotate_conflicts` — same platform within an hour on the
 * same local day), and measured best-time suggestions (post_metrics rollup)
 * are offered without ever silently re-timing a reviewed package.
 * Display timezone stays Asia/Karachi by default; account health (credential
 * references only, token expiry) stays on the page.
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
  /** WP-H: same-platform publish-window conflict, annotated by the API. */
  conflict?: boolean;
  conflict_with?: string[];
};

export const dynamic = "force-dynamic";

async function getSchedules(): Promise<ScheduleRow[] | null> {
  try {
    const res = await apiFetch(`/schedules?limit=200`, { cache: "no-store" });
    if (!res.ok) return null;
    const rows = (await res.json()) as ScheduleRow[];
    // Defense-in-depth: older APIs may not annotate conflicts — compute the
    // same flag client-side so the calendar never silently loses the warning.
    return annotateConflicts(rows);
  } catch {
    return null;
  }
}

type BestTimes = {
  suggestions: Record<string, { local_hour: number; sample_posts: number; avg_engagement: number }[]>;
};

async function getBestTimes(): Promise<BestTimes | null> {
  try {
    const res = await apiFetch(`/schedules/best-times`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** Client-side mirror of the API rule (schedules_api._annotate_conflicts):
 *  same platform, same local day, within 60 minutes → conflict. */
function annotateConflicts(rows: ScheduleRow[]): ScheduleRow[] {
  const WINDOW_MIN = 60;
  const active = rows.filter((r) =>
    ["needs_approval", "approved", "scheduled"].includes(r.state),
  );
  const slot = (r: ScheduleRow) => {
    const d = new Date(r.local_time);
    const day = d.toLocaleDateString("en-CA", { timeZone: r.timezone || DISPLAY_TZ });
    const parts = d.toLocaleTimeString("en-GB", {
      timeZone: r.timezone || DISPLAY_TZ, hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const [h, m] = parts.split(":").map(Number);
    return { day, minute: h * 60 + m };
  };
  const buckets = new Map<string, { row: ScheduleRow; minute: number }[]>();
  for (const row of rows) row.conflict = false;
  for (const row of active) {
    const { day, minute } = slot(row);
    const key = `${row.platform}|${day}`;
    buckets.set(key, [...(buckets.get(key) ?? []), { row, minute }]);
  }
  for (const entries of buckets.values()) {
    for (const a of entries) {
      for (const b of entries) {
        if (a.row.id !== b.row.id && Math.abs(a.minute - b.minute) <= WINDOW_MIN) {
          a.row.conflict = true;
          a.row.conflict_with = [...(a.row.conflict_with ?? []), b.row.id];
        }
      }
    }
  }
  return rows;
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

/** Day grouping key + grid label: the ISO local date (en-CA is ISO-like), so
 *  days sort chronologically instead of DD/MM/YYYY string order. */
function dayKey(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { timeZone: DISPLAY_TZ });
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    timeZone: DISPLAY_TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Week grouping (Mon–Sun) in the display timezone (WP-H week grid). */
function weekKey(iso: string): { key: string; monday: Date } {
  // The local date as YYYY-MM-DD (en-CA is the ISO-like locale) so the
  // weekday is derived from the DISPLAY-TZ date, never the host's zone.
  const [y, m, day] = new Date(iso)
    .toLocaleDateString("en-CA", { timeZone: DISPLAY_TZ })
    .split("-")
    .map(Number);
  // Rebuild as UTC noon: a fixed clock time keeps the calendar date stable
  // regardless of the host's timezone when formatting back later.
  const localNoon = Date.UTC(y, m - 1, day, 12);
  const weekday = new Date(localNoon).getUTCDay(); // 0 = Sun … 6 = Sat
  const shift = weekday === 0 ? 6 : weekday - 1; // days since Monday
  const monday = new Date(localNoon - shift * 86_400_000);
  return { key: monday.toISOString().slice(0, 10), monday };
}

function hourLabel(h: number): string {
  return `${String(h).padStart(2, "0")}:00`;
}

export default async function CalendarPage() {
  const [rows, accounts, best] = await Promise.all([
    getSchedules(),
    getAccounts(),
    getBestTimes(),
  ]);

  // ---- week grid: group rows by week, then by day within the week
  const weeks = new Map<string, { monday: Date; days: Map<string, ScheduleRow[]> }>();
  for (const row of rows ?? []) {
    const { key: wk, monday } = weekKey(row.local_time);
    const week = weeks.get(wk) ?? { monday, days: new Map() };
    const day = dayKey(row.local_time);
    week.days.set(day, [...(week.days.get(day) ?? []), row]);
    weeks.set(wk, week);
  }
  const sortedWeeks = [...weeks.entries()].sort(([a], [b]) => a.localeCompare(b));

  const bestEntries = Object.entries(best?.suggestions ?? {});

  return (
    <main className="page">
      <a href="/review" className="back">← Review desk</a>
      <a href="/analytics" className="back" style={{ marginLeft: "0.9rem" }}>Analytics →</a>
      <h1>Content calendar</h1>
      <p className="tagline">
        Week grid · per-platform/day publish windows · conflicts (same platform
        within an hour) flagged BEFORE approve · {DISPLAY_TZ} display timezone.
      </p>

      {bestEntries.length > 0 && (
        <section className="card" id="best-times">
          <h2>Measured best times</h2>
          <p className="muted small" style={{ marginTop: 0 }}>
            From your own published posts&apos; metrics (views + 2×(likes +
            comments)), grouped by the actual local publish hour. Suggestions
            only — moving a reviewed package still goes through approval and
            the release gate; hours with &lt; 2 measured posts are never shown.
          </p>
          <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap" }}>
            {bestEntries.map(([platform, hours]) => (
              <div key={platform} className="small">
                <strong>{platform}</strong>
                <ul style={{ margin: "0.2rem 0 0", paddingLeft: "1.1rem" }}>
                  {hours.map((h) => (
                    <li key={h.local_hour}>
                      {hourLabel(h.local_hour)} · {h.sample_posts} posts · engagement{" "}
                      {h.avg_engagement.toLocaleString()}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

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
        sortedWeeks.map(([weekStart, week]) => (
          <section className="card" key={weekStart}>
            <h2>
              Week of {week.monday.toLocaleDateString("en-GB", {
                timeZone: DISPLAY_TZ, day: "2-digit", month: "short",
              })}
            </h2>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
                gap: "0.8rem",
              }}
            >
              {[...week.days.entries()].sort(([a], [b]) => a.localeCompare(b)).map(
                ([day, items]) => (
                  <div
                    key={day}
                    style={{
                      border: "1px solid var(--border, #333)",
                      borderRadius: 8,
                      padding: "0.5rem",
                      minWidth: 0,
                    }}
                  >
                    <strong className="small">{day}</strong>
                    <div style={{ display: "grid", gap: "0.5rem", marginTop: "0.4rem" }}>
                      {items
                        .slice()
                        .sort((a, b) => a.local_time.localeCompare(b.local_time))
                        .map((s) => (
                          <div
                            key={s.id}
                            style={{
                              border: s.conflict ? "2px solid #f85149" : "1px solid transparent",
                              borderRadius: 6,
                              padding: "0.35rem 0.4rem",
                            }}
                          >
                            <div>
                              <span className="time">{timeLabel(s.local_time)}</span>{" "}
                              <strong>{s.platform}</strong>
                            </div>
                            <a className="small" href={`/offers/${s.offer_id}`}>
                              {s.offer_title}
                            </a>
                            {s.conflict && (
                              <div className="small" style={{ color: "#f85149" }}>
                                ⚠ {s.platform} posts again within an hour — move one BEFORE
                                approving (double-posting reads as spam to the audience and
                                the platform).
                              </div>
                            )}
                            <div
                              className="small"
                              style={{ marginTop: "0.2rem" }}
                            >
                              <span
                                className="badge"
                                style={{
                                  color: STATE_COLORS[s.state] ?? "#8b949e",
                                  borderColor: STATE_COLORS[s.state] ?? "#8b949e",
                                }}
                              >
                                {s.state}
                              </span>
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                ),
              )}
            </div>
            {/* Full controls stay under each week for actionable states */}
            <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.9rem" }}>
              {[...week.days.values()].flat().sort((a, b) => a.local_time.localeCompare(b.local_time)).map((s) => {
                let outcome: string | null = null;
                let held = false;
                let openAttempt = false;
                if (s.outcome_detail) {
                  try {
                    const parsed = JSON.parse(s.outcome_detail);
                    outcome = parsed?.detail ?? null;
                    held = Boolean(parsed?.hold);
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
                        {s.conflict && (
                          <div className="small" style={{ color: "#f85149" }}>
                            ⚠ {s.platform} posts again within an hour — move one BEFORE
                            approving (double-posting reads as spam to the audience and
                            the platform).
                          </div>
                        )}
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
