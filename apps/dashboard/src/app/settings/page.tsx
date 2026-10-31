/**
 * Settings (v0.26) — the operator's control room.
 *
 * The automation policy is the centerpiece: per-stage human/automation
 * control, guardrails, a one-click kill switch, and the live work queue.
 * Publishing windows (§17) and pipeline status stay in the same place.
 */

import "./styles.css";
import AutomationForm, { type AutomationPolicy } from "./AutomationForm";
import CostsCard, {
  type CostsBudget,
  type CostsSummary,
  type ProvidersInfo,
} from "./CostsCard";
import LanguagePolicyForm, { type LanguagePolicy } from "./LanguagePolicyForm";
import NotificationsCard from "./NotificationsCard";
import ReleasePolicyForm, { type ReleasePolicy } from "./ReleasePolicyForm";
import SettingsForm from "./SettingsForm";
import { loadJson, unavailableSections } from "@/lib/load";


type QuotaUsage = {
  quota_day: string;
  resets_at: string;
  limits: Record<string, number | null>;
  accounts: { account: string; bucket: string; consumed: number; reserved: number }[];
};

/** Q1: today's YouTube quota (Pacific day) per account, from the ledger. */
function QuotaCard({ usage }: { usage: QuotaUsage | null }) {
  const unitsLimit = usage?.limits?.units ?? 0;
  const rows = (usage?.accounts ?? []).filter((r) => r.bucket === "units");
  return (
    <section className="card">
      <h2>YouTube quota today</h2>
      {!usage ? (
        <p className="muted small">Quota ledger unavailable.</p>
      ) : (
        <>
          <p className="muted small" style={{ marginTop: 0 }}>
            Pacific day {usage.quota_day} · resets{" "}
            {new Date(usage.resets_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} PKT ·
            limit {unitsLimit ? unitsLimit.toLocaleString() : "unmetered"} units. Uploads reserve
            their whole package first; failed calls still count.
          </p>
          {rows.length === 0 ? (
            <p className="muted small">No YouTube calls reserved today.</p>
          ) : (
            rows.map((r) => {
              const used = Number(r.consumed) + Number(r.reserved);
              const pct = unitsLimit ? Math.min(100, Math.round((used / unitsLimit) * 100)) : 0;
              return (
                <div key={r.account} className="metric-row">
                  <span>{r.account}</span>
                  <span className="score-bar" style={{ flex: 1, margin: "0 0.8rem" }}>
                    <span style={{ width: `${pct}%` }} />
                  </span>
                  <strong>
                    {used.toLocaleString()}
                    {unitsLimit ? ` / ${unitsLimit.toLocaleString()}` : ""}
                  </strong>
                </div>
              );
            })
          )}
        </>
      )}
    </section>
  );
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

type MediaBackup = {
  enabled: boolean;
  schedule: string;
  retention_days: number;
  destination: string;
  last_run_at: string | null;
  last_status: "not_configured" | "running" | "ok" | "failed" | "verified";
  last_manifest: string;
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
  const loaded =
    await Promise.all([
    loadJson<{ key: string; value: { windows?: string[] } | null }>(
      "/settings/publish_windows",
      { key: "publish_windows", value: null },
    ),
    loadJson<{ key: string; value: LanguagePolicy | null }>(
      "/settings/language_policy",
      { key: "language_policy", value: null },
    ),
    loadJson<{ key: string; value: ReleasePolicy | null }>(
      "/settings/release_policy",
      { key: "release_policy", value: null },
    ),
    loadJson<{ key: string; value: MediaBackup | null }>(
      "/settings/media_backup",
      { key: "media_backup", value: null },
    ),
    loadJson<PolicyResponse>("/automation/policy", {
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
    loadJson<StatusResponse>("/automation/status", {
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
    loadJson<{ platform: string; account_handle: string; status: string }[]>(
      "/platform-accounts",
      [],
    ),
    loadJson<CostsSummary>("/costs/summary", {
      usd_today: 0,
      usd_7d: 0,
      usd_30d: 0,
      by_kind: [],
      published_videos_30d: 0,
      cost_per_published_video_usd_30d: null,
      pricing: {
        llm_input_usd_per_mtok: 0.15,
        llm_output_usd_per_mtok: 0.6,
        tts_usd_per_mchar: 15,
      },
    }),
    loadJson<CostsBudget>("/costs/budget", {
      llm: { used_usd_today: 0, limit_usd_per_day: 0, exhausted: false, blocked_today: 0 },
      tts: { chars_today: 0, limit_chars_per_day: 0, exhausted: false, blocked_today: 0 },
    }),
    loadJson<ProvidersInfo>("/costs/providers", {
      extraction: { configured: false, reachable: false, models: [] },
      tts: { configured: false, reachable: false, models: [] },
      cached: false,
    }),
    loadJson<QuotaUsage | null>("/quota?provider=youtube", null),
  ]);
  const [setting, languageRes, releaseRes, backupRes, policyRes, statusRes, accounts, costsRes, costBudgetRes, providersRes] =
    [loaded[0].data, loaded[1].data, loaded[2].data, loaded[3].data, loaded[4].data,
     loaded[5].data, loaded[6].data, loaded[7].data, loaded[8].data, loaded[9].data] as const;
  const policyLive = loaded[4].ok;
  const offline = unavailableSections({
    "publishing windows": loaded[0],
    "language policy": loaded[1],
    "release policy": loaded[2],
    "media backup": loaded[3],
    "automation policy": loaded[4],
    "automation status": loaded[5],
    "connected accounts": loaded[6],
    "costs": loaded[7],
    "budget": loaded[8],
    "providers": loaded[9],
    "YouTube quota": loaded[10],
  });

  const windows = setting.value?.windows ?? ["18:00"];
  const backup = backupRes.value;
  const languagePolicy = languageRes.value ?? FALLBACK_LANGUAGE_POLICY;
  const releasePolicy = releaseRes.value ?? { require_package_assets: true, require_playback_review: true };
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

      {offline.length > 0 && (
        <div className="notice notice-danger" role="alert">
          <strong>Live data unavailable</strong> for {offline.join(", ")}. The API did
          not answer, so those sections show placeholders, not your live
          configuration. Editing the automation policy is disabled until it loads.
        </div>
      )}

      <section className="card">
        <div className="settings-head">
          <h2>Automation control</h2>
          {policyLive ? (
            <span className="pill" style={{ color: stateColor, borderColor: stateColor }}>
              {summary?.state ?? "unknown"}
            </span>
          ) : (
            <span className="pill pill-muted">unavailable</span>
          )}
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
        {policyLive ? (
          <AutomationForm initialPolicy={policy} controls={controls} />
        ) : (
          <div className="empty-state">
            The automation policy could not be loaded. Nothing is shown here
            rather than a default that could be mistaken for the live policy —
            reload once the API is reachable.
          </div>
        )}
      </section>

      <CostsCard summary={costsRes} budget={costBudgetRes} providers={providersRes} />

      <QuotaCard usage={loaded[10].ok ? loaded[10].data : null} />

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
        <h2>Release policy (§17)</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          What a queued post must prove before an upload is authorized. Strict
          by default; relaxing a requirement is a recorded human decision.
        </p>
        <ReleasePolicyForm initial={releasePolicy} />
      </section>

      <section className="card">
        <h2>Publishing windows</h2>
        <SettingsForm initialWindows={windows} />
      </section>

      <NotificationsCard />

      <section className="card">
        <h2>Media backup</h2>
        {!backup || (!backup.enabled && backup.last_status === "not_configured") ? (
          <p className="muted small" style={{ marginTop: 0 }}>
            No media backup is recorded. Backups run from the deployment host
            (infra/backup.sh + a systemd timer) and report their status here via
            the <code>media_backup</code> setting.
          </p>
        ) : (
          <div className="stats">
            <div>
              <strong>
                <span
                  className={`pill ${
                    backup.last_status === "ok" || backup.last_status === "verified"
                      ? "pill-accent"
                      : backup.last_status === "failed"
                        ? "pill-danger"
                        : "pill-muted"
                  }`}
                >
                  {backup.last_status}
                </span>
              </strong>
              <span>last backup status</span>
            </div>
            <div>
              <strong>{backup.schedule}</strong>
              <span>schedule ({backup.retention_days}-day retention)</span>
            </div>
            <div>
              <strong>{backup.last_run_at ? backup.last_run_at.slice(0, 16).replace("T", " ") : "—"}</strong>
              <span>last run (UTC)</span>
            </div>
          </div>
        )}
        {backup?.destination && (
          <p className="muted small">
            Destination: <code>{backup.destination}</code>
            {backup.last_manifest ? (
              <>
                {" "}· manifest: <code>{backup.last_manifest}</code>
              </>
            ) : null}
          </p>
        )}
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
