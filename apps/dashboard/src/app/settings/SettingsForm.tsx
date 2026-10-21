"use client";

/** Operator settings (v0.19) — publish windows (§17) and the storage mode.
 * Every write goes through the API, which validates and audits it; the
 * browser never handles secrets. */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export default function SettingsForm({ initialWindows }: { initialWindows: string[] }) {
  const router = useRouter();
  const [windows, setWindows] = useState(initialWindows.join(", "));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setMsg(null);
    const list = windows
      .split(",")
      .map((w) => w.trim())
      .filter(Boolean);
    try {
      const res = await clientFetch("/settings/publish_windows", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value: { windows: list } }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMsg(`Saved: ${body.value.windows.join(", ")} (PKT)`);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} style={{ display: "grid", gap: "0.5rem", maxWidth: "38rem" }}>
      <label htmlFor="win" className="small">
        Publish windows — local Asia/Karachi times the calendar offers as slots
        (comma separated, HH:MM). The default when unset is a single 18:00 slot.
      </label>
      <input
        id="win"
        value={windows}
        onChange={(e) => setWindows(e.target.value)}
        placeholder="18:00, 20:30"
      />
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
        <button type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save settings"}
        </button>
        {msg && <span className="small" style={{ color: "#3fb950" }}>{msg}</span>}
        {error && <span className="small" style={{ color: "#f85149" }}>{error}</span>}
      </div>
    </form>
  );
}
