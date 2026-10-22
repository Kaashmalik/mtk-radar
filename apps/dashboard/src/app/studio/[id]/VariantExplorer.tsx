"use client";

import { useMemo, useState } from "react";

type Variant = {
  id: string;
  language: string;
  kind: string;
  platform: string | null;
  variant_key: string;
  payload: Record<string, unknown> | string;
  status: string;
};

export default function VariantExplorer({ variants }: { variants: Variant[] }) {
  const metadata = useMemo(
    () => variants.filter((variant) => variant.kind === "metadata"),
    [variants],
  );
  const languages = useMemo(
    () => Array.from(new Set(metadata.map((variant) => variant.language))),
    [metadata],
  );
  const platforms = useMemo(
    () => Array.from(new Set(metadata.map((variant) => variant.platform ?? "all"))),
    [metadata],
  );
  const [language, setLanguage] = useState(languages[0] ?? "en");
  const [platform, setPlatform] = useState(platforms[0] ?? "youtube");

  const visible = metadata.filter(
    (variant) => variant.language === language && (variant.platform ?? "all") === platform,
  );

  if (metadata.length === 0) {
    return (
      <div className="empty-state">
        No metadata variants yet. Generate content to create English titles,
        hashtags, CTA, pinned comment and A/B packaging.
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginBottom: "0.8rem" }}>
        <div className="lang-tabs" aria-label="Voiceover version">
          {languages.map((value) => (
            <button key={value} type="button" aria-pressed={value === language}
                    onClick={() => setLanguage(value)}>
              {value === "ur" ? "Urdu voiceover" : "English voiceover"}
            </button>
          ))}
        </div>
        <div className="lang-tabs" aria-label="Metadata platform">
          {platforms.map((value) => (
            <button key={value} type="button" aria-pressed={value === platform}
                    onClick={() => setPlatform(value)}>
              {value}
            </button>
          ))}
        </div>
      </div>
      <div className="grid-2">
        {visible.map((variant) => {
          const payload = typeof variant.payload === "string"
            ? {} : variant.payload;
          const title = String(payload.title ?? "Untitled");
          const caption = String(payload.caption ?? "");
          const hashtags = Array.isArray(payload.hashtags) ? payload.hashtags.map(String) : [];
          const pinned = String(payload.pinned_comment ?? "");
          const website = String(payload.website_url ?? "");
          return (
            <article className="variant-card" key={variant.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <h3>Variant {variant.variant_key.toUpperCase()}</h3>
                <span className="tag">{variant.status}</span>
              </div>
              <strong style={{ fontSize: "0.86rem" }}>{title}</strong>
              <pre>{caption}</pre>
              {hashtags.length > 0 && (
                <p className="small muted" style={{ marginBottom: 0 }}>{hashtags.join(" ")}</p>
              )}
              {website && <p className="small" style={{ marginBottom: 0 }}>↗ {website}</p>}
              {pinned && <p className="small muted" style={{ marginBottom: 0 }}>Pinned: {pinned}</p>}
            </article>
          );
        })}
      </div>
    </div>
  );
}
