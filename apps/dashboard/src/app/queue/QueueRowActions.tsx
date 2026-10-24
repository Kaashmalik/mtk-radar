"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Production-queue row actions (v0.35, WP-C). Archive and pin-to-top are
 * operator overrides — they only reorder/remove proposals; the human gates
 * downstream (verification, capture, approval) are untouched.
 */
export function QueueRowActions({
  id,
  pinned,
  onArchived,
}: {
  id: string;
  pinned: number | null;
  onArchived?: (id: string) => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [gone, setGone] = useState(false);

  if (gone) return null;

  async function archive() {
    setBusy("archive");
    try {
      const res = await clientFetch(`/queue/${id}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "operator archived from the queue page" }),
      });
      if (res.ok) {
        setGone(true);
        onArchived?.(id);
        router.refresh();
      }
    } finally {
      setBusy(null);
    }
  }

  async function pinTop() {
    if (pinned !== null) return; // already pinned: reorder owns the order
    setBusy("pin");
    try {
      // Read the current ready list from the server-rendered ordering this row
      // belongs to; the queue page passes ids via the data attribute below.
      const container = document?.getElementById("production-queue-list");
      const ids: string[] = JSON.parse(container?.dataset.ids ?? "[]");
      const order = [id, ...ids.filter((other) => other !== id)];
      const res = await clientFetch("/queue/reorder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: order }),
      });
      if (res.ok) router.refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <span style={{ display: "inline-flex", gap: "0.4rem", flexWrap: "wrap" }}>
      {pinned === null && (
        <button
          className="btn btn-ghost"
          type="button"
          onClick={pinTop}
          disabled={busy !== null}
          title="Pin this row above the computed ranking"
        >
          {busy === "pin" ? "Pinning…" : "📌 Pin top"}
        </button>
      )}
      <button
        className="btn btn-ghost"
        type="button"
        onClick={archive}
        disabled={busy !== null}
        title="Archive this row (with a recorded reason)"
      >
        {busy === "archive" ? "Archiving…" : "Archive"}
      </button>
    </span>
  );
}
