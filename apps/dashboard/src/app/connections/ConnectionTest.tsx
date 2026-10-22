"use client";

import { useState } from "react";
import { clientFetch } from "@/lib/api-client";

/**
 * Credential metadata check (plan §6.P0 "test connection").
 *
 * HONEST SCOPE: the database holds credential REFERENCES, never tokens, so
 * the API cannot make a live provider call. This button verifies what the
 * record itself claims — the reference exists, the recorded scopes cover the
 * platform's needs, the expiry is not in the past — and reports problems on
 * the account. A real live check happens in the worker holding the token.
 */
type TestResult = {
  ok: boolean;
  problems: string[];
  note: string;
};

export function ConnectionTest({ accountId }: { accountId: string }) {
  const [result, setResult] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await clientFetch(`/platform-accounts/${accountId}/test`, { method: "POST" });
      const body = await res.json().catch(() => null);
      if (!res.ok || !body) {
        setError(body?.detail ?? `HTTP ${res.status}`);
        return;
      }
      setResult(body);
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
      <button type="button" className="btn btn-ghost" onClick={() => void run()} disabled={busy}>
        {busy ? "checking…" : "Test"}
      </button>
      {result && (
        <span className={`tag ${result.ok ? "tag-ok" : "tag-hot"}`} title={result.problems.join("; ") || result.note}>
          {result.ok ? "metadata OK" : `${result.problems.length} problem(s)`}
        </span>
      )}
      {error && <span className="tag tag-hot" title={error}>failed</span>}
    </span>
  );
}
