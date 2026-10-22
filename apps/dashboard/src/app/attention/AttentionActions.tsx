"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientFetch } from "@/lib/api-client";
import { getReviewerName } from "@/lib/identity";

type Props = {
  kind: string;
  entityId: string | null;
  action: string;
};

/** One-click approval only for the two explicit approval gates. Everything
 * else deep-links to its full review screen so context is never lost. */
export default function AttentionActions({ kind, entityId, action }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!entityId || (kind !== "offer_approval" && kind !== "schedule_approval")) {
    return null;
  }

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const path = kind === "offer_approval"
        ? `/offers/${entityId}/transition`
        : `/schedules/${entityId}/transition`;
      const body = kind === "offer_approval"
        ? { to: "approved_for_video", reviewer: getReviewerName() }
        : { to: "approved", reviewer: getReviewerName() };
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

  return (
    <span className="attention-action">
      <button type="button" className="btn btn-primary btn-small" onClick={approve} disabled={busy}>
        {busy ? "Approving…" : action}
      </button>
      {error && <span className="muted small" role="alert"> {error}</span>}
    </span>
  );
}
