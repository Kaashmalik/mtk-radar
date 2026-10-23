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

export function CompetitorEvidence({ id }: { id: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function submit() {
    // One channel per line:  Name | subscribers | views in the last 28 days.
    // This is the operator's 3-competitor-rule research; the engine only
    // trusts measured numbers and shows the new drivers/risks on the radar.
    const competitors = text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [channel, subscribers, views] = line.split(/[|,]/).map((part) => part.trim());
        return {
          channel,
          subscribers: Number(subscribers ?? 0),
          views_28d: Number(views ?? 0),
        };
      })
      .filter((c) => c.channel && c.subscribers > 0);
    if (competitors.length === 0) {
      setMessage("One channel per line: Name | subscribers | 28d views");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await clientFetch(`/trends/${id}/competitors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ competitors }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMessage(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      const evidence = body.competitor_evidence ?? {};
      setMessage(
        `Rescored ${body.score}/100 — ${evidence.demand_hits ?? 0}/${evidence.in_band ?? 0} ` +
          "similar mid-size channels outsizing their subscribers",
      );
      setOpen(false);
      router.refresh();
    } catch {
      setMessage("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }}
          onClick={() => setOpen(true)}
        >
          3-competitor check
        </button>
        {message && <span className="small muted" role="status">{message}</span>}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 6, minWidth: 260 }}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"Mid A | 42000 | 91000\nMid B | 51000 | 110000\nMid C | 88000 | 120000"}
        rows={4}
        style={{ fontSize: "0.78rem", fontFamily: "inherit" }}
        aria-label="Competitor channels, one per line"
      />
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        <button type="button" className="btn btn-primary" style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }} disabled={busy} onClick={submit}>
          {busy ? "Scoring…" : "Apply evidence"}
        </button>
        <button type="button" className="btn btn-ghost" style={{ padding: "0.2rem 0.55rem", fontSize: "0.72rem" }} onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {message && <span className="small muted" role="status">{message}</span>}
    </div>
  );
}
