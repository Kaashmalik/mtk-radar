/**
 * Review inbox (Week 2): unprocessed candidates from trusted sources and saved
 * links — each exactly once, with source, timestamp, and dedup key visible.
 */

import "./styles.css";

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

    </main>
  );
}
