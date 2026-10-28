"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";


type Props = { scheduleId: string; state: string };

/** Operator controls — pause is always visible; resume/approve revalidate hashes. */
export default function ScheduleActions({ scheduleId, state }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState(false);
  const [newTime, setNewTime] = useState("");

  async function call(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(path, {
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
        { to: "needs_approval" },
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
          { to: "scheduled", acknowledge_unknown_attempt: true },
        );
      },
    });
  }
  if (state === "needs_approval") {
    buttons.push({
      label: "✓ Approve",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "approved" }),
    });
  }
  if (state === "approved") {
    buttons.push({
      label: "🗓 Schedule",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "scheduled" }),
    });
  }
  if (state === "approved" || state === "scheduled" || state === "failed") {
    buttons.push({ label: "⏸ Pause", action: () => call(`/schedules/${scheduleId}/pause`) });
  }
  if (state === "scheduled" || state === "paused" || state === "failed") {
    buttons.push({
      label: "⏱ Reschedule",
      action: () => {
        setRescheduling((v) => !v);
        setNewTime("");
      },
    });
  }

  async function reschedule() {
    if (!newTime) return;
    const iso = new Date(newTime);
    if (Number.isNaN(iso.getTime()) || iso.getTime() <= Date.now()) {
      setError("Pick a future date and time — to pull a post entirely, cancel it.");
      return;
    }
    await call(`/schedules/${scheduleId}/reschedule`, {
      local_time: iso.toISOString(),
      note: "rescheduled from the calendar",
    });
    setRescheduling(false);
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
      {rescheduling && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6 }}>
          <input
            type="datetime-local"
            value={newTime}
            onChange={(e) => setNewTime(e.target.value)}
            aria-label="New publish time"
            style={{
              padding: "0.25rem 0.45rem",
              fontSize: "0.75rem",
              borderRadius: 6,
              border: "1px solid #30363d",
              background: "var(--bg-inset)",
              color: "#e8eaf0",
              colorScheme: "dark",
            }}
          />
          <button
            type="button"
            disabled={busy || !newTime}
            onClick={reschedule}
            style={{
              padding: "0.25rem 0.6rem",
              fontSize: "0.75rem",
              borderRadius: 6,
              border: "1px solid #30363d",
              background: "#1f3a25",
              color: "#e8eaf0",
              cursor: busy ? "wait" : "pointer",
            }}
          >
            {busy ? "Moving…" : "Confirm new slot"}
          </button>
        </div>
      )}
      {error && <p style={{ color: "#f85149", fontSize: "0.72rem", margin: "0.3rem 0 0" }}>{error}</p>}
    </div>
  );
}
