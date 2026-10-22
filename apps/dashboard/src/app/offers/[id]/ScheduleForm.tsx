"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";


/**
 * Schedule a private test post (week 9). The API gates everything — approved
 * offer state, render existence, redaction review, idempotency.
 *
 * v0.18: operator-configured publish windows (settings.publish_windows,
 * §17) render as quick-picks; the default stays 18:00 PKT when unset.
 */
type RenderOption = {
  id: string;
  preset: string;
  language: string;
  width: number;
  height: number;
  duration_s: string | null;
  status?: string;
  qc_status?: string;
};

export default function ScheduleForm({
  offerId,
  renders = [],
}: {
  offerId: string;
  renders?: RenderOption[];
}) {
  const router = useRouter();
  const [platform, setPlatform] = useState("youtube");
  const [privacy, setPrivacy] = useState("private");
  const [language, setLanguage] = useState("en");
  const [renderId, setRenderId] = useState("");
  const [metadataVariant, setMetadataVariant] = useState("default");
  const [coverPath, setCoverPath] = useState("");
  const [accounts, setAccounts] = useState<{
    id: string;
    platform: string;
    account_handle: string;
    status?: string;
  }[]>([]);
  const [accountId, setAccountId] = useState("");
  const [allowedLanguages, setAllowedLanguages] = useState<string[]>(["en"]);
  const [windows, setWindows] = useState<string[]>([]);
  const [when, setWhen] = useState(() => defaultWhen("18:00"));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    clientFetch("/settings/publish_windows")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => {
        const list = b?.value?.windows;
        if (alive && Array.isArray(list) && list.length > 0) setWindows(list);
      })
      .catch(() => {}); // settings are an enhancement — the form works without them

    // Pin the exact upload account. The API also pins the first active
    // account when omitted, but an explicit choice prevents uploading a
    // YouTube package to the wrong channel.
    clientFetch("/platform-accounts")
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => {
        if (alive && Array.isArray(list)) setAccounts(list);
      })
      .catch(() => {});

    // English is always available; Urdu only appears after the operator
    // enables it in Settings → Language policy.
    clientFetch("/settings/language_policy")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => {
        const list = b?.value?.narration_languages;
        if (alive && Array.isArray(list) && list.length > 0) {
          setAllowedLanguages(list);
          setLanguage((current) => (list.includes(current) ? current : list[0]));
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const platformAccounts = accounts.filter(
    (account) => account.platform === platform && (account.status ?? "active") === "active",
  );
  const renderOptions = renders.filter(
    (render) =>
      render.language === language &&
      (render.status ?? "rendered") === "rendered" &&
      render.qc_status === "passed",
  );

  async function schedule() {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      // interpret the input as Asia/Karachi (+05:00) — display timezone per §17
      const res = await clientFetch(`/offers/${offerId}/schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform,
          privacy,
          local_time: `${when}:00+05:00`,
          timezone: "Asia/Karachi",
          language,
          metadata_variant: metadataVariant,
          ...(accountId ? { platform_account_id: accountId } : {}),
          ...(renderId ? { render_id: renderId } : {}),
          ...(coverPath.trim() ? { cover_path: coverPath.trim() } : {}),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMsg(
        body.created
          ? `Queued (${body.state}) — approve it on the calendar before it can publish`
          : `Already queued (${body.state}) — idempotent re-submit`,
      );
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: "0.6rem" }}>
      <select
        value={platform}
        onChange={(e) => {
          setPlatform(e.target.value);
          setAccountId("");
        }}
        style={inputStyle}
        aria-label="Platform"
      >
        <option value="youtube">YouTube</option>
        <option value="facebook">Facebook</option>
        <option value="instagram">Instagram</option>
        <option value="tiktok">TikTok</option>
      </select>
      {platformAccounts.length > 0 && (
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          style={inputStyle}
          aria-label="Platform account"
        >
          <option value="">Auto: first active account</option>
          {platformAccounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.account_handle}
            </option>
          ))}
        </select>
      )}
      <select
        value={language}
        onChange={(e) => {
          setLanguage(e.target.value);
          setRenderId("");
        }}
        style={inputStyle}
        aria-label="Language"
      >
        {allowedLanguages.map((code) => (
          <option key={code} value={code}>
            {code === "ur" ? "اردو (Urdu voiceover)" : "English"}
          </option>
        ))}
      </select>
      <select
        value={renderId}
        onChange={(e) => setRenderId(e.target.value)}
        style={inputStyle}
        aria-label="Render"
        title="Pin the exact rendered file. Auto uses the platform's native aspect."
      >
        <option value="">
          Auto: {platform === "instagram" || platform === "tiktok"
            ? "9:16 vertical"
            : "16:9 landscape"}
        </option>
        {renderOptions.map((render) => (
          <option key={render.id} value={render.id}>
            {render.preset} · {render.width}×{render.height}
            {render.duration_s ? ` · ${Number(render.duration_s).toFixed(0)}s` : ""}
          </option>
        ))}
      </select>
      <select
        value={metadataVariant}
        onChange={(e) => setMetadataVariant(e.target.value)}
        style={inputStyle}
        aria-label="Metadata variant"
      >
        <option value="default">Packaging A</option>
        <option value="b">Packaging B</option>
      </select>
      <input
        value={coverPath}
        onChange={(e) => setCoverPath(e.target.value)}
        placeholder="cover path (optional)"
        style={{ ...inputStyle, width: 170 }}
        aria-label="Cover path"
      />
      <input
        type="datetime-local"
        value={when}
        onChange={(e) => setWhen(e.target.value)}
        style={inputStyle}
      />
      <select
        value={privacy}
        onChange={(e) => setPrivacy(e.target.value)}
        style={inputStyle}
      >
        <option value="private">Private (test)</option>
        <option value="unlisted">Unlisted</option>
        <option value="public">Public</option>
      </select>
      <button
        disabled={busy}
        onClick={schedule}
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
        {busy ? "Scheduling…" : "🗓 Schedule test post"}
      </button>
      {msg && <span style={{ color: "#3fb950", fontSize: "0.75rem" }}>{msg}</span>}
      {error && <span style={{ color: "#f85149", fontSize: "0.75rem" }}>{error}</span>}
      {windows.length > 0 && (
        <div style={{ display: "flex", gap: 6, alignItems: "center", width: "100%" }}>
          <span className="muted small">publish windows:</span>
          {windows.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setWhen(defaultWhen(w))}
              style={{
                padding: "0.15rem 0.5rem",
                fontSize: "0.72rem",
                borderRadius: 999,
                border: "1px solid #30363d",
                background: "transparent",
                color: "#8b949e",
                cursor: "pointer",
              }}
            >
              {w}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** `when` values are PKT wall-clock (the submit appends +05:00). */
function defaultWhen(hhmm: string): string {
  const [hh, mm] = hhmm.split(":").map(Number);
  const pad = (x: number) => String(x).padStart(2, "0");
  const d = new Date(Date.now() + 24 * 3600 * 1000);
  // shift into Asia/Karachi wall-clock so the pre-filled slot matches the window
  const pkt = new Date(d.toLocaleString("en-US", { timeZone: "Asia/Karachi" }));
  pkt.setHours(hh, mm, 0, 0);
  return `${pkt.getFullYear()}-${pad(pkt.getMonth() + 1)}-${pad(pkt.getDate())}T${pad(pkt.getHours())}:${pad(pkt.getMinutes())}`;
}

const inputStyle: React.CSSProperties = {
  padding: "0.3rem 0.5rem",
  fontSize: "0.8rem",
  borderRadius: 6,
  border: "1px solid #30363d",
  background: "#0d1117",
  color: "#e8eaf0",
};
