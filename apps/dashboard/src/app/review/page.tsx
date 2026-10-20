import OfferActions from "./OfferActions";

/**
 * Review desk (Weeks 3-4): the reviewer queue.
 * Verified+ offers can only advance through recorded reviewer actions (the API
 * enforces gates server-side); stale offers surface the correction workflow.
 */

const API = process.env.API_URL ?? "http://localhost:8000";

type OfferRow = {
  id: string;
  title: string;
  provider: string;
  category: string;
  offer_type: string;
  state: string;
  confidence: string;
  expires_at: string | null;
  recheck_at: string;
  official_evidence: number;
  evidence_count: number;
  conflicts: unknown;
  correction_note: string | null;
};

type StaleRow = {
  id: string;
  title: string;
  provider: string;
  state: string;
  reason: string;
};

export const dynamic = "force-dynamic";

async function getOffers(): Promise<OfferRow[]> {
  try {
    const res = await fetch(`${API}/offers?limit=100`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function getStale(): Promise<StaleRow[]> {
  try {
    const res = await fetch(`${API}/offers/stale`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

const STATE_COLORS: Record<string, string> = {
  candidate: "#8b949e",
  evidence_needed: "#d29922",
  verified: "#3fb950",
  approved_for_video: "#58a6ff",
  published: "#bc8cff",
  expired: "#f85149",
  corrected: "#f0883e",
};

export default async function ReviewPage() {
  const offers = await getOffers();
  const stale = await getStale();

  return (
    <main className="page">
      <header>
        <a href="/" className="back">← Inbox</a>
        <h1>Review desk</h1>
        <p className="tagline">
          Unverified offers cannot advance: verified requires official,
          domain-checked evidence and a complete extraction — enforced by the API.
        </p>
      </header>

      {stale.length > 0 && (
        <section className="card stale">
          <h2>⚠ Stale / expiring ({stale.length})</h2>
          <ul>
            {stale.map((s) => (
              <li key={s.id}>
                <strong>{s.title}</strong> — {s.reason}{" "}
                <span className="muted small">({s.state})</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h2>Offers ({offers.length})</h2>
        {offers.length === 0 ? (
          <p className="muted">
            No offers yet. Promote inbox items at <a href="/">the review inbox</a>{" "}
            or POST <code>/offers</code>.
          </p>
        ) : (
          <div style={{ display: "grid", gap: "0.9rem" }}>
            {offers.map((offer) => (
              <article key={offer.id} className="offer">
                <div className="offer-head">
                  <div>
                    <h3>{offer.title}</h3>
                    <p className="muted small">
                      {offer.provider} · {offer.category} · {offer.offer_type}
                      {offer.expires_at && (
                        <> · expires {new Date(offer.expires_at).toLocaleDateString("en-GB")}</>
                      )}
                    </p>
                  </div>
                  <span
                    className="badge"
                    style={{
                      background: "transparent",
                      color: STATE_COLORS[offer.state] ?? "#8b949e",
                      borderColor: STATE_COLORS[offer.state] ?? "#8b949e",
                    }}
                  >
                    {offer.state}
                  </span>
                </div>

                <p className="small">
                  Evidence: <strong>{offer.official_evidence}</strong> official /
                  {offer.evidence_count} total
                  {offer.conflicts && Array.isArray(offer.conflicts) && offer.conflicts.length > 0 && (
                    <span style={{ color: "#f0883e" }}>
                      {" "}· ⚠ {offer.conflicts.length} extraction conflict(s)
                    </span>
                  )}
                  {offer.correction_note && !offer.conflicts && (
                    <span className="muted"> · {offer.correction_note}</span>
                  )}
                </p>

                <OfferActions offerId={offer.id} state={offer.state} />
              </article>
            ))}
          </div>
        )}
      </section>

      <style jsx global>{`
        .page {
          max-width: 960px;
          margin: 0 auto;
          padding: 2rem 1.25rem;
          font-family: system-ui, sans-serif;
          color: #e8eaf0;
          background: #0d1117;
          min-height: 100vh;
        }
        .back {
          color: #58a6ff;
          text-decoration: none;
          font-size: 0.85rem;
        }
        h1 {
          margin: 0.4rem 0 0;
          font-size: 1.6rem;
        }
        .tagline {
          color: #8b949e;
          margin-top: 0.3rem;
          font-size: 0.88rem;
        }
        .card {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 10px;
          padding: 1.1rem 1.25rem;
          margin-top: 1.25rem;
        }
        .card.stale {
          border-color: #f0883e;
        }
        .card h2 {
          margin: 0 0 0.5rem;
          font-size: 1.05rem;
        }
        .card.stale h2 {
          color: #f0883e;
        }
        .offer {
          border: 1px solid #21262d;
          border-radius: 8px;
          padding: 0.8rem 1rem;
        }
        .offer-head {
          display: flex;
          justify-content: space-between;
          gap: 0.8rem;
          align-items: flex-start;
        }
        .offer h3 {
          margin: 0;
          font-size: 0.98rem;
        }
        .badge {
          border: 1px solid;
          border-radius: 999px;
          padding: 0.12rem 0.6rem;
          font-size: 0.72rem;
          font-weight: 600;
          white-space: nowrap;
        }
        .muted {
          color: #8b949e;
        }
        .small {
          font-size: 0.78rem;
        }
        a {
          color: #58a6ff;
          text-decoration: none;
        }
        code {
          background: #21262d;
          padding: 0.05rem 0.3rem;
          border-radius: 4px;
          font-size: 0.78rem;
        }
      `}</style>
    </main>
  );
}
