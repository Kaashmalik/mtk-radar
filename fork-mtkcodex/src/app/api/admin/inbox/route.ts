import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { listConversations } from '@/lib/inbox';
import { markAdminActive } from '@/lib/notify';
import { channelStatus } from '@/lib/channels';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  // The open inbox is what makes the chat widget say "online".
  await markAdminActive();
  try {
    return NextResponse.json({ conversations: await listConversations(), channels: channelStatus() });
  } catch (error) {
    return NextResponse.json(
      { conversations: [], channels: channelStatus(), error: error instanceof Error ? error.message : 'Inbox unavailable' },
      { status: 500 },
    );
  }
}
