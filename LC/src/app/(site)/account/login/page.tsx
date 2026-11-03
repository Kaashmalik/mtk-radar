import { Suspense } from "react";
import type { Metadata } from "next";
import { Container } from "@/components/site/sections";
import { LoginFlow } from "@/components/account/login-flow";

export const metadata: Metadata = { title: "Sign in", robots: { index: false } };

export default function AccountLoginPage({ searchParams }: PageProps<"/account/login">) {
  return (
    <section className="grain pt-36 pb-24 md:pt-44">
      <Container className="max-w-md">
        <p className="eyebrow">My Laraib</p>
        <h1 className="mt-3 text-4xl text-plum">
          Sign in to <em className="text-wine">your account</em>
        </h1>
        <p className="mt-3 text-muted">Track orders, keep measurement profiles for the whole family, and re-order in two taps. No password — we email you a code.</p>
        <div className="mt-10">
          <Suspense>
            <LoginFlow nextPromise={searchParams.then((sp) => (typeof sp.next === "string" ? sp.next : ""))} />
          </Suspense>
        </div>
      </Container>
    </section>
  );
}
