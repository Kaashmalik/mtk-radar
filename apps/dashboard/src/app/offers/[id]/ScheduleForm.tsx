"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";


/**
 * Schedule a private test post (week 9). The API gates everything — approved
 * offer state, render existence, redaction review, idempotency.
 */
export default function ScheduleForm({ offerId }: { offerId: string }) {
  const router = useRouter();
  const [platform, setPlatform] = useState("youtube");
  const [privacy, setPrivacy] = useState("private");
  const [when, setWhen] = useState(() => {
    const d = new Date(Date.now() + 24 * 3600 * 1000);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T18:00`;
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMsg(body.created ? `Scheduled (${body.state})` : `Already scheduled (idempotent)`);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: "0.6rem" }}>
      <select
        value={platform}
        onChange={(e) => setPlatform(e.target.value)}
        style={inputStyle}
      >
        <option value="youtube">YouTube</option>
        <option value="facebook">Facebook</option>
        <option value="instagram">Instagram</option>
        <option value="tiktok">TikTok</option>
      </select>
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
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "0.3rem 0.5rem",
  fontSize: "0.8rem",
  borderRadius: 6,
  border: "1px solid #30363d",
  background: "#0d1117",
  color: "#e8eaf0",
};
