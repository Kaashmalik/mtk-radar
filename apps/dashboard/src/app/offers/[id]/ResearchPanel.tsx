"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Research brief + claim ledger (EP-03 UI).
 *
 * The API already versions briefs and gates script generation on the
 * ledger; this panel makes that visible and lets a HUMAN settle a claim
 * (supported / contradicted / unknown). A standing contradiction blocks copy
 * in every track, so it is shown first and loudly. Automation credentials
 * are refused by the API for these writes.
 */

export type ResearchClaim = {
  id: string;
  claim_text: string;
  claim_class: string;
  supporting_excerpt: string | null;
  source_url: string | null;
  source_owner: string | null;
  scope: string | null;
  status: "supported" | "contradicted" | "unknown";
  permitted_wording: string | null;
  recheck_at: string | null;
};

export type ResearchBrief = {
  id: string;
  version: number;
  content_type: string;
  viewer_question: string | null;
  angle: string | null;
  audience: string | null;
  limitations: string | null;
  auto_shortlisted: boolean;
  claims: ResearchClaim[];
};

const CLASS_LABEL: Record<string, string> = {
  author_reported: "Author reported",
  independently_reproduced: "Independently reproduced",
  tested_by_mtk: "Tested by MTK",
  editorial_analysis: "Our analysis",
};

const TRACK_LABEL: Record<string, string> = {
  explainer: "Research explainer",
  tested_tutorial: "Tested tutorial",
  claim_walkthrough: "Claim walkthrough",
  offer: "Offer",
};

const STATUS_ORDER = { contradicted: 0, unknown: 1, supported: 2 } as const;

function hostOf(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url.slice(0, 60);
  }
}

export default function ResearchPanel({
  offerId,
  brief,
  versions,
}: {
  offerId: string;
  brief: ResearchBrief | null;
  versions: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!brief) {
    return (
      <p className="empty-state">
        No research brief yet. Briefs are created when a trend is promoted, or by
        a reviewer through the API; promotion never means verified.
      </p>
    );
  }

  const claims = [...brief.claims].sort(
    (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status],
  );
  const contradicted = claims.filter((c) => c.status === "contradicted").length;
  const now = Date.now();

  async function setStatus(claim: ResearchClaim, status: ResearchClaim["status"]) {
    setBusy(claim.id);
    setError(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/research/claims/${claim.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable — claim unchanged");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="research">
      <div className="chip-row">
        <span className="tag tag-accent">{TRACK_LABEL[brief.content_type] ?? brief.content_type}</span>
        <span className="tag">brief v{brief.version}{versions > 1 ? ` of ${versions}` : ""}</span>
        {brief.auto_shortlisted && <span className="tag tag-warn">auto-shortlisted</span>}
        {contradicted > 0
          ? <span className="tag tag-warn">{contradicted} contradiction{contradicted > 1 ? "s" : ""} block copy</span>
          : <span className="tag tag-ok">no blocking contradictions</span>}
      </div>

      {(brief.viewer_question || brief.angle || brief.audience) && (
        <dl className="research-brief">
          {brief.viewer_question && (<><dt>Viewer question</dt><dd>{brief.viewer_question}</dd></>)}
          {brief.angle && (<><dt>Angle</dt><dd>{brief.angle}</dd></>)}
          {brief.audience && (<><dt>Audience</dt><dd>{brief.audience}</dd></>)}
          {brief.limitations && (<><dt>Limitations</dt><dd>{brief.limitations}</dd></>)}
        </dl>
      )}

      {claims.length === 0 ? (
        <p className="empty-state">This brief version has no claims yet.</p>
      ) : (
        <ul className="claim-list">
          {claims.map((claim) => {
            const due = claim.recheck_at && new Date(claim.recheck_at).getTime() <= now;
            return (
              <li key={claim.id} className="claim" data-status={claim.status}>
                <div className="claim-head">
                  <span className="claim-status">{claim.status}</span>
                  <span className="tag">{CLASS_LABEL[claim.claim_class] ?? claim.claim_class}</span>
                  {claim.scope && <span className="tag">{claim.scope}</span>}
                  {due && <span className="tag tag-warn">recheck due</span>}
                </div>
                <p className="claim-text">{claim.claim_text}</p>
                {claim.supporting_excerpt && (
                  <blockquote className="claim-excerpt">{claim.supporting_excerpt}</blockquote>
                )}
                <div className="claim-foot">
                  {claim.source_url ? (
                    <a href={claim.source_url} target="_blank" rel="noreferrer noopener">
                      {claim.source_owner || hostOf(claim.source_url)}
                    </a>
                  ) : (
                    <span className="muted small">no source cited</span>
                  )}
                  <div className="claim-actions" role="group" aria-label="Set claim status">
                    {(["supported", "unknown", "contradicted"] as const).map((status) => (
                      <button
                        key={status}
                        type="button"
                        className="btn btn-small btn-ghost"
                        aria-pressed={claim.status === status}
                        disabled={busy !== null || claim.status === status}
                        onClick={() => setStatus(claim, status)}
                      >
                        {status === "supported" ? "Supported" : status === "unknown" ? "Unknown" : "Contradicted"}
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {error && <p className="notice notice-danger small" role="alert">{error}</p>}
    </div>
  );
}
