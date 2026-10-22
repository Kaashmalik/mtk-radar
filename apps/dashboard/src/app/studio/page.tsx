/**
 * Studio index (v0.27) — pick a verified offer and build its bilingual
 * package: scripts, SEO variants, covers and beat sheets.
 */

import "../styles.css";
import Link from "next/link";

import { apiFetch } from "@/lib/api";

type OfferRow = {
  id: string;
  title: string;
  provider: string;
  category: string;
  state: string;
  official_evidence: number;
  evidence_count: number;
  recheck_at: string;
};

async function getOffers(): Promise<OfferRow[]> {
  try {
    const res = await apiFetch("/offers?limit=100", { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as OfferRow[];
  } catch {
    return [];
  }
}

const READY = new Set(["verified", "approved_for_video", "published"]);

export const dynamic = "force-dynamic";

export default async function StudioIndexPage() {
  const offers = await getOffers();
  const ready = offers.filter((offer) => READY.has(offer.state));
  const blocked = offers.filter((offer) => !READY.has(offer.state));

  return (
    <main className="page">
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">Production layer</span>
          <h1>Content studio</h1>
          <p>
            Turn one verified offer into an English-first package: platform metadata,
            A/B titles, hashtags, tracked website CTA, pinned comments, cover sources
            and an optional Urdu voiceover script when enabled in Settings.
            Generation is mechanical; approval is still a named human action.
          </p>
          <div className="hero-actions">
            <Link href="/radar" className="btn btn-primary">Find a topic</Link>
            <Link href="/review" className="btn btn-ghost">Review queue</Link>
          </div>
        </div>
        <aside className="panel">
          <div className="panel-head">
            <div><h2>Eligible offers</h2><p>Verified or approved for video</p></div>
            <span className="tag tag-ok">{ready.length}</span>
          </div>
          <div className="metric-row"><span>Total offers</span><strong>{offers.length}</strong></div>
          <div className="metric-row"><span>Ready for studio</span><strong>{ready.length}</strong></div>
          <div className="metric-row"><span>Needs verification</span><strong>{blocked.length}</strong></div>
          <p className="small muted" style={{ marginBottom: 0 }}>
            The API blocks generation before verification, so a blocked row can still be
            opened to inspect the evidence gap.
          </p>
        </aside>
      </section>

      <section className="card">
        <div className="panel-head">
          <div>
            <h2>Ready to produce</h2>
            <p>These offers have passed the verification gate.</p>
          </div>
          <span className="tag">{ready.length} offers</span>
        </div>
        {ready.length === 0 ? (
          <div className="empty-state">
            No verified offers yet. Promote a reviewed candidate, attach official evidence,
            and complete the extraction on the review desk.
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Offer</th><th>Provider</th><th>State</th><th>Evidence</th><th /></tr>
              </thead>
              <tbody>
                {ready.map((offer) => (
                  <tr key={offer.id}>
                    <td><strong>{offer.title}</strong><div className="muted small">{offer.category}</div></td>
                    <td>{offer.provider}</td>
                    <td><span className="tag tag-ok">{offer.state.replace(/_/g, " ")}</span></td>
                    <td>{offer.official_evidence}/{offer.evidence_count} official</td>
                    <td><Link href={`/studio/${offer.id}`} className="btn btn-ghost">Open studio →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <div className="panel-head">
          <div><h2>Blocked by truth gates</h2><p>Content cannot be generated for these yet.</p></div>
        </div>
        {blocked.length === 0 ? (
          <p className="muted small">No blocked offers.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Offer</th><th>Provider</th><th>State</th><th /></tr></thead>
              <tbody>
                {blocked.map((offer) => (
                  <tr key={offer.id}>
                    <td>{offer.title}</td>
                    <td>{offer.provider}</td>
                    <td><span className="tag">{offer.state.replace(/_/g, " ")}</span></td>
                    <td><Link href={`/offers/${offer.id}`} className="btn btn-ghost">Inspect</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
