"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientFetch } from "@/lib/api-client";

type Props = {
  kind: string;
  entityId: string | null;
  action: string;
};

/** One-click approval only for the two explicit approval gates; dead jobs get
 * a one-click retry (POST /jobs/{id}/retry). Everything else deep-links to its
 * full review screen so context is never lost. */
export default function AttentionActions({ kind, entityId, action }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isApproval = kind === "offer_approval" || kind === "schedule_approval";
  const isRetryableJob = kind === "job" && entityId !== null;
  if (!entityId || (!isApproval && !isRetryableJob)) {
    return null;
  }

  async function retryJob() {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/jobs/${entityId}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        setError(typeof detail === "string" ? detail : `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const path = kind === "offer_approval"
        ? `/offers/${entityId}/transition`
        : `/schedules/${entityId}/transition`;
      // The proxy binds the reviewer token; no name is accepted from the body.
      const body = kind === "offer_approval"
        ? { to: "approved_for_video" }
        : { to: "approved" };
      const res = await clientFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        setError(typeof detail === "string" ? detail : `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  if (isRetryableJob) {
    return (
      <span className="attention-action">
        <button type="button" className="btn btn-primary btn-small" onClick={retryJob} disabled={busy}>
          {busy ? "Retrying…" : "↻ Retry job"}
        </button>
        {error && <span className="muted small" role="alert"> {error}</span>}
      </span>
    );
  }

  return (
    <span className="attention-action">
      <button type="button" className="btn btn-primary btn-small" onClick={approve} disabled={busy}>
        {busy ? "Approving…" : action}
      </button>
      {error && <span className="muted small" role="alert"> {error}</span>}
    </span>
  );
}
