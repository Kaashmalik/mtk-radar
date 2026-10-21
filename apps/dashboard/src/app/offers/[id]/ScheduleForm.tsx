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
export default function ScheduleForm({ offerId }: { offerId: string }) {
  const router = useRouter();
  const [platform, setPlatform] = useState("youtube");
  const [privacy, setPrivacy] = useState("private");
  const [windows, setWindows] = useState<string[]>([]);
  const [when, setWhen] = useState(() => defaultWhen("18:00"));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    clientFetch("/settings/publish-windows")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => {
        const list = b?.value?.windows;
        if (alive && Array.isArray(list) && list.length > 0) setWindows(list);
      })
      .catch(() => {}); // settings are an enhancement — the form works without them
    return () => {
      alive = false;
    };
  }, []);

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
