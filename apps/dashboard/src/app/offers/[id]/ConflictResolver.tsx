"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";
import type { ExtractionField } from "./ExtractionEditor";

export type ExtractionConflict = {
  field?: string;
  reason?: string;
  values?: unknown;
  evidence_ids?: unknown;
  [key: string]: unknown;
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

type Draft = {
  include: boolean;
  replace: boolean;
  value: string;
  evidenceId: string;
  note: string;
};

/**
 * Per-conflict triage for the latest extraction.
 *
 * Each open conflict is decided on its own: keep the recorded claim (dismiss
 * the disagreement) or replace it with a corrected value that still cites an
 * immutable snapshot. Conflicts left unchecked stay open — a partial
 * resolution cannot silently whitewash a disagreement.
 */
export default function ConflictResolver({
  offerId,
  conflicts,
  fields,
}: {
  offerId: string;
  conflicts: ExtractionConflict[];
  fields: Record<string, ExtractionField>;
}) {
  const router = useRouter();
  const [drafts, setDrafts] = useState<Record<number, Draft>>(() =>
    Object.fromEntries(
      conflicts.map((conflict, index) => [
        index,
        {
          include: false,
          replace: false,
          value: "",
          evidenceId: fields[conflict.field ?? ""]?.evidence_id ?? "",
          note: "",
        } satisfies Draft,
      ]),
    ),
  );
  const [reviewNote, setReviewNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  if (conflicts.length === 0) return null;

  const selected = conflicts.filter((_, index) => drafts[index]?.include).length;

  function update(index: number, patch: Partial<Draft>) {
    setDrafts((current) => ({
      ...current,
      [index]: { ...current[index], ...patch },
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    const resolutions = conflicts
      .map((conflict, index) => ({ conflict, index }))
      .filter(({ index }) => drafts[index]?.include)
      .map(({ conflict, index }) => {
        const draft = drafts[index];
        return {
          field: conflict.field ?? "value",
          ...(draft.replace && draft.value.trim()
            ? {
                value: draft.value.trim(),
                ...(draft.evidenceId.trim()
                  ? { evidence_id: draft.evidenceId.trim() }
                  : {}),
              }
            : {}),
          ...(draft.note.trim() ? { note: draft.note.trim() } : {}),
        };
      });
    if (resolutions.length === 0) {
      setError("Tick at least one conflict to resolve.");
      setBusy(false);
      return;
    }
    try {
      const res = await clientFetch(`/offers/${offerId}/conflicts/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolutions, review_note: reviewNote.trim() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(detailText(body.detail) ?? `HTTP ${res.status}`);
        return;
      }
      const remaining = typeof body.remaining_conflicts === "number"
        ? body.remaining_conflicts
        : null;
      setResult(
        remaining === 0
          ? "All conflicts resolved. The offer still goes back for re-verification."
          : `Resolved. ${remaining} conflict(s) remain open.`,
      );
      setReviewNote("");
      setDrafts((current) =>
        Object.fromEntries(
          Object.entries(current).map(([index, draft]) => [
            index,
            { ...draft, include: false, note: "" },
          ]),
        ),
      );
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      style={{ display: "grid", gap: "0.75rem", marginTop: "0.8rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.8rem" }}
    >
      <p className="muted small" style={{ margin: 0 }}>
        Resolve each conflict individually. Unticked conflicts stay open and
        keep blocking verification. Replacing a value still needs a cited
        snapshot — the claim never loses its evidence.
      </p>

      {conflicts.map((conflict, index) => {
        const field = typeof conflict.field === "string" ? conflict.field : "value";
        const draft = drafts[index];
        const candidateValues = Array.isArray(conflict.values) ? conflict.values : null;
        const recorded = fields[field]?.value;
        return (
          <fieldset
            key={index}
            style={{
              border: "1px solid var(--border-subtle)",
              borderRadius: 8,
              padding: "0.6rem 0.75rem",
              margin: 0,
            }}
          >
            <legend className="small" style={{ padding: "0 0.3rem" }}>
              <strong>{FIELD_LABELS[field] ?? field}</strong>
              {conflict.reason ? ` — ${conflict.reason}` : ""}
            </legend>
            <label className="small" style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input
                type="checkbox"
                checked={draft.include}
                onChange={(event) => update(index, { include: event.target.checked })}
                style={{ marginTop: 3 }}
              />
              <span>I checked the cited snapshots for this conflict.</span>
            </label>
            {recorded !== undefined && (
              <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
                Recorded value: <code>{recorded}</code>
              </p>
            )}
            {candidateValues && candidateValues.length > 0 && (
              <p className="muted small" style={{ margin: "0.3rem 0 0" }}>
                Disagreeing values: {candidateValues.map(String).join(" vs ")}
              </p>
            )}
            <label className="small" style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 6 }}>
              <input
                type="checkbox"
                checked={draft.replace}
                onChange={(event) => update(index, { replace: event.target.checked })}
                style={{ marginTop: 3 }}
              />
              <span>Replace the recorded value with a corrected one:</span>
            </label>
            {draft.replace && (
              <div style={{ display: "grid", gap: 6, marginTop: 6 }}>
                <input
                  aria-label={`Corrected value for ${FIELD_LABELS[field] ?? field}`}
                  value={draft.value}
                  onChange={(event) => update(index, { value: event.target.value })}
                  placeholder="Corrected value"
                  style={{ width: "100%" }}
                />
                <input
                  aria-label={`Evidence id for ${FIELD_LABELS[field] ?? field}`}
                  value={draft.evidenceId}
                  onChange={(event) => update(index, { evidenceId: event.target.value })}
                  placeholder="Evidence id (snapshot uuid) supporting the corrected value"
                  style={{ width: "100%" }}
                />
              </div>
            )}
            <input
              aria-label={`Triage note for ${FIELD_LABELS[field] ?? field}`}
              value={draft.note}
              onChange={(event) => update(index, { note: event.target.value })}
              placeholder="Why this side is correct (recorded in the audit log)"
              style={{ width: "100%", marginTop: 6 }}
            />
          </fieldset>
        );
      })}

      <label htmlFor="conflict-review-note" className="small">
        Review note {selected === conflicts.length ? "(required when clearing the last conflict)" : "(required)"}
      </label>
      <textarea
        id="conflict-review-note"
        rows={2}
        value={reviewNote}
        onChange={(event) => setReviewNote(event.target.value)}
        placeholder="What you checked and why the resolutions are right"
        required
      />

      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      {result && <p className="small" style={{ color: "var(--ok)", margin: 0 }}>{result}</p>}

      <button type="submit" className="btn btn-primary btn-small" disabled={busy || selected === 0}>
        {busy ? "Saving…" : selected === 1 ? "Resolve 1 conflict" : `Resolve ${selected} conflicts`}
      </button>
    </form>
  );
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
