import Link from 'next/link';
import { ArrowRight, Radar, Zap } from 'lucide-react';
import { automations } from '@/data/services';
import { Button } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

// Always-dark band, inspired by enterprise workflow platforms.
export default function Automation() {
  return (
    <section className="night relative isolate overflow-hidden py-24">
      <div className="absolute inset-0 -z-10 opacity-60 [background-image:linear-gradient(rgba(98,216,78,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(98,216,78,0.07)_1px,transparent_1px)] [background-size:56px_56px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
      <div className="glow -z-10 left-1/2 top-1/2 size-[600px] -translate-x-1/2 -translate-y-1/2 bg-[#62d84e] opacity-15 aurora-1" />
      <div className="container-x grid items-center gap-14 lg:grid-cols-2">
        <div>
          <p className="eyebrow !text-lime">Automation & AI</p>
          <h2 className="mt-4 text-3xl font-bold leading-[1.1] sm:text-4xl lg:text-5xl">
            Put your workflows on <span className="text-lime-grad">autopilot.</span>
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-white/70">
            Invoices, reminders, approvals, reports, data entry — if your team does it twice, we can automate it. We connect your apps, CRMs,
            WhatsApp, email and payment gateways so work flows without manual effort.
          </p>
          <div className="mt-8 grid grid-cols-3 gap-4">
            {[
              ['20h+', 'admin hours saved weekly'],
              ['24/7', 'workflows that never sleep'],
              ['<2s', 'real-time AI alerts'],
            ].map(([v, l]) => (
              <div key={l}>
                <p className="font-display text-3xl font-bold text-lime">{v}</p>
                <p className="mt-1 text-sm text-white/60">{l}</p>
              </div>
            ))}
          </div>
          <Button href="/services/automation" size="lg" arrow className="mt-10">
            Automate my business
          </Button>
          <Link
            href="/products/mtk-radar#automation-flow"
            className="mt-6 flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4 transition hover:border-lime/50"
          >
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#f97316]/20 text-[#fb923c]">
              <Radar className="size-5" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">See a full pipeline in action: MTK Radar AI</span>
              <span className="block text-xs text-white/60">
                9 stages from discovery to publishing on YouTube, Facebook, Instagram and TikTok — Manual, Assisted or Autopilot.
              </span>
            </span>
            <ArrowRight className="ml-auto size-4 shrink-0 text-lime" />
          </Link>
        </div>

        <div className="space-y-4">
          {automations.map((a, i) => (
            <Reveal key={a.trigger} delay={i * 100}>
              <div className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur sm:flex-row sm:items-center">
                <div className="flex shrink-0 items-center gap-3 sm:w-48">
                  <span className="grid size-9 place-items-center rounded-lg bg-lime/15 text-lime">
                    <Zap className="size-4" />
                  </span>
                  <div>
                    <p className="text-[11px] uppercase tracking-wider text-white/50">When</p>
                    <p className="text-sm font-semibold">{a.trigger}</p>
                  </div>
                </div>
                <div className="hidden h-px flex-1 bg-[linear-gradient(90deg,#62d84e,#9aa8ff)] sm:block sm:max-w-10" />
                <div className="flex-1 rounded-xl bg-white/[0.04] px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wider text-white/50">Then</p>
                  <p className="text-sm text-white/85">{a.action}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
