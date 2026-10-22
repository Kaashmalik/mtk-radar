"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export type ExtractionField = {
  value: string;
  evidence_id: string;
  evidence_url: string;
  excerpt: string;
  confidence?: number | null;
  basis?: string | null;
  excluded_regions?: string[];
};

export type ExtractionSnapshot = {
  fields: Record<string, ExtractionField> | null;
  conflicts: unknown[] | null;
  coverage: Record<string, unknown> | null;
  model: string | null;
  created_at: string | null;
};

const FIELD_LABELS: Record<string, string> = {
  promo_code: "Promo code",
  price: "Price",
  value: "Value",
  benefit_type: "Benefit type",
  eligibility: "Eligibility",
  regions: "Regions",
  expiry: "Expiry",
  renewal: "Renewal",
  auto_renew: "Auto-renew",
};

/**
 * Review/edit the typed claims from the latest extraction.
 *
 * Every field stays bound to the immutable evidence snapshot that supported it;
 * this form edits the claim text, not the evidence. Clearing a conflict needs a
 * human note, which the API records in the audit log.
 */
export default function ExtractionEditor({
  offerId,
  extraction,
}: {
  offerId: string;
  extraction: ExtractionSnapshot | null;
}) {
  const router = useRouter();
  const initialFields = extraction?.fields ?? {};
  const initialConflicts = extraction?.conflicts ?? [];
  const [fields, setFields] = useState<Record<string, ExtractionField>>(initialFields);
  const [clearConflicts, setClearConflicts] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  if (!extraction) {
    return (
      <p className="muted small" style={{ margin: "0.5rem 0 0" }}>
        No structured extraction yet. The acquisition worker proposes one from
        official snapshots; verification is blocked until it is complete.
      </p>
    );
  }

  const names = Object.keys(fields).sort();
  const hasConflicts = initialConflicts.length > 0;

  function update(name: string, patch: Partial<ExtractionField>) {
    setFields((current) => ({
      ...current,
      [name]: { ...current[name], ...patch },
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/extraction`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fields,
          complete: false,
          conflicts: clearConflicts ? [] : initialConflicts,
          model: "dashboard-review",
          review_note: note.trim() || null,
          ...(extraction?.coverage ? { coverage: extraction.coverage } : {}),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(detailText(body.detail) ?? `HTTP ${res.status}`);
        return;
      }
      const errors = Array.isArray(body.validation_errors) ? body.validation_errors : [];
      setResult(
        errors.length
          ? `Saved. The offer stays unverified until these are fixed: ${errors.join(" · ")}`
          : "Claims saved. The offer was sent back for re-verification.",
      );
      setClearConflicts(false);
      setNote("");
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.75rem", marginTop: "0.8rem" }}>
      <p className="muted small" style={{ margin: 0 }}>
        Latest extraction {extraction.model ? `by ${extraction.model}` : ""}
        {extraction.created_at
          ? ` · ${new Date(extraction.created_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })}`
          : ""}
        . Editing any claim revokes verification until a reviewer re-verifies it.
      </p>

      {hasConflicts && (
        <div className="warnbox">
          <strong>{initialConflicts.length} unresolved conflict(s)</strong>
          <ul>
            {initialConflicts.map((conflict, index) => (
              <li key={index} className="small">
                <code>{JSON.stringify(conflict)}</code>
              </li>
            ))}
          </ul>
          <label className="small" style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={clearConflicts}
              onChange={(event) => setClearConflicts(event.target.checked)}
              style={{ marginTop: 3 }}
            />
            I checked the cited snapshots and resolved every conflict above.
          </label>
        </div>
      )}

      {names.length === 0 && (
        <p className="muted small" style={{ margin: 0 }}>
          No typed claims in this extraction. Add them with the acquisition
          worker before verifying.
        </p>
      )}

      {names.map((name) => (
        <fieldset
          key={name}
          style={{
            border: "1px solid var(--border-subtle)",
            borderRadius: 8,
            padding: "0.6rem 0.75rem",
            margin: 0,
          }}
        >
          <legend className="small" style={{ padding: "0 0.3rem" }}>
            {FIELD_LABELS[name] ?? name}
          </legend>
          <label htmlFor={`claim-${name}`} className="small">Claim value</label>
          <input
            id={`claim-${name}`}
            value={fields[name].value}
            onChange={(event) => update(name, { value: event.target.value })}
            required
            style={{ width: "100%" }}
          />
          <label htmlFor={`excerpt-${name}`} className="small" style={{ marginTop: 6, display: "block" }}>
            Exact supporting quote
          </label>
          <textarea
            id={`excerpt-${name}`}
            rows={2}
            value={fields[name].excerpt}
            onChange={(event) => update(name, { excerpt: event.target.value })}
            required
            style={{ width: "100%" }}
          />
          <div className="muted small" style={{ marginTop: 4 }}>
            Bound to <a href={fields[name].evidence_url} target="_blank" rel="noreferrer">snapshot</a>{" "}
            <code>{fields[name].evidence_id.slice(0, 8)}…</code>
          </div>
        </fieldset>
      ))}

      <label htmlFor="extraction-note" className="small">
        Review note {hasConflicts && clearConflicts ? "(required to clear conflicts)" : "(optional)"}
      </label>
      <textarea
        id="extraction-note"
        rows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="What you checked and why the claims/conflicts are now right"
        required={hasConflicts && clearConflicts}
      />

      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      {result && <p className="small" style={{ color: "var(--ok)", margin: 0 }}>{result}</p>}

      <button type="submit" className="btn btn-primary btn-small" disabled={busy || names.length === 0}>
        {busy ? "Saving…" : "Save reviewed claims"}
      </button>
    </form>
  );
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
