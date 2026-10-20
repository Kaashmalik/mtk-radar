"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REVIEWER = "kashif"; // TODO(week-5): real session identity

type Props = { offerId: string; state: string };

/** Reviewer actions. The API enforces every gate — buttons only propose. */
export default function OfferActions({ offerId, state }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function transition(to: string, note?: string) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API}/offers/${offerId}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to, reviewer: REVIEWER, note }),
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
  if (state === "verified") {
    actions.push({ to: "approved_for_video", label: "✓ Approve for video" });
  }
  if (state === "verified" || state === "approved_for_video") {
    actions.push({ to: "evidence_needed", label: "↻ Request re-verification" });
  }
  if (state !== "published" && state !== "expired") {
    actions.push({ to: "expired", label: "Mark expired" });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {actions.map((a) => (
          <button
            key={a.to}
            disabled={busy}
            onClick={() => transition(a.to, a.note)}
            style={{
              padding: "0.3rem 0.65rem",
              fontSize: "0.78rem",
              borderRadius: 6,
              border: "1px solid #30363d",
              background: a.to === "approved_for_video" ? "#238636" : "#21262d",
              color: "#e8eaf0",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {a.label}
          </button>
        ))}
      </div>
      {error && <span style={{ color: "#f85149", fontSize: "0.72rem" }}>{error}</span>}
    </div>
  );
}
