/**
 * Settings → Costs card (v0.37, enhancement plan 2026-10-24 WP-F §5.5).
 *
 * "See the money, cap the money": today/7d/30d estimated spend, the
 * per-stage split with cache-hit rates, the two hard daily budgets the
 * workers check BEFORE spending, and the provider capability probe
 * ("Extraction: ollama/qwen2.5:7b — reachable ✓").
 *
 * Every number is an ESTIMATE priced from the documented COST_* env knobs —
 * the ledger records usage, never a bill.
 */

type ByKind = {
  kind: string;
  unit_type: string;
  units: number;
  cost_usd_est: number;
  events: number;
  cache_hit_rate: number;
  blocked: number;
};

export type CostsSummary = {
  usd_today: number;
  usd_7d: number;
  usd_30d: number;
  by_kind: ByKind[];
  published_videos_30d: number;
  cost_per_published_video_usd_30d: number | null;
  /** One video cross-posted to N platforms is N posts. Absent on older APIs. */
  published_posts_30d?: number;
  cost_per_published_post_usd_30d?: number | null;
  pricing: {
    llm_input_usd_per_mtok: number;
    llm_output_usd_per_mtok: number;
    tts_usd_per_mchar: number;
  };
};

export type CostsBudget = {
  llm: {
    used_usd_today: number;
    limit_usd_per_day: number;
    exhausted: boolean;
    blocked_today: number;
  };
  tts: {
    chars_today: number;
    limit_chars_per_day: number;
    exhausted: boolean;
    blocked_today: number;
  };
};

export type ProvidersInfo = {
  extraction: {
    configured: boolean;
    reachable: boolean;
    models: string[];
    model?: string;
    probe?: string;
  };
  tts: {
    configured: boolean;
    reachable: boolean;
    models: string[];
    model?: string;
    voice?: string;
  };
  cached: boolean;
};

const KIND_LABELS: Record<string, string> = {
  llm_extract: "LLM extraction (verify)",
  tts: "TTS narration (render)",
  trend_fetch: "Trend fetches (collect)",
  youtube_quota: "YouTube API quota (metrics)",
};

function usd(value: number): string {
  return `$${value.toFixed(value < 1 ? 4 : 2)}`;
}

export default function CostsCard({
  summary,
  budget,
  providers,
}: {
  summary: CostsSummary | null;
  budget: CostsBudget | null;
  providers: ProvidersInfo | null;
}) {
  const kindRows = summary?.by_kind ?? [];
  const fmtPct = (rate: number) => `${Math.round(rate * 100)}%`;

  return (
    <section className="card" id="costs">
      <h2>Costs</h2>
      <p className="muted small" style={{ marginTop: 0 }}>
        Metered spend over the usage ledger; estimates priced from the
        documented <code>COST_*</code> env knobs — never a bill. Budget rows
        are checked by the workers BEFORE spending; an exhausted budget
        degrades the stage (rules-only extraction, capture audio) and shows
        in Needs-You.
      </p>

      <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap", margin: "0.6rem 0" }}>
        <div>
          <div className="muted small">today</div>
          <strong style={{ fontSize: "1.2rem" }}>
            {summary ? usd(summary.usd_today) : "—"}
          </strong>
        </div>
        <div>
          <div className="muted small">last 7 days</div>
          <strong style={{ fontSize: "1.2rem" }}>
            {summary ? usd(summary.usd_7d) : "—"}
          </strong>
        </div>
        <div>
          <div className="muted small">last 30 days</div>
          <strong style={{ fontSize: "1.2rem" }}>
            {summary ? usd(summary.usd_30d) : "—"}
          </strong>
        </div>
        <div>
          <div className="muted small" title="Spend ÷ unique videos (offer × language), however many platforms each went to">
            cost / unique video (30d)
          </div>
          <strong style={{ fontSize: "1.2rem" }}>
            {summary?.cost_per_published_video_usd_30d != null
              ? usd(summary.cost_per_published_video_usd_30d)
              : "—"}
          </strong>
          <div className="muted small">{summary?.published_videos_30d ?? 0} videos</div>
        </div>
        <div>
          <div className="muted small" title="Spend ÷ platform publications">cost / post (30d)</div>
          <strong style={{ fontSize: "1.2rem" }}>
            {summary?.cost_per_published_post_usd_30d != null
              ? usd(summary.cost_per_published_post_usd_30d)
              : "—"}
          </strong>
          <div className="muted small">{summary?.published_posts_30d ?? 0} posts</div>
        </div>
      </div>

      {kindRows.length > 0 && (
        <table style={{ width: "100%", fontSize: "0.82rem", borderCollapse: "collapse" }}>
          <thead>
            <tr className="muted small" style={{ textAlign: "left" }}>
              <th style={{ padding: "0.25rem 0.4rem" }}>stage</th>
              <th>usage (30d)</th>
              <th>est. spend</th>
              <th>cache-hit</th>
              <th>blocked today</th>
            </tr>
          </thead>
          <tbody>
            {kindRows.map((row) => (
              <tr key={row.kind}>
                <td style={{ padding: "0.25rem 0.4rem" }}>
                  {KIND_LABELS[row.kind] ?? row.kind}
                </td>
                <td>
                  {row.units.toLocaleString()} {row.unit_type}
                </td>
                <td>{usd(Number(row.cost_usd_est))}</td>
                <td
                  style={{
                    color:
                      row.cache_hit_rate >= 0.3 ? "var(--ok)" : undefined,
                  }}
                  title="served from the shared cache — zero tokens/chars spent"
                >
                  {fmtPct(Number(row.cache_hit_rate))}
                </td>
                <td style={{ color: row.blocked > 0 ? "var(--warn)" : undefined }}>
                  {row.blocked}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {budget && (
        <div style={{ display: "flex", gap: "1.2rem", flexWrap: "wrap", marginTop: "0.8rem" }}>
          <div
            className="small"
            style={{
              border: "1px solid",
              borderColor: budget.llm.exhausted ? "var(--danger)" : "var(--border, #333)",
              borderRadius: 8,
              padding: "0.4rem 0.7rem",
            }}
          >
            <strong>
              LLM budget: {usd(budget.llm.used_usd_today)} /{" "}
              {usd(budget.llm.limit_usd_per_day)} per day
            </strong>
            <div className="muted small">
              {budget.llm.exhausted
                ? "exhausted — extraction is on the rules path"
                : "checked before every extraction"}
              {budget.llm.blocked_today > 0
                ? ` · ${budget.llm.blocked_today} blocked calls today`
                : ""}
            </div>
          </div>
          <div
            className="small"
            style={{
              border: "1px solid",
              borderColor: budget.tts.exhausted ? "var(--danger)" : "var(--border, #333)",
              borderRadius: 8,
              padding: "0.4rem 0.7rem",
            }}
          >
            <strong>
              TTS budget: {budget.tts.chars_today.toLocaleString()} /{" "}
              {budget.tts.limit_chars_per_day.toLocaleString()} chars per day
            </strong>
            <div className="muted small">
              {budget.tts.exhausted
                ? "exhausted — renders use capture audio"
                : "checked before every narration"}
              {budget.tts.blocked_today > 0
                ? ` · ${budget.tts.blocked_today} blocked calls today`
                : ""}
            </div>
          </div>
        </div>
      )}

      {providers && (
        <p className="small" style={{ margin: "0.8rem 0 0" }}>
          <span
            style={{ color: providers.extraction.reachable ? "var(--ok)" : "var(--text-muted)" }}
          >
            Extraction:{" "}
            {providers.extraction.reachable
              ? `${providers.extraction.model ?? "llm"} (${providers.extraction.models.slice(0, 3).join(", ") || "models listed"}) — reachable ✓`
              : providers.extraction.configured
                ? "configured but unreachable — the rules extractor stays authoritative"
                : "not configured — deterministic rules extraction"}
          </span>
          {" · "}
          <span style={{ color: providers.tts.reachable ? "var(--ok)" : "var(--text-muted)" }}>
            TTS:{" "}
            {providers.tts.reachable
              ? `${providers.tts.model ?? "tts"} — reachable ✓`
              : providers.tts.configured
                ? "configured but unreachable — capture audio stays the fallback"
                : "not configured — no synthetic narration"}
            {providers.cached ? " (cached probe)" : ""}
          </span>
        </p>
      )}
    </section>
  );
}
