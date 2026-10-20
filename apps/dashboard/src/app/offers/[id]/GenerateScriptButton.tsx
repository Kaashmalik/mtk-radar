"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REVIEWER = "kashif"; // TODO(week-5): real session identity

/** Generates a versioned script — the API hard-gates this on verified state. */
export default function GenerateScriptButton({ offerId }: { offerId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `${API}/offers/${offerId}/script?created_by=${encodeURIComponent(REVIEWER)}`,
        { method: "POST" },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      const body = await res.json();
      if (body.unsafe_command_cards > 0) {
        setError(`${body.unsafe_command_cards} command card(s) unsafe — fix before filming`);
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        disabled={busy}
        onClick={generate}
        style={{
          padding: "0.35rem 0.8rem",
          fontSize: "0.8rem",
          borderRadius: 6,
          border: "1px solid #1f6feb",
          background: "#1f6feb",
          color: "#fff",
          cursor: busy ? "wait" : "pointer",
        }}
      >
        {busy ? "Generating…" : "⚡ Generate script (latest evidence)"}
      </button>
      {error && <p style={{ color: "#f0883e", fontSize: "0.75rem", margin: "0.4rem 0 0" }}>⚠ {error}</p>}
    </div>
  );
}
