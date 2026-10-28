"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";

type Props = { offerId: string; state: string };

/** Reviewer actions. The API enforces every gate — buttons only propose.
 * Identity: a reviewer token binds the actor server-side (v0.16); the name
 * is a fallback for dev-open APIs. */
export default function OfferActions({ offerId, state }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");

  async function transition(to: string, note?: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to, note }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const actions: Array<{ to: string; label: string; note?: string }> = [];
  if (["candidate", "evidence_needed", "corrected"].includes(state)) {
    actions.push({ to: "verified", label: "✓ Verify evidence" });
  }
  if (state === "verified") {
    actions.push({ to: "approved_for_video", label: "✓ Approve for video" });
  }
  if (state === "verified" || state === "approved_for_video") {
    actions.push({ to: "evidence_needed", label: "↻ Request re-verification" });
  }
  if (state !== "published" && state !== "expired") {
    actions.push({ to: "expired", label: "Mark expired" });
  }

  if (actions.length === 0) {
    return null;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Reason / source note (recorded in the audit log)"
        aria-label="Reason or source note"
        style={{
          padding: "0.3rem 0.45rem",
          fontSize: "0.74rem",
          borderRadius: 6,
          border: "1px solid #30363d",
          background: "var(--bg-inset)",
          color: "#e8eaf0",
        }}
      />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {actions.map((a) => (
          <button
            key={a.to}
            disabled={busy}
            onClick={() => transition(a.to, note.trim() || a.note)}
            style={{
              padding: "0.3rem 0.65rem",
              fontSize: "0.78rem",
              borderRadius: 6,
              border: "1px solid #30363d",
              background: a.to === "approved_for_video" || a.to === "verified"
                ? "#238636" : "#21262d",
              color: "#e8eaf0",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {a.label}
          </button>
        ))}
      </div>
      {error && <span style={{ color: "var(--danger)", fontSize: "0.72rem" }}>{error}</span>}
    </div>
  );
}
