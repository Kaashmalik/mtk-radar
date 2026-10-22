"use client";

import { useState } from "react";

import { clientFetch } from "@/lib/api-client";

export type LanguagePolicy = {
  metadata_language: string;
  captions_language: string;
  narration_languages: string[];
  default_narration_language: string;
  urdu_voiceover_enabled?: boolean;
};

const FALLBACK: LanguagePolicy = {
  metadata_language: "en",
  captions_language: "en",
  narration_languages: ["en"],
  default_narration_language: "en",
  urdu_voiceover_enabled: false,
};

export default function LanguagePolicyForm({ initial }: { initial?: LanguagePolicy | null }) {
  const start = { ...FALLBACK, ...(initial ?? {}) };
  const [urduVoiceover, setUrduVoiceover] = useState(
    (start.narration_languages ?? ["en"]).includes("ur"),
  );
  const [defaultNarration, setDefaultNarration] = useState(
    start.default_narration_language || "en",
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const narration = urduVoiceover ? ["en", "ur"] : ["en"];
    const body = {
      value: {
        // The operator-facing policy is deliberately English-first: titles,
        // descriptions, hashtags, covers and captions stay English. Only the
        // spoken voiceover is configurable here.
        metadata_language: "en",
        captions_language: "en",
        narration_languages: narration,
        default_narration_language: narration.includes(defaultNarration) ? defaultNarration : "en",
      },
    };
    try {
      const res = await clientFetch("/settings/language_policy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(payload.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMessage(
        narration.includes("ur")
          ? "Saved. Urdu voiceover is enabled; packaging/captions stay English by default."
          : "Saved. English-only voiceover; packaging and captions stay English.",
      );
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="muted small" style={{ marginTop: 0 }}>
        English-first packaging is the default: title, description, hashtags, cover
        and on-screen captions stay English for every video. Turn on Urdu voiceover
        only when you want a spoken Urdu version; the written package can stay English.
      </p>
      <div style={{ display: "grid", gap: "0.85rem", maxWidth: 720 }}>
        <div
          className="small"
          style={{
            display: "grid",
            gap: 6,
            padding: "0.7rem 0.8rem",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span className="muted">Title, description, hashtags, cover</span>
            <strong>English</strong>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span className="muted">On-screen captions</span>
            <strong>English</strong>
          </div>
          <span className="muted">
            English-first packaging is fixed here so every video stays searchable and
            shareable. Only the spoken language is optional.
          </span>
        </div>
        <label
          className="small"
          style={{ display: "flex", gap: 10, alignItems: "flex-start" }}
        >
          <input
            type="checkbox"
            checked={urduVoiceover}
            onChange={(event) => {
              setUrduVoiceover(event.target.checked);
              if (!event.target.checked && defaultNarration === "ur") {
                setDefaultNarration("en");
              }
            }}
            style={{ marginTop: 3 }}
          />
          <span>
            <strong style={{ color: "var(--text)" }}>Enable Urdu voiceover</strong>
            <span className="muted" style={{ display: "block", marginTop: 2 }}>
              When off, the renderer only speaks English. When on, you can render an
              Urdu-spoken version; the title, details, hashtags, cover and on-screen
              captions stay English.
            </span>
          </span>
        </label>
        {urduVoiceover && (
          <label className="small">
            <span className="muted">Default spoken language for new renders</span>
            <select
              className="input"
              value={defaultNarration}
              onChange={(event) => setDefaultNarration(event.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4 }}
            >
              <option value="en">English</option>
              <option value="ur">Urdu</option>
            </select>
          </label>
        )}
        <div style={{ display: "flex", gap: "0.7rem", alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save language policy"}
          </button>
          {message && <span className="small" style={{ color: "var(--ok)" }}>{message}</span>}
          {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
        </div>
      </div>
    </div>
  );
}
