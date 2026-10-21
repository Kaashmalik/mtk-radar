/**
 * Settings (v0.19) — operator configuration that used to live only in curl
 * calls: publish windows (§17) now editable from the desk, with the pipeline
 * status (what each worker is doing) in one place.
 */

import "./styles.css";
import SettingsForm from "./SettingsForm";
import { apiFetch } from "@/lib/api";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await apiFetch(path, { cache: "no-store" });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}

export default async function SettingsPage() {
  const setting = await getJson<{ key: string; value: { windows?: string[] } | null }>(
    "/settings/publish_windows",
    { key: "publish_windows", value: null },
  );
  const windows = setting.value?.windows ?? ["18:00"];

  const accounts = await getJson<
    { platform: string; account_handle: string; status: string }[]
  >("/platform-accounts", []);
  const candidates = await getJson<{ offer_id: string; title: string }[]>(
    "/render-candidates",
    [],
  );

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Settings</h1>
      <p className="tagline">Operator configuration (§17) and pipeline status.</p>

      <section className="card">
        <h2>Publishing</h2>
        <SettingsForm initialWindows={windows} />
      </section>

      <section className="card">
        <h2>Pipeline status</h2>
        <div className="stats">
          <div>
            <strong>{accounts.filter((a) => a.status === "active").length}</strong>
            <span>active connections</span>
          </div>
          <div>
            <strong>{candidates.length}</strong>
            <span>ready to render</span>
          </div>
          <div>
            <strong>{windows.length}</strong>
            <span>publish windows</span>
          </div>
        </div>
        {candidates.length > 0 && (
          <table>
            <thead>
              <tr><th>offer</th><th>offer id</th></tr>
            </thead>
            <tbody>
              {candidates.map((c) => (
                <tr key={c.offer_id}>
                  <td>{c.title}</td>
                  <td><code className="small">{c.offer_id}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Where the keys live</h2>
        <p className="muted small">
          Secrets never enter this app. The deploy env (<code>.env</code> next to
          the compose file) holds the keys; the{" "}
          <a href="/connections">Connections</a> page records where each account
          keeps them. The workers read them from the environment at runtime.
        </p>
      </section>
    </main>
  );
}
