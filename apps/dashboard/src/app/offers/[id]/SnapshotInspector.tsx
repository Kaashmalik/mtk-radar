"use client";

import { useState } from "react";

import { clientFetch } from "@/lib/api-client";

type Snapshot = {
  url: string;
  requested_url: string | null;
  captured_at: string | null;
  fetch_status: number | null;
  fetch_content_type: string | null;
  captured_text: string | null;
  captured_truncated: boolean | null;
  raw_text: string | null;
  raw_truncated: boolean | null;
  raw_preserved: boolean | null;
  raw_hash: string | null;
};

/**
 * On-demand inspection of the exact snapshot text a claim cites.
 *
 * The evidence list on the offer page is server-rendered metadata; the actual
 * captured text (and preserved raw bytes, when kept) is fetched only when the
 * operator opens it, and is never cached in the browser.
 */
export default function SnapshotInspector({
  offerId,
  evidenceId,
}: {
  offerId: string;
  evidenceId: string;
}) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(
        `/offers/${offerId}/evidence/${evidenceId}/snapshot?which=both`,
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(
          typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`,
        );
        return;
      }
      setSnap(body as Snapshot);
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  if (snap) {
    return (
      <div style={{ display: "grid", gap: "0.5rem" }}>
        {snap.captured_text ? (
          <div>
            <p className="small" style={{ margin: "0 0 0.25rem" }}>
              Captured text{snap.captured_truncated ? " (truncated to 200,000 chars)" : ""}:
            </p>
            <pre
              style={{
                maxHeight: 320,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                background: "var(--bg-inset, rgba(127,127,127,0.08))",
                padding: "0.5rem",
                borderRadius: 8,
                fontSize: "0.8rem",
              }}
            >
              {snap.captured_text}
            </pre>
          </div>
        ) : (
          <p className="muted small" style={{ margin: 0 }}>
            No captured text for this snapshot.
          </p>
        )}
        {snap.raw_preserved
          ? snap.raw_text && (
              <div>
                <p className="small" style={{ margin: "0 0 0.25rem" }}>
                  Raw bytes (decoded, hash-checked at ingest
                  {snap.raw_truncated ? ", truncated to 200,000 chars" : ""}):
                </p>
                <pre
                  style={{
                    maxHeight: 240,
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    background: "var(--bg-inset, rgba(127,127,127,0.08))",
                    padding: "0.5rem",
                    borderRadius: 8,
                    fontSize: "0.78rem",
                  }}
                >
                  {snap.raw_text}
                </pre>
              </div>
            )
          : (
              <p className="muted small" style={{ margin: 0 }}>
                Raw bytes were not preserved for this snapshot.
              </p>
            )}
        <p className="muted small" style={{ margin: 0 }}>
          Raw hash: <code>{snap.raw_hash ?? "—"}</code>
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 6 }}>
      <button
        type="button"
        className="btn btn-small"
        onClick={load}
        disabled={busy}
      >
        {busy ? "Loading snapshot…" : "Inspect snapshot text"}
      </button>
      {error && (
        <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>
          {error}
        </p>
      )}
    </div>
  );
}
