import { Activity, Gauge, Layers, Zap } from 'lucide-react';
import { products } from '@/data/products';
import { SectionHeading } from '@/components/ui/primitives';
import { AreaChart, BarChart, Donut, LiveChart, ProgressRing, Sparkline } from '@/components/motion/Charts';
import Reveal from '@/components/ui/Reveal';

/**
 * Showcase of the analytics UI we build for clients. Time-series values are sample data
 * (clearly labelled); the product/platform breakdowns reflect the real MTK Codex portfolio.
 */
export default function ImpactDashboard() {
  const byPlatform = [
    { name: 'Web SaaS', value: 5, color: '#14a89a' },
    { name: 'Mobile', value: 1, color: '#62d84e' },
    { name: 'Desktop', value: 1, color: '#3b82f6' },
  ];

  return (
    <section className="relative overflow-hidden py-20">
      <div className="container-x">
        <SectionHeading
          eyebrow="Analytics & insight"
          title={
            <>
              Dashboards that make <span className="text-gradient">decisions obvious.</span>
            </>
          }
          text="Real-time charts, KPIs and alerts are built into every platform we ship. Here's a taste of the analytics experience your team gets."
        />

        <div className="mt-14 grid gap-5 lg:grid-cols-3">
          <Reveal className="lg:col-span-2">
            <div className="card spotlight h-full p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="flex items-center gap-2 text-sm font-semibold">
                    <Activity className="size-4 text-accent" /> Live API throughput
                  </p>
                  <p className="text-xs text-fg-subtle">Requests / second · streaming sample</p>
                </div>
                <span className="flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent">
                  <span className="pulse-dot size-1.5 rounded-full bg-accent text-accent" /> Live
                </span>
              </div>
              <div className="mt-6 text-accent">
                <LiveChart color="var(--accent)" base={420} spread={90} height={170} unit=" rps" />
              </div>
            </div>
          </Reveal>

          <Reveal delay={100}>
            <div className="card spotlight h-full p-6">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <Layers className="size-4 text-brand" /> Our product portfolio
              </p>
              <p className="text-xs text-fg-subtle">Platforms shipped, by primary platform</p>
              <div className="mt-6">
                <Donut segments={byPlatform} label={String(products.length)} sub="products" />
              </div>
            </div>
          </Reveal>

          <Reveal>
            <div className="card spotlight h-full p-6">
              <p className="text-sm font-semibold">Monthly active users</p>
              <p className="text-xs text-fg-subtle">Sample growth curve</p>
              <div className="mt-6 text-brand">
                <AreaChart values={[12, 18, 17, 26, 31, 29, 40, 48, 55, 61, 72, 86]} color="var(--cta)" labels={['Jan', 'Apr', 'Jul', 'Oct', 'Dec']} />
              </div>
            </div>
          </Reveal>

          <Reveal delay={100}>
            <div className="card spotlight h-full p-6">
              <p className="text-sm font-semibold">Hours automated per week</p>
              <p className="text-xs text-fg-subtle">Sample client rollout</p>
              <div className="mt-6">
                <BarChart values={[4, 7, 9, 12, 15, 18, 22]} color="#3b82f6" labels={['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7']} />
              </div>
            </div>
          </Reveal>

          <Reveal delay={200}>
            <div className="card spotlight grid h-full gap-5 p-6">
              {[
                { icon: Gauge, label: 'Lighthouse performance', value: 95, color: '#62d84e' },
                { icon: Zap, label: 'Uptime on live products', value: 99.9, color: '#3b82f6', text: '99.9' },
              ].map((k) => (
                <div key={k.label} className="flex items-center gap-4">
                  <ProgressRing value={k.value} color={k.color} label={k.text} />
                  <div>
                    <p className="flex items-center gap-1.5 text-sm font-semibold">
                      <k.icon className="size-4" style={{ color: k.color }} /> {k.label}
                    </p>
                    <Sparkline values={[60, 72, 68, 80, 84, 82, 90, 94, 96]} color={k.color} className="mt-1 h-6 w-28" />
                  </div>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
        <p className="mt-4 text-center text-xs text-fg-subtle">Time-series charts show sample data to illustrate our dashboard components.</p>
      </div>
    </section>
  );
}
