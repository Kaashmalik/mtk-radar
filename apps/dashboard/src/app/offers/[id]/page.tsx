import GenerateScriptButton from "./GenerateScriptButton";

/**
 * Offer workspace (weeks 5-6): verified offer → script versions, command-card
 * safety, capture sessions with redaction-review state.
 */

const API = process.env.API_URL ?? "http://localhost:8000";

type Evidence = {
  id: string;
  url: string;
  captured_at: string;
  excerpt: string | null;
  official: boolean;
  domain_ok: boolean;
  content_hash: string;
};

type ScriptRow = {
  id: string;
  version: number;
  markdown: string;
  command_cards: string;
  created_by: string | null;
  created_at: string;
};

type CaptureRow = {
  id: string;
  video_path: string | null;
  secret_findings: string;
  redaction_reviewed: boolean;
  reviewer: string | null;
  created_at: string;
};

type OfferDetail = {
  id: string;
  title: string;
  provider: string;
  state: string;
  expires_at: string | null;
  promo_code: string | null;
  evidence: Evidence[];
  correction_note: string | null;
};

type CommandCard = {
  command: string;
  source_url?: string | null;
  expected_output?: string | null;
  unsafe_reasons: string[];
};

export const dynamic = "force-dynamic";

async function getOffer(id: string): Promise<OfferDetail | null> {
  try {
    const res = await fetch(`${API}/offers/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function getScripts(id: string): Promise<ScriptRow[]> {
  try {
    const res = await fetch(`${API}/offers/${id}/scripts`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function getCaptures(id: string): Promise<CaptureRow[]> {
  try {
    const res = await fetch(`${API}/captures?offer_id=${id}`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export default async function OfferPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const offer = await getOffer(id);
  const scripts = await getScripts(id);
  const captures = await getCaptures(id);

  if (!offer) {
    return (
      <main className="page">
        <a href="/review" className="back">← Review desk</a>
        <h1>Offer not found</h1>
      </main>
    );
  }

  const latestScript = scripts[0];
  let unsafeCards: CommandCard[] = [];
  if (latestScript?.command_cards) {
    try {
      unsafeCards = (
        JSON.parse(latestScript.command_cards) as CommandCard[]
      ).filter((c) => c.unsafe_reasons?.length);
    } catch { /* ignore parse issues */ }
  }

  return (
    <main className="page">
      <a href="/review" className="back">← Review desk</a>
      <h1>{offer.title}</h1>
      <p className="tagline">
        {offer.provider}
        {offer.promo_code && <> · code <code>{offer.promo_code}</code></>}
        {offer.expires_at && <> · expires {new Date(offer.expires_at).toLocaleDateString("en-GB")}</>}
        {offer.correction_note && <> · ⚠ {offer.correction_note}</>}
      </p>

      <section className="card">
        <h2>Script ({scripts.length} version{scripts.length === 1 ? "" : "s"})</h2>
        <GenerateScriptButton offerId={offer.id} />
        {unsafeCards.length > 0 && (
          <div className="warnbox">
            <strong>{unsafeCards.length} unsafe command card(s):</strong>
            <ul>
              {unsafeCards.map((c, i) => (
                <li key={i}>
                  <code>{c.command.slice(0, 60)}</code> — {c.unsafe_reasons.join("; ")}
                </li>
              ))}
            </ul>
          </div>
        )}
        {latestScript && (
          <details open={scripts.length === 1}>
            <summary>
              Latest: v{latestScript.version} by {latestScript.created_by ?? "unknown"} ·{" "}
              {new Date(latestScript.created_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })}
            </summary>
            <pre className="script">{latestScript.markdown}</pre>
          </details>
        )}
        {!latestScript && <p className="muted small">No script yet — generate one above.</p>}
      </section>

      <section className="card">
        <h2>Capture sessions ({captures.length})</h2>
        {captures.length === 0 ? (
          <p className="muted small">
            None yet. Run the guided capture worker:
            <code> python workers/capture/main.py --offer {offer.id}</code>
          </p>
        ) : (
          <ul>
            {captures.map((c) => (
              <li key={c.id}>
                {new Date(c.created_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} —{" "}
                {c.redaction_reviewed ? (
                  <span style={{ color: "#3fb950" }}>redaction reviewed ✓</span>
                ) : (
                  <span style={{ color: "#f0883e" }}>redaction review pending ⚠</span>
                )}
                {c.reviewer && <span className="muted small"> ({c.reviewer})</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Evidence ({offer.evidence.length})</h2>
        <ul>
          {offer.evidence.map((ev) => (
            <li key={ev.id}>
              <a href={ev.url} target="_blank" rel="noreferrer">{ev.url}</a>{" "}
              {ev.official && <span className="pill ok-pill">official</span>}{" "}
              {!ev.domain_ok && <span className="pill bad-pill">domain ✗</span>}
              <div className="muted small">
                captured {new Date(ev.captured_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} · hash {ev.content_hash.slice(0, 12)}…
              </div>
            </li>
          ))}
        </ul>
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
          margin: 0.5rem 0 0;
          font-size: 1.5rem;
        }
        .tagline {
          color: #8b949e;
          margin: 0.3rem 0 0;
          font-size: 0.88rem;
        }
        .card {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 10px;
          padding: 1.1rem 1.25rem;
          margin-top: 1.25rem;
        }
        .card h2 {
          margin: 0 0 0.6rem;
          font-size: 1.05rem;
        }
        .warnbox {
          margin-top: 0.6rem;
          border: 1px solid #f0883e;
          border-radius: 8px;
          padding: 0.6rem 0.8rem;
          font-size: 0.8rem;
        }
        .script {
          background: #0d1117;
          border: 1px solid #21262d;
          border-radius: 8px;
          padding: 0.8rem 1rem;
          font-size: 0.8rem;
          white-space: pre-wrap;
          max-height: 480px;
          overflow: auto;
        }
        .pill {
          border-radius: 999px;
          padding: 0.05rem 0.45rem;
          font-size: 0.68rem;
          font-weight: 600;
        }
        .ok-pill {
          background: #0f3520;
          color: #3fb950;
        }
        .bad-pill {
          background: #3d1418;
          color: #f85149;
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
        ul {
          padding-left: 1.1rem;
          margin: 0.3rem 0;
        }
        li {
          margin: 0.35rem 0;
        }
        summary {
          cursor: pointer;
          font-size: 0.85rem;
          margin: 0.6rem 0;
        }
      `}</style>
    </main>
  );
}
