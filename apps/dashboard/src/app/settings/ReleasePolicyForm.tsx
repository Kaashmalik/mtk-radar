"use client";

import { useState } from "react";

import { clientFetch } from "@/lib/api-client";

/**
 * Release policy (plan §17) — what a queued post must PROVE before upload:
 * mandatory YouTube package assets (thumbnail/captions/metadata) and a recorded
 * human playback sign-off. Defaults are strict; relaxing either is a recorded
 * operator decision (the write requires a human credential, like the
 * automation policy).
 */
export type ReleasePolicy = {
  require_package_assets: boolean;
  require_playback_review: boolean;
};

const FALLBACK: ReleasePolicy = {
  require_package_assets: true,
  require_playback_review: true,
};

export default function ReleasePolicyForm({ initial }: { initial?: ReleasePolicy | null }) {
  const [policy, setPolicy] = useState<ReleasePolicy>({ ...FALLBACK, ...(initial ?? {}) });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(next: ReleasePolicy) {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const res = await clientFetch("/settings/release_policy", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: next }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(payload.detail ?? `HTTP ${res.status}`);
        return;
      }
      setPolicy(next);
      setMessage("Saved. Applies to the next upload authorization.");
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  const rows: [keyof ReleasePolicy, string, string][] = [
    [
      "require_package_assets",
      "Require complete YouTube package",
      "The upload authorization refuses releases missing the thumbnail, captions file or approved metadata.",
    ],
    [
      "require_playback_review",
      "Require human playback sign-off",
      "A named human must record that they watched the final export before it can be released.",
    ],
  ];

  return (
    <div style={{ display: "grid", gap: "0.7rem" }}>
      {rows.map(([key, label, help]) => {
        const enabled = policy[key];
        return (
          <label key={key} style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={enabled}
              disabled={busy}
              onChange={(e) => void save({ ...policy, [key]: e.target.checked })}
            />
            <span>
              <strong>{label}</strong>
              <div className="muted small">{help}</div>
            </span>
          </label>
        );
      })}
      {message && <p className="small" style={{ color: "var(--ok)" }}>{message}</p>}
      {error && <p className="small" style={{ color: "var(--danger)" }}>{error}</p>}
      <p className="muted small" style={{ margin: 0 }}>
        These map to <code>settings.release_policy</code>; the release gate and
        the dashboard’s release-readiness card read the same value.
      </p>
    </div>
  );
}
