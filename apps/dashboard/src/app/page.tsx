/**
 * Dashboard home — placeholder for the review inbox (Week 2).
 * The dashboard is the source of truth: offers, evidence, projects, edits, scheduled posts.
 */

async function getHealth(): Promise<{ status?: string }> {
  try {
    const res = await fetch(`${process.env.API_URL ?? "http://localhost:8000"}/health`, {
      cache: "no-store",
    });
    return await res.json();
  } catch {
    return {};
  }
}

export default async function Home() {
  const health = await getHealth();

  return (
    <main className="page">
      <header className="header">
        <h1>MTK RADAR AI</h1>
        <p className="tagline">
          Trusted offer discovery · real claim walkthroughs · scheduled publishing
        </p>
      </header>

      <section className="card">
        <h2>System status</h2>
        <p>
          API:{" "}
          <strong className={health.status === "ok" ? "ok" : "down"}>
            {health.status === "ok" ? "healthy" : "unreachable"}
          </strong>
        </p>
      </section>

      <section className="card">
        <h2>Review inbox</h2>
        <p className="muted">
          Candidates from trusted sources and saved links will appear here for
          review — each exactly once, with source, timestamp, and a dedup key.
          {/* TODO(week-2): list GET /items where processed = false */}
        </p>
      </section>

      <style jsx global>{`
        .page {
          max-width: 880px;
          margin: 0 auto;
          padding: 2rem 1.25rem;
          font-family: system-ui, sans-serif;
          color: #e8eaf0;
          background: #0d1117;
          min-height: 100vh;
        }
        .header h1 {
          margin: 0;
          font-size: 1.9rem;
          letter-spacing: 0.02em;
        }
        .tagline {
          color: #8b949e;
          margin-top: 0.4rem;
        }
        .card {
          background: #161b22;
          border: 1px solid #30363d;
          border-radius: 10px;
          padding: 1.1rem 1.25rem;
          margin-top: 1.25rem;
        }
        .card h2 {
          margin: 0 0 0.5rem;
          font-size: 1.05rem;
        }
        .ok {
          color: #3fb950;
        }
        .down {
          color: #f85149;
        }
        .muted {
          color: #8b949e;
        }
      `}</style>
    </main>
  );
}
