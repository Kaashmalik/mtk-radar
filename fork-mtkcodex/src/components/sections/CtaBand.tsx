import { site, whatsappLink } from '@/data/site';
import { Button } from '@/components/ui/primitives';

export default function CtaBand({
  title = 'Ready to build software that scales?',
  text = 'Tell us what you need. Get a free consultation, a clear plan and a fixed quote — usually within 48 hours.',
}: {
  title?: string;
  text?: string;
}) {
  return (
    <section className="container-x pb-24 pt-8">
      <div className="relative isolate overflow-hidden night rounded-[28px] px-6 py-16 text-center text-white sm:px-12">
        <div className="glow -z-10 left-[-10%] top-[-50%] size-[420px] bg-[#14a89a] opacity-40 aurora-1" />
        <div className="glow -z-10 bottom-[-60%] right-[-10%] size-[420px] bg-[#62d84e] opacity-30 aurora-2" />
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-lime">{site.slogan}</p>
        <h2 className="mx-auto mt-4 max-w-3xl text-3xl font-bold sm:text-5xl">{title}</h2>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-white/70">{text}</p>
        <div className="mt-10 flex flex-col justify-center gap-3 sm:flex-row">
          <Button href="/contact?intent=demo" size="lg" arrow>
            Book a free demo
          </Button>
          <Button href={whatsappLink()} external size="lg" variant="secondary" className="!border-white/20 !bg-white/10 !text-white hover:!bg-white/20">
            Chat on WhatsApp
          </Button>
        </div>
      </div>
    </section>
  );
}
