import { getAdminSession } from '@/lib/admin-auth';
import { getAnalyticsSummary } from '@/lib/analytics';
import { listLeads, recentActivities, storageMode, type StorageMode } from '@/lib/leads';
import { whatsappConfigured } from '@/lib/whatsapp';
import Dashboard from '@/components/admin/Dashboard';
import type { ActivityPoint, FeedItem } from '@/components/admin/TodayPanel';
import { AlertTriangle } from 'lucide-react';
import type { AnalyticsSummary } from '@/lib/analytics-types';

export const dynamic = 'force-dynamic';

/** Start of the activity window shown in the "last 14 days" chart (plus a day of slack). */
function chartWindowStart(): string {
  return new Date(Date.now() - 15 * 86_400_000).toISOString();
}

export default async function AdminHomePage() {
  const session = await getAdminSession();
  let mode: StorageMode = storageMode();
  let leads = [] as Awaited<ReturnType<typeof listLeads>>['leads'];
  let loadError = '';

  const since = chartWindowStart();
  // Traffic and activity are bonus panels; a failure there must not hide the CRM.
  const [analytics, points, feed] = await Promise.all([
    getAnalyticsSummary().catch((): AnalyticsSummary | null => null),
    recentActivities({ since, kinds: ['message_out', 'message_in'], limit: 5000 }).catch(() => []),
    recentActivities({ limit: 25 }).catch(() => []),
  ]);

  try {
    const result = await listLeads();
    mode = result.mode;
    leads = result.leads;
  } catch (error) {
    loadError = error instanceof Error ? error.message : 'Could not load leads.';
  }

  if (loadError) {
    return (
      <div className="card mx-auto max-w-2xl p-6">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 text-amber-500" />
          <div>
            <h1 className="text-xl font-bold">Database not ready</h1>
            <p className="mt-2 text-sm leading-relaxed text-fg-muted">
              The leads table could not be reached. Run the migrations in{' '}
              <code className="rounded bg-muted px-1">supabase/migrations/</code> (0001 → 0004), then refresh.
            </p>
            <pre className="mt-3 overflow-x-auto rounded-lg bg-night p-3 text-xs text-white/80">{loadError}</pre>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Dashboard
      initialLeads={leads}
      mode={mode}
      email={session?.email || ''}
      analytics={analytics}
      points={points.map(({ kind, created_at }): ActivityPoint => ({ kind, created_at }))}
      feed={feed.map(({ id, lead_id, kind, summary, created_at, lead_name }): FeedItem => ({ id, lead_id, kind, summary, created_at, lead_name }))}
      whatsappEnabled={whatsappConfigured()}
      sheetUrl={(process.env.LEADS_SHEET_URL || '').trim()}
    />
  );
}
