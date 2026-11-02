import type { Metadata } from 'next';
import { analyticsEnabled, getAnalyticsSummary } from '@/lib/analytics';
import { listLeads, leadStats } from '@/lib/leads';
import { todayPKT } from '@/lib/lead-types';
import AnalyticsDashboard, { type OutreachSnapshot } from '@/components/admin/AnalyticsDashboard';
import type { AnalyticsSummary } from '@/lib/analytics-types';

export const metadata: Metadata = {
  title: 'Analytics',
  robots: { index: false, follow: false },
};

export const dynamic = 'force-dynamic';

export default async function AdminAnalyticsPage() {
  const configured = analyticsEnabled();
  let summary: AnalyticsSummary | null = null;
  let leadsError = '';

  try {
    summary = await getAnalyticsSummary();
  } catch {
    summary = null;
  }

  let leads: Awaited<ReturnType<typeof listLeads>>['leads'] = [];
  try {
    leads = (await listLeads()).leads;
  } catch (error) {
    leadsError = error instanceof Error ? error.message : 'Could not load leads';
  }

  const stats = leadStats(leads);
  const today = todayPKT();
  const outreach: OutreachSnapshot = {
    firstToday: leads.filter((lead) => lead.first_contacted === today).length,
    contacted: stats.contacted,
    due: stats.dueToday,
    queued: stats.queued,
    replied: (stats.byStatus.replied || 0) + (stats.byStatus.interested || 0),
    won: stats.won,
  };

  return (
    <>
      {leadsError && (
        <p className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          Outreach metrics unavailable: {leadsError}
        </p>
      )}
      <AnalyticsDashboard initial={summary} configured={configured} outreach={outreach} />
    </>
  );
}
