"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

type Row = {
  id: string;
  platform: string;
  offer_title: string;
  local_time: string;
  state: string;
};

type Result = { id: string; ok: boolean; state?: string; detail?: string };

/**
 * Batch approve & queue (WP-D) — a HUMAN bulk action on the calendar.
 *
 * The per-schedule rules, hash checks and audit are the single-transition
 * ones (`POST /schedules/batch-transition` fans out per id); this island only
 * saves the operator N clicks. Everything stays selected-by-default visible:
 * no "approve all" blindly — the operator sees every post they are about to
 * approve, and per-id results after the fact.
 */
export default function BatchApprove({ rows }: { rows: Row[] }) {
  const router = useRouter();
  const actionable = useMemo(
    () =>
      rows.filter((r) => r.state === "needs_approval" || r.state === "approved"),
    [rows],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Result[] | null>(null);

  // Select all actionable rows on first render (and after a refresh).
  const [initialized, setInitialized] = useState(false);
  if (!initialized && actionable.length > 0) {
    setInitialized(true);
    setSelected(new Set(actionable.map((r) => r.id)));
  }

  if (actionable.length === 0) return null;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run(to: "approved" | "scheduled") {
    // Only rows in the source state for this step are sent; the others stay
    // selected for the next step instead of coming back as conflicts.
    const fromState = to === "approved" ? "needs_approval" : "approved";
    const ids = actionable
      .filter((r) => selected.has(r.id) && r.state === fromState)
      .map((r) => r.id);
    if (ids.length === 0) return;
    if (to === "scheduled") {
      const ok = window.confirm(
        `Queue ${ids.length} approved post(s) for publishing? ` +
        "The release gate re-checks every row (offer freshness, script hash).",
      );
      if (!ok) return;
    }
    setBusy(to);
    setResults(null);
    try {
      const res = await clientFetch("/schedules/batch-transition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, to }),
      });
      const body = (await res.json().catch(() => ({}))) as
        | { results?: Result[]; detail?: string }
        | null;
      if (!res.ok) {
        setResults([{ id: "-", ok: false, detail: body?.detail ?? `HTTP ${res.status}` }]);
        return;
      }
      setResults(body?.results ?? []);
      setSelected(new Set());
      router.refresh();
    } catch {
      setResults([{ id: "-", ok: false, detail: "API unreachable" }]);
    } finally {
      setBusy(null);
    }
  }

  const needsApproval = actionable.filter((r) => r.state === "needs_approval");
  const approved = actionable.filter((r) => r.state === "approved");

  return (
    <section className="card">
      <h2>Batch approve &amp; queue ({selected.size} selected)</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        One human decision per post, N fewer clicks. Selection shows every post;
        approve from review, queue the approved ones into the publishing
        calendar. Service credentials can never do this — it is recorded under
        your reviewer identity.
      </p>

      <div style={{ display: "grid", gap: "0.4rem", margin: "0.6rem 0" }}>
        {actionable.map((r) => (
          <label
            key={r.id}
            style={{
              display: "flex", gap: "0.5rem", alignItems: "center",
              cursor: "pointer", fontSize: "0.85rem",
            }}
          >
            <input
              type="checkbox"
              checked={selected.has(r.id)}
              onChange={() => toggle(r.id)}
            />
            <strong>{r.platform}</strong>
            <span>{r.offer_title}</span>
            <span className="muted small">
              {new Date(r.local_time).toLocaleString("en-GB", {
                timeZone: "Asia/Karachi",
              })}
            </span>
            <span
              className="badge"
              style={{
                color: r.state === "approved" ? "var(--ok)" : "var(--warn)",
                borderColor: r.state === "approved" ? "var(--ok)" : "var(--warn)",
              }}
            >
              {r.state}
            </span>
          </label>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={busy !== null || needsApproval.length === 0 || selected.size === 0}
          title={needsApproval.length === 0 ? "nothing awaiting approval" : undefined}
          onClick={() => run("approved")}
        >
          {busy === "approved" ? "Approving…" : `✓ Approve selected (${needsApproval.length} ready)`}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy !== null || approved.length === 0 || selected.size === 0}
          title={approved.length === 0 ? "nothing approved to queue" : undefined}
          onClick={() => run("scheduled")}
        >
          {busy === "scheduled" ? "Queueing…" : `📅 Queue selected → calendar (${approved.length} ready)`}
        </button>
      </div>

      {results && (
        <ul className="small" style={{ margin: "0.6rem 0 0", paddingLeft: "1rem" }}>
          {results.map((r) => (
            <li key={r.id} style={{ color: r.ok ? "var(--ok)" : "var(--danger)" }}>
              {r.ok ? `✓ ${r.state ?? "done"}` : `✗ ${r.detail ?? "refused"}`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
