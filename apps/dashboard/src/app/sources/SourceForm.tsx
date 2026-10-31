"use client";

/** Register a source (v0.20) — the collectors can only poll what is
 * registered, and registering used to require curl. Trust tier decides how
 * much the source is trusted: A_provider_owned feeds can back a VERIFIED
 * offer (§3), B_discovery_lead can only produce candidates, C_excluded is
 * ignored.
 *
 * The adapter list and its config fields come from `GET /source-adapters`
 * (the Python registry) so a new adapter cannot exist in the collector/API
 * while this form silently omits it (CODE-09). */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export type AdapterOption = {
  kind: string;
  label: string;
  description: string;
  collector_polled: boolean;
  config_required: string[];
  config_optional: string[];
  approval_pending: boolean;
  available: boolean;
  unavailable_reason: string | null;
};

const TIERS = [
  { id: "A_provider_owned", label: "A — provider owned (can back a verified offer)" },
  { id: "B_discovery_lead", label: "B — discovery lead (candidates only)" },
  { id: "C_excluded", label: "C — excluded (ignored)" },
];

const CADENCES = ["1 hour", "6 hours", "12 hours", "24 hours"];

const CONFIG_LABELS: Record<string, string> = {
  feed_url: "Feed URL",
  repo: "Repository (owner/name)",
  url: "Page URL",
  query: "Search query",
  repos: "Repositories (owner/name, comma or newline separated)",
  geo: "Country code",
  subreddit: "Subreddit",
  min_points: "Minimum points",
  max_age_hours: "Maximum age (hours)",
  limit: "Maximum items per poll",
  date: "Date (optional)",
};

function configLabel(key: string): string {
  return CONFIG_LABELS[key] ?? key.replace(/_/g, " ");
}

export default function SourceForm({ adapters }: { adapters: AdapterOption[] }) {
  const router = useRouter();
  const firstAvailable = adapters.find((a) => a.available);
  const [provider, setProvider] = useState("");
  const [domain, setDomain] = useState("");
  const [category, setCategory] = useState("domains");
  const [adapter, setAdapter] = useState(firstAvailable?.kind ?? "");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [tier, setTier] = useState("B_discovery_lead");
  const [cadence, setCadence] = useState("6 hours");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = adapters.find((a) => a.kind === adapter);
  const configKeys = selected
    ? [...selected.config_required, ...selected.config_optional]
    : [];

  function chooseAdapter(kind: string) {
    setAdapter(kind);
    setConfig({}); // never submit the previous adapter's config
  }

  function setConfigValue(key: string, value: string) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !selected.available) {
      setError("choose an available adapter");
      return;
    }
    setBusy(true);
    setError(null);
    setMsg(null);

    const bodyConfig: Record<string, string | string[]> = {};
    for (const key of configKeys) {
      const value = (config[key] ?? "").trim();
      if (!value) continue;
      bodyConfig[key] = key === "repos"
        ? value.split(/[\n,]/).map((part) => part.trim()).filter(Boolean)
        : value;
    }

    try {
      const res = await clientFetch("/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider.trim(),
          canonical_domain: domain.trim() || null,
          category: category.trim() || "domains",
          adapter: selected.kind,
          config: bodyConfig,
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
      setConfig({});
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (adapters.length === 0) {
    return (
      <p className="muted">
        The adapter registry is unavailable — the API did not answer. Refusing
        to show a hardcoded fallback list that could drift from the collector.
      </p>
    );
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
      <select id="src-adapter" value={adapter} onChange={(e) => chooseAdapter(e.target.value)}>
        {adapters.map((a) => (
          <option key={a.kind} value={a.kind} disabled={!a.available}>
            {a.label}
            {a.available ? "" : " — approval pending"}
          </option>
        ))}
      </select>
      {selected ? <p className="muted small" style={{ margin: 0 }}>{selected.description}</p> : null}

      {configKeys.map((key) => {
        const required = selected?.config_required.includes(key) ?? false;
        const label = `${configLabel(key)}${required ? "" : " (optional)"}`;
        const id = `src-config-${key}`;
        return (
          <div key={key} style={{ display: "grid", gap: "0.3rem" }}>
            <label htmlFor={id} className="small">{label}</label>
            {key === "repos" ? (
              <textarea
                id={id}
                value={config[key] ?? ""}
                onChange={(e) => setConfigValue(key, e.target.value)}
                rows={3}
                required={required}
                placeholder={"acme/domains\nother/toolkit"}
              />
            ) : (
              <input
                id={id}
                value={config[key] ?? ""}
                onChange={(e) => setConfigValue(key, e.target.value)}
                required={required}
                inputMode={["min_points", "max_age_hours", "limit"].includes(key) ? "numeric" : undefined}
                placeholder={key === "geo" ? "US" : undefined}
              />
            )}
          </div>
        );
      })}

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
        <button type="submit" disabled={busy || provider.trim().length < 2 || !selected?.available}>
          {busy ? "Registering…" : "Register source"}
        </button>
        {msg && <span className="small" style={{ color: "var(--ok)" }}>{msg}</span>}
        {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
      </div>
    </form>
  );
}
