import "./styles.css";
import GenerateScriptButton from "./GenerateScriptButton";
import ScheduleForm from "./ScheduleForm";
import { apiFetch } from "@/lib/api";

/**
 * Offer workspace (weeks 5-6): verified offer → script versions, command-card
 * safety, capture sessions with redaction-review state.
 * Week 11 (§18): correction log linked to the affected videos/posts.
 */


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

type RenderRow = {
  id: string;
  preset: string;
  width: number;
  height: number;
  duration_s: string | null;
  video_path: string;
  script_version: number | null;
  disclosure: string | { synthetic_narration?: boolean };
  status: string;
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
    const res = await apiFetch(`/offers/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function getScripts(id: string): Promise<ScriptRow[]> {
  try {
    const res = await apiFetch(`/offers/${id}/scripts`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function getCaptures(id: string): Promise<CaptureRow[]> {
  try {
    const res = await apiFetch(`/captures?offer_id=${id}`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function getRenders(id: string): Promise<RenderRow[]> {
  try {
    const res = await apiFetch(`/renders?offer_id=${id}`, { cache: "no-store" });
    if (!res.ok) return [];
    const rows: RenderRow[] = await res.json();
    return rows.map((r) => ({
      ...r,
      disclosure:
        typeof r.disclosure === "string"
          ? (() => {
              try { return JSON.parse(r.disclosure as string); } catch { return {}; }
            })()
          : r.disclosure,
    }));
  } catch {
    return [];
  }
}

type CorrectionRow = {
  id: string;
  note: string;
  corrected_by: string;
  version_hash: string | null;
  created_at: string;
};

type ImpactRow = {
  offer: { state: string; correction_note: string | null };
  schedules: {
    id: string;
    platform: string;
    state: string;
    local_time: string;
    privacy: string;
    remote_post_id: string | null;
    outcome_detail: string | null;
  }[];
};

async function getCorrections(id: string): Promise<CorrectionRow[]> {
  try {
    const res = await apiFetch(`/offers/${id}/corrections`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

async function getImpact(id: string): Promise<ImpactRow | null> {
  try {
    const res = await apiFetch(`/offers/${id}/impact`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function OfferPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const offer = await getOffer(id);
  const scripts = await getScripts(id);
  const captures = await getCaptures(id);
  const renders = await getRenders(id);
  const [corrections, impact] = await Promise.all([getCorrections(id), getImpact(id)]);

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
        {" · "}
        <a href="/calendar">Open calendar →</a>
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
        {renders.length > 0 && (
          <div style={{ marginTop: "0.8rem" }}>
            <h3 className="small" style={{ margin: "0 0 0.4rem" }}>Schedule a test post (private first)</h3>
            <ScheduleForm offerId={offer.id} />
          </div>
        )}
      </section>

      <section className="card">
        <h2>Rendered exports ({renders.length})</h2>
        {renders.length === 0 ? (
          <p className="muted small">
            None yet. Render from versioned sources:
            <code> python workers/render/main.py --offer {offer.id} --video capture.mp4</code>
          </p>
        ) : (
          <ul>
            {renders.map((r) => (
              <li key={r.id}>
                <strong>{r.preset}</strong> {r.width}×{r.height}
                {r.duration_s && <> · {Number(r.duration_s).toFixed(0)}s</>}
                {r.script_version && <> · script v{r.script_version}</>}
                {r.disclosure && typeof r.disclosure === "object" && r.disclosure.synthetic_narration && (
                  <span style={{ color: "#f0883e" }}> · TTS narration (label required)</span>
                )}
                <div className="muted small">{r.video_path}</div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Corrections &amp; affected posts ({corrections.length})</h2>
        {corrections.length === 0 && !offer.correction_note ? (
          <p className="muted small">
            No corrections logged. Corrections pause affected scheduled posts
            automatically and link the videos/posts they came from (monitor:
            <code> python workers/monitor/main.py</code>).
          </p>
        ) : (
          <div style={{ display: "grid", gap: "0.6rem" }}>
            {offer.correction_note && (
              <p className="small" style={{ color: "#f0883e" }}>
                ⚠ Current correction note: {offer.correction_note}
              </p>
            )}
            {corrections.map((c) => (
              <article key={c.id} className="entry">
                <div className="small">
                  {new Date(c.created_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })} —{" "}
                  {c.note}
                  <div className="muted small">
                    by {c.corrected_by}
                    {c.version_hash && <> · supersedes script {c.version_hash}</>}
                  </div>
                </div>
              </article>
            ))}
            {impact && impact.schedules.length > 0 && (
              <div>
                <h3 className="small" style={{ margin: "0.3rem 0 0.4rem" }}>
                  Affected videos/posts (§18 week 11):
                </h3>
                <ul>
                  {impact.schedules.map((s) => {
                    let autoPaused: string | null = null;
                    if (s.outcome_detail) {
                      try { autoPaused = JSON.parse(s.outcome_detail)?.detail ?? null; } catch {}
                    }
                    return (
                      <li key={s.id} className="small">
                        <strong>{s.platform}</strong> — {s.state}
                        {s.remote_post_id && <> · live post {s.remote_post_id}</>}
                        {autoPaused && (
                          <span style={{ color: "#f0883e" }}> · {autoPaused}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>
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

    </main>
  );
}
