"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";
import MediaPlayer from "./MediaPlayer";

export type CaptureReview = {
  id: string;
  redaction_reviewed: boolean;
  findings: unknown;
  reviewer: string | null;
  claim_outcome: string | null;
  claim_outcome_reviewer: string | null;
};

/**
 * Release-blocking redaction review. Approving means the reviewer watched the
 * footage/terminal/captions; it also records what actually happened so a script
 * cannot claim a success that was never demonstrated.
 */
export default function RedactionReview({
  capture,
  videoPath,
}: {
  capture: CaptureReview;
  videoPath: string | null;
}) {
  const router = useRouter();
  const [approved, setApproved] = useState(true);
  const [outcome, setOutcome] = useState("not_attempted");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const findings = formatFindings(capture.findings);

  if (capture.redaction_reviewed) {
    return (
      <div className="small" style={{ marginTop: 4 }}>
        <span style={{ color: "var(--ok)" }}>redaction reviewed ✓</span>
        {capture.reviewer && <> by {capture.reviewer}</>}
        {capture.claim_outcome && (
          <> · claim outcome: <strong>{capture.claim_outcome.replaceAll("_", " ")}</strong></>
        )}
        {capture.claim_outcome_reviewer && (
          <> (attested by {capture.claim_outcome_reviewer})</>
        )}
        {videoPath && <MediaPlayer kind="captures" id={capture.id} label="footage" />}
      </div>
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/captures/${capture.id}/redaction-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved,
          note: note.trim() || null,
          ...(approved ? { claim_outcome: outcome } : {}),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(detailText(body.detail) ?? `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 6, marginTop: 8 }}>
      <div className="small">
        Secret scan:{" "}
        {findings.length ? (
          <span style={{ color: "var(--warn)" }}>{findings.join(", ")}</span>
        ) : (
          <span style={{ color: "var(--ok)" }}>no pattern matches</span>
        )}
        {videoPath && (
          <>
            <div className="muted small">Footage: <code>{videoPath}</code></div>
            <MediaPlayer kind="captures" id={capture.id} label="footage" />
          </>
        )}
      </div>
      <p className="muted small" style={{ margin: 0 }}>
        The scan is not the review. Watch the footage, terminal output and
        captions; then record what happened.
      </p>

      <label className="small" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input type="checkbox" checked={approved} onChange={(event) => setApproved(event.target.checked)} />
        Footage is clean and safe to release
      </label>

      {approved && (
        <>
          <label htmlFor={`outcome-${capture.id}`} className="small">What did the capture show?</label>
          <select
            id={`outcome-${capture.id}`}
            value={outcome}
            onChange={(event) => setOutcome(event.target.value)}
          >
            <option value="demonstrated">Benefit demonstrated in the footage</option>
            <option value="not_demonstrated">Steps ran, benefit not demonstrated</option>
            <option value="not_attempted">Benefit not attempted (setup only)</option>
          </select>
        </>
      )}

      <label htmlFor={`review-note-${capture.id}`} className="small">Review note</label>
      <input
        id={`review-note-${capture.id}`}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="What you checked (required when rejecting)"
        required={!approved}
      />

      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      <button
        type="submit"
        className={approved ? "btn btn-primary btn-small" : "btn btn-danger btn-small"}
        disabled={busy || (!approved && note.trim().length < 3)}
      >
        {busy ? "Recording…" : approved ? "Approve redaction" : "Reject redaction"}
      </button>
    </form>
  );
}

function formatFindings(raw: unknown): string[] {
  let value: unknown = raw;
  if (typeof raw === "string") {
    try { value = JSON.parse(raw); } catch { return [raw]; }
  }
  if (Array.isArray(value)) return value.map((item) => String(item));
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(
      ([key, count]) => `${key} ×${String(count)}`,
    );
  }
  return [];
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
