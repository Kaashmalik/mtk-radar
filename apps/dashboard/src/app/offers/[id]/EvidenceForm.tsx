"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

type SourceOption = {
  id: string;
  provider: string;
  canonical_domain: string | null;
  trust_tier: string;
};

/**
 * Attach a reviewer-witnessed evidence snapshot.
 *
 * The API decides `official` and `domain_ok`; this form cannot self-certify a
 * source. Official evidence needs snapshot text and a registered Tier-A source.
 * A machine-collected snapshot with provenance is still produced by the
 * acquisition worker, not this form.
 */
export default function EvidenceForm({
  offerId,
  sources,
}: {
  offerId: string;
  sources: SourceOption[];
}) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [captured, setCaptured] = useState("");
  const [official, setOfficial] = useState(false);
  const [screenshot, setScreenshot] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/evidence`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url.trim(),
          source_id: sourceId || null,
          excerpt: excerpt.trim() || null,
          captured_content: captured.trim() || null,
          official,
          screenshot_path: screenshot.trim() || null,
          supported_fields: [],
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(detailText(body.detail) ?? `HTTP ${res.status}`);
        return;
      }
      setResult(
        body.duplicate
          ? "Identical snapshot already stored — evidence was not duplicated."
          : `Evidence stored (${body.content_hash?.slice(0, 12)}…). Official: ${
              official ? (body.domain_ok ? "domain confirmed ✓" : "domain mismatch ✗") : "no"
            }.`,
      );
      setUrl("");
      setExcerpt("");
      setCaptured("");
      setScreenshot("");
      setOfficial(false);
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.45rem", marginTop: "0.9rem" }}>
      <h3 className="small" style={{ margin: 0 }}>Attach reviewer-witnessed evidence</h3>
      <p className="muted small" style={{ margin: 0 }}>
        Paste what you actually saw. The API hashes the snapshot and checks the
        provider&apos;s registered domain; it will not accept a self-declared
        official source.
      </p>

      <label htmlFor="ev-url" className="small">Evidence URL (HTTPS)</label>
      <input
        id="ev-url"
        type="url"
        required
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        placeholder="https://provider.example/terms"
      />

      <label htmlFor="ev-source" className="small">Registered source (optional)</label>
      <select id="ev-source" value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
        <option value="">— not linked —</option>
        {sources.map((source) => (
          <option key={source.id} value={source.id}>
            {source.provider} · {source.canonical_domain ?? "no domain"} · {source.trust_tier}
          </option>
        ))}
      </select>

      <label htmlFor="ev-excerpt" className="small">Supporting quote</label>
      <textarea
        id="ev-excerpt"
        rows={2}
        value={excerpt}
        onChange={(event) => setExcerpt(event.target.value)}
        placeholder="The exact sentence that supports the claim"
      />

      <label htmlFor="ev-captured" className="small">
        Snapshot text {official && <span style={{ color: "var(--warn)" }}>(required for official evidence)</span>}
      </label>
      <textarea
        id="ev-captured"
        rows={5}
        value={captured}
        onChange={(event) => setCaptured(event.target.value)}
        placeholder="Paste the relevant official page text you reviewed"
      />

      <label htmlFor="ev-screenshot" className="small">Screenshot storage path (optional)</label>
      <input
        id="ev-screenshot"
        value={screenshot}
        onChange={(event) => setScreenshot(event.target.value)}
        placeholder="projects/offer/screenshot.png"
      />

      <label className="small" style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="checkbox"
          checked={official}
          onChange={(event) => setOfficial(event.target.checked)}
        />
        This snapshot is official provider evidence (domain still checked server-side)
      </label>

      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      {result && <p className="small" style={{ color: "var(--ok)", margin: 0 }}>{result}</p>}

      <button
        type="submit"
        className="btn btn-primary btn-small"
        disabled={busy || !url.trim() || (official && !captured.trim())}
      >
        {busy ? "Storing…" : "Attach evidence"}
      </button>
    </form>
  );
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
