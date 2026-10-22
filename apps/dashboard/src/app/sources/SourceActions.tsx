"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export type SourcePermission = {
  id: string;
  provider: string;
  canonical_domain: string | null;
  tos_reviewed_at: string | null;
  tos_reviewer: string | null;
  tos_reference: string | null;
  tos_expires_at: string | null;
  tos_valid: boolean;
};

/**
 * Per-source permission review. Automated reads are only allowed after a named
 * human attests that the source's terms permit them; revoking stops new machine
 * evidence immediately. Existing evidence is immutable and stays auditable.
 */
export default function SourceActions({ source }: { source: SourcePermission }) {
  const router = useRouter();
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function attest(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/sources/${source.id}/tos-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reference: reference.trim() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      setReference("");
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!window.confirm("Withdraw permission to read this source? New machine evidence will stop immediately.")) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/sources/${source.id}/tos-review`, { method: "DELETE" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: 4, minWidth: 190 }}>
      {source.tos_valid ? (
        <>
          <span className="small" style={{ color: "var(--ok)" }}>permission current ✓</span>
          <span className="muted small">
            by {source.tos_reviewer ?? "unknown"}
            {source.tos_expires_at && (
              <> · expires {new Date(source.tos_expires_at).toLocaleDateString("en-GB")}</>
            )}
          </span>
          {source.tos_reference && (
            <span className="muted small">ref: {source.tos_reference}</span>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-small"
            onClick={revoke}
            disabled={busy}
          >
            Revoke permission
          </button>
        </>
      ) : (
        <form onSubmit={attest} style={{ display: "grid", gap: 4 }}>
          <span className="small" style={{ color: "var(--warn)" }}>
            {source.tos_reviewed_at ? "permission expired ⚠" : "not reviewed ⚠"}
          </span>
          <span className="muted small">
            Machine reads are blocked until a human records the terms reference.
          </span>
          <input
            aria-label={`Terms reference for ${source.provider}`}
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder="Terms URL or ticket id"
            required
            minLength={3}
          />
          <button
            type="submit"
            className="btn btn-primary btn-small"
            disabled={busy || reference.trim().length < 3}
          >
            {busy ? "Recording…" : "Attest permission"}
          </button>
        </form>
      )}
      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
    </div>
  );
}
