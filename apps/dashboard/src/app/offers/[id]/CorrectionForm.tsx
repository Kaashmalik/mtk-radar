"use client";

/** Records a correction (§3 Learn / §11 takedown workflow, v0.17). Legacy
 * free-text writes needed curl — this form makes the workflow first-class in
 * the desk: a correction demotes the offer (state machine rules), pauses
 * affected posts via the DB trigger, and is shown with the affected posts
 * below. The reviewer token binds `corrected_by` server-side. */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export default function CorrectionForm({ offerId }: { offerId: string }) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (note.trim().length < 3) {
      setError("describe what changed (≥3 chars)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setNote("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.4rem", maxWidth: "36rem" }}>
      <label htmlFor="correction-note" className="small" style={{ margin: 0 }}>
        Log a correction — what changed, and what it invalidates. Scheduled posts
        for this offer pause automatically; published posts stay listed below for
        manual follow-up.
      </label>
      <textarea
        id="correction-note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        placeholder="e.g. expired early — renewal now $49/yr; invalidates the pricing claims in v1"
        disabled={busy}
      />
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <button type="submit" disabled={busy || note.trim().length < 3}>
          {busy ? "Recording…" : "Record correction"}
        </button>
        {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
      </div>
    </form>
  );
}
