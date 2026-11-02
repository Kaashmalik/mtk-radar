'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Eye, Radio, TrendingUp, Users } from 'lucide-react';
import type { AnalyticsSummary } from '@/lib/analytics-types';
import { flagEmoji, placeLabel } from '@/lib/lead-types';

const number = new Intl.NumberFormat('en-US');
const clock = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Karachi',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const POLL_MS = 20_000;

/**
 * Live traffic strip. When `summary` is passed the parent owns refreshing (the
 * full analytics page already polls), so this component stays presentational.
 */
export default function LiveTraffic({
  initial,
  summary: controlled,
  compact = false,
  detailed = false,
}: {
  initial: AnalyticsSummary | null;
  summary?: AnalyticsSummary | null;
  compact?: boolean;
  detailed?: boolean;
}) {
  const [local, setLocal] = useState(initial);
  const [error, setError] = useState('');
  const summary = controlled === undefined ? local : controlled;
  const selfRefreshing = controlled === undefined;

  const load = useCallback(async () => {
    if (document.visibilityState === 'hidden') return;
    try {
      const res = await fetch('/api/admin/analytics', { cache: 'no-store' });
      const data = (await res.json().catch(() => ({}))) as {
        summary?: AnalyticsSummary | null;
        error?: string;
      };
      if (data.summary) {
        setLocal(data.summary);
        setError('');
      } else if (data.error) {
        setError('Could not refresh');
      }
    } catch {
      setError('Offline');
    }
  }, []);

  useEffect(() => {
    if (!selfRefreshing) return;
    const timer = window.setInterval(load, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [load, selfRefreshing]);

  if (!summary) return null;

  const live = summary.live.visitors;
  const today = summary.today.visitors;
  const yesterday = summary.yesterday.visitors;
  const delta = yesterday > 0 ? Math.round(((today - yesterday) / yesterday) * 100) : null;
  const refreshedAt = summary.generated_at;

  return (
    <section className="mt-6 rounded-2xl border border-line bg-elevated/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            <span className={`absolute inline-flex size-full rounded-full ${live > 0 ? 'animate-ping bg-emerald-400' : 'bg-fg-subtle'} opacity-60`} />
            <span className={`relative inline-flex size-2 rounded-full ${live > 0 ? 'bg-emerald-500' : 'bg-fg-subtle'}`} />
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Website traffic</h2>
          {live > 0 && <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">LIVE</span>}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-fg-subtle">
          {error ? (
            <span className="text-red-500">{error}</span>
          ) : (
            <span>Updated {refreshedAt ? clock.format(new Date(refreshedAt)) : '—'} PKT · auto 20s</span>
          )}
          {compact && (
            <Link href="/admin/analytics" className="inline-flex items-center gap-1 font-semibold text-brand hover:underline">
              Full analytics <ArrowUpRight className="size-3" />
            </Link>
          )}
        </div>
      </div>

      <div className={`mt-3 grid grid-cols-2 gap-2.5 ${detailed ? 'sm:grid-cols-3 lg:grid-cols-6' : 'lg:grid-cols-4'}`}>
        <Kpi
          icon={Radio}
          label="Live now"
          value={live}
          hint={live === 1 ? 'person on site' : 'people on site'}
          live={live > 0}
        />
        <Kpi
          icon={Users}
          label="Last 24 hours"
          value={summary.last24h.visitors}
          hint={`${number.format(summary.last24h.views)} page views`}
        />
        <Kpi
          icon={Eye}
          label="Today"
          value={today}
          hint={delta === null ? 'no visits yesterday' : `${delta >= 0 ? '+' : ''}${delta}% vs yesterday`}
          tone={delta === null ? undefined : delta >= 0 ? 'up' : 'down'}
        />
        <Kpi
          icon={TrendingUp}
          label="Last 7 days"
          value={summary.week.visitors}
          hint={`${number.format(summary.week.views)} page views`}
        />
        {detailed && (
          <>
            <Kpi
              icon={Users}
              label="Yesterday"
              value={yesterday}
              hint={`${number.format(summary.yesterday.views)} page views`}
            />
            <Kpi
              icon={TrendingUp}
              label="Last 30 days"
              value={summary.month.visitors}
              hint={`${number.format(summary.month.views)} page views`}
            />
          </>
        )}
      </div>
      {summary.live_visitors && summary.live_visitors.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="font-semibold text-fg-muted">On the site now:</span>
          {summary.live_visitors.slice(0, 8).map((visitor) => (
            <span key={visitor.id} className="inline-flex items-center gap-1 rounded-full border border-line bg-elevated px-2 py-0.5 text-fg-muted">
              <span aria-hidden>{flagEmoji(visitor.country)}</span>
              {placeLabel(visitor) || 'Unknown'}
              <span className="font-mono text-fg-subtle">{visitor.path}</span>
            </span>
          ))}
          {summary.live_visitors.length > 8 && <span className="text-fg-subtle">+{summary.live_visitors.length - 8} more</span>}
          <Link href="/admin/analytics" className="font-semibold text-brand hover:underline">
            Map →
          </Link>
        </div>
      )}
    </section>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  live,
  tone,
}: {
  icon: typeof Users;
  label: string;
  value: number;
  hint: string;
  live?: boolean;
  tone?: 'up' | 'down';
}) {
  return (
    <div className="rounded-xl border border-line bg-muted/40 px-3.5 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-fg-subtle">{label}</p>
        <Icon className={`size-3.5 ${live ? 'text-emerald-500' : 'text-fg-subtle'}`} />
      </div>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value.toLocaleString('en-US')}</p>
      <p
        className={`mt-0.5 truncate text-[11px] ${
          tone === 'up' ? 'text-emerald-600 dark:text-emerald-400' : tone === 'down' ? 'text-amber-600 dark:text-amber-400' : 'text-fg-subtle'
        }`}
      >
        {hint}
      </p>
    </div>
  );
}
