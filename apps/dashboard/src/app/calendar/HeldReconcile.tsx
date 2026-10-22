"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Reconcile a HELD/unknown upload after checking the platform.
 *
 * The worker cannot know whether an upload that timed out is live. A human must
 * look, then record one of three outcomes. Confirming "published" requires the
 * remote post id that was actually observed; an open attempt is never cleared
 * silently.
 */
export default function HeldReconcile({
  scheduleId,
  remotePostId,
}: {
  scheduleId: string;
  remotePostId: string | null;
}) {
  const router = useRouter();
  const [remoteId, setRemoteId] = useState(remotePostId ?? "");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reconcile(outcome: "published" | "not_live" | "still_processing") {
    if (outcome === "published" && !window.confirm(
      "Confirm this post is live on the platform with the remote post id below?",
    )) {
      return;
    }
    setBusy(outcome);
    setError(null);
    try {
      const res = await clientFetch(`/schedules/${scheduleId}/reconcile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          outcome,
          remote_post_id: outcome === "published" ? remoteId.trim() : null,
          remote_url: outcome === "published" ? remoteUrl.trim() || null : null,
          note: note.trim(),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="warnbox" style={{ marginTop: 8 }}>
      <strong className="small">Unknown upload outcome — reconcile before retrying</strong>
      <p className="muted small" style={{ margin: "0.35rem 0" }}>
        Open the platform account. If the post is there, record its id. If it is
        not, mark it not live before re-queueing. Never retry blind.
      </p>
      <div style={{ display: "grid", gap: 5, maxWidth: 460 }}>
        <label htmlFor={`remote-id-${scheduleId}`} className="small">Remote post id (required to confirm live)</label>
        <input
          id={`remote-id-${scheduleId}`}
          value={remoteId}
          onChange={(event) => setRemoteId(event.target.value)}
          placeholder="e.g. YouTube video id"
        />
        <label htmlFor={`remote-url-${scheduleId}`} className="small">Remote URL (optional)</label>
        <input
          id={`remote-url-${scheduleId}`}
          type="url"
          value={remoteUrl}
          onChange={(event) => setRemoteUrl(event.target.value)}
          placeholder="https://…"
        />
        <label htmlFor={`reconcile-note-${scheduleId}`} className="small">What you checked (required, min 3 chars)</label>
        <input
          id={`reconcile-note-${scheduleId}`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Checked channel uploads; video is private/live/absent"
        />
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-primary btn-small"
            disabled={busy !== null || !remoteId.trim() || note.trim().length < 3}
            onClick={() => reconcile("published")}
          >
            {busy === "published" ? "Saving…" : "Confirmed live"}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-small"
            disabled={busy !== null || note.trim().length < 3}
            onClick={() => reconcile("not_live")}
          >
            {busy === "not_live" ? "Saving…" : "Not live — safe to retry"}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-small"
            disabled={busy !== null || note.trim().length < 3}
            onClick={() => reconcile("still_processing")}
          >
            {busy === "still_processing" ? "Saving…" : "Still processing"}
          </button>
        </div>
        {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      </div>
    </div>
  );
}
