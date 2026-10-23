"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Edit the spoken script and save it as a NEW immutable revision.
 *
 * The previous version keeps its hash — anything already rendered or scheduled
 * stays pinned to the exact words it was approved with. A saved revision is a
 * new draft that must be re-reviewed; the wording guard rejects first-person
 * result claims the script's format forbids.
 */
export default function ScriptRevise({
  scriptId,
  version,
  language,
  markdown,
  format,
}: {
  scriptId: string;
  version: number;
  language: string;
  markdown: string;
  format: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(markdown);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await clientFetch(`/studio/scripts/${scriptId}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: text, note: note.trim() || null }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(detailText(body.detail) ?? `HTTP ${res.status}`);
        return;
      }
      setResult(`Saved as v${body.version}. Re-review and re-approve before render.`);
      setNote("");
      setOpen(false);
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      open={open}
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
      style={{ marginTop: "0.6rem" }}
    >
      <summary className="small">Edit script &amp; save revision</summary>
      <form onSubmit={submit} style={{ display: "grid", gap: "0.5rem", marginTop: "0.5rem" }}>
        <textarea
          aria-label={`Edited ${language} script`}
          rows={12}
          value={text}
          onChange={(event) => setText(event.target.value)}
          style={{
            width: "100%",
            direction: language === "ur" ? "rtl" : "ltr",
            textAlign: language === "ur" ? "right" : "left",
            fontFamily: "var(--font-mono, monospace)",
            fontSize: "0.8rem",
          }}
          required
        />
        <input
          aria-label="Revision note"
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="What you changed and why (recorded in the audit log)"
          style={{ width: "100%" }}
        />
        <p className="muted small" style={{ margin: 0 }}>
          Saving creates v{version + 1} as a new draft ({format} wording guard applies to
          your edited text). The current v{version} stays pinned for anything already scheduled.
        </p>
        {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
        {result && <p className="small" style={{ color: "var(--ok)", margin: 0 }}>{result}</p>}
        <div style={{ display: "flex", gap: 8 }}>
          <button type="submit" className="btn btn-primary btn-small" disabled={busy || !text.trim()}>
            {busy ? "Saving…" : "Save revision"}
          </button>
          <button
            type="button"
            className="btn btn-small"
            onClick={() => {
              setText(markdown);
              setError(null);
              setResult(null);
            }}
            disabled={busy}
          >
            Reset to v{version}
          </button>
        </div>
      </form>
    </details>
  );
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
