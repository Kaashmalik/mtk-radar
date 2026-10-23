"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api-client";

/**
 * Operator-authored package assets: captions, chapters, and YouTube
 * title/description copy.
 *
 * Everything saved here is a NEW draft variant — approving it stays a separate
 * human step in the variant list below. All text passes the same wording guard
 * as generated content, so hand-written captions cannot claim an outcome the
 * format forbids.
 */
export default function PackageEditor({
  offerId,
  languages,
}: {
  offerId: string;
  languages: string[];
}) {
  const router = useRouter();
  const [language, setLanguage] = useState(languages[0] ?? "en");
  const [captions, setCaptions] = useState("");
  const [chapters, setChapters] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  function parseChapters(): { time: string; label: string }[] {
    return chapters
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const match = line.match(/^((?:\d{1,2}:)?\d{1,2}:\d{2})\s+(.+)$/);
        if (!match) return { time: "", label: line };
        return { time: match[1], label: match[2] };
      });
  }

  async function save(
    kind: "captions" | "metadata",
    body: Record<string, unknown>,
  ): Promise<string | null> {
    const res = await clientFetch(`/studio/offers/${offerId}/variants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, language, ...body }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      setError(detailText(payload.detail) ?? `HTTP ${res.status}`);
      return null;
    }
    return `${kind} draft saved (v${payload.version})`;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const saved: string[] = [];
      if (captions.trim() || chapters.trim()) {
        const chapterList = parseChapters();
        if (chapters.trim() && chapterList.some((c) => !c.time)) {
          setError("Chapters need lines like “00:00 Intro” (mm:ss label per line).");
          setBusy(false);
          return;
        }
        const savedCaptions = await save("captions", {
          text_content: captions.trim(),
          payload: chapterList.length ? { chapters: chapterList } : {},
        });
        if (!savedCaptions) return void router.refresh();
        saved.push(savedCaptions);
      }
      if (title.trim() || description.trim()) {
        const savedMeta = await save("metadata", {
          platform: "youtube",
          variant_key: "operator_edit",
          text_content: title.trim() || description.trim(),
          payload: {
            ...(title.trim() ? { title: title.trim() } : {}),
            ...(description.trim() ? { description: description.trim() } : {}),
          },
        });
        if (!savedMeta) return void router.refresh();
        saved.push(savedMeta);
      }
      if (saved.length === 0) {
        setError("Nothing to save yet — write captions, chapters, or title/description.");
        return;
      }
      setResult(`${saved.join(" · ")}. Approve them in the variant list.`);
      setCaptions("");
      setChapters("");
      setTitle("");
      setDescription("");
      router.refresh();
    } catch {
      setError("API unreachable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.7rem" }}>
      <p className="muted small" style={{ margin: 0 }}>
        Hand-edited assets are drafts, not approvals. Chapters use one{" "}
        <code>mm:ss label</code> per line. The wording guard runs on everything you
        write — same rules as generated content.
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <label htmlFor="pkg-language" className="small">Language</label>
        <select
          id="pkg-language"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
        >
          {languages.map((lang) => (
            <option key={lang} value={lang}>{lang === "ur" ? "Urdu (اردو)" : "English"}</option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="pkg-captions" className="small">Captions / subtitles text</label>
        <textarea
          id="pkg-captions"
          rows={4}
          value={captions}
          onChange={(event) => setCaptions(event.target.value)}
          placeholder="On-screen captions or subtitle cues for the chosen voiceover language"
          style={{ width: "100%" }}
        />
      </div>

      <div>
        <label htmlFor="pkg-chapters" className="small">Chapters (one per line)</label>
        <textarea
          id="pkg-chapters"
          rows={4}
          value={chapters}
          onChange={(event) => setChapters(event.target.value)}
          placeholder={"00:00 Intro\n00:22 Eligibility\n01:10 How to claim"}
          style={{ width: "100%" }}
        />
      </div>

      <div style={{ display: "grid", gap: "0.5rem" }}>
        <div>
          <label htmlFor="pkg-title" className="small">YouTube title (edited)</label>
          <input
            id="pkg-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Truthful, specific title — leave empty to keep generated copy"
            style={{ width: "100%" }}
            maxLength={100}
          />
        </div>
        <div>
          <label htmlFor="pkg-description" className="small">YouTube description (edited)</label>
          <textarea
            id="pkg-description"
            rows={4}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Description with official links, eligibility limits and correction info"
            style={{ width: "100%" }}
          />
        </div>
      </div>

      {error && <p role="alert" className="small" style={{ color: "var(--danger)", margin: 0 }}>{error}</p>}
      {result && <p className="small" style={{ color: "var(--ok)", margin: 0 }}>{result}</p>}

      <div>
        <button type="submit" className="btn btn-primary btn-small" disabled={busy}>
          {busy ? "Saving…" : "Save drafts"}
        </button>
      </div>
    </form>
  );
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}
