import { Bot, Database, LayoutDashboard, Lock, Smartphone, Workflow } from 'lucide-react';
import { Button } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

const layers = [
  { icon: LayoutDashboard, name: 'Experiences', text: 'Web portals, dashboards, storefronts', color: '#9aa8ff' },
  { icon: Smartphone, name: 'Apps', text: 'iOS, Android & desktop', color: '#c4b5fd' },
  { icon: Workflow, name: 'Workflows & Automation', text: 'Queues, schedules, approvals, notifications', color: '#62d84e' },
  { icon: Bot, name: 'AI Layer', text: 'Assistants, OCR, predictions, vision', color: '#5eead4' },
  { icon: Lock, name: 'Security & Tenancy', text: 'RLS, RBAC, audit logs, SSO', color: '#fbbf24' },
  { icon: Database, name: 'Data & Integrations', text: 'PostgreSQL, Redis, Kafka, payment & IoT APIs', color: '#60a5fa' },
];

/** Always-dark "one platform" section with an animated architecture stack. */
export default function PlatformDiagram({ cta = true }: { cta?: boolean }) {
  return (
    <section className="night relative isolate overflow-hidden py-24">
      <div className="absolute inset-0 -z-10 opacity-50 [background-image:linear-gradient(rgba(98,216,78,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(98,216,78,0.07)_1px,transparent_1px)] [background-size:48px_48px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
      <div className="aurora-2 glow -z-10 right-[-10%] top-[10%] size-[520px] bg-[#62d84e] opacity-20" />
      <div className="container-x grid items-center gap-16 lg:grid-cols-[1fr_1.1fr]">
        <div>
          <p className="eyebrow !text-lime">The MTK Codex Platform</p>
          <h2 className="mt-4 text-3xl font-bold leading-[1.1] sm:text-5xl">
            One foundation. <span className="text-lime-grad">Every product we build.</span>
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-white/70">
            Every MTK Codex solution — SaaS or custom — runs on the same battle-tested foundation: multi-tenant data, built-in security, an
            automation engine and an AI layer. You get enterprise architecture without enterprise cost or timelines.
          </p>
          <dl className="mt-8 grid grid-cols-2 gap-6">
            {[
              ['Multi-tenant', 'complete data isolation per customer'],
              ['Secure by default', 'RLS, RBAC & audit logging'],
              ['Automation-ready', 'background jobs & event streams'],
              ['AI-native', 'GPT, OCR & on-device ML'],
            ].map(([t, d]) => (
              <div key={t} className="border-l-2 border-lime/60 pl-4">
                <dt className="font-semibold">{t}</dt>
                <dd className="mt-1 text-sm text-white/60">{d}</dd>
              </div>
            ))}
          </dl>
          {cta && (
            <Button href="/platform" size="lg" arrow className="mt-10">
              Explore the platform
            </Button>
          )}
        </div>

        <div className="relative">
          {/* animated connector rail */}
          <svg className="absolute left-[27px] top-6 h-[calc(100%-48px)] w-4" preserveAspectRatio="none" viewBox="0 0 4 100" aria-hidden>
            <line x1="2" y1="0" x2="2" y2="100" stroke="#62d84e" strokeOpacity="0.25" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            <line className="flow-line" x1="2" y1="0" x2="2" y2="100" stroke="#62d84e" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </svg>
          <ol className="space-y-3">
            {layers.map((l, i) => (
              <Reveal as="li" key={l.name} delay={i * 90}>
                <div className="group relative flex items-center gap-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur transition duration-300 hover:translate-x-1 hover:border-white/25 hover:bg-white/[0.07]">
                  <span
                    className="relative z-10 grid size-10 shrink-0 place-items-center rounded-xl"
                    style={{ background: `${l.color}22`, color: l.color, boxShadow: `inset 0 0 0 1px ${l.color}55` }}
                  >
                    <l.icon className="size-5" />
                  </span>
                  <div className="min-w-0">
                    <p className="font-semibold">{l.name}</p>
                    <p className="truncate text-sm text-white/55">{l.text}</p>
                  </div>
                  <span className="pulse-dot ml-auto size-2 shrink-0 rounded-full" style={{ background: l.color, color: l.color, animationDelay: `${i * 0.3}s` }} />
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
