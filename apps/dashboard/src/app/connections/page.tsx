/**
 * Connections (v0.19) — the operator console for social accounts.
 *
 * "Add the key, connect the account" in one place: this page shows every
 * registered platform account with its health, and the form below registers a
 * NEW one by pointing at where its credentials live (env prefix / vault path).
 * Secrets never pass through the browser (§6, §11).
 */

import "./styles.css";
import ConnectForm from "./ConnectForm";
import { ConnectionTest } from "./ConnectionTest";
import { apiFetch } from "@/lib/api";

type Account = {
  id: string;
  platform: string;
  account_handle: string;
  credential_source: string;
  scopes: string[] | null;
  status: string;
  expires_at: string | null;
  last_refreshed_at: string | null;
  last_error: string | null;
};

export default async function ConnectionsPage() {
  let accounts: Account[] = [];
  let apiDown = false;
  try {
    const res = await apiFetch("/platform-accounts", { cache: "no-store" });
    if (res.ok) {
      accounts = await res.json();
    } else {
      apiDown = true;
    }
  } catch {
    apiDown = true;
  }

  return (
    <main className="page">
      <a href="/" className="back">← Inbox</a>
      <h1>Connections</h1>
      <p className="tagline">
        Social accounts this deployment may publish to (§6). Keys live in the
        deploy environment — this page only records <em>where</em> they are.
      </p>

      {apiDown ? (
        <section className="card">
          <p className="muted">API unreachable — start the stack (pnpm dev).</p>
        </section>
      ) : (
        <>
          <section className="card">
            <h2>Connected accounts ({accounts.length})</h2>
            {accounts.length === 0 ? (
              <p className="muted small">
                No accounts connected yet. Add your keys to the deploy env, then
                register the account below — workers read the keys from the
                environment, never from the database.
              </p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>platform</th><th>handle</th><th>credentials</th>
                    <th>scopes</th><th>status</th><th>expires</th><th>last error</th><th>check</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id}>
                      <td>{a.platform}</td>
                      <td>{a.account_handle}</td>
                      <td><code className="small">{a.credential_source}</code></td>
                      <td className="small">{(a.scopes ?? []).join(", ") || "–"}</td>
                      <td>
                        <span style={{ color: a.status === "active" ? "var(--ok)" : "var(--danger)" }}>
                          {a.status}
                        </span>
                      </td>
                      <td className="small">
                        {a.expires_at
                          ? new Date(a.expires_at).toLocaleString("en-GB", { timeZone: "Asia/Karachi" })
                          : "–"}
                      </td>
                      <td className="small">{a.last_error ?? "–"}</td>
                      <td><ConnectionTest accountId={a.id} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="card">
            <h2>Connect an account</h2>
            <ConnectForm />
          </section>
        </>
      )}
    </main>
  );
}
