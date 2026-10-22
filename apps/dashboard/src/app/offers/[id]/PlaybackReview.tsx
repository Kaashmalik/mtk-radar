"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";

/**
 * Human playback sign-off (plan §6.F) — the final gate before release.
 *
 * A measured QC report cannot tell you the narration matches the approved
 * script or the captions read correctly. A named human records that they
 * watched THIS export; the API refuses automation tokens, and the release
 * gate refuses renders without it.
 */
export function PlaybackReview({
  renderId,
  approved,
  reviewer,
  reviewedAt,
}: {
  renderId: string;
  approved: boolean | null;
  reviewer: string | null;
  reviewedAt: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(
    "Watched end to end: narration and captions match the approved script.",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(approved: boolean) {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/renders/${renderId}/playback-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, note: note.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setOpen(false);
      router.refresh();
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  if (open) {
    return (
      <span className="playback-review">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={1000}
          aria-label="Playback review note"
          style={{ minWidth: 240 }}
        />
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void submit(true)}>
          Approved
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void submit(false)}>
          Rejected
        </button>
        <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
          ✕
        </button>
        {error && <span style={{ color: "var(--danger)" }}>{error}</span>}
      </span>
    );
  }

  if (approved === null || reviewedAt === null) {
    return (
      <button type="button" className="btn btn-ghost" onClick={() => setOpen(true)}>
        Playback review…
      </button>
    );
  }

  return (
    <span className="playback-review">
      <span className={`tag ${approved ? "tag-ok" : "tag-hot"}`} title={reviewer ? `${reviewer}: ${reviewedAt}` : undefined}>
        {approved ? "playback approved" : "playback rejected"}
      </span>
      <button type="button" className="btn btn-ghost" onClick={() => setOpen(true)} title="Re-review this export">
        re-review…
      </button>
    </span>
  );
}
