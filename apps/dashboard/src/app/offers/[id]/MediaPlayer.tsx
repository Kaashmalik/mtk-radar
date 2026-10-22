"use client";

import { useState } from "react";

/**
 * Authenticated media playback for review.
 *
 * The browser never holds a storage credential: the same-origin
 * /api/backend proxy attaches the signed reviewer session, forwards Range
 * requests, and streams the bytes from the API. `preload="none"` keeps the
 * review page cheap until the reviewer actually asks to watch.
 */
export default function MediaPlayer({
  kind,
  id,
  label,
}: {
  kind: "captures" | "renders";
  id: string;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const src = `/api/backend/${kind}/${encodeURIComponent(id)}/video`;

  if (!open) {
    return (
      <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(true)}>
        ▶ Watch {label}
      </button>
    );
  }

  return (
    <div style={{ marginTop: 8, maxWidth: 720 }}>
      <video
        controls
        preload="metadata"
        src={src}
        style={{ width: "100%", borderRadius: 8, background: "#000" }}
      >
        Your browser cannot play this video.
      </video>
      <p className="muted small" style={{ margin: "4px 0 0" }}>
        Authenticated stream · seeking uses byte ranges.{" "}
        <a href={src} target="_blank" rel="noreferrer">Open in a new tab</a>
      </p>
    </div>
  );
}
