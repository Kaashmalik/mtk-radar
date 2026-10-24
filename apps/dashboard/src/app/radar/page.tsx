/**
 * Trend radar (v0.27) — discovery, not verification.
 *
 * Each lead carries the six explainable scores that produced the total, plus
 * the reasons and risks. Shortlisting is a human decision; verification still
 * has to happen on the official source before any script can be generated.
 */

import "../styles.css";
import Link from "next/link";

import RadarScope, { type RadarCandidate } from "../RadarScope";
import { CompetitorEvidence, PromoteButton, ScanButton, TrendAction } from "./RadarActions";
import { apiFetch } from "@/lib/api";

type Candidate = RadarCandidate & {
  url: string;
  country_scope: string[];
  language: string;
  status: string;
  demand_score: number;
  freshness_score: number;
  feasibility_score: number;
  competition_gap: number;
  audience_fit: number;
  monetization: number;
  score_reason: {
    why_now?: string[];
    risks?: string[];
    keywords?: string[];
    age_hours?: number | null;
  } | null;
  signals: { keyword_hits?: string[]; source_tier?: string | null } | null;
  velocity: number;
  peak_score: number;
  corroboration: number;
  updated_at: string;
};

type TrendsResponse = {
  candidates: Candidate[];
  summary: { total: number; hot: number; shortlisted: number; average_score: number };
};

async function getTrends(): Promise<TrendsResponse> {
  try {
    const res = await apiFetch("/trends?limit=100", { cache: "no-store" });
    if (!res.ok) return { candidates: [], summary: { total: 0, hot: 0, shortlisted: 0, average_score: 0 } };
    return (await res.json()) as TrendsResponse;
  } catch {
    return { candidates: [], summary: { total: 0, hot: 0, shortlisted: 0, average_score: 0 } };
  }
}

function scoreTone(score: number): string {
  if (score >= 78) return "tag-hot";
  if (score >= 55) return "tag-accent";
  return "";
}

/**
 * Momentum chips (Trend Radar v2): the radar measured these itself — score
 * delta per hour between re-scores, how many independent sources observed the
 * story, and the all-time peak. Nothing here is invented: a lead with no
 * re-score history simply shows no chip.
 */
function momentumChips(candidate: Candidate): { label: string; tone: string; title: string }[] {
  const chips: { label: string; tone: string; title: string }[] = [];
  const velocity = Number(candidate.velocity ?? 0);
  if (velocity > 0) {
    chips.push({
      label: `▲ ${formatVelocity(velocity)}/h`,
      tone: "tag-accent",
      title: "Score gained per hour between the last two radar observations",
    });
  } else if (velocity < 0) {
    chips.push({
      label: `▼ ${formatVelocity(Math.abs(velocity))}/h`,
      tone: "tag",
      title: "Score fading between the last two radar observations",
    });
  }
  const corroborating = Number(candidate.corroboration ?? 0);
  if (corroborating >= 2) {
    chips.push({
      label: `${corroborating} sources`,
      tone: "tag-accent",
      title: "Independent sources that observed this story",
    });
  }
  const score = Number(candidate.score ?? 0);
  const peak = Number(candidate.peak_score ?? 0);
  if (peak > score + 0.05) {
    chips.push({
      label: `peak ${peak.toFixed(0)}`,
      tone: "tag",
      title: "Highest score this lead ever reached on the radar",
    });
  }
  return chips;
}

function formatVelocity(velocity: number): string {
  if (velocity >= 10) return velocity.toFixed(0);
  if (velocity >= 1) return velocity.toFixed(1);
  return velocity.toFixed(2);
}

function scoreRow(label: string, value: number) {
  return (
    <div className="metric-row" key={label}>
      <span>{label}</span>
      <strong>{value.toFixed(0)}</strong>
    </div>
  );
}

export const dynamic = "force-dynamic";

export default async function RadarPage() {
  const data = await getTrends();
  const top = data.candidates[0];

  return (
    <main className="page">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Discovery layer</span>
          <h1>Trend radar</h1>
          <p>
            A transparent six-signal score for every lead: demand, freshness,
            feasibility, competition gap, audience fit and monetization. The radar
            proposes a topic; a reviewer still verifies the official claim.
          </p>
          <div className="hero-actions">
            <ScanButton />
            <Link href="/review" className="btn btn-ghost">Review desk</Link>
          </div>
        </div>
        <aside className="panel">
          <div className="panel-head">
            <div>
              <h2>Signal health</h2>
              <p>Latest scored cohort</p>
            </div>
            <span className="tag tag-accent">{data.summary.total} leads</span>
          </div>
          <div className="metric-row"><span>Hot (≥ 78)</span><strong>{data.summary.hot}</strong></div>
          <div className="metric-row"><span>Shortlisted</span><strong>{data.summary.shortlisted}</strong></div>
          <div className="metric-row"><span>Average score</span><strong>{Number(data.summary.average_score || 0).toFixed(1)}</strong></div>
          <div className="metric-row"><span>Human gate</span><strong>verification</strong></div>
        </aside>
      </section>

      <section className="grid-2">
        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Radar scope</h2>
              <p>Hotter leads sit closer to the centre.</p>
            </div>
          </div>
          <RadarScope candidates={data.candidates} label="Full topic radar" />
        </div>

        <div className="panel">
          <div className="panel-head">
            <div>
              <h2>Top lead</h2>
              <p>Why this one is moving now.</p>
            </div>
            {top && <span className={`tag ${scoreTone(Number(top.score))}`}>{Number(top.score).toFixed(1)}</span>}
          </div>
          {!top ? (
            <div className="empty-state">
              No leads yet. Scan the inbox to score unprocessed items against the radar model.
            </div>
          ) : (
            <>
              <h3 style={{ margin: "0 0 0.3rem", fontSize: "1rem" }}>{top.title}</h3>
              <p className="small muted" style={{ marginTop: 0 }}>
                {top.source_provider ?? "unknown source"} · {top.language} · {top.status}
              </p>
              <div className="chip-row" style={{ marginTop: "0.3rem" }}>
                {momentumChips(top).map((chip) => (
                  <span key={chip.label} className={`tag ${chip.tone}`} title={chip.title}>
                    {chip.label}
                  </span>
                ))}
              </div>
              <ul className="reason-list">
                {(top.score_reason?.why_now ?? []).map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
              {top.score_reason?.risks?.length ? (
                <p className="small" style={{ color: "var(--warn)" }}>
                  Check: {top.score_reason.risks.join(" · ")}
                </p>
              ) : null}
              <div className="grid-2" style={{ gap: "0.2rem 1rem", marginTop: "0.6rem" }}>
                {scoreRow("Demand", Number(top.demand_score))}
                {scoreRow("Freshness", Number(top.freshness_score))}
                {scoreRow("Feasibility", Number(top.feasibility_score))}
                {scoreRow("Competition gap", Number(top.competition_gap))}
                {scoreRow("Audience fit", Number(top.audience_fit))}
                {scoreRow("Monetization", Number(top.monetization))}
              </div>
              <a className="btn btn-ghost" href={top.url} target="_blank" rel="noreferrer" style={{ marginTop: "0.7rem" }}>
                Open official lead ↗
              </a>
            </>
          )}
        </div>
      </section>

      <section className="card">
        <div className="panel-head">
          <div>
            <h2>Scored leads</h2>
            <p>Every bar can be recomputed from the item; no opaque model score.</p>
          </div>
          <span className="tag">{data.candidates.length} shown</span>
        </div>
        {data.candidates.length === 0 ? (
          <div className="empty-state">
            Nothing scored yet. Use “Scan inbox → radar”; unprocessed items become ranked
            candidates and never enter an offer automatically.
          </div>
        ) : (
          <div className="table-wrap">
            {data.candidates.map((candidate) => {
              const score = Number(candidate.score);
              return (
                <div className="trend-row" key={candidate.id}>
                  <div>
                    <h3>{candidate.title}</h3>
                    <p>
                      {candidate.source_provider ?? "unknown"} ·{" "}
                      {(candidate.country_scope ?? []).join(", ") || "region unknown"} ·{" "}
                      {candidate.score_reason?.keywords?.slice(0, 4).join(" · ") || "no keyword signal"}
                    </p>
                    <div className="chip-row" style={{ marginTop: 4 }}>
                      {momentumChips(candidate).map((chip) => (
                        <span key={chip.label} className={`tag ${chip.tone}`} title={chip.title}>
                          {chip.label}
                        </span>
                      ))}
                    </div>
                    <ul className="reason-list">
                      {(candidate.score_reason?.why_now ?? []).slice(0, 2).map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="score-bar" title={`${score.toFixed(1)}/100`}>
                      <span style={{ width: `${Math.max(2, score)}%` }} />
                    </div>
                    <div className="small muted" style={{ marginTop: 4 }}>{score.toFixed(1)} / 100</div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
                    <span className={`tag ${scoreTone(score)}`}>{candidate.status}</span>
                    <PromoteButton id={candidate.id} status={candidate.status} />
                    <TrendAction id={candidate.id} status={candidate.status} />
                    <CompetitorEvidence id={candidate.id} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
