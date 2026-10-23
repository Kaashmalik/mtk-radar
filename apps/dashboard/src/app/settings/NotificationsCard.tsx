"use client";

import { useState } from "react";

import { clientFetch } from "@/lib/api-client";

type ProbeResult = {
  configured: boolean;
  ok: boolean;
  status?: number | null;
  detail?: string | null;
};

/** Human-only webhook delivery probe (v0.33). The API returns an honest
 * contract: `configured: false` means no webhook is set in this environment —
 * it never fakes a successful delivery. SMTP stays testable from the monitor
 * worker CLI (`--test-notification`), which owns the email credentials. */
export default function NotificationsCard() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ProbeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function test() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await clientFetch("/settings/test-notification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        const detail = data?.detail;
        setError(typeof detail === "string" ? detail : `HTTP ${res.status}`);
        return;
      }
      setResult(data as ProbeResult);
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Notifications</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        Sends ONE test event to the alert webhook configured in the deployment
        environment (<code>MTK_NOTIFY_WEBHOOK_URL</code>). Nothing is stored;
        delivery is reported honestly, including &ldquo;not configured&rdquo;.
        Email delivery is tested from the monitor worker CLI.
      </p>
      <button type="button" className="btn btn-primary" onClick={test} disabled={busy}>
        {busy ? "Sending test…" : "Send test notification"}
      </button>
      {result && (
        <p
          className="small"
          role="status"
          style={{ marginTop: "0.6rem", color: result.ok ? "var(--ok)" : "var(--danger)" }}
        >
          {result.ok
            ? "✔ delivered"
            : result.configured
              ? "✖ not delivered"
              : "• not configured"}{" "}
          <span className="muted">
            {result.status != null ? `(HTTP ${result.status}) ` : ""}
            {result.detail}
          </span>
        </p>
      )}
      {error && (
        <p className="small" role="alert" style={{ color: "var(--danger)", marginTop: "0.6rem" }}>
          {error}
        </p>
      )}
    </section>
  );
}
