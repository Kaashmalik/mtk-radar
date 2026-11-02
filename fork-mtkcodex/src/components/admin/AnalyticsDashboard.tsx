'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowUpRight,
  CalendarClock,
  Globe2,
  Laptop,
  MessageSquare,
  RefreshCw,
  Send,
  Smartphone,
  Tablet,
  Trophy,
} from 'lucide-react';
import LiveTraffic from '@/components/admin/LiveTraffic';
import LiveMap from '@/components/admin/LiveMap';
import { flagEmoji, placeLabel } from '@/lib/lead-types';
import type { AnalyticsSummary } from '@/lib/analytics-types';

const number = new Intl.NumberFormat('en-US');
const hourFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Karachi', hour: '2-digit', hour12: false });
const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short' });
const clockFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Karachi',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});
const pktDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Karachi',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

export type OutreachSnapshot = {
  firstToday: number;
  contacted: number;
  due: number;
  queued: number;
  replied: number;
  won: number;
};

type HourBar = { key: string; at: Date; views: number; visitors: number };
type DayBar = { day: string; views: number; visitors: number };

function buildHours(summary: AnalyticsSummary): HourBar[] {
  const map = new Map(summary.hourly.map((point) => [new Date(point.bucket).toISOString().slice(0, 13), point]));
  const end = new Date(summary.generated_at);
  const out: HourBar[] = [];
  for (let i = 23; i >= 0; i -= 1) {
    const at = new Date(end.getTime() - i * 3_600_000);
    const key = at.toISOString().slice(0, 13);
    const point = map.get(key);
    out.push({ key, at, views: point?.views ?? 0, visitors: point?.visitors ?? 0 });
  }
  return out;
}

function buildDays(summary: AnalyticsSummary): DayBar[] {
  const map = new Map(summary.daily.map((point) => [point.day, point]));
  const end = new Date(summary.generated_at);
  const out: DayBar[] = [];
  for (let i = 13; i >= 0; i -= 1) {
    const at = new Date(end.getTime() - i * 86_400_000);
    const day = pktDay.format(at);
    const point = map.get(day);
    out.push({ day, views: point?.views ?? 0, visitors: point?.visitors ?? 0 });
  }
  return out;
}

function flag(code: string): string {
  if (!/^[A-Z]{2}$/.test(code)) return '🌐';
  return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

const devices = [
  { key: 'desktop', label: 'Desktop', icon: Laptop },
  { key: 'mobile', label: 'Mobile', icon: Smartphone },
  { key: 'tablet', label: 'Tablet', icon: Tablet },
] as const;

export default function AnalyticsDashboard({
  initial,
  configured,
  outreach,
}: {
  initial: AnalyticsSummary | null;
  configured: boolean;
  outreach: OutreachSnapshot;
}) {
  const [summary, setSummary] = useState(initial);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (silent && document.visibilityState === 'hidden') return;
    if (!silent) setRefreshing(true);
    try {
      const res = await fetch('/api/admin/analytics', { cache: 'no-store' });
      const data = (await res.json().catch(() => ({}))) as { summary?: AnalyticsSummary | null; error?: string };
      if (data.summary) {
        setSummary(data.summary);
        setError('');
      } else if (data.error) {
        setError(data.error);
      }
    } catch {
      setError('Could not reach the analytics API');
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => load(true), 20_000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') load(true);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load]);

  const hours = useMemo(() => (summary ? buildHours(summary) : []), [summary]);
  const days = useMemo(() => (summary ? buildDays(summary) : []), [summary]);
  const totalDevices = summary?.devices.reduce((sum, row) => sum + row.visitors, 0) || 0;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Analytics</p>
          <h1 className="mt-2 text-3xl font-bold">Website traffic</h1>
          <p className="mt-1 text-sm text-fg-muted">
            First-party, cookieless measurement. Visitors are unique per day; times are Asia/Karachi (PKT).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => load()}
            disabled={refreshing}
            className="inline-flex h-10 items-center gap-2 rounded-full border border-line px-4 text-sm font-semibold text-fg-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
          >
            <RefreshCw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
          </button>
          <Link
            href="/admin/outreach"
            className="inline-flex h-10 items-center gap-2 rounded-full bg-cta px-4 text-sm font-semibold text-on-cta transition hover:bg-cta-hover"
          >
            <Send className="size-4" /> Outreach
          </Link>
        </div>
      </div>

      {error && (
        <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {!configured ? (
        <SetupCard
          title="Analytics is not configured"
          body="Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to the deployment, then redeploy."
        />
      ) : !summary ? (
        <SetupCard
          title="Analytics table not ready"
          body="Run supabase/migrations/0002_analytics.sql in the Supabase SQL editor, then refresh this page."
        />
      ) : (
        <>
          <LiveTraffic initial={summary} summary={summary} detailed />

          <section className="card mt-4 p-4">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-sm font-bold">Live visitors by location</h2>
              <p className="text-[11px] text-fg-subtle">City-level from the hosting edge · refreshes every 20 s</p>
            </div>
            {summary.live_visitors ? (
              <LiveMap live={summary.live_visitors} points={summary.map || []} />
            ) : (
              <Empty text="Run supabase/migrations/0004_crm_v2.sql to record cities and show the live map." />
            )}
          </section>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Last 24 hours"
              subtitle={`${number.format(summary.last24h.views)} page views · ${number.format(summary.last24h.visitors)} visitors`}
              bars={hours.map((hour) => ({
                label: hourFmt.format(hour.at),
                views: hour.views,
                visitors: hour.visitors,
                title: `${hourFmt.format(hour.at)}:00 — ${hour.views} views, ${hour.visitors} visitors`,
              }))}
              labelEvery={6}
            />
            <ChartCard
              title="Last 14 days"
              subtitle={`${number.format(summary.daily.reduce((sum, d) => sum + d.views, 0))} page views in this window`}
              bars={days.map((day) => ({
                label: dayFmt.format(new Date(`${day.day}T12:00:00Z`)),
                views: day.views,
                visitors: day.visitors,
                title: `${day.day} — ${day.views} views, ${day.visitors} visitors`,
              }))}
              labelEvery={3}
              highlightLast
            />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel title="Top pages" subtitle="Last 30 days">
              {summary.pages.length === 0 ? (
                <Empty text="No page views yet." />
              ) : (
                <ul className="divide-y divide-line">
                  {summary.pages.map((page) => (
                    <li key={page.path} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                      <span className="min-w-0 flex-1 truncate font-mono text-xs text-fg-muted">{page.path}</span>
                      <span className="shrink-0 text-xs tabular-nums text-fg-muted">{number.format(page.views)}</span>
                      <span className="w-16 shrink-0 text-right text-[11px] text-fg-subtle">
                        {number.format(page.visitors)} visitors
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Sources" subtitle="Last 30 days">
              {summary.referrers.length === 0 ? (
                <Empty text="No referrers yet." />
              ) : (
                <ul className="space-y-3">
                  {summary.referrers.map((source) => (
                    <li key={source.source}>
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="truncate font-medium">{source.source === 'direct' ? 'Direct / none' : source.source}</span>
                        <span className="shrink-0 tabular-nums text-fg-subtle">{number.format(source.views)}</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-brand/70"
                          style={{ width: `${Math.max(4, (source.views / summary.referrers[0].views) * 100)}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
            <Panel title="Devices" subtitle="Last 30 days">
              {totalDevices === 0 ? (
                <Empty text="No devices yet." />
              ) : (
                <ul className="space-y-3">
                  {devices.map((device) => {
                    const row = summary.devices.find((item) => item.device === device.key);
                    const value = row?.visitors || 0;
                    const pct = Math.round((value / totalDevices) * 100);
                    return (
                      <li key={device.key}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="inline-flex items-center gap-1.5 font-medium">
                            <device.icon className="size-3.5 text-fg-subtle" /> {device.label}
                          </span>
                          <span className="tabular-nums text-fg-subtle">
                            {number.format(value)} · {pct}%
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-sky-500/70" style={{ width: `${pct}%` }} />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Panel>

            <Panel title="Top cities" subtitle="Last 30 days">
              {!summary.cities?.length ? (
                <Empty text="Cities appear once the live site serves visitors after migration 0004." />
              ) : (
                <ul className="space-y-2.5">
                  {summary.cities.map((row) => (
                    <li key={`${row.city}-${row.region}-${row.country}`} className="flex items-center justify-between gap-2 text-xs">
                      <span className="inline-flex min-w-0 items-center gap-2">
                        <span aria-hidden>{flagEmoji(row.country)}</span>
                        <span className="truncate font-medium">{placeLabel(row)}</span>
                      </span>
                      <span className="tabular-nums text-fg-subtle">{number.format(row.visitors)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Countries" subtitle="Last 30 days">
              {summary.countries.length === 0 ? (
                <Empty text="Location data appears once the live site serves visitors." />
              ) : (
                <ul className="space-y-2.5">
                  {summary.countries.map((row) => (
                    <li key={row.country} className="flex items-center justify-between gap-2 text-xs">
                      <span className="inline-flex items-center gap-2">
                        <span aria-hidden>{flag(row.country)}</span>
                        <span className="font-medium">{row.country === 'Unknown' ? 'Unknown' : row.country}</span>
                      </span>
                      <span className="tabular-nums text-fg-subtle">{number.format(row.visitors)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="Recent visits" subtitle="Last 7 days">
              {summary.recent.length === 0 ? (
                <Empty text="Waiting for the first visit." />
              ) : (
                <ul className="space-y-2">
                  {summary.recent.map((visit, index) => (
                    <li key={`${visit.created_at}-${index}`} className="flex items-center gap-2 text-xs">
                      <Globe2 className="size-3 shrink-0 text-fg-subtle" />
                      <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-fg-muted">{visit.path}</span>
                      <span className="shrink-0 text-[11px] text-fg-subtle">{clockFmt.format(new Date(visit.created_at))}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <OutreachCard
              icon={MessageSquare}
              label="First messages today"
              value={outreach.firstToday}
              hint="first messages sent today"
              href="/admin/outreach"
            />
            <OutreachCard icon={Send} label="Total contacted" value={outreach.contacted} hint="all time in CRM" href="/admin" />
            <OutreachCard icon={CalendarClock} label="Follow-ups due" value={outreach.due} hint="due today or overdue" href="/admin" />
            <OutreachCard
              icon={outreach.won > 0 ? Trophy : Send}
              label={outreach.won > 0 ? 'Clients won' : 'In send queue'}
              value={outreach.won > 0 ? outreach.won : outreach.queued}
              hint={outreach.won > 0 ? `${outreach.replied} replied` : 'ready to message'}
              href={outreach.won > 0 ? '/admin' : '/admin/outreach'}
            />
          </div>

          <p className="mt-4 text-[11px] leading-relaxed text-fg-subtle">
            No cookies are set for this measurement. The visitor id is a daily HMAC of IP + browser, so it cannot be traced
            back and resets every day. Bots and admin pages are excluded. Data is kept for 180 days.
          </p>
        </>
      )}
    </div>
  );
}

function SetupCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="mt-6 card p-6">
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-fg-muted">{body}</p>
      <p className="mt-3 text-xs text-fg-subtle">
        See <code className="rounded bg-muted px-1">docs/CRM.md</code> for the full setup.
      </p>
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  bars,
  labelEvery,
  highlightLast = false,
}: {
  title: string;
  subtitle: string;
  bars: { label: string; views: number; visitors: number; title: string }[];
  labelEvery: number;
  highlightLast?: boolean;
}) {
  const max = Math.max(1, ...bars.map((bar) => bar.views));
  const total = bars.reduce((sum, bar) => sum + bar.views, 0);

  return (
    <section className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold">{title}</h2>
          <p className="mt-0.5 text-xs text-fg-subtle">{subtitle}</p>
        </div>
        <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg-subtle">
          Views
        </span>
      </div>

      {total === 0 ? (
        <div className="mt-6 grid h-32 place-items-center rounded-lg border border-dashed border-line text-xs text-fg-subtle">
          No visits in this window yet.
        </div>
      ) : (
        <>
          <div className="mt-5 flex h-32 items-end gap-[3px] border-b border-line">
            {bars.map((bar, index) => {
              const isLast = index === bars.length - 1;
              const empty = bar.views === 0;
              return (
                <div
                  key={`${bar.label}-${index}`}
                  className={`group relative flex-1 rounded-t transition-colors ${
                    empty
                      ? 'bg-line'
                      : highlightLast && isLast
                        ? 'bg-cta'
                        : 'bg-brand/60 hover:bg-brand'
                  }`}
                  style={{ height: empty ? '2px' : `${Math.max(4, (bar.views / max) * 100)}%` }}
                  title={bar.title}
                >
                  {!empty && (
                    <span className="pointer-events-none absolute inset-x-0 -top-2 hidden h-1 rounded-full bg-brand group-hover:block" />
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex justify-between text-[10px] text-fg-subtle">
            {bars
              .filter((_, index) => index % labelEvery === 0 || index === bars.length - 1)
              .map((bar, index) => (
                <span key={`${bar.label}-${index}`}>{bar.label}</span>
              ))}
          </div>
        </>
      )}
    </section>
  );
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="card p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold">{title}</h2>
        <span className="text-[10px] uppercase tracking-wide text-fg-subtle">{subtitle}</span>
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-xs text-fg-subtle">{text}</p>;
}

function OutreachCard({
  icon: Icon,
  label,
  value,
  hint,
  href,
}: {
  icon: typeof Send;
  label: string;
  value: number;
  hint: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl border border-line bg-elevated/60 p-4 transition hover:border-brand/40 hover:bg-muted/40"
    >
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-fg-subtle">{label}</p>
        <Icon className="size-3.5 text-fg-subtle" />
      </div>
      <p className="mt-1.5 text-2xl font-bold tabular-nums">{number.format(value)}</p>
      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-fg-subtle">
        {hint}
        <ArrowUpRight className="size-3 opacity-0 transition group-hover:opacity-100" />
      </p>
    </Link>
  );
}
