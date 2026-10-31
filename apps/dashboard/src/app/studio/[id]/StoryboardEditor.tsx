"use client";

/**
 * Storyboard editor (V7) — choose, order and time the scenes of a research
 * explainer, and capture the public source pages it shows.
 *
 * What a reviewer can change: scene order (drag or ↑/↓), include/exclude,
 * relative duration, and the text of title / page / closing scenes. Claim
 * scenes are locked: their wording, attribution and source come from the
 * claim ledger (the API re-derives them on save and again at render time),
 * so the editor can never make a claim say more than the evidence does.
 * Saves are new versions; a conflicting save is refused with a reload hint.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { clientFetch } from "@/lib/api-client";

type Kind = "title" | "claim" | "page" | "close";

type Scene = {
  id: string;
  kind: Kind;
  heading: string;
  body?: string;
  source?: string;
  scope?: string;
  claim_ids?: string[];
  page_capture_id?: string;
  weight: number;
  include: boolean;
};

type Claim = {
  id: string;
  status: "supported" | "unknown" | "contradicted";
  claim_class: string;
  text: string;
  source_url?: string | null;
};

type PageCapture = {
  id: string;
  url: string;
  final_url?: string | null;
  title?: string | null;
  status: "requested" | "ok" | "failed" | "refused";
  detail?: string | null;
  captured_at?: string | null;
};

type Board = {
  brief: { id: string; version: number; content_type: string } | null;
  current: { version: number; scenes: Scene[]; sha256: string; created_by: string; created_at: string } | null;
  suggested: Scene[];
  claims: Claim[];
  page_captures: PageCapture[];
  problems: string[];
  limits: { max_scenes: number; weight: [number, number]; heading: number; body: number };
};

const KIND_LABEL: Record<Kind, string> = {
  title: "Opening question",
  claim: "Claim",
  page: "Source page",
  close: "Close",
};

const SECONDS_PER_WEIGHT = 6; // matches the renderer's default without narration

export default function StoryboardEditor({ offerId }: { offerId: string }) {
  const [board, setBoard] = useState<Board | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string; list?: string[] } | null>(null);
  const dragFrom = useRef<number | null>(null);

  /** `keepScenes`: refresh the inputs (captures, claims, problems) without
   * replacing the scene list — used after a capture request so unsaved
   * storyboard edits are never wiped. */
  const load = useCallback(async (keepScenes = false) => {
    try {
      const res = await clientFetch(`/offers/${offerId}/storyboard`);
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as Board;
      setBoard(data);
      if (!keepScenes) {
        setScenes((data.current?.scenes ?? data.suggested).map((s) => ({
          ...s, weight: Number(s.weight ?? 1), include: s.include !== false,
        })));
        setDirty(false);
      }
      setState("ready");
    } catch {
      if (!keepScenes) setState("unavailable");
    }
  }, [offerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalWeight = useMemo(
    () => scenes.filter((s) => s.include).reduce((sum, s) => sum + s.weight, 0),
    [scenes],
  );

  if (state === "loading") {
    return <div className="skeleton-row"><span className="skeleton" /><span className="skeleton" /></div>;
  }
  if (state === "unavailable" || !board) {
    return <p className="notice small" role="status">Storyboard unavailable — the API did not answer.</p>;
  }
  if (!board.brief || board.brief.content_type !== "explainer") {
    return (
      <p className="empty-state">
        Storyboards apply to research explainers. Promote a trend or create an
        explainer research brief for this offer first.
      </p>
    );
  }

  function update(next: Scene[]) {
    setScenes(next);
    setDirty(true);
    setMessage(null);
  }

  function patch(index: number, change: Partial<Scene>) {
    update(scenes.map((s, i) => (i === index ? { ...s, ...change } : s)));
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= scenes.length || from === to) return;
    const next = [...scenes];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    update(next);
  }

  const usedClaims = new Set(scenes.flatMap((s) => s.claim_ids ?? []));
  const usedPages = new Set(scenes.map((s) => s.page_capture_id).filter(Boolean));
  const addableClaims = board.claims.filter((c) => c.status !== "contradicted" && !usedClaims.has(c.id));
  const addablePages = board.page_captures.filter((p) => p.status === "ok" && !usedPages.has(p.id));

  function addClaim(claim: Claim) {
    const closeAt = scenes.findIndex((s) => s.kind === "close");
    const scene: Scene = {
      id: `claim-${claim.id}`, kind: "claim", heading: "From the claim ledger",
      body: claim.text, claim_ids: [claim.id], weight: 1, include: true,
    };
    const next = [...scenes];
    next.splice(closeAt < 0 ? next.length : closeAt, 0, scene);
    update(next);
  }

  function addPage(page: PageCapture) {
    const scene: Scene = {
      id: `page-${page.id}`, kind: "page", heading: page.title || "Source page", body: "",
      source: page.final_url || page.url, page_capture_id: page.id, weight: 1, include: true,
    };
    const next = [...scenes];
    next.splice(Math.min(1, next.length), 0, scene);
    update(next);
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/storyboard`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: board?.current?.version ?? 0,
          scenes: scenes.map((s) => ({
            kind: s.kind, heading: s.heading, body: s.body ?? "", weight: s.weight,
            include: s.include, claim_ids: s.claim_ids, page_capture_id: s.page_capture_id,
          })),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.status === 409) {
        setMessage({ tone: "error", text: body.detail ?? "The storyboard changed — reload." });
        return;
      }
      if (!res.ok) {
        const problems = body?.detail?.problems as string[] | undefined;
        setMessage({ tone: "error", text: problems ? "Fix these scenes:" : (body.detail ?? `HTTP ${res.status}`), list: problems });
        return;
      }
      setMessage({ tone: "ok", text: `Saved as version ${body.version}. The next render draws exactly this.` });
      await load();
    } catch {
      setMessage({ tone: "error", text: "API unreachable — nothing was saved." });
    } finally {
      setBusy(false);
    }
  }

  const [minW, maxW] = board.limits.weight;

  return (
    <div className="storyboard">
      <div className="storyboard-head">
        <div className="chip-row">
          <span className="tag tag-accent">brief v{board.brief.version}</span>
          <span className="tag">
            {board.current ? `storyboard v${board.current.version} · ${board.current.created_by}` : "suggested (not saved yet)"}
          </span>
          <span className="tag">{scenes.filter((s) => s.include).length} scenes</span>
          <span className="tag">≈{Math.round(totalWeight * SECONDS_PER_WEIGHT)}s without narration</span>
          {dirty && <span className="tag tag-warn">unsaved changes</span>}
        </div>
        <div className="storyboard-actions">
          <button type="button" className="btn btn-ghost btn-small" disabled={busy}
            onClick={() => update(board.suggested.map((s) => ({ ...s, weight: 1, include: true })))}>
            Reset to suggestion
          </button>
          <button type="button" className="btn btn-primary btn-small" disabled={busy || !dirty} onClick={save}>
            {busy ? "Saving…" : "Save storyboard"}
          </button>
        </div>
      </div>

      {board.problems.length > 0 && (
        <div className="notice notice-danger small" role="alert">
          The saved storyboard no longer matches the evidence — the renderer will drop:
          <ul>{board.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}

      <div className="timeline" aria-hidden="true">
        {scenes.filter((s) => s.include).map((s) => (
          <span key={s.id} className="timeline-seg" data-kind={s.kind}
            style={{ flexGrow: s.weight }} title={`${KIND_LABEL[s.kind]} · ${s.heading}`} />
        ))}
      </div>

      <ol className="scene-list">
        {scenes.map((scene, index) => {
          const locked = scene.kind === "claim";
          return (
            <li
              key={scene.id}
              className="scene"
              data-kind={scene.kind}
              data-excluded={!scene.include || undefined}
              draggable
              onDragStart={() => { dragFrom.current = index; }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragFrom.current !== null) move(dragFrom.current, index);
                dragFrom.current = null;
              }}
            >
              <div className="scene-rail">
                <span className="scene-index">{index + 1}</span>
                <button type="button" className="icon-btn" aria-label="Move scene up"
                  disabled={index === 0} onClick={() => move(index, index - 1)}>↑</button>
                <button type="button" className="icon-btn" aria-label="Move scene down"
                  disabled={index === scenes.length - 1} onClick={() => move(index, index + 1)}>↓</button>
              </div>
              <div className="scene-main">
                <div className="scene-top">
                  <span className="scene-kind">{KIND_LABEL[scene.kind]}</span>
                  {locked && <span className="tag" title="Wording, attribution and source come from the claim ledger">locked to ledger</span>}
                  <label className="small scene-include">
                    <input type="checkbox" checked={scene.include}
                      onChange={(e) => patch(index, { include: e.target.checked })} />
                    Include
                  </label>
                </div>
                {scene.kind === "page" && scene.page_capture_id && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img className="scene-shot" alt={`Screenshot: ${scene.heading}`} loading="lazy"
                    src={`/api/backend/page-captures/${encodeURIComponent(scene.page_capture_id)}/image`} />
                )}
                {locked ? (
                  <>
                    <p className="scene-heading">{scene.heading}</p>
                    <p className="scene-body">{scene.body}</p>
                  </>
                ) : (
                  <>
                    <input className="scene-heading-input" value={scene.heading}
                      maxLength={board.limits.heading} aria-label="Scene heading"
                      onChange={(e) => patch(index, { heading: e.target.value })} />
                    <textarea value={scene.body ?? ""} rows={2} maxLength={board.limits.body}
                      aria-label={scene.kind === "page" ? "Caption" : "Scene text"}
                      placeholder={scene.kind === "page" ? "Optional caption shown with the source" : ""}
                      onChange={(e) => patch(index, { body: e.target.value })} />
                  </>
                )}
                {scene.source && <p className="muted small scene-source">{scene.source}</p>}
                <label className="small scene-weight">
                  Duration
                  <input type="range" min={minW} max={maxW} step={0.5} value={scene.weight}
                    onChange={(e) => patch(index, { weight: Number(e.target.value) })} />
                  <span className="mono">×{scene.weight.toFixed(1)}</span>
                </label>
              </div>
              <button type="button" className="icon-btn scene-remove" aria-label="Remove scene"
                onClick={() => update(scenes.filter((_, i) => i !== index))}>✕</button>
            </li>
          );
        })}
      </ol>

      {(addableClaims.length > 0 || addablePages.length > 0) && (
        <div className="scene-add">
          <span className="muted small">Add scene:</span>
          {addableClaims.map((c) => (
            <button key={c.id} type="button" className="chip-btn" onClick={() => addClaim(c)}
              title={c.text}>
              + claim{c.status === "unknown" ? " (unconfirmed)" : ""}: {c.text.slice(0, 40)}
              {c.text.length > 40 ? "…" : ""}
            </button>
          ))}
          {addablePages.map((p) => (
            <button key={p.id} type="button" className="chip-btn" onClick={() => addPage(p)}>
              + page: {(p.title || p.url).slice(0, 40)}
            </button>
          ))}
        </div>
      )}

      {message && (
        <div className={`notice small ${message.tone === "ok" ? "notice-ok" : "notice-danger"}`} role="status">
          {message.text}
          {message.list && <ul>{message.list.map((p) => <li key={p}>{p}</li>)}</ul>}
        </div>
      )}

      <PageCapturePanel offerId={offerId} board={board} onChanged={() => load(true)} />
    </div>
  );
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname || url;
  } catch {
    return url.slice(0, 40);
  }
}

/** Ask the sandboxed worker to screenshot public source pages. */
function PageCapturePanel({ offerId, board, onChanged }: {
  offerId: string;
  board: Board;
  onChanged: () => Promise<void>;
}) {
  const suggestions = useMemo(
    () => [...new Set(board.claims.map((c) => c.source_url).filter((u): u is string => !!u))],
    [board.claims],
  );
  const [urls, setUrls] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  async function request() {
    const list = urls.split(/\s+/).map((u) => u.trim()).filter(Boolean);
    if (!list.length) return;
    setBusy(true);
    setResult(null);
    try {
      const res = await clientFetch(`/offers/${offerId}/page-captures/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: list.slice(0, 10) }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setResult(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
        return;
      }
      const refused = (body.refused ?? []) as { url: string; detail: string }[];
      setResult(`${body.queued?.length ?? 0} queued for capture` +
        (refused.length ? ` · refused: ${refused.map((r) => `${r.url} (${r.detail})`).join("; ")}` : ""));
      setUrls("");
      await onChanged();
    } catch {
      setResult("API unreachable — nothing was queued");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="page-capture">
      <summary>Capture public source pages ({board.page_captures.length})</summary>
      <p className="muted small">
        Public https pages only. A sandboxed worker (fresh browser, no logins, private
        networks blocked, robots.txt honoured) takes one screenshot per page; successful
        captures become &ldquo;Source page&rdquo; scenes.
      </p>
      {suggestions.length > 0 && (
        <div className="chip-row">
          {suggestions.map((u) => (
            <button key={u} type="button" className="chip-btn"
              onClick={() => setUrls((v) => (v.includes(u) ? v : `${v}\n${u}`.trim()))}>
              + {hostOf(u)}
            </button>
          ))}
        </div>
      )}
      <textarea rows={3} value={urls} onChange={(e) => setUrls(e.target.value)}
        placeholder="https://… one URL per line (max 10)" aria-label="Page URLs" />
      <button type="button" className="btn btn-small" disabled={busy || !urls.trim()} onClick={request}>
        {busy ? "Queueing…" : "Capture pages"}
      </button>
      {result && <p className="small" role="status">{result}</p>}
      {board.page_captures.length > 0 && (
        <ul className="capture-list">
          {board.page_captures.map((p) => (
            <li key={p.id} className="small">
              <span className={`tag ${p.status === "ok" ? "tag-ok" : p.status === "requested" ? "" : "tag-warn"}`}>
                {p.status}
              </span>{" "}
              <span className="truncate">{p.title || p.url}</span>
              {p.detail && <span className="muted"> — {p.detail}</span>}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}
