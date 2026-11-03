import Link from "next/link";
import { Logo } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grain grid min-h-screen place-items-center px-6 text-center">
      <div>
        <Link href="/" className="inline-block text-plum" aria-label="Laraib Creative home">
          <Logo />
        </Link>
        <p className="font-display mt-12 text-8xl text-gold/60 italic">404</p>
        <h1 className="mt-4 text-4xl text-plum">This page came unstitched.</h1>
        <p className="mx-auto mt-4 max-w-md text-muted">The link may be old or mistyped. Let&rsquo;s get you back to something beautiful.</p>
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          <ButtonLink href="/">Back to home</ButtonLink>
          <ButtonLink href="/designs" variant="outline">
            Browse the Lookbook
          </ButtonLink>
        </div>
      </div>
    </main>
  );
}
