"use client";

/** Route error boundary — a recoverable message instead of a white page. */

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="page">
      <div className="state-banner error" role="alert">
        <strong>Something went wrong while loading this page.</strong>
        <span className="muted small">
          {error.digest ? `ref: ${error.digest}` : "The request failed — check the API and try again."}
        </span>
        <button className="btn btn-primary" onClick={reset}>
          Retry
        </button>
      </div>
    </main>
  );
}
