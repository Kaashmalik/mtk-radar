"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";

const FORMATS = [
  {
    id: "official_explainer",
    label: "Official terms explainer",
    hint: "Explains the published terms. No first-person claim or demonstrated result. Works without footage.",
  },
  {
    id: "tested_tutorial",
    label: "Tested tutorial",
    hint: "Shows the setup steps. Needs a capture whose redaction was reviewed; result wording follows what the reviewer saw.",
  },
  {
    id: "claim_walkthrough",
    label: "Claim walkthrough",
    hint: "First-person claim. Needs a reviewed capture and a reviewer-attested demonstrated benefit.",
  },
] as const;

/**
 * Generates a versioned script. The API hard-gates the offer state and the
 * selected format; disabling options here is only a convenience, not the gate.
 */
export default function GenerateScriptButton({
  offerId,
  hasReviewedCapture = false,
  hasDemonstratedCapture = false,
}: {
  offerId: string;
  hasReviewedCapture?: boolean;
  hasDemonstratedCapture?: boolean;
}) {
  const router = useRouter();
  const [format, setFormat] = useState<string>("official_explainer");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = FORMATS.find((item) => item.id === format) ?? FORMATS[0];
  const blocked =
    (format === "tested_tutorial" && !hasReviewedCapture) ||
    (format === "claim_walkthrough" && !hasDemonstratedCapture);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const params = new URLSearchParams({ format, language });
      const res = await clientFetch(`/offers/${offerId}/script?${params}`, {
        method: "POST",
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      if (body.unsafe_command_cards > 0) {
        setError(`${body.unsafe_command_cards} command card(s) unsafe — fix before filming`);
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 6, marginBottom: 8 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <label htmlFor={`format-${offerId}`} className="small">Format</label>
        <select
          id={`format-${offerId}`}
          value={format}
          onChange={(event) => {
            setFormat(event.target.value);
            setError(null);
          }}
        >
          {FORMATS.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
              {item.id === "tested_tutorial" && !hasReviewedCapture ? " — needs reviewed capture" : ""}
              {item.id === "claim_walkthrough" && !hasDemonstratedCapture ? " — needs demonstrated claim" : ""}
            </option>
          ))}
        </select>
        <label htmlFor={`language-${offerId}`} className="small">Language</label>
        <select
          id={`language-${offerId}`}
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
        >
          <option value="en">English</option>
          <option value="ur">Urdu</option>
        </select>
        <button
          className="btn btn-primary btn-small"
          disabled={busy || blocked}
          onClick={generate}
          type="button"
        >
          {busy ? "Generating…" : "⚡ Generate script"}
        </button>
      </div>
      <p className="muted small" style={{ margin: 0 }}>{selected.hint}</p>
      {blocked && (
        <p className="small" style={{ color: "var(--warn)", margin: 0 }}>
          {format === "claim_walkthrough"
            ? "No reviewer-attested demonstrated claim capture is available. Use tested tutorial or official explainer, or review a capture first."
            : "No redaction-reviewed capture is available. Use official explainer, or review a capture first."}
        </p>
      )}
      {error && <p role="alert" style={{ color: "var(--warn)", fontSize: "0.8rem", margin: 0 }}>⚠ {error}</p>}
    </div>
  );
}
