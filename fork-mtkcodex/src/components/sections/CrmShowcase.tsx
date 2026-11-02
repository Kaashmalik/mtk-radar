'use client';

import { useEffect, useRef, useState } from 'react';
import { BellRing, CheckCircle2, MessageCircle, Pause, Play } from 'lucide-react';
import { Button, SectionHeading } from '@/components/ui/primitives';
import { prefersReducedMotion } from '@/components/motion/useInView';

type Deal = { id: number; name: string; value: number; stage: number; source: string };

const stages = [
  { name: 'New lead', color: '#60a5fa' },
  { name: 'Qualified', color: '#2dd4bf' },
  { name: 'Proposal', color: '#fbbf24' },
  { name: 'Won', color: '#62d84e' },
];
const names = ['Al-Noor Traders', 'Green Valley Farms', 'City School System', 'Lahore Lions CC', 'Zara Boutique', 'Prime Electronics', 'Indus Logistics', 'Bright Future Academy', 'Royal Furnishers', 'Metro Pharmacy'];
const sources = ['Website form', 'WhatsApp', 'Scraped lead', 'Referral', 'Facebook ad'];

const initial: Deal[] = [
  { id: 1, name: names[0], value: 1800, stage: 0, source: sources[0] },
  { id: 2, name: names[1], value: 4200, stage: 0, source: sources[2] },
  { id: 3, name: names[2], value: 6500, stage: 1, source: sources[3] },
  { id: 4, name: names[3], value: 3100, stage: 2, source: sources[1] },
  { id: 5, name: names[4], value: 2400, stage: 1, source: sources[4] },
  { id: 6, name: names[5], value: 5200, stage: 3, source: sources[0] },
];

/** Self-running sample CRM board: deals advance through the pipeline while automations fire. */
export default function CrmShowcase() {
  const [deals, setDeals] = useState(initial);
  const [feed, setFeed] = useState<string[]>(['Lead from website auto-assigned to Ali']);
  const [running, setRunning] = useState(true);
  const nextId = useRef(7);
  const dealsRef = useRef(deals);
  useEffect(() => {
    dealsRef.current = deals;
  }, [deals]);

  useEffect(() => {
    if (!running || prefersReducedMotion()) return;
    const t = setInterval(() => {
      const ds = dealsRef.current;
      const movable = ds.filter((d) => d.stage < 3);
      const d = movable[Math.floor(Math.random() * movable.length)];
      if (!d) return;
      const stage = d.stage + 1;
      const msgs = [
        stage === 1
          ? `Lead score 82 → ${d.name} marked qualified`
          : stage === 2
            ? `Proposal PDF generated & emailed to ${d.name}`
            : `🎉 ${d.name} won · invoice created automatically`,
      ];
      let next = ds.map((x) => (x.id === d.id ? { ...x, stage } : x));
      // Keep the board lively: recycle the oldest win into a fresh lead.
      const wins = next.filter((x) => x.stage === 3);
      if (wins.length > 3) {
        const id = nextId.current++;
        next = next.filter((x) => x.id !== wins[0].id);
        next.push({ id, name: names[id % names.length], value: 1000 + ((id * 937) % 6000), stage: 0, source: sources[id % sources.length] });
        msgs.unshift(`New lead captured via ${sources[id % sources.length]}`);
      }
      setDeals(next);
      setFeed((f) => [...msgs, ...f].slice(0, 3));
    }, 2200);
    return () => clearInterval(t);
  }, [running]);

  const pipeline = deals.filter((d) => d.stage < 3).reduce((s, d) => s + d.value, 0);
  const won = deals.filter((d) => d.stage === 3).reduce((s, d) => s + d.value, 0);

  return (
    <section id="crm" className="relative scroll-mt-20 py-24">
      <div className="container-x">
        <SectionHeading
          eyebrow="CRM systems"
          title={
            <>
              A CRM that <span className="text-gradient">works while you sleep.</span>
            </>
          }
          text="Custom-built or expertly configured HubSpot, Zoho or Salesforce — every lead captured, scored, followed up and closed with automation doing the heavy lifting."
        />

        <div className="mt-12 grid gap-6 lg:grid-cols-[1.7fr_1fr]">
          <div className="card overflow-hidden" onMouseEnter={() => setRunning(false)} onMouseLeave={() => setRunning(true)}>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
              <div className="flex gap-6 text-sm">
                <div>
                  <p className="text-xs text-fg-subtle">Open pipeline</p>
                  <p className="font-display text-lg font-bold tabular-nums">${pipeline.toLocaleString('en-US')}</p>
                </div>
                <div>
                  <p className="text-xs text-fg-subtle">Won</p>
                  <p className="font-display text-lg font-bold tabular-nums text-accent">${won.toLocaleString('en-US')}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setRunning((r) => !r)}
                className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-fg-muted hover:border-brand hover:text-brand"
              >
                {running ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {running ? 'Pause demo' : 'Play demo'}
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 p-4 md:grid-cols-4">
              {stages.map((s, si) => (
                <div key={s.name} className="min-h-56 rounded-2xl bg-muted p-2.5">
                  <p className="mb-2 flex items-center justify-between px-1 text-xs font-semibold">
                    <span className="flex items-center gap-1.5">
                      <span className="size-2 rounded-full" style={{ background: s.color }} /> {s.name}
                    </span>
                    <span className="text-fg-subtle">{deals.filter((d) => d.stage === si).length}</span>
                  </p>
                  <div className="space-y-2">
                    {deals
                      .filter((d) => d.stage === si)
                      .map((d) => (
                        <div key={`${d.id}-${d.stage}`} className="word-in rounded-xl border border-line bg-elevated p-2.5 text-xs shadow-card" style={{ borderLeft: `3px solid ${s.color}` }}>
                          <p className="truncate font-semibold">{d.name}</p>
                          <p className="mt-0.5 flex justify-between text-fg-subtle">
                            <span className="truncate">{d.source}</span>
                            <span className="font-semibold text-fg">${d.value.toLocaleString('en-US')}</span>
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="border-t border-line px-5 py-2 text-[11px] text-fg-subtle">Sample data · hover or press pause to stop the demo</p>
          </div>

          <div className="flex flex-col gap-5">
            <div className="card p-5">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <BellRing className="size-4 text-accent" /> Automations firing
              </p>
              <ul className="mt-3 space-y-2" aria-live="off">
                {feed.map((f, i) => (
                  <li key={`${f}-${i}`} className={`rounded-xl bg-muted px-3 py-2 text-xs ${i === 0 ? 'word-in font-medium' : 'text-fg-muted'}`}>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
            <div className="card flex-1 p-5">
              <ul className="space-y-2.5 text-sm">
                {['Lead capture from web, WhatsApp, ads & scrapers', 'Lead scoring & auto-assignment', 'Follow-up sequences on WhatsApp & email', 'Quotes, invoices & payments in one place', 'Sales dashboards & forecasting'].map((t) => (
                  <li key={t} className="flex gap-2">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" /> {t}
                  </li>
                ))}
              </ul>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button href="/services/crm" arrow>
                  CRM services
                </Button>
                <Button href="/contact?service=crm" variant="secondary">
                  <MessageCircle className="size-4" /> Free CRM audit
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
