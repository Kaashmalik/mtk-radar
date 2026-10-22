"use client";

/**
 * Automation control (v0.26) — the single place where the operator decides,
 * per pipeline stage, whether the system may act alone or must wait for a
 * named human. Every save is validated and audited by the API.
 *
 * The kill switch and dry-run controls are deliberately prominent: a
 * misconfigured autopilot must be stoppable in one click.
 */

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export type AutomationPolicy = {
  schema_version?: number;
  mode: string;
  paused: boolean;
  dry_run: boolean;
  stages: Record<string, string>;
  guardrails: {
    auto_verify_min_confidence: number;
    auto_verify_max_evidence_age_hours: number;
    auto_approve_requires_render: boolean;
    auto_approve_block_unsafe_commands: boolean;
    auto_schedule_platforms: string[];
    auto_schedule_privacy: string;
    auto_publish_max_per_day: number;
    auto_retry: boolean;
    retry_max_attempts: number;
    retry_base_seconds: number;
  };
};

type StageRow = { stage: string; label: string; mode: string; active: boolean };

const STAGE_ORDER = ["collect", "verify", "script", "render", "approve", "schedule"] as const;
const PLATFORMS = ["youtube", "facebook", "instagram", "tiktok"] as const;
const PRIVACY = ["private", "unlisted", "public"] as const;

export default function AutomationForm({
  initialPolicy,
  controls,
}: {
  initialPolicy: AutomationPolicy;
  controls: StageRow[];
}) {
  const router = useRouter();
  const [policy, setPolicy] = useState<AutomationPolicy>(initialPolicy);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const labels = useMemo(
    () => Object.fromEntries(controls.map((c) => [c.stage, c.label])),
    [controls],
  );

  function updateStage(stage: string, mode: string) {
    setPolicy((p) => ({ ...p, stages: { ...p.stages, [stage]: mode } }));
  }

  function updateGuardrail<K extends keyof AutomationPolicy["guardrails"]>(
    key: K,
    value: AutomationPolicy["guardrails"][K],
  ) {
    setPolicy((p) => ({ ...p, guardrails: { ...p.guardrails, [key]: value } }));
  }

  async function call(path: string, init: RequestInit, busyKey: string) {
    setBusy(busyKey);
    setError(null);
    setMsg(null);
    try {
      const res = await clientFetch(path, init);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return null;
      }
      setMsg("Saved — the tools read this policy on their next action.");
      router.refresh();
      return body;
    } catch {
      setError("API unreachable — the policy was not saved.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    const payload = {
      mode: policy.mode,
      paused: policy.paused,
      dry_run: policy.dry_run,
      stages: policy.stages,
      guardrails: policy.guardrails,
    };
    const body = await call(
      "/automation/policy",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ policy: payload }),
      },
      "save",
    );
    if (body?.policy) setPolicy(body.policy as AutomationPolicy);
  }

  async function preset(name: string) {
    await call(`/automation/preset/${name}`, { method: "POST" }, `preset-${name}`);
    const fresh = await clientFetch("/automation/policy").then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (fresh?.policy) setPolicy(fresh.policy as AutomationPolicy);
  }

  async function togglePause() {
    const path = policy.paused ? "/automation/resume" : "/automation/pause";
    const body = await call(
      path,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
      "pause",
    );
    // Only mirror a server-confirmed change: resume also clears dry-run.
    if (body?.policy) setPolicy(body.policy as AutomationPolicy);
  }

  const stageMode = (stage: string) => policy.stages[stage] ?? "human";

  return (
    <div className="automation-form">
      <div className="automation-topline">
        <div>
          <strong>Current mode: {policy.mode}</strong>
          <div className="muted small">
            {policy.paused
              ? "All automation is paused. Humans can still act."
              : policy.dry_run
                ? "Dry-run: the tools report what they would do but change nothing."
                : "Automation acts only on stages set to auto, inside the guardrails below."}
          </div>
        </div>
        <div className="automation-killswitch">
          <button
            type="button"
            className={policy.paused ? "btn btn-primary" : "btn btn-danger"}
            disabled={busy !== null}
            onClick={togglePause}
          >
            {policy.paused ? "▶ Resume automation" : "⏸ Pause all automation"}
          </button>
        </div>
      </div>

      <div className="preset-row" role="group" aria-label="Automation presets">
        {["manual", "assisted", "autopilot"].map((name) => (
          <button
            key={name}
            type="button"
            className={`preset ${policy.mode === name ? "preset-active" : ""}`}
            disabled={busy !== null}
            onClick={() => preset(name)}
            title={
              name === "manual"
                ? "Every gated step waits for a person."
                : name === "assisted"
                  ? "Collect, verify, script and render automatically; approve and schedule by hand."
                  : "Every stage may advance automatically inside the guardrails."
            }
          >
            {busy === `preset-${name}` ? "Applying…" : name}
          </button>
        ))}
      </div>

      <table className="automation-table">
        <thead>
          <tr><th>Stage</th><th>Control</th></tr>
        </thead>
        <tbody>
          {STAGE_ORDER.map((stage) => (
            <tr key={stage}>
              <td>
                <strong>{stage}</strong>
                <div className="muted small">{labels[stage]}</div>
              </td>
              <td>
                <select
                  aria-label={`${stage} control`}
                  value={stageMode(stage)}
                  onChange={(e) => updateStage(stage, e.target.value)}
                  disabled={busy !== null}
                >
                  <option value="human">Human approval</option>
                  <option value="auto">Automation</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="automation-subhead">Guardrails</h3>
      <div className="guardrail-grid">
        <label className="small">
          Minimum verification confidence
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={policy.guardrails.auto_verify_min_confidence}
            onChange={(e) => updateGuardrail("auto_verify_min_confidence", Number(e.target.value))}
          />
        </label>
        <label className="small">
          Max evidence age (hours)
          <input
            type="number"
            min={1}
            max={720}
            value={policy.guardrails.auto_verify_max_evidence_age_hours}
            onChange={(e) =>
              updateGuardrail("auto_verify_max_evidence_age_hours", Number(e.target.value))
            }
          />
        </label>
        <label className="small">
          Auto-approved posts / day
          <input
            type="number"
            min={0}
            max={100}
            value={policy.guardrails.auto_publish_max_per_day}
            onChange={(e) => updateGuardrail("auto_publish_max_per_day", Number(e.target.value))}
          />
        </label>
        <label className="small">
          Auto-schedule privacy
          <select
            value={policy.guardrails.auto_schedule_privacy}
            onChange={(e) => updateGuardrail("auto_schedule_privacy", e.target.value)}
          >
            {PRIVACY.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="small">
          Auto-retry failed posts
          <select
            value={policy.guardrails.auto_retry ? "yes" : "no"}
            onChange={(e) => updateGuardrail("auto_retry", e.target.value === "yes")}
          >
            <option value="yes">yes — exponential backoff</option>
            <option value="no">no — wait for a human</option>
          </select>
        </label>
        <label className="small">
          Retry attempts
          <input
            type="number"
            min={0}
            max={10}
            value={policy.guardrails.retry_max_attempts}
            onChange={(e) => updateGuardrail("retry_max_attempts", Number(e.target.value))}
          />
        </label>
        <label className="small">
          Retry backoff base (seconds)
          <input
            type="number"
            min={30}
            max={86400}
            value={policy.guardrails.retry_base_seconds}
            onChange={(e) => updateGuardrail("retry_base_seconds", Number(e.target.value))}
          />
        </label>
      </div>

      <fieldset className="platforms">
        <legend className="small">Platforms automation may queue</legend>
        {PLATFORMS.map((platform) => {
          const on = policy.guardrails.auto_schedule_platforms.includes(platform);
          return (
            <label key={platform} className="small platform-check">
              <input
                type="checkbox"
                checked={on}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...policy.guardrails.auto_schedule_platforms, platform]
                    : policy.guardrails.auto_schedule_platforms.filter((p) => p !== platform);
                  // the API requires a non-empty list; keep the last choice
                  updateGuardrail("auto_schedule_platforms", next.length ? next : [platform]);
                }}
              />
              {platform}
            </label>
          );
        })}
      </fieldset>

      <div className="checkbox-row">
        <label className="small">
          <input
            type="checkbox"
            checked={policy.guardrails.auto_approve_requires_render}
            onChange={(e) => updateGuardrail("auto_approve_requires_render", e.target.checked)}
          />
          Require a rendered, redaction-reviewed video before auto-approval
        </label>
        <label className="small">
          <input
            type="checkbox"
            checked={policy.guardrails.auto_approve_block_unsafe_commands}
            onChange={(e) => updateGuardrail("auto_approve_block_unsafe_commands", e.target.checked)}
          />
          Block auto-approval when the script has unsafe command cards
        </label>
        <label className="small">
          <input
            type="checkbox"
            checked={policy.dry_run}
            onChange={(e) => setPolicy((p) => ({ ...p, dry_run: e.target.checked }))}
          />
          Dry-run (observe only — no state changes)
        </label>
      </div>

      <div className="automation-actions">
        <button type="submit" className="btn btn-primary" disabled={busy !== null} onClick={save}>
          {busy === "save" ? "Saving…" : "Save automation policy"}
        </button>
        {msg && <span className="small" style={{ color: "var(--ok)" }}>{msg}</span>}
        {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
      </div>
    </div>
  );
}
