"use client";
import { useEffect } from "react";
import { whatsappLink } from "@/lib/config";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="grid min-h-[70vh] place-items-center px-6 text-center">
      <div>
        <p className="eyebrow">Something went wrong</p>
        <h1 className="mt-4 text-4xl text-plum">We dropped a stitch.</h1>
        <p className="mx-auto mt-4 max-w-md text-muted">
          Please try again. If it keeps happening, message us on WhatsApp{error.digest && ` with code ${error.digest}`} and we&rsquo;ll help right away.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button onClick={reset} className="h-11 rounded-full bg-plum px-6 text-ivory hover:bg-wine">
            Try again
          </button>
          <a href={whatsappLink(`Hi, I saw an error on the website${error.digest ? ` (code ${error.digest})` : ""}.`)} className="inline-flex h-11 items-center rounded-full border border-plum/25 px-6 text-plum">
            WhatsApp us
          </a>
        </div>
      </div>
    </main>
  );
}
