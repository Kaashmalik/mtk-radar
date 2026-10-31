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
  privacy: string;
  language: string | null;
  render_id: string | null;
  platform_account_id: string | null;
  package_hash: string | null;
  conflict: boolean;
};

type Result = { id: string; ok: boolean; state?: string; detail?: string; already_queued?: boolean };

const REVIEWABLE = new Set(["draft", "needs_approval", "approved"]);

/**
 * Review → Approve & queue (G20) — ONE human decision after seeing the
 * exact packages.
 *
 * Every pending post is listed with what will actually go out (platform,
 * time, privacy, language, pinned render/account, package fingerprint).
 * Nothing is pre-selected: the operator ticks what they reviewed. The click
 * sends each post's package hash as the reviewed version; the API refuses a
 * package that changed since (stale preview), walks the ordinary
 * draft → needs_approval → approved → scheduled transitions per post in one
 * transaction, and returns per-post results. Retrying a partial result only
 * moves the posts that are still pending.
 */
export default function BatchApprove({ rows }: { rows: Row[] }) {
  const router = useRouter();
  const pending = useMemo(() => rows.filter((r) => REVIEWABLE.has(r.state)), [rows]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Record<string, Result> | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (pending.length === 0) return null;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const chosen = pending.filter((r) => selected.has(r.id));
  const publicCount = chosen.filter((r) => r.privacy === "public").length;

  async function approveAndQueue() {
    if (chosen.length === 0) return;
    const ok = window.confirm(
      `Approve and queue ${chosen.length} reviewed post(s)` +
      (publicCount ? ` — ${publicCount} will be PUBLIC` : "") +
      "? Each post is re-checked by the release gate; a package that changed " +
      "since you reviewed it is refused.",
    );
    if (!ok) return;
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const res = await clientFetch("/schedules/approve-and-queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          targets: chosen.map((r) => ({ id: r.id, expected_package_hash: r.package_hash })),
        }),
      });
      const body = (await res.json().catch(() => ({}))) as
        | { results?: Result[]; detail?: string }
        | null;
      if (!res.ok) {
        setError(body?.detail ?? `HTTP ${res.status}`);
        return;
      }
      const byId = Object.fromEntries((body?.results ?? []).map((r) => [r.id, r]));
      setResults(byId);
      // Keep failures selected so a retry only targets what is unresolved.
      setSelected(new Set(chosen.filter((r) => !byId[r.id]?.ok).map((r) => r.id)));
      router.refresh();
    } catch {
      setError("API unreachable — nothing was approved or queued");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card review-queue">
      <div className="panel-head">
        <div>
          <h2>Review &amp; queue ({pending.length} pending)</h2>
          <p>
            Tick the posts you reviewed, then approve and queue them in one step.
            Recorded under your reviewer identity; service credentials can never do this.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-small"
          onClick={() =>
            setSelected(selected.size === pending.length
              ? new Set()
              : new Set(pending.map((r) => r.id)))}
        >
          {selected.size === pending.length ? "Clear" : "Select all"}
        </button>
      </div>

      <div className="review-list">
        {pending.map((r) => {
          const outcome = results?.[r.id];
          return (
            <label key={r.id} className="review-item" data-selected={selected.has(r.id) || undefined}>
              <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
              <div className="review-item-main">
                <div className="review-item-title">
                  <strong>{r.platform}</strong>
                  <span className="truncate">{r.offer_title}</span>
                </div>
                <div className="chip-row">
                  <span className="tag">
                    {new Date(r.local_time).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} PKT
                  </span>
                  <span className={`tag ${r.privacy === "public" ? "tag-warn" : ""}`}>{r.privacy}</span>
                  <span className="tag">{(r.language ?? "en").toUpperCase()}</span>
                  <span className="tag">{r.render_id ? "render pinned" : "render: auto"}</span>
                  <span className="tag">{r.platform_account_id ? "account pinned" : "account: auto"}</span>
                  <span className="tag mono" title={r.package_hash ?? "no package yet"}>
                    pkg {r.package_hash ? r.package_hash.slice(0, 8) : "—"}
                  </span>
                  <span className="tag">{r.state.replace("_", " ")}</span>
                  {r.conflict && <span className="tag tag-warn">time conflict</span>}
                </div>
                {outcome && (
                  <p className="small review-outcome" data-ok={outcome.ok || undefined}>
                    {outcome.ok
                      ? outcome.already_queued ? "Already queued — no change" : `Queued (${outcome.state ?? "scheduled"})`
                      : outcome.detail ?? "refused"}
                  </p>
                )}
              </div>
            </label>
          );
        })}
      </div>

      <div className="schedule-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || chosen.length === 0}
          onClick={approveAndQueue}
        >
          {busy ? "Approving & queueing…" : `Approve & queue ${chosen.length || ""} reviewed`.trim()}
        </button>
        {publicCount > 0 && (
          <span className="small" style={{ color: "var(--warn)" }}>
            {publicCount} selected post(s) will be public
          </span>
        )}
        {error && <span className="small" role="alert" style={{ color: "var(--danger)" }}>{error}</span>}
      </div>
    </section>
  );
}
