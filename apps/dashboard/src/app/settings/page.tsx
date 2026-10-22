/**
 * Settings (v0.26) — the operator's control room.
 *
 * The automation policy is the centerpiece: per-stage human/automation
 * control, guardrails, a one-click kill switch, and the live work queue.
 * Publishing windows (§17) and pipeline status stay in the same place.
 */

import "./styles.css";
import AutomationForm, { type AutomationPolicy } from "./AutomationForm";
import LanguagePolicyForm, { type LanguagePolicy } from "./LanguagePolicyForm";
import SettingsForm from "./SettingsForm";
import { apiFetch } from "@/lib/api";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await apiFetch(path, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

type StageRow = { stage: string; label: string; mode: string; active: boolean };

type PolicyResponse = {
  policy: AutomationPolicy;
  summary: {
    state: string;
    mode: string;
    controls: StageRow[];
    automation_stages: string[];
    human_stages: string[];
    fixed_guarantees: string[];
  };
  presets: Record<string, AutomationPolicy>;
  updated_at: string | null;
  updated_by: string | null;
};

type StatusResponse = {
  summary: PolicyResponse["summary"];
  budget: { used_today: number; limit_per_day: number; remaining: number; exhausted: boolean };
  queue: Record<string, number>;
  recent_automation_actions: {
    actor: string;
    action: string;
    entity: string;
    entity_id: string | null;
    detail: string | null;
    created_at: string;
  }[];
};

const FALLBACK_POLICY: AutomationPolicy = {
  mode: "assisted",
  paused: false,
  dry_run: false,
  stages: {
    collect: "auto",
    verify: "auto",
    script: "auto",
    render: "auto",
    approve: "human",
    schedule: "human",
  },
  guardrails: {
    auto_verify_min_confidence: 0,
    auto_verify_max_evidence_age_hours: 72,
    auto_approve_requires_render: true,
    auto_approve_block_unsafe_commands: true,
    auto_schedule_platforms: ["youtube"],
    auto_schedule_privacy: "private",
    auto_publish_max_per_day: 3,
    auto_retry: true,
    retry_max_attempts: 3,
    retry_base_seconds: 300,
  },
};

const FALLBACK_LANGUAGE_POLICY: LanguagePolicy = {
  metadata_language: "en",
  captions_language: "en",
  narration_languages: ["en"],
  default_narration_language: "en",
  urdu_voiceover_enabled: false,
};

const FALLBACK_CONTROLS: StageRow[] = [
  { stage: "collect", label: "Collect candidates from registered sources", mode: "auto", active: true },
  { stage: "verify", label: "Collect official evidence and promote to verified", mode: "auto", active: true },
  { stage: "script", label: "Generate the versioned claim script", mode: "auto", active: true },
  { stage: "render", label: "Render captions / 16:9 / 9:16 exports", mode: "auto", active: true },
  { stage: "approve", label: "Approve the offer for video and each post", mode: "human", active: false },
  { stage: "schedule", label: "Queue approved posts at a publish window", mode: "human", active: false },
];

export const dynamic = "force-dynamic";

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { timeZone: "Asia/Karachi" });
}

export default async function SettingsPage() {
  const [setting, languageRes, policyRes, statusRes, accounts] = await Promise.all([
    getJson<{ key: string; value: { windows?: string[] } | null }>(
      "/settings/publish_windows",
      { key: "publish_windows", value: null },
    ),
    getJson<{ key: string; value: LanguagePolicy | null }>(
      "/settings/language_policy",
      { key: "language_policy", value: null },
    ),
    getJson<PolicyResponse>("/automation/policy", {
      policy: FALLBACK_POLICY,
      summary: {
        state: "running",
        mode: "assisted",
        controls: FALLBACK_CONTROLS,
        automation_stages: ["collect", "verify", "script", "render"],
        human_stages: ["approve", "schedule"],
        fixed_guarantees: [],
      },
      presets: {},
      updated_at: null,
      updated_by: null,
    }),
    getJson<StatusResponse>("/automation/status", {
      summary: {
        state: "running",
        mode: "assisted",
        controls: FALLBACK_CONTROLS,
        automation_stages: [],
        human_stages: [],
        fixed_guarantees: [],
      },
      budget: { used_today: 0, limit_per_day: 0, remaining: 0, exhausted: false },
      queue: {},
      recent_automation_actions: [],
    }),
    getJson<{ platform: string; account_handle: string; status: string }[]>(
      "/platform-accounts",
      [],
    ),
  ]);

  const windows = setting.value?.windows ?? ["18:00"];
  const languagePolicy = languageRes.value ?? FALLBACK_LANGUAGE_POLICY;
  const policy = policyRes.policy ?? FALLBACK_POLICY;
  const summary = policyRes.summary ?? statusRes.summary;
  const controls = summary?.controls?.length ? summary.controls : FALLBACK_CONTROLS;
  const budget = statusRes.budget;
  const queue = statusRes.queue ?? {};
  const actions = statusRes.recent_automation_actions ?? [];

  const stateColor =
    summary?.state === "running"
      ? "var(--ok)"
      : summary?.state === "dry_run"
        ? "var(--warn)"
        : summary?.state === "paused"
          ? "var(--danger)"
          : "var(--text-muted)";

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Settings</h1>
      <p className="tagline">
        Human-vs-automation control for every pipeline stage · guardrails ·
        publishing windows (§17) · live status.
      </p>

      <section className="card">
        <div className="settings-head">
          <h2>Automation control</h2>
          <span className="pill" style={{ color: stateColor, borderColor: stateColor }}>
            {summary?.state ?? "unknown"}
          </span>
        </div>
        <p className="muted small" style={{ marginTop: 0 }}>
          Changes are validated and audited by the API. The workers re-check this
          policy before every gated action, so a stale worker cannot bypass a
          human-only stage.
          {policyRes.updated_at && (
            <> Last changed {timeLabel(policyRes.updated_at)}
              {policyRes.updated_by && <> by {policyRes.updated_by}</>}.</>
          )}
        </p>
        <AutomationForm initialPolicy={policy} controls={controls} />
      </section>

      <section className="card">
        <h2>Live automation status</h2>
        <div className="stats">
          <div>
            <strong style={{ color: budget?.exhausted ? "var(--warn)" : "var(--ok)" }}>
              {budget?.used_today ?? 0}/{budget?.limit_per_day ?? 0}
            </strong>
            <span>auto-approved today</span>
          </div>
          <div>
            <strong>{queue.awaiting_verification ?? 0}</strong>
            <span>awaiting verification</span>
          </div>
          <div>
            <strong>{queue.awaiting_render ?? 0}</strong>
            <span>awaiting render</span>
          </div>
          <div>
            <strong>{queue.awaiting_offer_approval ?? 0}</strong>
            <span>offers awaiting approval</span>
          </div>
          <div>
            <strong>{queue.awaiting_schedule_approval ?? 0}</strong>
            <span>posts awaiting approval</span>
          </div>
          <div>
            <strong>{queue.scheduled ?? 0}</strong>
            <span>scheduled posts</span>
          </div>
        </div>
        {budget?.exhausted && (
          <p className="small" style={{ color: "var(--warn)" }}>
            ⚠ The daily automation budget is exhausted. Autopilot stops approving
            posts; a human can still approve manually or raise the limit.
          </p>
        )}
        {queue.awaiting_redaction ? (
          <p className="small muted">
            {queue.awaiting_redaction} capture(s) still need a human redaction
            review — automation can never perform this attestation.
          </p>
        ) : null}

        <h3 className="small" style={{ margin: "0.9rem 0 0.3rem" }}>
          Recent automation actions (audit trail)
        </h3>
        {actions.length === 0 ? (
          <p className="muted small">No automation actions recorded yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>when</th><th>actor</th><th>action</th><th>entity</th></tr>
            </thead>
            <tbody>
              {actions.map((a, i) => (
                <tr key={`${a.created_at}-${i}`}>
                  <td className="small">{timeLabel(a.created_at)}</td>
                  <td><code className="small">{a.actor}</code></td>
                  <td className="small">{a.action}</td>
                  <td className="small">{a.entity}{a.entity_id ? ` · ${a.entity_id.slice(0, 8)}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Language policy</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          Public packaging stays English for every video. Urdu is opt-in and applies
          to the voiceover only.
        </p>
        <LanguagePolicyForm initial={languagePolicy} />
      </section>

      <section className="card">
        <h2>Publishing windows</h2>
        <SettingsForm initialWindows={windows} />
      </section>

      <section className="card">
        <h2>Pipeline contract</h2>
        <table>
          <thead>
            <tr><th>Stage</th><th>Current control</th><th>What it means</th></tr>
          </thead>
          <tbody>
            {controls.map((c) => (
              <tr key={c.stage}>
                <td><strong>{c.stage}</strong></td>
                <td>
                  <span
                    className={`pill ${c.mode === "auto" && c.active ? "pill-accent" : "pill-muted"}`}
                  >
                    {c.mode === "auto" ? (c.active ? "automation" : "auto (paused)") : "human"}
                  </span>
                </td>
                <td className="small muted">{c.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {summary?.fixed_guarantees?.length ? (
          <>
            <h3 className="small" style={{ margin: "0.9rem 0 0.3rem" }}>
              Guarantees that cannot be switched off
            </h3>
            <ul>
              {summary.fixed_guarantees.map((g) => (
                <li key={g} className="small muted">• {g}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>Connections &amp; keys</h2>
        <div className="stats">
          <div>
            <strong>{accounts.filter((a) => a.status === "active").length}</strong>
            <span>active connections</span>
          </div>
          <div>
            <strong>{accounts.length}</strong>
            <span>registered accounts</span>
          </div>
          <div>
            <strong>{windows.length}</strong>
            <span>publish windows</span>
          </div>
        </div>
        <p className="muted small">
          Secrets never enter this app. The deploy env (<code>.env</code> next to
          the compose file) holds the keys; the{" "}
          <a href="/connections">Connections</a> page records where each account
          keeps them. The workers read them from the environment at runtime.
        </p>
      </section>
    </main>
  );
}
