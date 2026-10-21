"use client";

/** Identity badge + token setup (v0.16). Probes GET /whoami with the stored
 * reviewer token: valid → shows who is acting; invalid → prompts to paste a
 * token minted with `python -m scripts.mint_reviewer --name <name>`. */

import { useCallback, useEffect, useState } from "react";

import {
  clearReviewerIdentity,
  getReviewerName,
  getReviewerToken,
  setReviewerIdentity,
} from "@/lib/identity";
import { clientFetch } from "@/lib/api-client";

export default function IdentityBadge() {
  const [state, setState] = useState<
    { kind: "loading" } | { kind: "idle"; name: null | string } | { kind: "setup"; error?: string }
  >({ kind: "loading" });
  const [name, setName] = useState("");
  const [token, setToken] = useState("");

  const probe = useCallback(async () => {
    if (!getReviewerToken()) {
      setState({ kind: "setup" });
      return;
    }
    try {
      const res = await clientFetch("/whoami", { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        const body = await res.json();
        if (body.auth === "reviewer" && body.actor) {
          setState({ kind: "idle", name: body.actor });
          return;
        }
        // valid credential but not a reviewer token (service/dev) — identity
        // is not bound; keep prompting for a personal token
        setState({ kind: "setup", error: body.auth === "service"
          ? "that is the shared worker token — paste a personal reviewer token" : undefined });
        return;
      }
      clearReviewerIdentity();
      setState({ kind: "setup", error: res.status === 401 ? "token invalid or revoked — paste a fresh one" : undefined });
    } catch {
      setState({ kind: "setup" }); // API unreachable — still allow setup
    }
  }, []);

  useEffect(() => { void probe(); }, [probe]);

  function save(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 2 || token.trim().length < 20) {
      setState({ kind: "setup", error: "need a name (≥2 chars) and a minted token" });
      return;
    }
    setReviewerIdentity(trimmed, token.trim());
    setState({ kind: "loading" });
    void probe();
    setToken("");
  }

  if (state.kind === "loading") return null;

  if (state.kind === "idle") {
    return (
      <span
        role="status"
        title="Reviewer identity — actions are audited under this name"
        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}
      >
        <span style={{ color: "var(--text-muted)" }}>as</span>
        <strong>{state.name}</strong>
        <button
          type="button"
          onClick={() => { clearReviewerIdentity(); setState({ kind: "setup" }); }}
          style={btnStyle}
          aria-label="Sign out"
        >⎋</button>
      </span>
    );
  }

  return (
    <form onSubmit={save} style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
        {getReviewerName()}{state.error ? ` — ${state.error}` : " — paste your reviewer token:"}
      </span>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="name"
        aria-label="Reviewer name"
        style={inputStyle}
        defaultValue={getReviewerName() !== "operator" ? getReviewerName() : ""}
      />
      <input
        value={token}
        onChange={(e) => setToken(e.target.value)}
        placeholder="minted token"
        type="password"
        autoComplete="off"
        aria-label="Reviewer token"
        style={{ ...inputStyle, width: 260 }}
      />
      <button type="submit" style={btnStyle}>Use</button>
    </form>
  );
}

const btnStyle: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 6, background: "transparent",
  padding: "2px 8px", cursor: "pointer", fontSize: 13,
};
const inputStyle: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-elevated, transparent)",
  padding: "2px 8px", fontSize: 13, width: 110,
};
