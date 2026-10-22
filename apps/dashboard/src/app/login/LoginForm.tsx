"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = { nextPath: string; reason?: string };

/**
 * Token entry is the only place a reviewer token is ever typed. It is posted
 * once to /api/session and exchanged for an HttpOnly cookie; the token is not
 * stored in localStorage, sessionStorage or any client-readable state.
 */
export default function LoginForm({ nextPath, reason }: Props) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(reasonText(reason));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token.trim() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `Sign-in failed (HTTP ${res.status})`);
        return;
      }
      setToken("");
      router.replace(nextPath);
      router.refresh();
    } catch {
      setError("Dashboard is unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.9rem" }}>
      <div>
        <label htmlFor="reviewer-token" style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>
          Personal reviewer token
        </label>
        <input
          id="reviewer-token"
          name="token"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          value={token}
          onChange={(event) => setToken(event.target.value)}
          placeholder="Paste the token minted for you"
          style={inputStyle}
        />
        <p className="muted small" style={{ margin: "0.45rem 0 0" }}>
          Mint one with{" "}
          <code>python -m scripts.mint_reviewer --name &quot;Your Name&quot;</code>{" "}
          from <code>services/api/</code>. Service, worker and extension tokens
          are not accepted here.
        </p>
      </div>

      {error && (
        <p role="alert" className="notice" style={{ borderColor: "var(--danger)", margin: 0 }}>
          {error}
        </p>
      )}

      <button type="submit" className="btn btn-primary" disabled={busy || token.trim().length < 20}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function reasonText(reason?: string): string | null {
  if (reason === "not_configured") {
    return "Dashboard authentication is not configured. Set MTK_SESSION_SECRET to a random value of at least 32 characters.";
  }
  if (reason === "expired") return "Your session expired. Sign in again.";
  return null;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "0.6rem 0.7rem",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)",
  background: "var(--bg-inset)",
  color: "var(--text)",
  fontFamily: "var(--mono)",
  fontSize: "0.86rem",
};
