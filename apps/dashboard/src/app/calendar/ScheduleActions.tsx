"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";


type Props = { scheduleId: string; state: string };

/** Operator controls — pause is always visible; resume/approve revalidate hashes. */
export default function ScheduleActions({ scheduleId, state }: Props) {
  const router = useRouter();
  const REVIEWER = "kashif"; // TODO(week-10+): session identity
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function call(path: string, body?: unknown, method = "POST") {
    setBusy(true);
    setError(null);
    try {
      const url = path.includes("?") || body !== undefined
        ? path
        : `${path}?reviewer=${encodeURIComponent(REVIEWER)}`;
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
  if (state === "draft" || state === "failed" || state === "paused") {
    buttons.push({
      label: state === "paused" ? "▶ Resume" : "→ Needs approval",
      action: () =>
        call(
          `/schedules/${scheduleId}/transition`,
          { to: state === "paused" ? "scheduled" : "needs_approval", reviewer: REVIEWER },
        ),
    });
  }
  if (state === "needs_approval") {
    buttons.push({
      label: "✓ Approve",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "approved", reviewer: REVIEWER }),
    });
  }
  if (state === "approved") {
    buttons.push({
      label: "🗓 Schedule",
      action: () => call(`/schedules/${scheduleId}/transition`, { to: "scheduled", reviewer: REVIEWER }),
    });
  }
  if (state === "approved" || state === "scheduled") {
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
