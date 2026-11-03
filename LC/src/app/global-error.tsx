"use client";

// Last-resort boundary (root layout failed), so it renders its own <html> with inline styles.
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en-PK">
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#f7f1e8", color: "#3b1f2b", fontFamily: "Georgia, serif", textAlign: "center" }}>
        <div>
          <h1 style={{ fontSize: 36, fontWeight: 400 }}>We dropped a stitch.</h1>
          <p style={{ color: "#6f6468", fontFamily: "system-ui, sans-serif" }}>Please refresh the page, or message Laraib Creative on WhatsApp.</p>
          <button onClick={reset} style={{ marginTop: 16, padding: "12px 24px", borderRadius: 999, border: 0, background: "#3b1f2b", color: "#f7f1e8", cursor: "pointer" }}>
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
