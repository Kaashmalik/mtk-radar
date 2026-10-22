"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export default function StudioGenerateButton({
  offerId,
  hasContent = false,
  allowedLanguages = ["en"],
}: {
  offerId: string;
  hasContent?: boolean;
  allowedLanguages?: string[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await clientFetch(`/studio/offers/${offerId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          languages: allowedLanguages,
          platforms: ["youtube", "instagram", "tiktok"],
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMessage(
        `${body.scripts_created} script(s), ${body.variants_created} variant(s) generated as drafts.`,
      );
      router.refresh();
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
      <button type="button" className="btn btn-primary" onClick={generate} disabled={busy}>
        {busy
          ? "Generating…"
          : `${hasContent ? "Regenerate" : "Generate"} ${
              allowedLanguages.includes("ur") ? "English + Urdu" : "English"
            } content`}
      </button>
      {message && <span className="small" style={{ color: "var(--ok)" }} role="status">{message}</span>}
      {error && <span className="small" style={{ color: "var(--danger)" }} role="alert">{error}</span>}
    </div>
  );
}
