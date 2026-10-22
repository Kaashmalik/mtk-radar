"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";

/**
 * Release readiness (plan §17) — the SAME gate the upload authorization runs,
 * surfaced to the human before anything is released.
 *
 * For every queued schedule we show the structured problem list from
 * `GET /schedules/{id}/release-check` (package completeness, playback
 * sign-off, offer freshness, format/claim binding). Nothing here bypasses the
 * gate: it explains it. Cancelling is a human decision — the API refuses
 * machine credentials — and records the reason.
 */

type Problem = { code: string; detail: string };

const CODE_LABELS: Record<string, string> = {
  offer_state: "Offer needs re-approval",
  offer_freshness: "Offer freshness (recheck/expiry)",
  render_missing: "No pinned render",
  render_qc: "Render is not QC-passed",
  script_hash: "Script version mismatch",
  offer_mismatch: "Render belongs to another offer",
  language_mismatch: "Render language mismatch",
  render_bytes_changed: "Render bytes changed after approval",
  claim_outcome: "Claim not demonstrated on camera",
  capture_review: "Capture redaction review missing",
  package_incomplete: "Package incomplete (thumbnail/captions/metadata)",
  playback_review: "Missing human playback sign-off",
  open_attempt: "Upload attempt still open",
};

export function ReleaseReadiness({
  schedules,
}: {
  schedules: {
    id: string;
    platform: string;
    state: string;
    local_time: string;
  }[];
}) {
  const router = useRouter();
  const queued = schedules.filter((s) =>
    ["approved", "scheduled", "paused"].includes(s.state),
  );
  const [checks, setChecks] = useState<Record<string, { ok: boolean; problems: Problem[] } | "error">>({});
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [note, setNote] = useState("Withdrawing this queued post (operator decision)");
  const [busy, setBusy] = useState(false);

  const check = useCallback(async (id: string) => {
    try {
      const res = await clientFetch(`/schedules/${id}/release-check`);
      const body = await res.json().catch(() => null);
      if (!res.ok || !body || typeof body.ok !== "boolean") {
        setChecks((prev) => ({ ...prev, [id]: "error" }));
        return;
      }
      setChecks((prev) => ({ ...prev, [id]: { ok: body.ok, problems: body.problems ?? [] } }));
    } catch {
      setChecks((prev) => ({ ...prev, [id]: "error" }));
    }
  }, []);

  useEffect(() => {
    for (const s of queued) void check(s.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queued.map((s) => s.id).join(",")]);

  async function cancel(id: string) {
    if (!note.trim()) return;
    setBusy(true);
    try {
      const res = await clientFetch(`/schedules/${id}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note.trim() }),
      });
      if (res.ok) {
        setCancelling(null);
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  if (queued.length === 0) return null;

  return (
    <div className="release-readiness">
      {queued.map((s) => {
        const result = checks[s.id];
        return (
          <div className="release-item" key={s.id}>
            <div className="release-item-head">
              <strong>
                {s.platform} · {s.state}
              </strong>
              <span>{new Date(s.local_time).toLocaleString()}</span>
              {result === undefined && <span className="tag">checking…</span>}
              {result === "error" && <span className="tag tag-hot">gate unreachable</span>}
              {result && result !== "error" && (
                <span className={`tag ${result.ok ? "tag-ok" : "tag-hot"}`}>
                  {result.ok ? "release-ready" : "blocked by release gate"}
                </span>
              )}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => void check(s.id)}
                title="Re-run the release check"
              >
                ↻
              </button>
            </div>
            {result && result !== "error" && !result.ok && (
              <ul className="release-problems">
                {result.problems.map((p) => (
                  <li key={p.code}>
                    <strong>{CODE_LABELS[p.code] ?? p.code}</strong>
                    {p.detail ? ` — ${p.detail}` : ""}
                  </li>
                ))}
              </ul>
            )}
            {cancelling === s.id ? (
              <div className="cancel-confirm">
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={1000}
                  aria-label="Cancellation reason"
                />
                <button type="button" className="btn" disabled={busy} onClick={() => void cancel(s.id)}>
                  Confirm cancel
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setCancelling(null)}>
                  Keep queued
                </button>
              </div>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={() => setCancelling(s.id)}>
                Cancel post…
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
