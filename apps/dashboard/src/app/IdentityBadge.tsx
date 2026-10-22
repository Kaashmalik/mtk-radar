"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Shows the signed-in reviewer and clears the HttpOnly session cookie.
 * The token itself is never available to this component. */
export default function IdentityBadge({ actor }: { actor: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    try {
      await fetch("/api/session", { method: "DELETE" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <span
      role="status"
      title="Reviewer identity — actions are audited under this name"
      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}
    >
      <span style={{ color: "var(--text-muted)" }}>as</span>
      <strong>{actor}</strong>
      <button
        type="button"
        onClick={signOut}
        disabled={busy}
        aria-label="Sign out"
        style={btnStyle}
      >
        ⎋
      </button>
    </span>
  );
}

const btnStyle: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 6,
  background: "transparent",
  padding: "2px 8px",
  cursor: "pointer",
  fontSize: 13,
};
