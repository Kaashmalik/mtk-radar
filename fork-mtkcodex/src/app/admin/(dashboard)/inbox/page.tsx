import type { Metadata } from 'next';
import { listConversations } from '@/lib/inbox';
import { markAdminActive } from '@/lib/notify';
import { channelStatus } from '@/lib/channels';
import { defaultTemplate } from '@/lib/whatsapp';
import Inbox from '@/components/admin/Inbox';
import type { Conversation } from '@/lib/lead-types';

export const metadata: Metadata = {
  title: 'Inbox',
  robots: { index: false, follow: false },
};

export const dynamic = 'force-dynamic';

export default async function InboxPage() {
  await markAdminActive();
  const result = await listConversations().catch((error: unknown) => ({
    error: error instanceof Error ? error.message : 'Could not load conversations',
  }));
  const conversations: Conversation[] = Array.isArray(result) ? result : [];

  return (
    <>
      {!Array.isArray(result) && (
        <p className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
          Inbox storage unavailable — run <code>supabase/migrations/0004_crm_v2.sql</code>. ({result.error})
        </p>
      )}
      <Inbox initialConversations={conversations} channels={channelStatus()} defaultTemplate={defaultTemplate()} />
    </>
  );
}
