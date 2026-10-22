"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Resolve an inbox candidate without hand-calling the API.
 *
 * Promote uses the existing `/offers/from-item/{id}` endpoint, which creates a
 * tracked offer in `candidate` state and marks the item processed. Dismiss
 * marks the item processed so it leaves the queue. The offer still has to earn
 * `verified` through the review desk — promotion is not verification.
 */
export function InboxActions({
  itemId,
  provider,
  category,
}: {
  itemId: string;
  provider: string | null;
  category: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<"promote" | "dismiss" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function promote() {
    setBusy("promote");
    setMessage(null);
    try {
      const res = await clientFetch(`/offers/from-item/${itemId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider || "Unknown provider",
          category: category || "domains",
          offer_type: "discount",
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      router.push(`/offers/${body.id}`);
    } catch {
      setMessage("API unreachable");
    } finally {
      setBusy(null);
    }
  }

  async function dismiss() {
    setBusy("dismiss");
    setMessage(null);
    try {
      const res = await clientFetch(
        `/items/${itemId}/processed?processed=true`,
        { method: "PATCH" },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setMessage(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setMessage("API unreachable");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      <button
        type="button"
        className="btn btn-primary"
        style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }}
        onClick={promote}
        disabled={busy !== null}
      >
        {busy === "promote" ? "Promoting…" : "Promote"}
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }}
        onClick={dismiss}
        disabled={busy !== null}
      >
        {busy === "dismiss" ? "Dismissing…" : "Dismiss"}
      </button>
      {message && (
        <span className="small muted" role="status" style={{ maxWidth: 220 }}>
          {message}
        </span>
      )}
    </div>
  );
}
