import type { Metadata } from "next";

import LoginForm from "./LoginForm";

export const metadata: Metadata = { title: "Sign in" };

type Props = {
  searchParams: Promise<{ next?: string | string[]; reason?: string | string[] }>;
};

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function safeNext(value: string | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  if (value.startsWith("/login")) return "/";
  return value;
}

export default async function LoginPage({ searchParams }: Props) {
  const params = await searchParams;
  return (
    <main className="page" style={{ maxWidth: 520, paddingTop: "12vh" }}>
      <p className="eyebrow">MTK RADAR AI</p>
      <h1>Sign in</h1>
      <p className="tagline">
        The dashboard is an operator console. A personal reviewer token binds
        every approval, correction and attestation to a named human.
      </p>
      <section className="card" style={{ marginTop: "1.2rem" }}>
        <LoginForm nextPath={safeNext(first(params.next))} reason={first(params.reason)} />
      </section>
      <p className="muted small" style={{ marginTop: "1rem" }}>
        The token is kept in a signed HttpOnly cookie. Browser JavaScript never
        reads it; interactive calls go through a same-origin proxy that adds it
        server-side.
      </p>
    </main>
  );
}
