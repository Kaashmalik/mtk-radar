/**
 * Content Studio (v0.27) — one verified offer becomes a reviewable bilingual
 * package: scripts, SEO metadata (A/B), covers and motion-ready beats.
 * Generation creates drafts only; approval and rendering stay explicit.
 */

import "../../styles.css";
import Link from "next/link";

import StudioGenerateButton from "./StudioGenerateButton";
import PackageEditor from "./PackageEditor";
import ScriptRevise from "./ScriptRevise";
import VariantExplorer from "./VariantExplorer";
import { apiFetch } from "@/lib/api";

type Script = {
  id: string;
  version: number;
  language: string;
  format: string;
  markdown: string;
  metadata: Record<string, unknown> | string;
  created_by: string | null;
  created_at: string;
};

type Variant = {
  id: string;
  language: string;
  kind: string;
  platform: string | null;
  variant_key: string;
  payload: Record<string, unknown> | string;
  text_content: string | null;
  status: string;
  version: number;
  version_hash: string | null;
  created_at: string;
};

type LanguagePolicy = {
  metadata_language: string;
  captions_language: string;
  narration_languages: string[];
  default_narration_language: string;
  urdu_voiceover_enabled?: boolean;
};

type Studio = {
  offer: {
    id: string;
    title: string;
    provider: string;
    category: string | null;
    state: string;
    promo_code: string | null;
    redemption_url: string | null;
  };
  brand: { website_url?: string; name?: string; cta?: string };
  languages: string[];
  allowed_narration_languages?: string[];
  language_policy?: LanguagePolicy;
  platforms: string[];
  scripts: Script[];
  variants: Variant[];
  has_content: boolean;
};

async function getStudio(id: string): Promise<Studio | null> {
  try {
    const res = await apiFetch(`/studio/offers/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as Studio;
  } catch {
    return null;
  }
}

async function getLanguagePolicy(): Promise<LanguagePolicy> {
  const fallback: LanguagePolicy = {
    metadata_language: "en",
    captions_language: "en",
    narration_languages: ["en"],
    default_narration_language: "en",
    urdu_voiceover_enabled: false,
  };
  try {
    const res = await apiFetch("/settings/language_policy", { cache: "no-store" });
    if (!res.ok) return fallback;
    const body = (await res.json()) as { value?: Partial<LanguagePolicy> | null };
    return { ...fallback, ...(body.value ?? {}) };
  } catch {
    return fallback;
  }
}

function coverStyle(payload: Record<string, unknown>): React.CSSProperties {
  const palette = (payload.palette ?? {}) as Record<string, string>;
  return {
    background: `linear-gradient(135deg, ${palette.bg ?? "#07111f"}, ${palette.bg2 ?? "#0b2239"})`,
    borderColor: palette.accent ?? "var(--border)",
    color: palette.text ?? "var(--text)",
    minHeight: 150,
    display: "flex",
    flexDirection: "column",
    justifyContent: "space-between",
    padding: "0.9rem",
    borderRadius: 10,
    borderWidth: 1,
    borderStyle: "solid",
    direction: payload.language === "ur" ? "rtl" : "ltr",
  };
}

export const dynamic = "force-dynamic";

export default async function StudioOfferPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [data, policy] = await Promise.all([getStudio(id), getLanguagePolicy()]);

  if (!data) {
    return (
      <main className="page">
        <Link href="/studio" className="back">← Studio</Link>
        <h1>Content studio unavailable</h1>
        <p className="tagline">The offer was not found, or the API is unreachable.</p>
      </main>
    );
  }

  const { offer } = data;
  const scriptsByLanguage = new Map<string, Script>();
  for (const script of data.scripts) {
    if (!scriptsByLanguage.has(script.language)) scriptsByLanguage.set(script.language, script);
  }
  const covers = data.variants.filter((variant) => variant.kind === "cover");
  const scriptVariants = data.variants.filter((variant) => variant.kind === "script");
  const renderable = ["verified", "approved_for_video", "published"].includes(offer.state);
  const allowed = data.allowed_narration_languages
    ?? policy.narration_languages
    ?? ["en"];
  const scriptLanguages = allowed.includes("ur") ? (["en", "ur"] as const) : (["en"] as const);
  const copyLanguage = policy.metadata_language || "en";
  const captionsLanguage = policy.captions_language || "en";

  return (
    <main className="page">
      <Link href="/studio" className="back">← Content studio</Link>
      <section className="hero" style={{ marginTop: "0.6rem" }}>
        <div className="hero-copy">
          <span className="eyebrow">Content studio</span>
          <h1>{offer.title}</h1>
          <p>
            {offer.provider} · {offer.category ?? "uncategorised"} ·{" "}
            <span className={`tag ${renderable ? "tag-ok" : "tag-hot"}`}>{offer.state}</span>
          </p>
          <div className="hero-actions">
            <StudioGenerateButton
              offerId={offer.id}
              hasContent={data.has_content}
              allowedLanguages={allowed}
            />
            <Link href={`/offers/${offer.id}`} className="btn btn-ghost">Offer workspace</Link>
          </div>
        </div>
        <aside className="panel">
          <div className="panel-head">
            <div>
              <h2>Package</h2>
              <p>Drafts are reviewable source assets.</p>
            </div>
          </div>
          <div className="metric-row"><span>Voiceover</span><strong>{allowed.includes("ur") ? "English + Urdu" : "English only"}</strong></div>
          <div className="metric-row"><span>Title / details</span><strong>{copyLanguage === "en" ? "English" : "Urdu"}</strong></div>
          <div className="metric-row"><span>Screen captions</span><strong>{captionsLanguage === "en" ? "English" : "Urdu"}</strong></div>
          <div className="metric-row"><span>Script versions</span><strong>{scriptVariants.length}</strong></div>
          <div className="metric-row"><span>Metadata variants</span><strong>{data.variants.filter((v) => v.kind === "metadata").length}</strong></div>
          <div className="metric-row"><span>Covers</span><strong>{covers.length}</strong></div>
          <div className="metric-row"><span>Website CTA</span><strong className="small">{data.brand?.website_url || "not set"}</strong></div>
        </aside>
      </section>

      {!renderable && (
        <section className="card">
          <p style={{ margin: 0, color: "var(--warn)" }}>
            This offer is not verified yet. Content generation is blocked by the API
            until official evidence and a complete extraction exist.
          </p>
        </section>
      )}

      {!allowed.includes("ur") && (
        <section className="card">
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            <strong style={{ color: "var(--text)" }}>English-first package.</strong>{" "}
            Titles, descriptions, hashtags, covers and on-screen captions stay in English.
            Urdu voiceover is off; enable it in Settings → Language policy when you want
            an Urdu-spoken version.
          </p>
        </section>
      )}

      <section className={scriptLanguages.length > 1 ? "grid-2" : ""}>
        {scriptLanguages.map((language) => {
          const script = scriptsByLanguage.get(language);
          return (
            <div className="panel" key={language}>
              <div className="panel-head">
                <div>
                  <h2>{language === "ur" ? "اردو اسکرپٹ" : "English script"}</h2>
                  <p>{script ? `v${script.version} · ${new Date(script.created_at).toLocaleString("en-GB")}` : "not generated"}</p>
                </div>
                {script && <span className="tag tag-accent">{(script.metadata as { beats?: unknown[] } | undefined)?.beats?.length ?? 0} beats</span>}
              </div>
              {!script ? (
                <div className="empty-state">
                  Generate content to create the {language === "ur" ? "Urdu" : "English"} script,
                  captions and metadata from verified evidence.
                </div>
              ) : (
                <>
                  <pre
                    className="mono"
                    style={{
                      maxHeight: 360,
                      overflow: "auto",
                      whiteSpace: "pre-wrap",
                      direction: language === "ur" ? "rtl" : "ltr",
                      textAlign: language === "ur" ? "right" : "left",
                      fontSize: "0.76rem",
                      lineHeight: 1.65,
                      margin: 0,
                    }}
                  >
                    {script.markdown}
                  </pre>
                  <ScriptRevise
                    scriptId={script.id}
                    version={script.version}
                    language={language}
                    markdown={script.markdown}
                    format={script.format}
                  />
                </>
              )}
            </div>
          );
        })}
      </section>

      <section className="card">
        <div className="panel-head">
          <div>
            <h2>Publishing metadata</h2>
            <p>
              English titles, descriptions and hashtags for every voiceover version;
              platform limits, tracked website link, CTA and pinned comment.
            </p>
          </div>
        </div>
        <VariantExplorer variants={data.variants} />
        {data.has_content ? (
          <>
            <div style={{ height: "0.8rem" }} />
            <details>
              <summary className="small"><strong>Edit captions, chapters &amp; metadata</strong></summary>
              <div style={{ marginTop: "0.6rem" }}>
                <PackageEditor offerId={offer.id} languages={scriptLanguages as unknown as string[]} />
              </div>
            </details>
          </>
        ) : null}
      </section>

      <section className="card">
        <div className="panel-head">
          <div>
            <h2>Cover sources</h2>
            <p>Deterministic SVG covers; the renderer converts to PNG when Pillow is available.</p>
          </div>
        </div>
        {covers.length === 0 ? (
          <div className="empty-state">No covers yet — generate the content package first.</div>
        ) : (
          <div className="grid-3">
            {covers.map((cover) => {
              const payload = (typeof cover.payload === "string" ? {} : cover.payload) as Record<string, unknown>;
              // 2026 packaging rule: the big thumbnail wording is at most 3
              // words and never repeats the title; the full title stays as a
              // small reference line (and in the real render, the aria-label).
              const thumbText = String(payload.thumbnail_text ?? payload.title ?? offer.title);
              const title = String(payload.title ?? offer.title);
              const variant = String(payload.variant ?? cover.variant_key);
              return (
                <div key={cover.id} style={coverStyle(payload)}>
                  <div>
                    <div style={{ fontSize: "0.62rem", letterSpacing: "0.14em", opacity: 0.85 }}>
                      {String(payload.eyebrow ?? "VERIFIED CLAIM")}
                    </div>
                    <strong style={{ display: "block", marginTop: 6, fontSize: "1.35rem", textTransform: "uppercase" }}>{thumbText}</strong>
                    <span style={{ display: "block", marginTop: 4, fontSize: "0.62rem", opacity: 0.65 }}>{title}</span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "end", gap: 6 }}>
                    <span style={{ fontSize: "0.65rem", opacity: 0.8 }}>{cover.language} · {variant}</span>
                    <span style={{ fontSize: "0.65rem", color: String((payload.palette as Record<string, string> | undefined)?.warm ?? "#fbbf24") }}>
                      {String(payload.cta ?? "")}
                    </span>
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
