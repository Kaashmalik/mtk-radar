"use client";

/** Connect a social platform (v0.19). The desk is where the operator
 * registers WHICH account the system may post to — never the secret itself:
 * the form records a credential REFERENCE (env prefix / vault path) and the
 * key material stays in the environment (or vault) on the deploy host.
 * The server refuses references that look like token material (§6). */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

const PLATFORMS = [
  {
    id: "youtube",
    label: "YouTube",
    envPrefix: "env:YOUTUBE_",
    keys: ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
    scopes: "youtube.upload, youtube.force-upload, yt-analytics.readonly",
  },
  {
    id: "facebook",
    label: "Facebook",
    envPrefix: "env:FACEBOOK_",
    keys: ["FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"],
    scopes: "pages_manage_posts, pages_read_engagement, read_insights",
  },
  {
    id: "instagram",
    label: "Instagram",
    envPrefix: "env:INSTAGRAM_",
    keys: ["INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN"],
    scopes: "instagram_basic, instagram_content_publish, instagram_manage_insights",
  },
  {
    id: "tiktok",
    label: "TikTok",
    envPrefix: "env:TIKTOK_",
    keys: ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"],
    scopes: "video.publish, video.upload (approved developer app required)",
  },
];

export default function ConnectForm() {
  const router = useRouter();
  const [platform, setPlatform] = useState("youtube");
  const [handle, setHandle] = useState("");
  const [credentialSource, setCredentialSource] = useState("");
  const [scopes, setScopes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const spec = PLATFORMS.find((p) => p.id === platform)!;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const res = await clientFetch("/platform-accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform,
          account_handle: handle.trim(),
          credential_source: credentialSource.trim() || spec.envPrefix,
          scopes: scopes
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMsg(`Connected ${platform} account “${handle.trim()}”`);
      setHandle("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.5rem", maxWidth: "38rem" }}>
      <label htmlFor="conn-platform" className="small">Platform</label>
      <select
        id="conn-platform"
        value={platform}
        onChange={(e) => {
          setPlatform(e.target.value);
          setCredentialSource("");
        }}
      >
        {PLATFORMS.map((p) => (
          <option key={p.id} value={p.id}>{p.label}</option>
        ))}
      </select>

      <label htmlFor="conn-handle" className="small">
        Account handle — how this account appears in the audit log
      </label>
      <input
        id="conn-handle"
        value={handle}
        onChange={(e) => setHandle(e.target.value)}
        placeholder="mtk-radar-main"
        required
      />

      <label htmlFor="conn-source" className="small">
        Credential reference — where the key material lives (never the key itself)
      </label>
      <input
        id="conn-source"
        value={credentialSource}
        onChange={(e) => setCredentialSource(e.target.value)}
        placeholder={spec.envPrefix}
      />
      <span className="muted small">
        Put these in the deploy env, then reference them:
        {spec.keys.map((k) => (
          <code key={k} style={{ marginLeft: "0.4rem" }}>{k}</code>
        ))}
      </span>

      <label htmlFor="conn-scopes" className="small">Scopes granted (comma separated)</label>
      <input
        id="conn-scopes"
        value={scopes}
        onChange={(e) => setScopes(e.target.value)}
        placeholder={spec.scopes}
      />

      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <button type="submit" disabled={busy || handle.trim().length < 2}>
          {busy ? "Connecting…" : "Connect account"}
        </button>
        {msg && <span className="small" style={{ color: "#3fb950" }}>{msg}</span>}
        {error && <span className="small" style={{ color: "#f85149" }}>{error}</span>}
      </div>
    </form>
  );
}
