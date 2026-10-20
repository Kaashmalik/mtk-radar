/**
 * Review inbox (Week 2): unprocessed candidates from trusted sources and saved
 * links — each exactly once, with source, timestamp, and dedup key visible.
 */

type ItemRow = {
  id: string;
  url: string;
  canonical_url: string | null;
  title: string | null;
  observed_at: string;
  duplicate_group: string | null;
  source_provider: string | null;
  source_category: string | null;
  trust_tier: string | null;
};

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

async function getInbox(): Promise<ItemRow[]> {
  try {
    const res = await fetch(
      `${process.env.API_URL ?? "http://localhost:8000"}/items?processed=false&limit=50`,
      { cache: "no-store" },
    );
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export const dynamic = "force-dynamic";

export default async function Home() {
  const health = await getHealth();
  const items = await getInbox();

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
          </strong>{" "}
          · <a href="/review">Open review desk →</a>
          {" · "}
          <a href="/calendar">Content calendar →</a>
        </p>
      </section>

      <section className="card">
        <h2>Review inbox</h2>
        {items.length === 0 ? (
          <p className="muted">
            No candidates yet. Run the seed script and the collector worker, save a
            page with the extension, and new candidates will appear here — each
            exactly once, deduplicated by canonical URL.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Source</th>
                <th>Tier</th>
                <th>Observed</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <a href={item.url} target="_blank" rel="noreferrer">
                      {item.title ?? item.url}
                    </a>
                    <div className="muted small">{item.canonical_url}</div>
                  </td>
                  <td>
                    {item.source_provider}
                    <div className="muted small">{item.source_category}</div>
                  </td>
                  <td>
                    <span className={`tier ${item.trust_tier?.startsWith("A") ? "tier-a" : "tier-b"}`}>
                      {item.trust_tier?.split("_")[0]}
                    </span>
                  </td>
                  <td className="muted small">
                    {new Date(item.observed_at).toLocaleString("en-GB", {
                      timeZone: "Asia/Karachi",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <style jsx global>{`
        .page {
          max-width: 960px;
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
        .small {
          font-size: 0.78rem;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.9rem;
        }
        th {
          text-align: left;
          color: #8b949e;
          font-weight: 500;
          padding: 0.4rem 0.6rem;
          border-bottom: 1px solid #30363d;
        }
        td {
          padding: 0.55rem 0.6rem;
          border-bottom: 1px solid #21262d;
          vertical-align: top;
        }
        a {
          color: #58a6ff;
          text-decoration: none;
        }
        a:hover {
          text-decoration: underline;
        }
        .tier {
          display: inline-block;
          padding: 0.1rem 0.5rem;
          border-radius: 999px;
          font-size: 0.72rem;
          font-weight: 600;
        }
        .tier-a {
          background: #0f3520;
          color: #3fb950;
        }
        .tier-b {
          background: #34250f;
          color: #d29922;
        }
      `}</style>
    </main>
  );
}
