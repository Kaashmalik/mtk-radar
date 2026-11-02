import { listLeads, storageMode } from '@/lib/leads';
import OutreachQueue from '@/components/admin/OutreachQueue';

export const dynamic = 'force-dynamic';

export default async function OutreachPage() {
  const result = await listLeads().catch((error: unknown) => ({
    error: error instanceof Error ? error.message : 'Could not load the outreach queue.',
  }));

  if ('error' in result) {
    return (
      <div className="card mx-auto max-w-2xl p-6">
        <h1 className="text-xl font-bold">Outreach unavailable</h1>
        <p className="mt-2 text-sm text-fg-muted">
          {result.error} (storage: {storageMode()})
        </p>
      </div>
    );
  }
  return <OutreachQueue initialLeads={result.leads} mode={result.mode} sheetUrl={(process.env.LEADS_SHEET_URL || '').trim()} />;
}
