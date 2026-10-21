"use client";

/** Register a source (v0.20) — the collectors can only poll what is
 * registered, and registering used to require curl. Trust tier decides how
 * much the source is trusted: A_provider_owned feeds can back a VERIFIED
 * offer (§3), B_discovery_lead can only produce candidates, C_excluded is
 * ignored. */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

const ADAPTERS = [
  { id: "rss", label: "RSS / Atom feed", needs: "config.feed_url" },
  { id: "github_releases", label: "GitHub releases", needs: "config.repo" },
  { id: "page_watch", label: "Web page (watch)", needs: "config.url" },
  { id: "extension", label: "Browser extension saves", needs: "— (manual saves)" },
  { id: "manual", label: "Manual (seed only)", needs: "—" },
];

const TIERS = [
  { id: "A_provider_owned", label: "A — provider owned (can back a verified offer)" },
  { id: "B_discovery_lead", label: "B — discovery lead (candidates only)" },
  { id: "C_excluded", label: "C — excluded (ignored)" },
];

const CADENCES = ["1 hour", "6 hours", "12 hours", "24 hours"];

export default function SourceForm() {
  const router = useRouter();
  const [provider, setProvider] = useState("");
  const [domain, setDomain] = useState("");
  const [category, setCategory] = useState("domains");
  const [adapter, setAdapter] = useState("rss");
  const [feedUrl, setFeedUrl] = useState("");
  const [repo, setRepo] = useState("");
  const [tier, setTier] = useState("B_discovery_lead");
  const [cadence, setCadence] = useState("6 hours");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);

    const config: Record<string, string> = {};
    if (adapter === "rss" && feedUrl.trim()) config.feed_url = feedUrl.trim();
    if (adapter === "github_releases" && repo.trim()) config.repo = repo.trim();
    if (adapter === "page_watch" && feedUrl.trim()) config.url = feedUrl.trim();

    try {
      const res = await clientFetch("/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider.trim(),
          canonical_domain: domain.trim() || null,
          category: category.trim() || "domains",
          adapter,
          config,
          polling_cadence: cadence,
          trust_tier: tier,
          enabled: true,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMsg(body.created ? "Source registered — the collector will pick it up" :
        "Source already registered (idempotent)");
      setProvider("");
      setDomain("");
      setFeedUrl("");
      setRepo("");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.5rem", maxWidth: "40rem" }}>
      <label htmlFor="src-provider" className="small">Provider name</label>
      <input id="src-provider" value={provider} onChange={(e) => setProvider(e.target.value)}
             placeholder="Acme Domains" required />

      <label htmlFor="src-domain" className="small">Canonical domain (the provider's own site)</label>
      <input id="src-domain" value={domain} onChange={(e) => setDomain(e.target.value)}
             placeholder="acme.com" />

      <label htmlFor="src-category" className="small">Category</label>
      <input id="src-category" value={category} onChange={(e) => setCategory(e.target.value)}
             placeholder="domains" />

      <label htmlFor="src-adapter" className="small">Adapter (how it is polled)</label>
      <select id="src-adapter" value={adapter} onChange={(e) => setAdapter(e.target.value)}>
        {ADAPTERS.map((a) => (
          <option key={a.id} value={a.id}>{a.label}</option>
        ))}
      </select>

      {adapter === "rss" && (
        <>
          <label htmlFor="src-feed" className="small">Feed URL</label>
          <input id="src-feed" value={feedUrl} onChange={(e) => setFeedUrl(e.target.value)}
                 placeholder="https://acme.com/offers.xml" />
        </>
      )}
      {adapter === "github_releases" && (
        <>
          <label htmlFor="src-repo" className="small">Repository (owner/name)</label>
          <input id="src-repo" value={repo} onChange={(e) => setRepo(e.target.value)}
                 placeholder="acme/domains" />
        </>
      )}
      {adapter === "page_watch" && (
        <>
          <label htmlFor="src-url" className="small">Page URL</label>
          <input id="src-url" value={feedUrl} onChange={(e) => setFeedUrl(e.target.value)}
                 placeholder="https://acme.com/offers" />
        </>
      )}

      <label htmlFor="src-tier" className="small">Trust tier</label>
      <select id="src-tier" value={tier} onChange={(e) => setTier(e.target.value)}>
        {TIERS.map((t) => (
          <option key={t.id} value={t.id}>{t.label}</option>
        ))}
      </select>

      <label htmlFor="src-cadence" className="small">Polling cadence</label>
      <select id="src-cadence" value={cadence} onChange={(e) => setCadence(e.target.value)}>
        {CADENCES.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <button type="submit" disabled={busy || provider.trim().length < 2}>
          {busy ? "Registering…" : "Register source"}
        </button>
        {msg && <span className="small" style={{ color: "#3fb950" }}>{msg}</span>}
        {error && <span className="small" style={{ color: "#f85149" }}>{error}</span>}
      </div>
    </form>
  );
}
