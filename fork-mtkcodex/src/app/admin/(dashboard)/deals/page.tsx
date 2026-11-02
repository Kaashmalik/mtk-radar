import type { Metadata } from 'next';
import { listLeads } from '@/lib/leads';
import { whatsappConfigured } from '@/lib/whatsapp';
import DealsBoard from '@/components/admin/DealsBoard';

export const metadata: Metadata = {
  title: 'Deals',
  robots: { index: false, follow: false },
};

export const dynamic = 'force-dynamic';

export default async function DealsPage() {
  const result = await listLeads().catch((error: unknown) => ({
    error: error instanceof Error ? error.message : 'Could not load leads.',
  }));

  if ('error' in result) {
    return (
      <div className="card mx-auto max-w-2xl p-6">
        <h1 className="text-xl font-bold">Deals unavailable</h1>
        <p className="mt-2 text-sm text-fg-muted">
          {result.error} Run <code>supabase/migrations/0004_crm_v2.sql</code> if the deal columns are missing.
        </p>
      </div>
    );
  }
  return <DealsBoard initialLeads={result.leads} whatsappEnabled={whatsappConfigured()} readOnly={result.mode === 'readonly'} />;
}
