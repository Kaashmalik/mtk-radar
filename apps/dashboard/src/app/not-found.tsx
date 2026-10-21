import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page">
      <div className="state-banner" role="status">
        <strong>Nothing here.</strong>
        <span className="muted small">
          The page, offer, or record you followed does not exist (or was removed).
        </span>
        <Link className="btn btn-primary" href="/">
          Back to inbox
        </Link>
      </div>
    </main>
  );
}
