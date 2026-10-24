"use client";

/**
 * One-click Start Automation (v0.30).
 *
 * The button arms a safe policy preset — it never starts Docker. The host
 * launcher (`scripts/mtk-start.sh`) owns the worker stack, and a fresh
 * server-side preflight refuses to arm if a worker is missing, a connection
 * is dead, or an unattended mode has no alert channel.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { clientFetch } from "@/lib/api-client";

type CheckStatus = "pass" | "warn" | "fail";

type PreflightCheck = {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  blocking: boolean;
};

type Preflight = {
  generated_at: string;
  mode: string;
  ready: boolean;
  blocking: PreflightCheck[];
  warnings: PreflightCheck[];
  checks: PreflightCheck[];
  worker_status: {
    expected_count: number;
    online_count: number;
    all_online: boolean;
    workers: { name: string; label: string; state: string; online: boolean }[];
  };
  attention: { total: number; counts: Record<string, number>; severity: string };
  policy: { mode: string; paused: boolean; dry_run: boolean };
};

type Policy = {
  mode: string;
  paused: boolean;
  dry_run: boolean;
  stages: Record<string, string>;
  guardrails: Record<string, unknown>;
};

const MODES = [
  ["assisted", "Start assisted", "Collect, verify, script and render automatically. You approve and schedule every post."],
  ["autopilot_private", "Start autopilot · private", "Every stage may advance inside guardrails. Uploads stay private; two auto-approved posts/day."],
] as const;

function icon(status: CheckStatus): string {
  if (status === "pass") return "✓";
  if (status === "warn") return "!";
  return "✕";
}

function StatusRow({ check }: { check: PreflightCheck }) {
  return (
    <li className={`preflight-check preflight-${check.status}`}>
      <span className="preflight-icon" aria-hidden="true">{icon(check.status)}</span>
      <span>
        <strong>{check.label}</strong>
        <span className="muted small"> — {check.detail}</span>
      </span>
    </li>
  );
}

export default function AutomationCard() {
  const router = useRouter();
  const [report, setReport] = useState<Preflight | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showChecks, setShowChecks] = useState(false);

  const load = useCallback(async () => {
    try {
      const pol = await clientFetch("/automation/policy", { cache: "no-store" });
      let policyMode = "assisted";
      if (pol.ok) {
        const body = (await pol.json()) as { policy: Policy };
        setPolicy(body.policy);
        policyMode = body.policy.mode === "autopilot" ? "autopilot_private" : "assisted";
      }
      const pre = await clientFetch(
        `/automation/preflight?mode=${encodeURIComponent(policyMode)}`,
        { cache: "no-store" },
      );
      if (pre.ok) setReport((await pre.json()) as Preflight);
    } catch {
      setError("API unreachable — cannot check automation readiness.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runNow() {
    setBusy("run-now");
    setError(null);
    setMessage(null);
    try {
      const res = await clientFetch("/automation/run-now", { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      const armed = (body.armed ?? {}) as Record<string, number>;
      const summary = Object.entries(armed)
        .filter(([, n]) => n > 0)
        .map(([stage, n]) => `${stage} ${n}`)
        .join(" · ");
      setMessage(
        summary
          ? `Owed work armed now: ${summary}. Human gates untouched.`
          : "Nothing owed right now — every unattended stage is already current.",
      );
      router.refresh();
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(null);
    }
  }

  async function start(mode: string) {
    if (mode === "autopilot_public") {
      const ok = window.confirm(
        "Public autopilot publishes without a human approval step. Start with ONE post/day and only after 10–20 clean private videos. Continue?",
      );
      if (!ok) return;
    }
    setBusy(mode);
    setError(null);
    setMessage(null);
    try {
      const res = await clientFetch("/automation/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          confirm_public: mode === "autopilot_public",
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = body?.detail;
        if (detail && typeof detail === "object" && detail.preflight) {
          setReport(detail.preflight as Preflight);
          setError(String(detail.message ?? "Preflight failed."));
        } else {
          setError(typeof detail === "string" ? detail : `HTTP ${res.status}`);
        }
        return;
      }
      if (body?.policy) setPolicy(body.policy as Policy);
      if (body?.preflight) setReport(body.preflight as Preflight);
      setMessage(
        mode === "assisted"
          ? "Assisted automation is armed. Watch Needs You for approvals and redaction reviews."
          : "Autopilot is armed inside the guardrails. A failed worker or dead token will page you.",
      );
      router.refresh();
    } catch {
      setError("API unreachable — automation was not armed.");
    } finally {
      setBusy(null);
    }
  }

  async function stop() {
    setBusy("stop");
    setError(null);
    setMessage(null);
    try {
      const res = await clientFetch("/automation/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      if (body?.policy) setPolicy(body.policy as Policy);
      setMessage("Automation stopped. Scheduled posts are not cancelled; humans can still act.");
      router.refresh();
    } catch {
      setError("API unreachable — the stop request was not recorded.");
    } finally {
      setBusy(null);
    }
  }

  const paused = policy?.paused ?? report?.policy.paused ?? false;
  const activeMode = policy?.mode ?? report?.policy.mode ?? "assisted";
  const online = report?.worker_status.all_online ?? false;
  const attention = report?.attention.total ?? 0;

  return (
    <section className="panel automation-card">
      <div className="panel-head">
        <div>
          <h2>Start automation</h2>
          <p>
            The launcher starts the workers; this button verifies them and arms a
            safe policy. Nothing here bypasses verification, redaction or approval.
          </p>
        </div>
        <Link href="/attention" className="btn btn-ghost">
          Needs You{attention ? ` · ${attention}` : ""}
        </Link>
      </div>

      <div className="automation-status">
        <span className={`tag ${paused ? "tag-warn" : activeMode === "autopilot" ? "tag-hot" : "tag-accent"}`}>
          {paused ? "paused" : activeMode}
        </span>
        <span className={`small ${online ? "ok" : "down"}`}>
          {report
            ? `${report.worker_status.online_count}/${report.worker_status.expected_count} workers online`
            : "checking workers…"}
        </span>
        {report && (
          <button
            type="button"
            className="btn btn-ghost btn-small"
            onClick={() => setShowChecks((v) => !v)}
          >
            {showChecks ? "Hide checks" : `Preflight ${report.ready ? "ready" : "blocked"} · ${report.checks.length}`}
          </button>
        )}
      </div>

      {showChecks && report && (
        <ul className="preflight-list" aria-live="polite">
          {report.checks.map((check) => <StatusRow key={check.id} check={check} />)}
        </ul>
      )}

      {report && !report.ready && (
        <div className="notice notice-danger small">
          <strong>Start is blocked.</strong>{" "}
          {report.blocking.map((c) => c.label).join(", ")}. Run{" "}
          <code>scripts/mtk-start.sh</code> on the laptop host, then refresh.
          <span className="muted"> The browser never controls Docker directly.</span>
        </div>
      )}

      {error && <div className="notice notice-danger small" role="alert">{error}</div>}
      {message && <div className="notice notice-ok small" role="status">{message}</div>}

      <div className="automation-actions">
        {MODES.map(([mode, label, hint]) => (
          <button
            key={mode}
            type="button"
            className="btn btn-primary"
            title={hint}
            disabled={busy !== null}
            onClick={() => start(mode)}
          >
            {busy === mode
              ? "Checking…"
              : !paused && activeMode === "assisted" && mode === "assisted"
                ? "Re-arm assisted"
                : label}
          </button>
        ))}
        {!paused && activeMode !== "manual" && (
          <button type="button" className="btn btn-danger" onClick={stop} disabled={busy !== null}>
            {busy === "stop" ? "Stopping…" : "⏸ Stop automation"}
          </button>
        )}
        <button
          type="button"
          className="btn btn-ghost"
          title="Collect, trend-scan, script and render the owed backlog immediately. Never touches the human stages."
          disabled={busy !== null}
          onClick={runNow}
        >
          {busy === "run-now" ? "Arming…" : "▶ Run now"}
        </button>
        <Link href="/settings" className="btn btn-ghost">Guardrails &amp; budget</Link>
      </div>

      <p className="muted small automation-footnote">
        Autopilot stays private by default. Public publishing is a separate,
        explicit acknowledgement and is never armed by this button.
      </p>
    </section>
  );
}
