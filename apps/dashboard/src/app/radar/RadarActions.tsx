"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

export function ScanButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function scan() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await clientFetch("/trends/scan?limit=200", { method: "POST" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setMessage(`Scanned ${body.scanned} · ${body.created} new · ${body.updated} updated`);
      router.refresh();
    } catch {
      setMessage("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
      <button className="btn btn-primary" type="button" onClick={scan} disabled={busy}>
        {busy ? "Scanning…" : "Scan inbox → radar"}
      </button>
      {message && <span className="small muted" role="status">{message}</span>}
    </span>
  );
}

export function TrendAction({ id, status }: { id: string; status: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [next, setNext] = useState(status);

  async function update(value: string) {
    setBusy(true);
    try {
      const res = await clientFetch(`/trends/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: value }),
      });
      if (res.ok) {
        setNext(value);
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }}
        disabled={busy || next === "shortlisted"}
        onClick={() => update("shortlisted")}
      >
        Shortlist
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }}
        disabled={busy || next === "dismissed"}
        onClick={() => update("dismissed")}
      >
        Dismiss
      </button>
    </div>
  );
}
