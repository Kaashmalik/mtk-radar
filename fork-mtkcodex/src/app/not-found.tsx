import { Button } from '@/components/ui/primitives';

export default function NotFound() {
  return (
    <section className="container-x flex min-h-[60vh] flex-col items-center justify-center py-24 text-center">
      <p className="text-gradient font-display text-8xl font-extrabold">404</p>
      <h1 className="mt-4 text-3xl font-bold">This page doesn&apos;t exist.</h1>
      <p className="mt-3 text-fg-muted">The link may be broken or the page may have moved.</p>
      <div className="mt-8 flex gap-3">
        <Button href="/" arrow>
          Back home
        </Button>
        <Button href="/contact" variant="secondary">
          Contact us
        </Button>
      </div>
    </section>
  );
}
