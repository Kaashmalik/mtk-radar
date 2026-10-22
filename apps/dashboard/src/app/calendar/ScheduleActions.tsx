"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";
import { getReviewerName } from "@/lib/identity";


type Props = { scheduleId: string; state: string };

/** Operator controls — pause is always visible; resume/approve revalidate hashes. */
export default function ScheduleActions({ scheduleId, state }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError(null);
    try {
      const url = path.includes("?") || body !== undefined
        ? path
        : `${path}?reviewer=${encodeURIComponent(getReviewerName())}`;
      const res = await clientFetch(url, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const buttons: Array<{ label: string; action: () => void }> = [];
  if (state === "draft") {
    buttons.push({
      label: "→ Needs approval",
      action: () => call(
        `/schedules/${scheduleId}/transition`,
        { to: "needs_approval", reviewer: getReviewerName() },
      ),
    });
  }
  if (state === "failed" || state === "paused") {
    buttons.push({
      label: state === "paused" ? "▶ Resume" : "↻ Retry",
      action: () => {
        // A failed post may have uploaded before the error was recorded. The
        // worker re-confirms a known remote id, but an unknown outcome must be
        // checked by a human before this post is allowed back in the queue.
        const ok = window.confirm(
          "Only continue after checking the platform. If a previous upload's " +
          "outcome is unknown, it may already be live and retrying could " +
          "publish a duplicate. Continue?",
        );
        if (!ok) return;
        call(
          `/schedules/${scheduleId}/transition`,
          {
            to: "scheduled",
            reviewer: getReviewerName(),
            acknowledge_unknown_attempt: true,
          },
        );
      },
    });
  }
  if (state === "needs_approval") {
    buttons.push({
      label: "✓ Approve",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "approved", reviewer: getReviewerName() }),
    });
  }
  if (state === "approved") {
    buttons.push({
      label: "🗓 Schedule",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "scheduled", reviewer: getReviewerName() }),
    });
  }
  if (state === "approved" || state === "scheduled" || state === "failed") {
    buttons.push({ label: "⏸ Pause", action: () => call(`/schedules/${scheduleId}/pause`) });
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {buttons.map((b) => (
          <button
            key={b.label}
            disabled={busy}
            onClick={b.action}
            style={{
              padding: "0.25rem 0.6rem",
              fontSize: "0.75rem",
              borderRadius: 6,
              border: "1px solid #30363d",
              background: b.label.startsWith("⏸") ? "#62222a" : "#21262d",
              color: "#e8eaf0",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {b.label}
          </button>
        ))}
      </div>
      {error && <p style={{ color: "#f85149", fontSize: "0.72rem", margin: "0.3rem 0 0" }}>{error}</p>}
    </div>
  );
}
